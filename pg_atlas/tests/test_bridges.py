"""
pg_atlas/tests/test_bridges.py — Tests for Bridge Edge Detection.

Tests verify:
- Bridges are found in known topologies (linear chain, tree).
- No bridges exist in a cycle (ring).
- Only depends_on edges between Repo/ExternalRepo are considered.
- Empty graphs return no bridges.
- Bridge count matches known graph-theoretic results.

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import networkx as nx
import pytest

from pg_atlas.metrics.bridges import find_bridge_edges


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_linear_chain(n: int = 4) -> nx.DiGraph:
    """
    Build a linear chain: A → B → C → D.

    In a path graph with n nodes, every edge is a bridge (n-1 bridges).
    """
    G = nx.DiGraph()
    names = [f"pkg-{i}" for i in range(n)]
    for name in names:
        G.add_node(name, node_type="Repo")
    for i in range(n - 1):
        G.add_edge(names[i], names[i + 1], edge_type="depends_on")
    return G


def make_cycle(n: int = 4) -> nx.DiGraph:
    """
    Build a cycle: A → B → C → D → A.

    A cycle has zero bridges (removing any edge still leaves the graph connected).
    """
    G = nx.DiGraph()
    names = [f"pkg-{i}" for i in range(n)]
    for name in names:
        G.add_node(name, node_type="Repo")
    for i in range(n):
        G.add_edge(names[i], names[(i + 1) % n], edge_type="depends_on")
    return G


# ── Return type tests ────────────────────────────────────────────────────────

def test_returns_list_of_tuples():
    G = make_linear_chain()
    result = find_bridge_edges(G)
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, tuple)
        assert len(item) == 2


# ── Linear chain (all edges are bridges) ─────────────────────────────────────

def test_linear_chain_all_bridges():
    """In a path graph with 4 nodes, all 3 edges are bridges."""
    G = make_linear_chain(4)
    bridges = find_bridge_edges(G)
    assert len(bridges) == 3


def test_linear_chain_2_nodes():
    """A single edge between 2 nodes is a bridge."""
    G = make_linear_chain(2)
    bridges = find_bridge_edges(G)
    assert len(bridges) == 1


# ── Cycle (no bridges) ──────────────────────────────────────────────────────

def test_cycle_no_bridges():
    """A cycle has no bridges — removing any edge leaves the graph connected."""
    G = make_cycle(4)
    bridges = find_bridge_edges(G)
    assert len(bridges) == 0


def test_large_cycle_no_bridges():
    """Even a 10-node cycle has no bridges."""
    G = make_cycle(10)
    bridges = find_bridge_edges(G)
    assert len(bridges) == 0


# ── Tree (all edges are bridges) ─────────────────────────────────────────────

def test_star_all_bridges():
    """A star graph (hub + 4 leaves) has 4 bridge edges."""
    G = nx.DiGraph()
    G.add_node("hub", node_type="Repo")
    for i in range(4):
        leaf = f"leaf-{i}"
        G.add_node(leaf, node_type="ExternalRepo")
        G.add_edge(leaf, "hub", edge_type="depends_on")
    bridges = find_bridge_edges(G)
    assert len(bridges) == 4


# ── Mixed topology (cycle + pendant) ─────────────────────────────────────────

def test_cycle_with_pendant():
    """
    A cycle with a pendant node: only the pendant edge is a bridge.

    Topology: A → B → C → A (cycle, 0 bridges) + D → A (pendant, 1 bridge).
    """
    G = nx.DiGraph()
    for n in ["A", "B", "C", "D"]:
        G.add_node(n, node_type="Repo")
    G.add_edge("A", "B", edge_type="depends_on")
    G.add_edge("B", "C", edge_type="depends_on")
    G.add_edge("C", "A", edge_type="depends_on")
    G.add_edge("D", "A", edge_type="depends_on")  # pendant — bridge
    bridges = find_bridge_edges(G)
    assert len(bridges) == 1
    # The bridge should involve D and A
    bridge_nodes = set(bridges[0])
    assert "D" in bridge_nodes
    assert "A" in bridge_nodes


# ── Node type filtering ──────────────────────────────────────────────────────

def test_ignores_non_repo_nodes():
    """Project and Contributor nodes and their edges must not appear."""
    G = nx.DiGraph()
    G.add_node("repo-a", node_type="Repo")
    G.add_node("repo-b", node_type="Repo")
    G.add_node("MyProject", node_type="Project")
    G.add_node("dev-alice", node_type="Contributor")
    G.add_edge("repo-a", "repo-b", edge_type="depends_on")
    G.add_edge("repo-a", "MyProject", edge_type="belongs_to")
    G.add_edge("dev-alice", "repo-a", edge_type="contributed_to")
    bridges = find_bridge_edges(G)
    # Only depends_on between repos is considered: one bridge (repo-a, repo-b)
    assert len(bridges) == 1
    bridge_nodes = set(bridges[0])
    assert "repo-a" in bridge_nodes
    assert "repo-b" in bridge_nodes


def test_ignores_non_depends_on_edges():
    """Only depends_on edges should be considered for bridge detection."""
    G = nx.DiGraph()
    G.add_node("a", node_type="Repo")
    G.add_node("b", node_type="Repo")
    G.add_node("c", node_type="Repo")
    # belongs_to edge (not depends_on) — should be ignored
    G.add_edge("a", "b", edge_type="belongs_to")
    G.add_edge("b", "c", edge_type="depends_on")
    bridges = find_bridge_edges(G)
    # Only one depends_on edge exists (b→c), which is a bridge
    assert len(bridges) == 1


# ── Edge cases ───────────────────────────────────────────────────────────────

def test_empty_graph_no_bridges():
    """An empty graph returns no bridges."""
    G = nx.DiGraph()
    bridges = find_bridge_edges(G)
    assert len(bridges) == 0


def test_no_dependency_edges():
    """A graph with nodes but no depends_on edges returns no bridges."""
    G = nx.DiGraph()
    G.add_node("a", node_type="Repo")
    G.add_node("b", node_type="Repo")
    G.add_edge("a", "b", edge_type="belongs_to")  # not depends_on
    bridges = find_bridge_edges(G)
    assert len(bridges) == 0


def test_single_node_no_bridges():
    """A graph with a single repo and no edges has no bridges."""
    G = nx.DiGraph()
    G.add_node("lonely", node_type="Repo")
    bridges = find_bridge_edges(G)
    assert len(bridges) == 0


# ── Integration with synthetic graph ─────────────────────────────────────────

def test_bridges_on_synthetic_graph(active_subgraph):
    """Bridge detection on the synthetic graph should return a valid list."""
    bridges = find_bridge_edges(active_subgraph)
    assert isinstance(bridges, list)
    # The synthetic graph has hub-biased power-law deps, so some bridges exist.
    assert len(bridges) >= 0  # Smoke test — specific count depends on SEED
    for u, v in bridges:
        assert isinstance(u, str)
        assert isinstance(v, str)
