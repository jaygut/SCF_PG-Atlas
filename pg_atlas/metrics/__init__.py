"""
pg_atlas.metrics — Graph metric computation pipeline.

Modules:
    criticality    — A9: BFS transitive dependent count + temporal decay.
    pony_factor    — A9: Binary pony factor + HHI + Shannon entropy.
    adoption       — A10: Download/star/fork percentile composite score.
    kcore          — K-core decomposition (structural skeleton).
    bridges        — Bridge edge detection (single points of failure).

All metrics operate on the active subgraph returned by
pg_atlas.graph.active_subgraph.active_subgraph_projection().

All thresholds and gate parameters live in pg_atlas.config.PGAtlasConfig.
"""
