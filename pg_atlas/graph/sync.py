"""
pg_atlas/graph/sync.py — Delta update from PostgreSQL on re-ingestion.

STUB: Implements the graph sync interface but returns G unchanged until
Alex Olieman's A2 PostgreSQL schema is locked and available.

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import logging
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)


def sync_graph_delta(
    G: nx.DiGraph,
    conn: Any,
    since_timestamp: str,
) -> nx.DiGraph:
    """
    Incrementally update the in-memory graph with changes from PostgreSQL.

    STUB: Logs a warning and returns G unchanged.

    When Alex's schema (A2/D5) is locked, this function should:
        1. Query repos modified since `since_timestamp`
        2. Update node attributes (days_since_commit, stars, etc.)
        3. Add/remove dependency edges changed since last sync
        4. Add new contributor edges from the git log parser
        5. Re-run active_subgraph_projection on the updated graph

    Args:
        G:               Current in-memory graph (nx.DiGraph).
        conn:            psycopg2 / asyncpg connection to the PG Atlas database.
        since_timestamp: ISO 8601 timestamp string — only sync changes after this.

    Returns:
        G: The graph unchanged (stub behavior).
    """
    logger.warning(
        "sync_graph_delta called but PostgreSQL schema (A2) is not yet locked. "
        "Graph returned unchanged. since_timestamp='%s'.",
        since_timestamp,
    )
    return G
