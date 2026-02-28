"""
pg_atlas/metrics/adoption.py — A10: Adoption Signals Aggregation.

Translated from the validated prototype:
  06_demos/01_active_subgraph_prototype/build_notebook.py (Section 8)

Adoption signals (GitHub stars, forks, registry downloads) proxy the relevance
of a package in the ecosystem. Because purely ordinal rankings are invariant
under monotonic transformations, we compute direct percentile ranks on the raw
signals rather than log-transforming (mathematically redundant for percentiles).

Composite adoption score = mean(stars_pct, forks_pct, downloads_pct).

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import logging

import networkx as nx
import pandas as pd

logger = logging.getLogger(__name__)


def compute_adoption_scores(
    G_active: nx.DiGraph,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """
    Compute adoption percentile scores for all Repo and ExternalRepo nodes.

    Algorithm:
        1. Collect raw adoption signals (stars, forks, downloads) from node attrs.
           Missing signals default to 0.
        2. Compute percentile ranks on each raw signal (pandas rank(pct=True) × 100).
        3. Composite adoption score = mean of three percentile columns.
        4. Write adoption_score back to G_active node attributes.

    Args:
        G_active: Active subgraph from active_subgraph_projection().
                  Nodes of type 'Repo' or 'ExternalRepo' should carry 'stars',
                  'forks', and 'downloads' attributes (from ingestion enrichment
                  or the synthetic graph). Missing attributes default to 0.

    Returns:
        df_adopt:        pandas DataFrame with columns:
                            node, node_type, stars, forks, downloads,
                            stars_pct, forks_pct, downloads_pct, adoption_score
                         One row per Repo / ExternalRepo node.
        adoption_scores: Dict mapping node_id → composite adoption_score (float, 0–100).

    Notes:
        - percentile values are in [0.0, 100.0] for all three components and
          the composite score.
        - The composite score is the simple arithmetic mean of three component
          percentiles (equal weighting). This is intentional: we have no empirical
          basis yet to weight one signal over another.
        - adoption_score is written back to G_active.nodes[node]['adoption_score']
          as a side effect, enabling downstream gate evaluation without extra lookups.
        - Repos with all-zero signals (stars=0, forks=0, downloads=0) will cluster
          near the 0th percentile but will not be excluded.

    Reference:
        Prototype: build_notebook.py Section 8 (adoption signals computation).
    """
    adoption_records = []
    for node, data in G_active.nodes(data=True):
        if data.get("node_type") in ("Repo", "ExternalRepo"):
            adoption_records.append(
                {
                    "node": node,
                    "node_type": data.get("node_type"),
                    "stars": data.get("stars", 0) or 0,
                    "forks": data.get("forks", 0) or 0,
                    "downloads": data.get("downloads", 0) or 0,
                }
            )

    if not adoption_records:
        logger.warning(
            "compute_adoption_scores: no Repo or ExternalRepo nodes found in active subgraph."
        )
        return pd.DataFrame(), {}

    df_adopt = pd.DataFrame(adoption_records)

    # Percentile ranks: pandas rank(pct=True) returns proportions in (0, 1] → ×100
    df_adopt["stars_pct"] = df_adopt["stars"].rank(pct=True) * 100
    df_adopt["forks_pct"] = df_adopt["forks"].rank(pct=True) * 100
    df_adopt["downloads_pct"] = df_adopt["downloads"].rank(pct=True) * 100

    # Composite score: equal-weighted mean of three percentiles.
    df_adopt["adoption_score"] = df_adopt[
        ["stars_pct", "forks_pct", "downloads_pct"]
    ].mean(axis=1)

    # Write back to graph for downstream gate evaluation.
    adoption_scores: dict[str, float] = {}
    for _, row in df_adopt.iterrows():
        node_id = row["node"]
        score = float(row["adoption_score"])
        adoption_scores[node_id] = score
        if node_id in G_active.nodes:
            G_active.nodes[node_id]["adoption_score"] = score

    logger.debug(
        "Adoption scores computed for %d nodes. Mean score: %.1f.",
        len(adoption_scores),
        df_adopt["adoption_score"].mean(),
    )

    return df_adopt, adoption_scores
