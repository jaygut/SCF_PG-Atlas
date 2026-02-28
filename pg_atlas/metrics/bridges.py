"""
pg_atlas/metrics/bridges.py — Bridge Edge Detection (Single Points of Failure).

Translated from the validated prototype:
  06_demos/01_active_subgraph_prototype/build_notebook.py (Section 9)

A bridge is an edge whose removal would disconnect two previously connected
components of the graph. In the dependency context: a bridge dependency is a
relationship where Package A is the *only* way that one part of the ecosystem
connects to another.

If the package at one end of a bridge is deprecated or abandoned, the other
end loses its connection to the rest of the dependency network — a structural
fracture, not just a package absence.

Bridge detection uses Tarjan's algorithm (O(V + E)) on the undirected
dependency graph, as exposed by NetworkX's nx.bridges() function.

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import logging

import networkx as nx

logger = logging.getLogger(__name__)


def find_bridge_edges(
    G_active: nx.DiGraph,
) -> list[tuple[str, str]]:
    """
    Find bridge edges in the active dependency subgraph.

    A bridge edge is one whose removal disconnects the graph. These represent
    single-point-of-failure dependency relationships: if the package at either
    end of a bridge becomes unavailable, an entire cluster of the ecosystem
    loses connectivity.

    Algorithm (Tarjan's bridge-finding, O(V + E)):
        1. Extract the dependency subgraph (Repo + ExternalRepo nodes,
           depends_on edges only).
        2. Convert to undirected graph.
        3. Apply nx.bridges() (Tarjan's algorithm implementation).

    Args:
        G_active: Active subgraph from active_subgraph_projection().
                  Nodes must carry 'node_type' attribute.
                  Edges must carry 'edge_type' attribute.

    Returns:
        bridges: List of (u, v) edge tuples that are bridges.
                 Order is arbitrary (determined by DFS traversal order).
                 The returned tuples follow undirected convention — (u, v)
                 and (v, u) represent the same bridge.

    Notes:
        - Bridge detection operates on the undirected version of the
          dependency subgraph (same rationale as kcore analysis).
        - An empty list is returned if the graph has no bridges or no
          dependency edges (e.g., the graph is a tree or a complete graph).
        - Bridges are most actionable when combined with criticality scores:
          a bridge edge adjacent to a high-criticality package represents
          the highest structural risk.

    Reference:
        Prototype: build_notebook.py Section 9, find_bridge_edges()
    """
    dep_nodes: set[str] = {
        n for n, d in G_active.nodes(data=True)
        if d.get("node_type") in ("Repo", "ExternalRepo")
    }

    dep_edges: list[tuple[str, str]] = [
        (u, v) for u, v, d in G_active.edges(data=True)
        if d.get("edge_type") == "depends_on"
        and u in dep_nodes and v in dep_nodes
    ]

    G_u = nx.Graph()
    G_u.add_nodes_from(dep_nodes)
    G_u.add_edges_from(dep_edges)

    bridges: list[tuple[str, str]] = list(nx.bridges(G_u))

    logger.debug(
        "Bridge detection complete: %d bridges found in %d-node dependency subgraph.",
        len(bridges),
        len(dep_nodes),
    )

    return bridges
