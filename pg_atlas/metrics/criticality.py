"""
pg_atlas/metrics/criticality.py — A9: Criticality Score (BFS cascade).

Translated from the validated prototype:
  06_demos/01_active_subgraph_prototype/build_notebook.py (Section 5)

The flagship metric. A package is critical not because many things directly
depend on it, but because many active packages *transitively* depend on it —
removing it would cascade across the entire dependent tree.

Algorithm: BFS on the reversed dependency graph.
The dependency graph has edges pointing *toward* dependencies (A → B means
"A depends on B"). To count dependents, we reverse the graph and run BFS
from each package — the set of nodes reachable from P in the reversed graph
is exactly the set of packages that (transitively) depend on P.

This is the software-ecosystem equivalent of trophic cascade modeling:
removing a keystone package cascades the same way removing a keystone
species collapses a food web.

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import logging

import networkx as nx
import numpy as np

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig

logger = logging.getLogger(__name__)


def compute_criticality_scores(G_active: nx.DiGraph) -> dict[str, int]:
    """
    Compute transitive active dependent count for every Repo and ExternalRepo node.

    Algorithm:
        1. Extract the dependency subgraph (only 'depends_on' edges between
           Repo and ExternalRepo nodes).
        2. Reverse the dependency subgraph so edges point from depended-upon
           packages *toward* their dependents.
        3. For each package P, count all nodes reachable from P in the reversed
           graph that are marked active — these are the active transitive dependents.

    Args:
        G_active: Active subgraph from active_subgraph_projection().
                  Nodes must carry 'node_type' and 'active' attributes.
                  Edges must carry 'edge_type' attribute.

    Returns:
        criticality: Dict mapping node_id → transitive active dependent count (int).
                     Nodes with no dependents score 0.

    Complexity:
        O(V × (V + E)) worst case. Practical performance is much faster due to
        power-law degree distribution (most nodes are leaves with trivial BFS).

    Reference:
        Prototype: build_notebook.py Section 5, compute_criticality_scores()
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

    G_dep = nx.DiGraph()
    G_dep.add_nodes_from(dep_nodes)
    G_dep.add_edges_from(dep_edges)

    # Reverse: edges now flow FROM depended-upon package TO its dependents.
    G_rev = G_dep.reverse(copy=True)

    criticality: dict[str, int] = {}
    for node in dep_nodes:
        transitive_dependents = nx.descendants(G_rev, node)
        active_dependents = {
            n for n in transitive_dependents
            if G_active.nodes[n].get("active", False)
        }
        criticality[node] = len(active_dependents)

    logger.debug(
        "Criticality computed for %d nodes. Max score: %d.",
        len(criticality),
        max(criticality.values(), default=0),
    )
    return criticality


def compute_decay_criticality(
    G_active: nx.DiGraph,
    base_criticality: dict[str, int],
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> dict[str, float]:
    """
    Temporal-decay weighted criticality score (Tier 2 extension).

    Each transitive dependent contributes exp(-days_since_commit / halflife)
    weight rather than a flat 1.0 count:
        - Dependent committed yesterday → weight ≈ 1.0
        - Dependent committed 30 days ago → weight = exp(-1) ≈ 0.37
        - Dependent committed 90 days ago → weight = exp(-3) ≈ 0.05

    This rewards packages that are depended on by *recently active* projects
    and discounts dependencies from projects that are fading into dormancy.

    Args:
        G_active:         Active subgraph from active_subgraph_projection().
        base_criticality: Output of compute_criticality_scores() (used only to
                          share the dep_nodes set for efficiency; not actually
                          applied as weights here).
        config:           PGAtlasConfig. Uses config.decay_halflife_days.

    Returns:
        decay_criticality: Dict mapping node_id → decay-weighted score (float).
                           Values are always <= the corresponding base criticality.

    Reference:
        Prototype: build_notebook.py Section 5, compute_decay_criticality()
    """
    halflife: float = config.decay_halflife_days

    dep_nodes: set[str] = {
        n for n, d in G_active.nodes(data=True)
        if d.get("node_type") in ("Repo", "ExternalRepo")
    }

    dep_edges: list[tuple[str, str]] = [
        (u, v) for u, v, d in G_active.edges(data=True)
        if d.get("edge_type") == "depends_on"
        and u in dep_nodes and v in dep_nodes
    ]

    G_dep = nx.DiGraph()
    G_dep.add_nodes_from(dep_nodes)
    G_dep.add_edges_from(dep_edges)
    G_rev = G_dep.reverse(copy=True)

    decay_criticality: dict[str, float] = {}
    for node in dep_nodes:
        transitive_dependents = nx.descendants(G_rev, node)
        active_dependents = {
            n for n in transitive_dependents
            if G_active.nodes[n].get("active", False)
        }
        score = sum(
            np.exp(
                -G_active.nodes[n].get("days_since_commit", 0) / halflife
            )
            for n in active_dependents
        )
        decay_criticality[node] = round(float(score), 3)

    return decay_criticality


def compute_percentile_ranks(
    scores: dict[str, int | float],
) -> dict[str, float]:
    """
    Convert raw criticality scores to percentile ranks within [0, 100].

    Uses numpy searchsorted on the sorted score array, which is equivalent
    to the proportion of scores strictly below a given value (exclusive rank).
    This matches the prototype's implementation.

    Args:
        scores: Dict mapping node_id → raw score (int or float).

    Returns:
        percentiles: Dict mapping node_id → percentile rank in [0.0, 100.0].

    Notes:
        - Nodes with the minimum score receive 0th percentile.
        - Nodes with the maximum score receive a percentile < 100
          (equal to (n-1)/n × 100) because searchsorted uses the exclusive rank.
        - All output values are guaranteed to be in [0, 100].

    Reference:
        Prototype: build_notebook.py Section 5 (inline percentile computation).
    """
    if not scores:
        return {}

    all_scores = np.array(list(scores.values()), dtype=float)
    sorted_scores = np.sort(all_scores)
    n = len(sorted_scores)

    percentiles: dict[str, float] = {}
    for node, score in scores.items():
        rank = int(np.searchsorted(sorted_scores, score))
        percentiles[node] = rank / n * 100.0

    return percentiles
