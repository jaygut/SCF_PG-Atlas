"""
pg_atlas.storage — PostgreSQL persistence layer.

STUB MODULE — To be implemented once Alex Olieman's A2 schema is locked.

Planned modules:
    schema    — PostgreSQL DDL + migration helpers (Alex interface).
    postgres  — psycopg2 connection layer and query helpers.

Critical blocker: A2 (PostgreSQL schema, owned by Alex Olieman) must be
locked before production storage code can be written. Until then, all
graph operations use the CSV builder (pg_atlas.graph.builder.build_graph_from_csv).
"""
