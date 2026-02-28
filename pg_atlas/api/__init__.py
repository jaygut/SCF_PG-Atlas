"""
pg_atlas.api — FastAPI analytics endpoints.

STUB MODULE — Agent Delta fills this in (D7/A11 contribution).

Planned modules:
    endpoints — FastAPI analytics endpoints exposing:
        GET /projects/{title}/metrics  — Full metric profile for a project.
        GET /projects/gate             — Layer 1 gate results for all projects.
        GET /ecosystem/criticality     — Top N critical packages.
        GET /ecosystem/maintenance-debt — MDS watch list.
        GET /ecosystem/graph           — Serialized graph for visualization.

All endpoints read from the in-memory graph or PostgreSQL (once A2 ships).
Depends on: pg_atlas.metrics (all modules), pg_atlas.metrics.gate (Agent Gamma).
"""
