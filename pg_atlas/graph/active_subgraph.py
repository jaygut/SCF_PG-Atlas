"""
pg_atlas/graph/active_subgraph.py — A6: Active Subgraph Projection.

Translates the validated prototype algorithm from:
  06_demos/01_active_subgraph_prototype/build_notebook.py (Section 4)

This is the prerequisite step for every downstream metric. The raw dependency
graph contains dormant repos — projects that received SCF funding but have
since gone quiet. Including them in criticality scoring would inflate scores
for packages they depend on even though those packages no longer serve active
downstream users.

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import logging
import networkx as nx

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig

logger = logging.getLogger(__name__)


def active_subgraph_projection(
    G: nx.DiGraph,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> tuple[nx.DiGraph, set]:
    """
    Project the full multi-layer dependency graph onto active nodes only.

    Algorithm (O(V + E)):
        1. Classify every node as active or dormant:
           - Project nodes: always retained (funding/strategy layer).
           - Contributor nodes: always retained (contributor graph layer).
           - Repo / ExternalRepo nodes: active iff
               days_since_commit <= config.active_window_days
               AND NOT archived.
        2. Build the induced subgraph over the active node set.
        3. Annotate the resulting graph with audit metadata:
               G_active.graph['active_window_days']
               G_active.graph['nodes_retained']
               G_active.graph['nodes_removed']
               G_active.graph['dormant_nodes']   (list, for audit trail)

    Args:
        G:      Full multi-layer directed graph (NetworkX DiGraph).
                Nodes must carry 'node_type', 'days_since_commit', and
                optionally 'archived' attributes.
        config: PGAtlasConfig instance. Uses config.active_window_days
                to determine the dormancy threshold.

    Returns:
        G_active:      Induced subgraph over active nodes (nx.DiGraph).
        dormant_nodes: Set of node IDs that were pruned from the graph.

    Notes:
        - The returned graph is a *copy* of the induced subgraph.
          Mutations to G_active do not affect the original G.
        - All edge attributes (edge_type, commits, confidence, etc.) are
          preserved in the induced subgraph.
        - Project and Contributor nodes are retained unconditionally so
          that the funding layer and contributor risk layer remain intact
          even when all of a project's repos are dormant.

    Reference:
        NORTH_STAR.md — "Active Subgraph Threshold" design rationale.
        Prototype: build_notebook.py Section 4, active_subgraph_projection()
    """
    active_window_days: int = config.active_window_days

    active_nodes: set = set()
    dormant_nodes: set = set()

    for node, data in G.nodes(data=True):
        node_type = data.get("node_type", "")

        if node_type in ("Project", "Contributor"):
            # Always retain: funding layer and contributor graph are not filtered.
            active_nodes.add(node)

        elif node_type in ("Repo", "ExternalRepo"):
            days = data.get("days_since_commit")
            archived = data.get("archived", False)

            if days is None:
                if node_type == "ExternalRepo":
                    # ExternalRepo nodes represent external ecosystem dependencies
                    # (e.g. Soroban core crates). A7 never parses them because
                    # they are not SCF submission repos. Retain them so that
                    # dep-graph metrics (criticality, k-core, bridges) can
                    # traverse the full dependency structure.
                    active_nodes.add(node)
                else:
                    # Repo with no A7 data yet — treat as dormant conservatively.
                    dormant_nodes.add(node)
                continue

            if days <= active_window_days and not archived:
                active_nodes.add(node)
            else:
                dormant_nodes.add(node)

        else:
            # Unknown node type: retain conservatively and log a warning.
            logger.warning(
                "Unknown node_type '%s' on node '%s' — retaining in active subgraph.",
                node_type,
                node,
            )
            active_nodes.add(node)

    # Build the induced subgraph (copy preserves all node/edge attributes).
    G_active: nx.DiGraph = G.subgraph(active_nodes).copy()

    # Annotate for audit trail.
    G_active.graph["active_window_days"] = active_window_days
    G_active.graph["nodes_retained"] = len(active_nodes)
    G_active.graph["nodes_removed"] = len(dormant_nodes)
    G_active.graph["dormant_nodes"] = list(dormant_nodes)

    logger.info(
        "Active subgraph projection complete: %d nodes retained, %d dormant pruned "
        "(window=%d days).",
        len(active_nodes),
        len(dormant_nodes),
        active_window_days,
    )

    return G_active, dormant_nodes
