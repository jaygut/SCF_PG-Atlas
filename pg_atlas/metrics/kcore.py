"""
pg_atlas/metrics/kcore.py — K-Core Decomposition (Structural Skeleton).

Translated from the validated prototype:
  06_demos/01_active_subgraph_prototype/build_notebook.py (Section 6)

K-core decomposition reveals the nested shell structure of the dependency graph.
The k-core is the maximal subgraph where every node has at least k connections
to other nodes in the subgraph. Higher k = more deeply embedded in mutual
dependencies.

Why this matters for PG Atlas:
The innermost core (highest k) contains the packages most deeply woven into
the ecosystem — the ones that are both depended-upon AND depend on other core
packages. In ecological terms: the keystone species of the Stellar developer
ecosystem.

Note: K-core decomposition requires an undirected graph (mutual relationships).
We use the undirected version of the dependency subgraph.

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import logging

import networkx as nx

logger = logging.getLogger(__name__)


def kcore_analysis(
    G_active: nx.DiGraph,
) -> tuple[nx.Graph, dict[str, int]]:
    """
    Compute k-core decomposition of the active dependency graph.

    Algorithm:
        1. Extract the dependency subgraph (Repo + ExternalRepo nodes only,
           depends_on edges only).
        2. Convert to undirected graph (k-core requires symmetric connections).
        3. Copy node attributes from G_active to preserve metadata.
        4. Run NetworkX's core_number() to assign each node its k-core number.

    Args:
        G_active: Active subgraph from active_subgraph_projection().
                  Nodes must carry 'node_type' attribute.
                  Edges must carry 'edge_type' attribute.

    Returns:
        G_undirected: Undirected version of the dependency subgraph (nx.Graph).
                      Nodes carry all attributes from G_active.
        core_numbers: Dict mapping node_id → k-core number (int).
                      Higher k = more central in the structural skeleton.

    Notes:
        - Only 'depends_on' edges are considered (not 'belongs_to' or
          'contributed_to'). The k-core structure is a property of the
          package dependency topology, not the funding or contributor layers.
        - The maximum core number gives the size of the innermost structural
          skeleton. Nodes at max_core are the "keystone species" of the
          Stellar ecosystem.

    Reference:
        Prototype: build_notebook.py Section 6, kcore_analysis()
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

    G_undirected = nx.Graph()
    G_undirected.add_nodes_from(dep_nodes)
    G_undirected.add_edges_from(dep_edges)

    # Copy node attributes from the active graph.
    for n in dep_nodes:
        G_undirected.nodes[n].update(G_active.nodes[n])

    core_numbers: dict[str, int] = nx.core_number(G_undirected)

    max_core = max(core_numbers.values(), default=0)
    logger.debug(
        "K-core decomposition complete: %d nodes, max k = %d.",
        len(core_numbers),
        max_core,
    )

    return G_undirected, core_numbers
