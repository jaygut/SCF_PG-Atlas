"""
pg_atlas.graph — NetworkX graph construction and projection layer.

Modules:
    active_subgraph  — A6: Project the full graph onto active nodes only.
    builder          — Load the graph from CSV seed data or PostgreSQL.
    sync             — Delta update from PostgreSQL on re-ingestion (stub).

All graph objects are NetworkX DiGraphs with the multi-layer schema:
    Node types : Project, Repo, ExternalRepo, Contributor
    Edge types : belongs_to, depends_on, contributed_to
"""
