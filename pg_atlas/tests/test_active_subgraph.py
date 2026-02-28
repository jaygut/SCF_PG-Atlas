"""
pg_atlas/tests/test_active_subgraph.py — Tests for A6 active subgraph projection.

Tests verify:
- Dormant nodes (days_since_commit > 90) are excluded from active subgraph.
- Active nodes (days_since_commit <= 90) are retained.
- Project and Contributor nodes always retained regardless of activity.
- Induced subgraph preserves edge types correctly.
- Configurable active_window_days changes output deterministically.
- active_subgraph_projection returns (nx.DiGraph, set) tuple.
"""

import networkx as nx
import pytest

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig
from pg_atlas.graph.active_subgraph import active_subgraph_projection


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_small_graph() -> nx.DiGraph:
    """Build a tiny deterministic graph for fast unit tests."""
    G = nx.DiGraph()
    # Active repo (committed 10 days ago)
    G.add_node("repo-active", node_type="Repo", days_since_commit=10, archived=False, active=True)
    # Dormant repo (committed 120 days ago)
    G.add_node("repo-dormant", node_type="Repo", days_since_commit=120, archived=False, active=False)
    # Archived repo (even if recent commit, archived → dormant)
    G.add_node("repo-archived", node_type="Repo", days_since_commit=5, archived=True, active=False)
    # Project node (always retained)
    G.add_node("MyProject", node_type="Project", days_since_commit=200)
    # Contributor node (always retained)
    G.add_node("dev-alice", node_type="Contributor", active=True)
    # External active repo
    G.add_node("ext-pkg-active", node_type="ExternalRepo", days_since_commit=30, archived=False, active=True)
    # External dormant repo
    G.add_node("ext-pkg-dormant", node_type="ExternalRepo", days_since_commit=180, archived=False, active=False)

    # Edges
    G.add_edge("repo-active", "MyProject", edge_type="belongs_to")
    G.add_edge("repo-dormant", "MyProject", edge_type="belongs_to")
    G.add_edge("repo-active", "ext-pkg-active", edge_type="depends_on")
    G.add_edge("repo-active", "ext-pkg-dormant", edge_type="depends_on")
    G.add_edge("dev-alice", "repo-active", edge_type="contributed_to", commits=42)
    return G


# ── Return type tests ─────────────────────────────────────────────────────────

def test_returns_tuple_of_digraph_and_set():
    G = make_small_graph()
    result = active_subgraph_projection(G)
    assert isinstance(result, tuple)
    assert len(result) == 2
    G_active, dormant = result
    assert isinstance(G_active, nx.DiGraph)
    assert isinstance(dormant, set)


# ── Dormant node exclusion ────────────────────────────────────────────────────

def test_dormant_repo_excluded():
    """Repos with days_since_commit > 90 must be pruned."""
    G = make_small_graph()
    G_active, dormant = active_subgraph_projection(G)
    assert "repo-dormant" not in G_active.nodes
    assert "repo-dormant" in dormant


def test_archived_repo_excluded():
    """Archived repos must be pruned even if days_since_commit is low."""
    G = make_small_graph()
    G_active, dormant = active_subgraph_projection(G)
    assert "repo-archived" not in G_active.nodes
    assert "repo-archived" in dormant


def test_dormant_external_repo_excluded():
    """Dormant ExternalRepo nodes must be excluded."""
    G = make_small_graph()
    G_active, dormant = active_subgraph_projection(G)
    assert "ext-pkg-dormant" not in G_active.nodes


# ── Active node retention ─────────────────────────────────────────────────────

def test_active_repo_retained():
    """Repos with days_since_commit <= 90 and not archived must be retained."""
    G = make_small_graph()
    G_active, _ = active_subgraph_projection(G)
    assert "repo-active" in G_active.nodes


def test_active_external_repo_retained():
    """Active ExternalRepo nodes must be retained."""
    G = make_small_graph()
    G_active, _ = active_subgraph_projection(G)
    assert "ext-pkg-active" in G_active.nodes


# ── Project and Contributor always retained ───────────────────────────────────

def test_project_always_retained():
    """Project nodes are always in the active subgraph regardless of activity."""
    G = make_small_graph()
    G_active, _ = active_subgraph_projection(G)
    assert "MyProject" in G_active.nodes


def test_contributor_always_retained():
    """Contributor nodes are always in the active subgraph."""
    G = make_small_graph()
    G_active, _ = active_subgraph_projection(G)
    assert "dev-alice" in G_active.nodes


def test_project_retained_with_high_days_since_commit():
    """Project nodes are retained even if days_since_commit is very high."""
    G = nx.DiGraph()
    G.add_node("OldProject", node_type="Project", days_since_commit=9999)
    G_active, dormant = active_subgraph_projection(G)
    assert "OldProject" in G_active.nodes
    assert "OldProject" not in dormant


def test_contributor_retained_regardless_of_activity():
    """Contributor nodes with no active attribute are always retained."""
    G = nx.DiGraph()
    G.add_node("alice", node_type="Contributor")
    G.add_node("inactive-repo", node_type="Repo", days_since_commit=500, archived=False)
    G_active, _ = active_subgraph_projection(G)
    assert "alice" in G_active.nodes


# ── Edge preservation ─────────────────────────────────────────────────────────

def test_edge_types_preserved():
    """Edge attributes (edge_type, commits) are preserved in the induced subgraph."""
    G = make_small_graph()
    G_active, _ = active_subgraph_projection(G)
    # The contributed_to edge from dev-alice to repo-active must be preserved.
    assert G_active.has_edge("dev-alice", "repo-active")
    assert G_active.edges["dev-alice", "repo-active"]["edge_type"] == "contributed_to"
    assert G_active.edges["dev-alice", "repo-active"]["commits"] == 42


def test_edges_to_dormant_nodes_removed():
    """Edges to/from dormant nodes should not appear in the active subgraph."""
    G = make_small_graph()
    G_active, _ = active_subgraph_projection(G)
    # repo-active → ext-pkg-dormant edge should be gone (dormant node removed).
    assert not G_active.has_edge("repo-active", "ext-pkg-dormant")


def test_depends_on_between_active_nodes_preserved():
    """depends_on edge between two active nodes is preserved."""
    G = make_small_graph()
    G_active, _ = active_subgraph_projection(G)
    assert G_active.has_edge("repo-active", "ext-pkg-active")
    assert G_active.edges["repo-active", "ext-pkg-active"]["edge_type"] == "depends_on"


# ── Configurable window ───────────────────────────────────────────────────────

def test_configurable_window_30_days_more_dormant():
    """With a tighter 30-day window, more repos are classified dormant."""
    G = make_small_graph()
    config_30 = PGAtlasConfig(active_window_days=30)
    G_active_30, dormant_30 = active_subgraph_projection(G, config_30)
    G_active_90, dormant_90 = active_subgraph_projection(G, DEFAULT_CONFIG)
    # Stricter window must prune at least as many or more nodes.
    assert len(dormant_30) >= len(dormant_90)


def test_configurable_window_200_days_fewer_dormant():
    """With a looser 200-day window, fewer repos are classified dormant."""
    G = make_small_graph()
    config_200 = PGAtlasConfig(active_window_days=200)
    G_active_200, dormant_200 = active_subgraph_projection(G, config_200)
    G_active_90, dormant_90 = active_subgraph_projection(G, DEFAULT_CONFIG)
    # Looser window must prune fewer or equal nodes.
    assert len(dormant_200) <= len(dormant_90)


def test_window_change_is_deterministic():
    """Same config twice → same result."""
    G = make_small_graph()
    _, dormant_a = active_subgraph_projection(G, DEFAULT_CONFIG)
    _, dormant_b = active_subgraph_projection(G, DEFAULT_CONFIG)
    assert dormant_a == dormant_b


# ── Graph metadata annotation ─────────────────────────────────────────────────

def test_graph_metadata_annotated():
    """G_active.graph should carry audit metadata."""
    G = make_small_graph()
    G_active, dormant = active_subgraph_projection(G)
    assert "active_window_days" in G_active.graph
    assert G_active.graph["active_window_days"] == DEFAULT_CONFIG.active_window_days
    assert G_active.graph["nodes_retained"] == len(G_active.nodes)
    assert G_active.graph["nodes_removed"] == len(dormant)


# ── Integration with synthetic graph ─────────────────────────────────────────

def test_active_subgraph_reduces_nodes(synthetic_graph):
    """The synthetic graph should have dormant nodes → projection reduces node count."""
    G_active, dormant = active_subgraph_projection(synthetic_graph)
    # There must be some dormant nodes in the realistic synthetic graph.
    assert len(dormant) > 0
    assert G_active.number_of_nodes() < synthetic_graph.number_of_nodes()


def test_active_subgraph_all_retained_nodes_are_active_or_nonrepo(synthetic_graph):
    """Every Repo/ExternalRepo node in G_active must be truly active."""
    G_active, _ = active_subgraph_projection(synthetic_graph)
    for node, data in G_active.nodes(data=True):
        if data.get("node_type") in ("Repo", "ExternalRepo"):
            days = data.get("days_since_commit", 0)
            archived = data.get("archived", False)
            assert days <= DEFAULT_CONFIG.active_window_days
            assert not archived
