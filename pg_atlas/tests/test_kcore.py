"""
pg_atlas/tests/test_kcore.py — Tests for K-Core Decomposition.

Tests verify:
- K-core operates only on Repo/ExternalRepo nodes with depends_on edges.
- Returns (nx.Graph, dict) tuple.
- Core numbers are correct for known graph topologies.
- Project and Contributor nodes are excluded from kcore analysis.
- Empty dependency graph returns empty core numbers.
- Node attributes from G_active are copied to the undirected graph.

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import networkx as nx
import pytest

from pg_atlas.metrics.kcore import kcore_analysis


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_kcore_graph() -> nx.DiGraph:
    """
    Build a graph with known k-core structure.

    Topology (depends_on edges only):
        A ──→ B ──→ C ──→ A   (triangle: each has degree 2 → k-core = 2)
        D ──→ A               (pendant: degree 1 → k-core = 1)
        E ──→ B               (pendant: degree 1 → k-core = 1)

    Also includes non-dep nodes (Project, Contributor) that must be excluded.
    """
    G = nx.DiGraph()
    # Triangle of repos (forms a 2-core)
    G.add_node("A", node_type="Repo", days_since_commit=10, ecosystem="cargo")
    G.add_node("B", node_type="Repo", days_since_commit=20, ecosystem="cargo")
    G.add_node("C", node_type="Repo", days_since_commit=30, ecosystem="cargo")
    G.add_edge("A", "B", edge_type="depends_on")
    G.add_edge("B", "C", edge_type="depends_on")
    G.add_edge("C", "A", edge_type="depends_on")

    # Pendant repos (leaf nodes → 1-core)
    G.add_node("D", node_type="ExternalRepo", days_since_commit=5, ecosystem="npm")
    G.add_node("E", node_type="ExternalRepo", days_since_commit=15, ecosystem="npm")
    G.add_edge("D", "A", edge_type="depends_on")
    G.add_edge("E", "B", edge_type="depends_on")

    # Non-dependency nodes (must be excluded from kcore)
    G.add_node("MyProject", node_type="Project")
    G.add_node("dev-alice", node_type="Contributor")
    G.add_edge("A", "MyProject", edge_type="belongs_to")
    G.add_edge("dev-alice", "A", edge_type="contributed_to", commits=50)

    return G


# ── Return type tests ────────────────────────────────────────────────────────

def test_returns_tuple_of_graph_and_dict():
    G = make_kcore_graph()
    result = kcore_analysis(G)
    assert isinstance(result, tuple)
    assert len(result) == 2
    G_u, cores = result
    assert isinstance(G_u, nx.Graph)
    assert isinstance(cores, dict)


def test_undirected_graph_is_undirected():
    """The returned graph must be undirected (not DiGraph)."""
    G = make_kcore_graph()
    G_u, _ = kcore_analysis(G)
    assert not G_u.is_directed()


# ── Node filtering ───────────────────────────────────────────────────────────

def test_only_repo_and_external_repo_nodes():
    """K-core graph must contain only Repo and ExternalRepo nodes."""
    G = make_kcore_graph()
    G_u, cores = kcore_analysis(G)
    assert "MyProject" not in G_u.nodes
    assert "dev-alice" not in G_u.nodes
    for node in G_u.nodes:
        assert G_u.nodes[node].get("node_type") in ("Repo", "ExternalRepo")


def test_only_depends_on_edges():
    """Only depends_on edges should be in the undirected graph."""
    G = make_kcore_graph()
    G_u, _ = kcore_analysis(G)
    # belongs_to and contributed_to edges must not appear
    assert not G_u.has_edge("A", "MyProject")
    assert not G_u.has_edge("dev-alice", "A")


# ── Core number correctness ─────────────────────────────────────────────────

def test_triangle_nodes_are_2_core():
    """Nodes in a triangle (mutual dependencies) should have core number = 2."""
    G = make_kcore_graph()
    _, cores = kcore_analysis(G)
    assert cores["A"] == 2
    assert cores["B"] == 2
    assert cores["C"] == 2


def test_pendant_nodes_are_1_core():
    """Leaf nodes connected to the triangle should have core number = 1."""
    G = make_kcore_graph()
    _, cores = kcore_analysis(G)
    assert cores["D"] == 1
    assert cores["E"] == 1


def test_max_core_equals_2():
    """Max k-core in the test graph is 2 (the triangle)."""
    G = make_kcore_graph()
    _, cores = kcore_analysis(G)
    assert max(cores.values()) == 2


# ── Edge cases ───────────────────────────────────────────────────────────────

def test_empty_graph():
    """A graph with no dependency nodes returns empty core numbers."""
    G = nx.DiGraph()
    G.add_node("MyProject", node_type="Project")
    G_u, cores = kcore_analysis(G)
    assert len(cores) == 0
    assert G_u.number_of_nodes() == 0


def test_single_node_no_edges():
    """A single repo node with no edges has core number = 0."""
    G = nx.DiGraph()
    G.add_node("lonely", node_type="Repo", days_since_commit=5)
    _, cores = kcore_analysis(G)
    assert cores["lonely"] == 0


def test_disconnected_components():
    """Two disconnected pairs have independent k-core structure."""
    G = nx.DiGraph()
    G.add_node("a1", node_type="Repo")
    G.add_node("a2", node_type="Repo")
    G.add_node("b1", node_type="Repo")
    G.add_node("b2", node_type="Repo")
    G.add_edge("a1", "a2", edge_type="depends_on")
    G.add_edge("b1", "b2", edge_type="depends_on")
    _, cores = kcore_analysis(G)
    # All nodes in simple edges have core number 1
    assert cores["a1"] == 1
    assert cores["a2"] == 1
    assert cores["b1"] == 1
    assert cores["b2"] == 1


def test_star_topology():
    """Hub with 4 leaves: hub has degree 4 but k-core = 1 (leaves are degree 1)."""
    G = nx.DiGraph()
    G.add_node("hub", node_type="Repo")
    for i in range(4):
        leaf = f"leaf-{i}"
        G.add_node(leaf, node_type="ExternalRepo")
        G.add_edge(leaf, "hub", edge_type="depends_on")
    _, cores = kcore_analysis(G)
    # In a star, the max k-core is 1 (all leaves have degree 1).
    assert cores["hub"] == 1
    for i in range(4):
        assert cores[f"leaf-{i}"] == 1


# ── Attribute preservation ───────────────────────────────────────────────────

def test_node_attributes_copied():
    """Node attributes from G_active must be copied to the undirected graph."""
    G = make_kcore_graph()
    G_u, _ = kcore_analysis(G)
    assert G_u.nodes["A"]["ecosystem"] == "cargo"
    assert G_u.nodes["A"]["days_since_commit"] == 10
    assert G_u.nodes["D"]["ecosystem"] == "npm"


# ── Integration with synthetic graph ─────────────────────────────────────────

def test_kcore_on_synthetic_graph(active_subgraph):
    """K-core analysis on the synthetic graph should produce meaningful results."""
    G_u, cores = kcore_analysis(active_subgraph)
    assert len(cores) > 0
    assert max(cores.values()) >= 1  # Must have at least some connected structure
    # All nodes in the kcore result should be Repo or ExternalRepo
    for node in G_u.nodes:
        nt = G_u.nodes[node].get("node_type", "")
        assert nt in ("Repo", "ExternalRepo"), f"Unexpected node type {nt} for {node}"
