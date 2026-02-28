"""
pg_atlas.viz — Interactive visualization components.

STUB MODULE — Agent Delta fills this in (D8/A12 contribution).

Planned modules:
    dashboard       — Streamlit interactive governance dashboard.
    plotly_graph    — Interactive force-directed Plotly dependency graph.
                      This is the D8 deliverable: a zoomable, filterable
                      graph visualization of the active dependency subgraph
                      with nodes colored by criticality and sized by adoption.

Depends on: pg_atlas.metrics (all modules), pg_atlas.metrics.gate (Agent Gamma).
"""

from pg_atlas.viz.figures import generate_all_figures
