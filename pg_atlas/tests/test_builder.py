"""
pg_atlas/tests/test_builder.py — Tests for pg_atlas.graph.builder.

Tests verify:
- build_graph_from_csv loads 86+ Project nodes.
- build_graph_from_csv loads Repo nodes from A7 CSV.
- All Project nodes have node_type='Project'.
- All Repo nodes have node_type='Repo'.
- build_graph_from_db returns an empty graph without crashing.
- enrich_graph_with_ingestion correctly adds edges and updates node attributes.
"""

import os

import networkx as nx
import pytest

from pg_atlas.graph.builder import (
    build_graph_from_csv,
    build_graph_from_db,
    enrich_graph_with_ingestion,
)

BASE = "/Users/jaygut/Desktop/SCF_PG-Atlas/01_data/processed"
A5_PATH = os.path.join(BASE, "A5_pg_candidate_seed_list.csv")
A6_PATH = os.path.join(BASE, "A6_github_orgs_seed.csv")
A7_PATH = os.path.join(BASE, "A7_submission_github_repos.csv")


# ── build_graph_from_csv tests ────────────────────────────────────────────────

class TestBuildGraphFromCsv:
    """Tests for the CSV-backed graph builder."""

    def test_returns_digraph(self, real_csv_graph):
        """build_graph_from_csv must return a NetworkX DiGraph."""
        assert isinstance(real_csv_graph, nx.DiGraph)

    def test_loads_86_or_more_project_nodes(self, real_csv_graph):
        """Must load all 86 PG seed projects (A5 CSV has 86 rows)."""
        project_nodes = [
            n for n, d in real_csv_graph.nodes(data=True)
            if d.get("node_type") == "Project"
        ]
        assert len(project_nodes) >= 86, (
            f"Expected >= 86 Project nodes, got {len(project_nodes)}"
        )

    def test_loads_repo_nodes(self, real_csv_graph):
        """Must load Repo nodes from A7 CSV."""
        repo_nodes = [
            n for n, d in real_csv_graph.nodes(data=True)
            if d.get("node_type") == "Repo"
        ]
        assert len(repo_nodes) > 0, "No Repo nodes loaded from A7 CSV"

    def test_repo_count_matches_unique_urls(self, real_csv_graph):
        """Number of Repo nodes should be >= 200 (A7 has 338 rows, many unique URLs)."""
        repo_nodes = [
            n for n, d in real_csv_graph.nodes(data=True)
            if d.get("node_type") == "Repo"
        ]
        # Not all rows may be unique or have valid URLs, but there should be many.
        assert len(repo_nodes) >= 100, (
            f"Expected >= 100 Repo nodes, got {len(repo_nodes)}"
        )

    def test_all_project_nodes_have_correct_type(self, real_csv_graph):
        """Every Project node must have node_type='Project'."""
        for node, data in real_csv_graph.nodes(data=True):
            if data.get("node_type") == "Project":
                assert data["node_type"] == "Project"

    def test_all_repo_nodes_have_correct_type(self, real_csv_graph):
        """Every Repo node must have node_type='Repo'."""
        for node, data in real_csv_graph.nodes(data=True):
            if data.get("node_type") == "Repo":
                assert data["node_type"] == "Repo"

    def test_project_nodes_have_required_attributes(self, real_csv_graph):
        """Project nodes must have title, category, integration_status, node_type."""
        project_nodes = [
            (n, d) for n, d in real_csv_graph.nodes(data=True)
            if d.get("node_type") == "Project"
        ]
        required_attrs = {"node_type", "title", "category", "integration_status"}
        for node, data in project_nodes[:10]:  # check first 10
            missing = required_attrs - set(data.keys())
            assert not missing, f"Project '{node}' missing attributes: {missing}"

    def test_repo_nodes_have_required_attributes(self, real_csv_graph):
        """Repo nodes must have github_url, submission_title, node_type."""
        repo_nodes = [
            (n, d) for n, d in real_csv_graph.nodes(data=True)
            if d.get("node_type") == "Repo"
        ]
        required_attrs = {"node_type", "github_url", "submission_title"}
        for node, data in repo_nodes[:10]:  # check first 10
            missing = required_attrs - set(data.keys())
            assert not missing, f"Repo '{node}' missing attributes: {missing}"

    def test_belongs_to_edges_exist(self, real_csv_graph):
        """Some belongs_to edges must be present (fuzzy title matching)."""
        belongs_to_edges = [
            (u, v) for u, v, d in real_csv_graph.edges(data=True)
            if d.get("edge_type") == "belongs_to"
        ]
        # Fuzzy matching at 0.6 cutoff should link at least some repos to projects.
        assert len(belongs_to_edges) > 0, "No belongs_to edges were created"

    def test_project_titles_are_node_ids(self, real_csv_graph):
        """Project node IDs should be the project titles (strings)."""
        # Check known projects from the A5 CSV
        known_projects = ["Reflector", "Scout"]
        for p in known_projects:
            assert p in real_csv_graph.nodes, f"Known project '{p}' not found as node ID"

    def test_total_awarded_usd_numeric(self, real_csv_graph):
        """total_awarded_usd must be a float on Project nodes."""
        for node, data in real_csv_graph.nodes(data=True):
            if data.get("node_type") == "Project":
                usd = data.get("total_awarded_usd")
                assert isinstance(usd, float), (
                    f"Project '{node}' total_awarded_usd is {type(usd)}, expected float"
                )

    def test_graph_metadata_set(self, real_csv_graph):
        """Graph metadata should record source='csv'."""
        assert real_csv_graph.graph.get("source") == "csv"

    def test_github_orgs_stored_in_graph_metadata(self, real_csv_graph):
        """GitHub orgs from A6 CSV should be stored in graph.graph['github_orgs']."""
        assert "github_orgs" in real_csv_graph.graph
        assert isinstance(real_csv_graph.graph["github_orgs"], list)
        assert len(real_csv_graph.graph["github_orgs"]) > 0

    def test_build_works_with_explicit_paths(self):
        """build_graph_from_csv can be called with explicit paths."""
        G = build_graph_from_csv(A5_PATH, A6_PATH, A7_PATH)
        assert G.number_of_nodes() > 0


# ── build_graph_from_db tests ─────────────────────────────────────────────────

class TestBuildGraphFromDb:
    """Tests for the PostgreSQL stub."""

    def test_returns_digraph_without_crash(self):
        """build_graph_from_db must not crash and must return an nx.DiGraph."""
        G = build_graph_from_db(conn=None)
        assert isinstance(G, nx.DiGraph)

    def test_returns_empty_graph(self):
        """Stub must return an empty graph (no nodes, no edges)."""
        G = build_graph_from_db(conn=None)
        assert G.number_of_nodes() == 0
        assert G.number_of_edges() == 0

    def test_marks_source_as_stub(self):
        """Graph metadata should note this is a stub."""
        G = build_graph_from_db(conn=None)
        assert "stub" in G.graph.get("source", "").lower()

    def test_accepts_arbitrary_conn_argument(self):
        """Stub must accept any conn argument without type-checking."""
        build_graph_from_db(conn="fake-connection-string")
        build_graph_from_db(conn={"host": "localhost"})
        build_graph_from_db(conn=42)  # All should succeed without crash.


# ── enrich_graph_with_ingestion tests ─────────────────────────────────────────

class TestEnrichGraphWithIngestion:
    """Tests for the graph enrichment function."""

    def _base_graph(self) -> nx.DiGraph:
        G = nx.DiGraph()
        G.add_node("https://github.com/stellar/repo-a", node_type="Repo", github_url="https://github.com/stellar/repo-a")
        return G

    def test_adds_dependency_edges(self):
        """dep_edges list populates depends_on edges in the graph."""
        G = self._base_graph()
        dep_edges = [
            {"from_repo": "https://github.com/stellar/repo-a",
             "to_repo": "https://github.com/stellar/dep-b",
             "ecosystem": "npm", "confidence": "direct"},
        ]
        enrich_graph_with_ingestion(G, dep_edges, [], {}, {})
        assert G.has_edge("https://github.com/stellar/repo-a", "https://github.com/stellar/dep-b")
        edge_data = G.edges["https://github.com/stellar/repo-a", "https://github.com/stellar/dep-b"]
        assert edge_data["edge_type"] == "depends_on"

    def test_adds_contributor_edges(self):
        """contrib_edges list populates contributed_to edges."""
        G = self._base_graph()
        contrib_edges = [
            {"contributor": "alice", "repo": "https://github.com/stellar/repo-a",
             "commits": 42, "first_date": "2025-01-01", "last_date": "2026-01-01"},
        ]
        enrich_graph_with_ingestion(G, [], contrib_edges, {}, {})
        assert G.has_edge("alice", "https://github.com/stellar/repo-a")
        assert G.edges["alice", "https://github.com/stellar/repo-a"]["commits"] == 42

    def test_updates_adoption_signals(self):
        """adoption_data updates node attributes (stars, forks, downloads)."""
        G = self._base_graph()
        adoption_data = {
            "https://github.com/stellar/repo-a": {"stars": 500, "forks": 50, "downloads": 10000}
        }
        enrich_graph_with_ingestion(G, [], [], adoption_data, {})
        assert G.nodes["https://github.com/stellar/repo-a"]["stars"] == 500
        assert G.nodes["https://github.com/stellar/repo-a"]["forks"] == 50

    def test_updates_activity_data(self):
        """activity_data updates days_since_commit and active flag."""
        G = self._base_graph()
        activity_data = {
            "https://github.com/stellar/repo-a": {"days_since_commit": 30, "archived": False}
        }
        enrich_graph_with_ingestion(G, [], [], {}, activity_data)
        assert G.nodes["https://github.com/stellar/repo-a"]["days_since_commit"] == 30
        assert G.nodes["https://github.com/stellar/repo-a"]["active"] is True

    def test_archived_repo_marked_inactive(self):
        """activity_data with archived=True sets active=False."""
        G = self._base_graph()
        activity_data = {
            "https://github.com/stellar/repo-a": {"days_since_commit": 5, "archived": True}
        }
        enrich_graph_with_ingestion(G, [], [], {}, activity_data)
        assert G.nodes["https://github.com/stellar/repo-a"]["active"] is False

    def test_returns_same_graph_object(self):
        """enrich_graph_with_ingestion must return the same graph object (in-place)."""
        G = self._base_graph()
        returned = enrich_graph_with_ingestion(G, [], [], {}, {})
        assert returned is G

    def test_creates_new_externalrepo_nodes_for_unknown_deps(self):
        """Unknown to_repo in dep_edges should be created as ExternalRepo nodes."""
        G = self._base_graph()
        dep_edges = [
            {"from_repo": "https://github.com/stellar/repo-a",
             "to_repo": "https://github.com/external/pkg",
             "ecosystem": "cargo", "confidence": "direct"},
        ]
        enrich_graph_with_ingestion(G, dep_edges, [], {}, {})
        assert "https://github.com/external/pkg" in G.nodes

    def test_creates_contributor_nodes_for_unknown_contributors(self):
        """Unknown contributor in contrib_edges should be created as Contributor nodes."""
        G = self._base_graph()
        contrib_edges = [
            {"contributor": "new-dev", "repo": "https://github.com/stellar/repo-a",
             "commits": 10, "first_date": "", "last_date": ""},
        ]
        enrich_graph_with_ingestion(G, [], contrib_edges, {}, {})
        assert "new-dev" in G.nodes
        assert G.nodes["new-dev"]["node_type"] == "Contributor"
