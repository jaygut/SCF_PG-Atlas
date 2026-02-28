"""
pg_atlas/metrics/keystone_contributor.py — Tier 3 Strategic Metric.

Keystone Contributor Index: identifies individuals whose absence would cascade
across multiple critical projects simultaneously.

Standard pony factor treats each repo in isolation. The KCI reveals correlated
human capital risk — a contributor with PF=1 in 5 high-criticality projects
represents 5x the ecosystem risk of a contributor with PF=1 in 1 project.

Formula: KCI(contributor) = Sigma(pony_factor_flag × criticality_score)
         for all repos where contributor is dominant.

Author: Jay Gutierrez, PhD | SCF #41
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from pg_atlas.metrics.criticality import compute_percentile_ranks

logger = logging.getLogger(__name__)


@dataclass
class KeystoneContributorResult:
    """
    KCI result for a single contributor.

    Fields:
        contributor:             Contributor node ID.
        dominant_repos:          Repos where this contributor has PF=1 (is top contributor
                                 and pony_factor flag is set).
        repo_criticality_scores: {repo: criticality_score} for dominant repos.
        kci_score:               Sum of criticality scores across dominant repos.
        kci_percentile:          Percentile of kci_score across all contributors.
        total_dominant_repos:    Count of repos where this contributor is dominant.
        aggregate_criticality:   Sum of criticality scores for all dominant repos.
        at_risk_downstream:      Union count of transitive deps across all dominant repos.
        risk_narrative:          Human-readable cascade description.
    """

    contributor: str
    dominant_repos: list[str]
    repo_criticality_scores: dict[str, int]
    kci_score: float
    kci_percentile: float
    total_dominant_repos: int
    aggregate_criticality: float
    at_risk_downstream: int
    risk_narrative: str


def compute_transitive_union(
    G_active: nx.DiGraph,
    repo_list: list[str],
) -> int:
    """
    Count the UNION of transitive dependents across all repos in repo_list.

    Uses BFS on reversed dependency graph. Deduplicates shared dependents so
    that a package depending on two of the listed repos is counted only once.

    Algorithm:
        1. Build the dependency subgraph (depends_on edges only).
        2. Reverse it (edges now flow toward dependents).
        3. For each repo in repo_list, collect all reachable nodes.
        4. Take the union of all reachable sets and return the cardinality.

    Args:
        G_active:  Active subgraph from active_subgraph_projection().
        repo_list: List of repo node IDs to compute the union for.

    Returns:
        Integer count of unique transitive downstream packages at risk.
    """
    if not repo_list:
        return 0

    # Build dependency subgraph
    dep_nodes: set[str] = {
        n for n, d in G_active.nodes(data=True)
        if d.get("node_type") in ("Repo", "ExternalRepo")
    }
    dep_edges = [
        (u, v) for u, v, d in G_active.edges(data=True)
        if d.get("edge_type") == "depends_on"
        and u in dep_nodes and v in dep_nodes
    ]

    G_dep = nx.DiGraph()
    G_dep.add_nodes_from(dep_nodes)
    G_dep.add_edges_from(dep_edges)
    G_rev = G_dep.reverse(copy=True)

    all_at_risk: set[str] = set()
    for repo in repo_list:
        if repo in G_rev:
            descendants = nx.descendants(G_rev, repo)
            all_at_risk.update(descendants)

    return len(all_at_risk)


def generate_kci_narrative(result: KeystoneContributorResult) -> str:
    """
    Generate a cascade risk narrative for a keystone contributor.

    Template:
        "If {contributor} became unavailable, {N} packages across
        {M} projects would lose their primary maintainer (KCI={kci:.1f}).
        These repos account for {K} unique transitive downstream dependencies."

    Args:
        result: KeystoneContributorResult with all fields populated except risk_narrative.

    Returns:
        Human-readable risk narrative string.
    """
    return (
        f"If {result.contributor} became unavailable, {result.total_dominant_repos} "
        f"packages across {result.total_dominant_repos} projects would lose their "
        f"primary maintainer (KCI={result.kci_score:.1f}). "
        f"These repos account for {result.at_risk_downstream} unique transitive "
        f"downstream dependencies."
    )


def compute_keystone_contributors(
    G_active: nx.DiGraph,
    criticality_scores: dict[str, int],
    pony_results: dict,
) -> list[KeystoneContributorResult]:
    """
    Compute the Keystone Contributor Index for all contributors.

    A contributor qualifies as a keystone if they are the top_contributor
    with pony_factor == 1 in at least one repo in the active subgraph.

    Algorithm:
        1. For each contributor, find all repos where they are the top_contributor
           AND pony_factor == 1 (dominant AND the repo is single-contributor risk).
        2. KCI = sum of criticality_scores for those dominant repos.
        3. Compute union of transitive dependents across all their dominant repos.
        4. Compute KCI percentile across all contributors (including those with KCI=0).
        5. Generate narrative for each contributor with KCI > 0.

    Args:
        G_active:           Active subgraph from active_subgraph_projection().
        criticality_scores: Output of compute_criticality_scores().
        pony_results:       Output of compute_pony_factors() — maps repo → ContributorRiskResult.

    Returns:
        List of KeystoneContributorResult sorted by kci_score descending (highest risk first).
        Only contributors with KCI > 0 are returned.
    """
    # ── Step 1: Map contributor → dominant repos (where PF=1) ────────────────
    contributor_to_repos: dict[str, list[str]] = defaultdict(list)

    for repo, pony_result in pony_results.items():
        if pony_result.pony_factor == 1:
            contributor_to_repos[pony_result.top_contributor].append(repo)

    # ── Step 2: Compute KCI scores ────────────────────────────────────────────
    raw_kci: dict[str, float] = {}
    contributor_repo_scores: dict[str, dict[str, int]] = {}

    for contributor, repos in contributor_to_repos.items():
        repo_scores = {
            r: criticality_scores.get(r, 0)
            for r in repos
        }
        kci = float(sum(repo_scores.values()))
        raw_kci[contributor] = kci
        contributor_repo_scores[contributor] = repo_scores

    if not raw_kci:
        logger.info("compute_keystone_contributors: no contributors with KCI > 0 found.")
        return []

    # ── Step 3: Compute KCI percentiles ──────────────────────────────────────
    percentiles = compute_percentile_ranks(raw_kci)

    # ── Step 4: Build results ─────────────────────────────────────────────────
    results: list[KeystoneContributorResult] = []

    for contributor, kci_score in raw_kci.items():
        if kci_score == 0:
            continue

        repos = contributor_to_repos[contributor]
        repo_scores = contributor_repo_scores[contributor]
        agg_criticality = float(sum(repo_scores.values()))

        # Count union of transitive dependents across all dominant repos
        at_risk = compute_transitive_union(G_active, repos)

        result = KeystoneContributorResult(
            contributor=contributor,
            dominant_repos=sorted(repos),
            repo_criticality_scores=repo_scores,
            kci_score=round(kci_score, 2),
            kci_percentile=round(percentiles.get(contributor, 0.0), 1),
            total_dominant_repos=len(repos),
            aggregate_criticality=round(agg_criticality, 2),
            at_risk_downstream=at_risk,
            risk_narrative="",  # placeholder — filled below
        )
        result.risk_narrative = generate_kci_narrative(result)
        results.append(result)

    # ── Step 5: Sort by KCI score descending ─────────────────────────────────
    results.sort(key=lambda r: r.kci_score, reverse=True)

    logger.info(
        "Keystone Contributor Index: %d contributors identified with KCI > 0. "
        "Top contributor: %s (KCI=%.1f).",
        len(results),
        results[0].contributor if results else "N/A",
        results[0].kci_score if results else 0.0,
    )
    return results


def kci_summary(results: list[KeystoneContributorResult]) -> dict:
    """
    Compute a summary of the Keystone Contributor Index results.

    Returns:
        {
          'total_keystone_contributors': int,  # contributors with KCI > 0
          'top_5': list of top 5 as name+kci dicts,
          'total_at_risk_downstream': int,     # total unique downstream packages at risk
        }

    Note: total_at_risk_downstream is the sum of at_risk_downstream across
    all keystone contributors. This may double-count repos that appear in
    multiple contributors' portfolios, which is intentional: it reflects the
    aggregate exposure surface rather than the deduplicated count.

    Args:
        results: List of KeystoneContributorResult from compute_keystone_contributors().

    Returns:
        Summary dict.
    """
    return {
        "total_keystone_contributors": len(results),
        "top_5": [
            {
                "contributor": r.contributor,
                "kci_score": r.kci_score,
                "dominant_repos": r.total_dominant_repos,
                "at_risk_downstream": r.at_risk_downstream,
            }
            for r in results[:5]
        ],
        "total_at_risk_downstream": sum(r.at_risk_downstream for r in results),
    }
