"""
pg_atlas/viz/plotly_graph.py — Interactive Plotly force-directed graph.

Generates an interactive HTML/Plotly visualization of the PG Atlas active subgraph.

Visual encoding:
    - Node size:   Proportional to criticality score (log scale, clamped [5, 40])
    - Node color:  K-core number (viridis scale: yellow=peripheral, purple=core)
    - Red border:  Pony Factor = 1 (single-contributor concentration risk)
    - Amber (orange) border: Bridge edge endpoint
    - Edge color:  Gray for depends_on, blue for contributed_to, green for belongs_to
    - Hover:       Project name, criticality score, HHI, days_since_commit, k-core

Author: Jay Gutierrez, PhD | SCF #41
"""

import logging
import math
from math import sqrt
from typing import Optional

import networkx as nx

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig

logger = logging.getLogger(__name__)

# ── Optional Plotly dependency ─────────────────────────────────────────────────
try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    go = None
    HAS_PLOTLY = False

# ── Edge type visual config ────────────────────────────────────────────────────
_EDGE_COLORS = {
    "depends_on": "rgba(150, 150, 150, 0.4)",
    "contributed_to": "rgba(70, 130, 200, 0.5)",
    "belongs_to": "rgba(60, 180, 80, 0.5)",
}
_EDGE_WIDTHS = {
    "depends_on": 1,
    "contributed_to": 1.5,
    "belongs_to": 1.5,
}
_NODE_COLORS_BY_TYPE = {
    "Repo": "steelblue",
    "ExternalRepo": "mediumpurple",
    "Contributor": "coral",
    "Project": "gold",
}


def _compute_layout(
    G: nx.Graph,
    seed: int = 42,
) -> dict[str, tuple[float, float]]:
    """
    Compute spring layout positions for all nodes in G.

    Uses nx.spring_layout with k=2/sqrt(N+1) to give a visually balanced
    force-directed layout that scales with graph size.

    Args:
        G:    NetworkX graph (directed or undirected) to compute layout for.
        seed: Random seed for reproducibility.

    Returns:
        Dict mapping node_id → (x, y) coordinate tuple.
    """
    k_value = 2.0 / sqrt(len(G.nodes) + 1)
    pos = nx.spring_layout(G, seed=seed, k=k_value)
    return {node: (float(x), float(y)) for node, (x, y) in pos.items()}


def build_plotly_figure(
    G_active: nx.DiGraph,
    criticality_scores: dict[str, int],
    pony_results: dict,
    kcore_numbers: dict[str, int],
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> "go.Figure":
    """
    Build an interactive Plotly force-directed graph of the active subgraph.

    Visual encoding:
        - Node size:   max(5, min(40, 5 + log1p(criticality) * 8))
        - Node color:  k-core number via viridis colorscale
        - Node border: red if pony_factor==1, white otherwise
        - Edge color:  by edge_type (gray/blue/green)
        - Hover text:  node_id, node_type, criticality, HHI, days_since_commit, k-core

    Args:
        G_active:            Active subgraph from active_subgraph_projection().
        criticality_scores:  Output of compute_criticality_scores().
        pony_results:        Output of compute_pony_factors() — maps repo → ContributorRiskResult.
        kcore_numbers:       Dict mapping node → k-core number.
        config:              PGAtlasConfig (reserved for future threshold coloring).

    Returns:
        Plotly Figure object (no IO, no files written).

    Raises:
        ImportError: If plotly is not installed.
    """
    if not HAS_PLOTLY:
        raise ImportError("plotly is required: pip install plotly")

    pos = _compute_layout(G_active, seed=42)

    # ── Build edge traces grouped by edge type ────────────────────────────────
    edge_traces = []
    edge_groups: dict[str, list[tuple]] = {}

    for u, v, data in G_active.edges(data=True):
        etype = data.get("edge_type", "depends_on")
        if etype not in edge_groups:
            edge_groups[etype] = []
        edge_groups[etype].append((u, v))

    for etype, edges in edge_groups.items():
        x_coords = []
        y_coords = []
        for u, v in edges:
            if u not in pos or v not in pos:
                continue
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            x_coords += [x0, x1, None]
            y_coords += [y0, y1, None]

        color = _EDGE_COLORS.get(etype, "rgba(150,150,150,0.3)")
        width = _EDGE_WIDTHS.get(etype, 1)

        trace = go.Scatter(
            x=x_coords,
            y=y_coords,
            mode="lines",
            line={"width": width, "color": color},
            name=etype,
            legendgroup=f"edge_{etype}",
            showlegend=True,
            hoverinfo="none",
        )
        edge_traces.append(trace)

    # ── Build node traces grouped by node type ────────────────────────────────
    node_traces = []
    node_type_groups: dict[str, list[str]] = {}

    for node in G_active.nodes():
        ntype = G_active.nodes[node].get("node_type", "Unknown")
        if ntype not in node_type_groups:
            node_type_groups[ntype] = []
        node_type_groups[ntype].append(node)

    for ntype, nodes in node_type_groups.items():
        x_coords = []
        y_coords = []
        sizes = []
        colors = []
        border_colors = []
        hover_texts = []

        for node in nodes:
            if node not in pos:
                continue

            x, y = pos[node]
            x_coords.append(x)
            y_coords.append(y)

            # Node size: log scale of criticality, clamped [5, 40]
            crit = criticality_scores.get(node, 0)
            size = max(5, min(40, 5 + math.log1p(crit) * 8))
            sizes.append(size)

            # Node color: k-core number
            kcore = kcore_numbers.get(node, 0)
            colors.append(kcore)

            # Border: red if pony_factor=1
            pony_result = pony_results.get(node)
            if pony_result is not None and pony_result.pony_factor == 1:
                border_colors.append("red")
            else:
                border_colors.append("white")

            # Hover text
            node_data = G_active.nodes[node]
            hhi_val = pony_result.hhi if pony_result is not None else "N/A"
            days = node_data.get("days_since_commit", "N/A")
            hover = (
                f"<b>{node}</b><br>"
                f"Type: {ntype}<br>"
                f"Criticality: {crit}<br>"
                f"HHI: {hhi_val}<br>"
                f"Days since commit: {days}<br>"
                f"K-core: {kcore}"
            )
            hover_texts.append(hover)

        if not x_coords:
            continue

        trace = go.Scatter(
            x=x_coords,
            y=y_coords,
            mode="markers",
            name=ntype,
            marker={
                "size": sizes,
                "color": colors,
                "colorscale": "Viridis",
                "showscale": True if ntype == "Repo" else False,
                "colorbar": {"title": "K-Core"} if ntype == "Repo" else None,
                "line": {
                    "color": border_colors,
                    "width": 2,
                },
            },
            text=hover_texts,
            hovertemplate="%{text}<extra></extra>",
            legendgroup=f"node_{ntype}",
            showlegend=True,
        )
        node_traces.append(trace)

    # ── Assemble figure ───────────────────────────────────────────────────────
    all_traces = edge_traces + node_traces

    fig = go.Figure(
        data=all_traces,
        layout=go.Layout(
            title="PG Atlas — Active Dependency Graph",
            showlegend=True,
            hovermode="closest",
            xaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            yaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            margin={"l": 20, "r": 20, "t": 60, "b": 20},
            paper_bgcolor="white",
            plot_bgcolor="white",
        ),
    )

    logger.info(
        "Plotly figure built: %d nodes, %d edges, %d traces.",
        G_active.number_of_nodes(),
        G_active.number_of_edges(),
        len(all_traces),
    )
    return fig


def save_figure_html(
    fig: "go.Figure",
    output_path: str,
) -> None:
    """
    Write a Plotly figure to a self-contained HTML file.

    Args:
        fig:         Plotly Figure object from build_plotly_figure().
        output_path: Full path to the output .html file.

    Raises:
        ImportError: If plotly is not installed.
    """
    if not HAS_PLOTLY:
        raise ImportError("plotly is required: pip install plotly")

    fig.write_html(output_path, include_plotlyjs="cdn")
    logger.info("Plotly figure saved to: %s", output_path)


def build_summary_charts(
    gate_results: list,
    mds_entries: list,
    fer_results: list,
) -> "dict[str, go.Figure]":
    """
    Build a set of standalone Plotly summary charts for the dashboard.

    Returns:
        {
            'gate_funnel': Bar chart showing pass/fail breakdown by signal.
            'mds_scatter': Scatter plot of criticality_pct vs HHI colored by commit_trend.
            'fer_bar':     Horizontal bar chart of top 10 underfunded projects by FER score.
        }

    Args:
        gate_results: List of MetricGateResult from evaluate_all_projects().
        mds_entries:  List of MaintenanceDebtEntry from compute_maintenance_debt_surface().
        fer_results:  List of FundingEfficiencyResult from compute_funding_efficiency().

    Returns:
        Dict of figure name → Plotly Figure.

    Raises:
        ImportError: If plotly is not installed.
    """
    if not HAS_PLOTLY:
        raise ImportError("plotly is required: pip install plotly")

    charts = {}

    # ── Gate Funnel ───────────────────────────────────────────────────────────
    if gate_results:
        passed = sum(1 for r in gate_results if r.passed)
        failed = len(gate_results) - passed
        crit_pass = sum(1 for r in gate_results if r.criticality.passed)
        pony_pass = sum(1 for r in gate_results if r.pony_factor.passed)
        adopt_pass = sum(1 for r in gate_results if r.adoption.passed)

        gate_fig = go.Figure(
            data=[
                go.Bar(
                    x=["Total", "Criticality Pass", "Pony Pass", "Adoption Pass", "Gate Pass", "Gate Fail"],
                    y=[len(gate_results), crit_pass, pony_pass, adopt_pass, passed, failed],
                    marker_color=["steelblue", "cornflowerblue", "cornflowerblue", "cornflowerblue", "green", "red"],
                )
            ],
            layout=go.Layout(
                title="Metric Gate — Signal Pass Breakdown",
                xaxis_title="Signal",
                yaxis_title="Count",
            ),
        )
        charts["gate_funnel"] = gate_fig
    else:
        charts["gate_funnel"] = go.Figure(layout=go.Layout(title="Metric Gate (no data)"))

    # ── MDS Scatter ───────────────────────────────────────────────────────────
    if mds_entries:
        crit_pcts = [e.criticality_percentile for e in mds_entries]
        hhis = [e.hhi for e in mds_entries]
        trends = [e.commit_trend for e in mds_entries]
        projects = [e.project for e in mds_entries]

        trend_colors = {"stagnant": "orange", "declining": "red", "stable": "green", "active": "blue"}
        colors = [trend_colors.get(t, "gray") for t in trends]

        mds_fig = go.Figure(
            data=[
                go.Scatter(
                    x=crit_pcts,
                    y=hhis,
                    mode="markers",
                    marker={"color": colors, "size": 12, "opacity": 0.8},
                    text=[f"{p}<br>Trend: {t}" for p, t in zip(projects, trends)],
                    hovertemplate="%{text}<extra></extra>",
                )
            ],
            layout=go.Layout(
                title="Maintenance Debt Surface — Criticality vs HHI",
                xaxis_title="Criticality Percentile",
                yaxis_title="HHI",
            ),
        )
        charts["mds_scatter"] = mds_fig
    else:
        charts["mds_scatter"] = go.Figure(layout=go.Layout(title="MDS (no data)"))

    # ── FER Bar ───────────────────────────────────────────────────────────────
    underfunded = [
        r for r in fer_results
        if hasattr(r, "fer_tier") and r.fer_tier in ("critically_underfunded", "underfunded")
    ][:10]

    if underfunded:
        # Sort by FER descending
        underfunded.sort(key=lambda r: (r.fer if r.fer is not None else 0), reverse=True)
        projects = [r.project for r in underfunded]
        fers = [r.fer if r.fer is not None else 0 for r in underfunded]

        fer_fig = go.Figure(
            data=[
                go.Bar(
                    x=fers,
                    y=projects,
                    orientation="h",
                    marker_color="orangered",
                )
            ],
            layout=go.Layout(
                title="Top Underfunded Projects by FER Score",
                xaxis_title="FER Score",
                yaxis_title="Project",
                yaxis={"autorange": "reversed"},
            ),
        )
        charts["fer_bar"] = fer_fig
    else:
        charts["fer_bar"] = go.Figure(layout=go.Layout(title="FER (no underfunded data)"))

    return charts
