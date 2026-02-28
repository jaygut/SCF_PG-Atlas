"""
pg_atlas/graph/builder.py — NetworkX graph construction layer.

Builds a NetworkX DiGraph from either real CSV seed data (operational today)
or PostgreSQL once Alex Olieman's A2 schema is locked (stub until then).

The graph uses the three-layer architecture:
    Layer 1 — Package Dependency Graph  (Repo, ExternalRepo, depends_on edges)
    Layer 2 — Contributor Graph         (Contributor, contributed_to edges)
    Layer 3 — Funding Graph             (Project, SCFRound, funded_by edges)

The CSV builder populates Layers 1 and 3 from processed seed data.
Layer 2 (contributor edges) is populated separately via enrich_graph_with_ingestion()
once the A7 git log parser has run.

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import difflib
import logging
import os
from typing import Any

import networkx as nx
import pandas as pd

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig

logger = logging.getLogger(__name__)


_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "01_data", "processed")
_DEFAULT_SEED_LIST = os.path.join(_DATA_DIR, "A5_pg_candidate_seed_list.csv")
_DEFAULT_ORGS = os.path.join(_DATA_DIR, "A6_github_orgs_seed.csv")
_DEFAULT_REPOS = os.path.join(_DATA_DIR, "A7_submission_github_repos.csv")


def build_graph_from_csv(
    seed_list_path: str | None = None,
    orgs_path: str | None = None,
    repos_path: str | None = None,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> nx.DiGraph:
    """
    Build the initial graph from the Airtable CSV extracts.

    Loads 86 PG seed projects as Project nodes, submission repos as Repo nodes,
    and constructs belongs_to edges by fuzzy-matching repo submission titles to
    project titles.

    Node types created:
        - Project  (from A5_pg_candidate_seed_list.csv)
        - Repo     (from A7_submission_github_repos.csv — one Repo per github_url)

    Edge types:
        - belongs_to: Repo → Project (matched by submission_title ≈ project title)

    Node attributes on Project:
        title, category, integration_status, github_url, website,
        total_awarded_usd, open_source, description, node_type='Project'

    Node attributes on Repo:
        github_url, round, submission_title, total_awarded_usd,
        use_soroban, tranche_completion, node_type='Repo',
        active=None (populated by active_subgraph projection after git log parse),
        days_since_commit=None (populated by A7 git log parser)

    Args:
        seed_list_path: Absolute path to A5_pg_candidate_seed_list.csv.
        orgs_path:      Absolute path to A6_github_orgs_seed.csv.
        repos_path:     Absolute path to A7_submission_github_repos.csv.
        config:         PGAtlasConfig instance (currently unused in CSV builder,
                        reserved for future threshold-dependent filtering).

    Returns:
        G: nx.DiGraph with Project + Repo nodes and belongs_to edges.

    Notes:
        - Orgs CSV (A6) is loaded for future use (e.g., root nodes for the
          dependency crawler). Orgs are not yet added as graph nodes — that
          happens during ingestion enrichment.
        - Fuzzy matching uses difflib.SequenceMatcher with a 0.6 similarity
          cutoff. Projects without a match receive no belongs_to edge; they
          are still present as isolated Repo nodes and can be manually linked
          via enrich_graph_with_ingestion().
        - github_url is used as the node ID for Repo nodes (unique per row
          after deduplication on (submission_title, github_url)).
    """
    seed_list_path = seed_list_path or _DEFAULT_SEED_LIST
    orgs_path = orgs_path or _DEFAULT_ORGS
    repos_path = repos_path or _DEFAULT_REPOS

    G = nx.DiGraph()

    # ── Load Project nodes from A5 seed list ─────────────────────────────────
    logger.info("Loading PG seed projects from: %s", seed_list_path)
    df_projects = pd.read_csv(seed_list_path)
    df_projects["total_awarded_usd"] = pd.to_numeric(
        df_projects["total_awarded_usd"], errors="coerce"
    ).fillna(0.0)

    project_titles: list[str] = []
    for _, row in df_projects.iterrows():
        title = str(row.get("title", "")).strip()
        if not title:
            continue
        project_titles.append(title)
        G.add_node(
            title,
            node_type="Project",
            title=title,
            category=str(row.get("category", "")),
            integration_status=str(row.get("integration_status", "")),
            github_url=str(row.get("github_url", "")),
            website=str(row.get("website", "")),
            total_awarded_usd=float(row.get("total_awarded_usd", 0)),
            open_source=str(row.get("open_source", "")),
            description=str(row.get("description", "")),
        )

    logger.info("Added %d Project nodes.", len(project_titles))

    # ── Load Repo nodes from A7 submission repos ──────────────────────────────
    logger.info("Loading submission repos from: %s", repos_path)
    df_repos = pd.read_csv(repos_path)
    df_repos["total_awarded_usd"] = pd.to_numeric(
        df_repos["total_awarded_usd"], errors="coerce"
    ).fillna(0.0)

    # Deduplicate on (submission_title, github_url) — same URL may appear
    # in multiple rounds with different submission_title values.
    repo_nodes_added = 0
    seen_urls: set[str] = set()

    for _, row in df_repos.iterrows():
        url = str(row.get("github_url", "")).strip()
        submission_title = str(row.get("submission_title", "")).strip()

        if not url or url == "nan" or pd.isna(row.get("github_url")):
            logger.debug("Skipping repo row with empty github_url: %s", row.to_dict())
            continue

        # Use URL as node ID (first occurrence wins if duplicated).
        node_id = url
        if node_id not in seen_urls:
            seen_urls.add(node_id)
            G.add_node(
                node_id,
                node_type="Repo",
                github_url=url,
                round=str(row.get("round", "")),
                submission_title=submission_title,
                total_awarded_usd=float(row.get("total_awarded_usd", 0)),
                use_soroban=str(row.get("use_soroban", "")),
                tranche_completion=str(row.get("tranche_completion", "")),
                # These will be populated by A7 git log parser:
                active=None,
                days_since_commit=None,
            )
            repo_nodes_added += 1

    logger.info("Added %d Repo nodes.", repo_nodes_added)

    # ── Add belongs_to edges via fuzzy title matching ─────────────────────────
    edges_added = 0
    for node_id, data in G.nodes(data=True):
        if data.get("node_type") != "Repo":
            continue
        submission_title = data.get("submission_title", "")
        if not submission_title or submission_title == "nan":
            continue

        match = _fuzzy_match_project(submission_title, project_titles, cutoff=0.6)
        if match:
            G.add_edge(node_id, match, edge_type="belongs_to")
            edges_added += 1
        else:
            logger.debug(
                "No project match for repo '%s' (submission_title='%s').",
                node_id,
                submission_title,
            )

    logger.info(
        "Added %d belongs_to edges (fuzzy match, cutoff=0.6).", edges_added
    )

    # ── Load orgs for future use (no nodes added yet) ─────────────────────────
    logger.info("Loading GitHub orgs from: %s (for future crawler use)", orgs_path)
    df_orgs = pd.read_csv(orgs_path)
    G.graph["github_orgs"] = df_orgs["github_org"].tolist() if "github_org" in df_orgs.columns else []
    G.graph["source"] = "csv"
    G.graph["seed_list_path"] = seed_list_path
    G.graph["repos_path"] = repos_path

    logger.info(
        "Graph construction complete: %d nodes, %d edges.",
        G.number_of_nodes(),
        G.number_of_edges(),
    )
    return G


def _fuzzy_match_project(
    submission_title: str,
    project_titles: list[str],
    cutoff: float = 0.6,
) -> str | None:
    """
    Find the closest project title to submission_title using SequenceMatcher.

    Returns the best-matching title if similarity >= cutoff, else None.

    This is a best-effort heuristic. Unmatched repos should be manually
    linked once Alex's schema provides authoritative project→repo mappings.
    """
    best_title: str | None = None
    best_ratio: float = 0.0

    s_lower = submission_title.lower()
    for title in project_titles:
        ratio = difflib.SequenceMatcher(None, s_lower, title.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_title = title

    return best_title if best_ratio >= cutoff else None


def build_graph_from_db(conn: Any, config: PGAtlasConfig = DEFAULT_CONFIG) -> nx.DiGraph:
    """
    Build the operational graph from PostgreSQL (D5 schema by Alex Olieman).

    STUB: Returns an empty graph until Alex's A2 schema is locked.

    When the schema is available, implement queries for:
        - repo table             → Repo nodes
        - external_repo table    → ExternalRepo nodes
        - depends_on table       → dependency edges
        - contributor table      → Contributor nodes
        - contributed_to table   → contribution edges

    Anticipated schema (update when Alex finalizes A2):
        repo(id, project_id, ecosystem, latest_commit_date, archived,
             adoption_stars, adoption_forks, adoption_downloads)
        depends_on(from_repo, to_repo, version_range, confidence)
        contributor(id, display_name, email_aliases)
        contributed_to(contributor_id, repo_id, commits,
                      first_commit_date, last_commit_date)

    Args:
        conn:   psycopg2 / asyncpg connection (any type until schema locked).
        config: PGAtlasConfig instance.

    Returns:
        G: Empty nx.DiGraph (stub — replace with real queries when A2 ships).
    """
    logger.warning(
        "build_graph_from_db called but PostgreSQL schema (A2) is not yet locked. "
        "Returning empty graph. Implement this function once Alex Olieman's schema ships."
    )
    G = nx.DiGraph()
    G.graph["source"] = "postgresql_stub"
    return G


def enrich_graph_with_ingestion(
    G: nx.DiGraph,
    dep_edges: list[dict],
    contrib_edges: list[dict],
    adoption_data: dict[str, dict],
    activity_data: dict[str, dict],
) -> nx.DiGraph:
    """
    Enrich an existing graph with outputs from the ingestion pipeline.

    Mutates G in-place and also returns it for method chaining.

    Args:
        G:              NetworkX DiGraph to enrich (typically from build_graph_from_csv).
        dep_edges:      Dependency edges from deps_dev_client / crates_io_client.
                        Each dict: {from_repo, to_repo, ecosystem, confidence}.
                        'from_repo' and 'to_repo' are github_url strings.
        contrib_edges:  Contribution edges from git_log_parser.
                        Each dict: {contributor, repo, commits, first_date, last_date}.
                        'contributor' is a display_name string; 'repo' is github_url.
        adoption_data:  Adoption signals from download APIs + GitHub.
                        {repo_url: {stars, forks, downloads}}.
        activity_data:  Activity signals from git log parser.
                        {repo_url: {days_since_commit, archived}}.

    Returns:
        G: The same graph, mutated in-place.

    Edge attributes set:
        depends_on edges: edge_type='depends_on', ecosystem, confidence
        contributed_to edges: edge_type='contributed_to', commits, first_date, last_date

    Node attributes updated:
        Repo nodes: stars, forks, downloads (from adoption_data)
        Repo nodes: days_since_commit, archived, active (from activity_data)
        Contributor nodes: added if not already present (node_type='Contributor')
    """
    # ── Dependency edges ──────────────────────────────────────────────────────
    dep_added = 0
    for edge in dep_edges:
        from_repo = edge.get("from_repo", "")
        # Support both "to_repo" (graph enrichment) and "to_package" (orchestrator CSV key)
        to_repo = edge.get("to_repo") or edge.get("to_package", "")
        if not from_repo or not to_repo:
            continue
        # Add ExternalRepo nodes for packages not already in the graph.
        if from_repo not in G:
            G.add_node(from_repo, node_type="ExternalRepo", github_url=from_repo,
                       ecosystem=edge.get("ecosystem", ""), active=None, days_since_commit=None)
        if to_repo not in G:
            G.add_node(to_repo, node_type="ExternalRepo", github_url=to_repo,
                       ecosystem=edge.get("ecosystem", ""), active=None, days_since_commit=None)
        G.add_edge(
            from_repo, to_repo,
            edge_type="depends_on",
            ecosystem=edge.get("ecosystem", ""),
            confidence=edge.get("confidence", "inferred"),
        )
        dep_added += 1
    logger.info("Added %d depends_on edges from ingestion.", dep_added)

    # ── Contributor edges ─────────────────────────────────────────────────────
    contrib_added = 0
    for edge in contrib_edges:
        contributor = edge.get("contributor", "")
        repo = edge.get("repo", "")
        if not contributor or not repo:
            continue
        if contributor not in G:
            G.add_node(contributor, node_type="Contributor", display_name=contributor, active=True)
        G.add_edge(
            contributor, repo,
            edge_type="contributed_to",
            commits=edge.get("commits", 0),
            first_date=edge.get("first_date", ""),
            last_date=edge.get("last_date", ""),
        )
        contrib_added += 1
    logger.info("Added %d contributed_to edges from ingestion.", contrib_added)

    # ── Adoption data ─────────────────────────────────────────────────────────
    for repo_url, signals in adoption_data.items():
        if repo_url in G:
            G.nodes[repo_url]["stars"] = signals.get("stars", 0)
            G.nodes[repo_url]["forks"] = signals.get("forks", 0)
            G.nodes[repo_url]["downloads"] = signals.get("downloads", 0)

    # ── Activity data ─────────────────────────────────────────────────────────
    for repo_url, activity in activity_data.items():
        if repo_url in G:
            days = activity.get("days_since_commit", None)
            archived = activity.get("archived", False)
            G.nodes[repo_url]["days_since_commit"] = days
            G.nodes[repo_url]["archived"] = archived
            if days is not None:
                G.nodes[repo_url]["active"] = (days <= 90 and not archived)

    logger.info("Graph enrichment complete.")
    return G
