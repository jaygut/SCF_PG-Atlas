"""
pg_atlas/viz/dashboard.py — Streamlit dashboard for PG Atlas.

Four-page analytics dashboard for the SCF governance instrument.

Pages:
    1. Ecosystem Overview  — active graph stats + gate pass/fail summary
    2. Maintenance Debt    — MDS table sorted by risk_score
    3. Metric Gate         — full gate results with audit narratives
    4. Funding Efficiency  — FER scatter + underfunded critical list

Usage:
    streamlit run pg_atlas/viz/dashboard.py

Note: Requires streamlit and plotly. Stub is importable without them.

Author: Jay Gutierrez, PhD | SCF #41
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Optional Streamlit dependency ──────────────────────────────────────────────
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    st = None
    HAS_STREAMLIT = False

# ── Optional Plotly dependency ─────────────────────────────────────────────────
try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    go = None
    HAS_PLOTLY = False


def _render_ecosystem_overview(snapshot, gate_results: list) -> None:
    """
    Render Page 1: Ecosystem Overview.

    Shows active graph statistics and gate pass/fail summary table.

    Args:
        snapshot:     EcosystemSnapshot from generate_governance_report().
        gate_results: List of MetricGateResult.
    """
    st.header("Ecosystem Overview")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Active Projects", snapshot.total_active_projects)
    col2.metric("Active Repos", snapshot.total_active_repos)
    col3.metric("Dependency Edges", snapshot.total_dependency_edges)
    col4.metric("Max K-Core", snapshot.max_kcore)

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("Bridge Edges", snapshot.bridge_edge_count)
    col6.metric("Mean HHI", f"{snapshot.mean_hhi:.0f}")
    col7.metric("Pony Factor Rate", f"{snapshot.pony_factor_rate:.1%}")
    col8.metric("Gate Pass Rate", f"{snapshot.gate_pass_rate:.1%}")

    st.subheader("North Star Answer")
    st.info(snapshot.north_star_answer)

    if gate_results:
        st.subheader("Gate Summary")
        passed = sum(1 for r in gate_results if r.passed)
        failed = len(gate_results) - passed
        borderline = sum(1 for r in gate_results if r.borderline)

        if HAS_PLOTLY:
            fig = go.Figure(
                data=[
                    go.Bar(
                        x=["Passed", "Failed", "Borderline"],
                        y=[passed, failed, borderline],
                        marker_color=["green", "red", "orange"],
                    )
                ],
                layout=go.Layout(title="Gate Results", yaxis_title="Count"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.write(f"Passed: {passed}, Failed: {failed}, Borderline: {borderline}")


def _render_maintenance_debt(mds_entries: list) -> None:
    """
    Render Page 2: Maintenance Debt Surface.

    Shows the MDS table sorted by risk_score descending.

    Args:
        mds_entries: List of MaintenanceDebtEntry.
    """
    st.header("Maintenance Debt Surface")
    st.caption(
        "Projects in the top criticality quartile with high contributor concentration "
        "AND declining/stagnant activity — the highest-risk silent failures."
    )

    if not mds_entries:
        st.success("No projects currently qualify for the Maintenance Debt Surface.")
        return

    import pandas as pd

    rows = [
        {
            "Project": e.project,
            "Criticality %ile": f"{e.criticality_percentile:.0f}th",
            "HHI": f"{e.hhi:.0f}",
            "HHI Tier": e.hhi_tier,
            "Commit Trend": e.commit_trend,
            "Days Since Commit": e.days_since_last_commit,
            "Risk Score": f"{e.risk_score:.4f}",
        }
        for e in mds_entries
    ]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    st.subheader("Urgency Narratives (Top 5)")
    for entry in mds_entries[:5]:
        with st.expander(f"{entry.project} — Risk Score: {entry.risk_score:.4f}"):
            st.warning(entry.urgency_narrative)


def _render_metric_gate(gate_results: list) -> None:
    """
    Render Page 3: Metric Gate Results.

    Shows full gate results with audit narratives, failed projects first.

    Args:
        gate_results: List of MetricGateResult.
    """
    st.header("Metric Gate Results")

    if not gate_results:
        st.info("No gate results available.")
        return

    passed = sum(1 for r in gate_results if r.passed)
    failed = len(gate_results) - passed
    borderline = sum(1 for r in gate_results if r.borderline)

    col1, col2, col3 = st.columns(3)
    col1.metric("Passed", passed)
    col2.metric("Failed", failed)
    col3.metric("Borderline", borderline)

    # Failed projects
    failed_results = [r for r in gate_results if not r.passed]
    if failed_results:
        st.subheader("Failed Projects (Priority Review)")
        for r in failed_results:
            with st.expander(f"[FAIL] {r.project} — {r.signals_passed}/{r.signals_required} signals"):
                st.code(r.gate_explanation)

    # Borderline projects
    borderline_results = [r for r in gate_results if r.borderline]
    if borderline_results:
        st.subheader("Borderline Projects (Recommended for Human Review)")
        for r in borderline_results:
            with st.expander(f"[BORDERLINE] {r.project}"):
                st.code(r.gate_explanation)

    # All passed projects
    passed_results = [r for r in gate_results if r.passed and not r.borderline]
    if passed_results:
        st.subheader("Passed Projects")
        import pandas as pd
        rows = [
            {
                "Project": r.project,
                "Signals": f"{r.signals_passed}/{r.signals_required}",
                "Criticality": "PASS" if r.criticality.passed else "FAIL",
                "Pony Factor": "PASS" if r.pony_factor.passed else "FAIL",
                "Adoption": "PASS" if r.adoption.passed else "FAIL",
            }
            for r in passed_results
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)


def _render_funding_efficiency(fer_results: list) -> None:
    """
    Render Page 4: Funding Efficiency Analysis.

    Shows FER tier distribution and underfunded critical infrastructure list.

    Args:
        fer_results: List of FundingEfficiencyResult.
    """
    st.header("Funding Efficiency Analysis")
    st.caption(
        "Funding Efficiency Ratio (FER) = criticality_percentile / funding_percentile. "
        "FER > 1.3 = underfunded relative to structural ecosystem importance."
    )

    if not fer_results:
        st.info("No funding efficiency data available.")
        return

    # Tier counts
    tier_counts = {}
    for r in fer_results:
        tier = getattr(r, "fer_tier", "unknown")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Critically Underfunded",
        tier_counts.get("critically_underfunded", 0),
    )
    col2.metric("Underfunded", tier_counts.get("underfunded", 0))
    col3.metric("Unfunded", tier_counts.get("unfunded", 0))

    # FER tier bar chart
    if HAS_PLOTLY:
        tiers = [
            "critically_underfunded", "underfunded", "balanced",
            "overfunded", "significantly_overfunded", "unfunded",
        ]
        counts = [tier_counts.get(t, 0) for t in tiers]
        tier_labels = [t.replace("_", " ").title() for t in tiers]
        tier_colors = ["red", "orangered", "green", "cornflowerblue", "steelblue", "gray"]

        fig = go.Figure(
            data=[go.Bar(x=tier_labels, y=counts, marker_color=tier_colors)],
            layout=go.Layout(title="FER Tier Distribution", yaxis_title="Count"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # Underfunded projects table
    underfunded = [
        r for r in fer_results
        if getattr(r, "fer_tier", "") in ("critically_underfunded", "underfunded")
    ]
    if underfunded:
        st.subheader("Underfunded Critical Infrastructure")
        import pandas as pd

        rows = [
            {
                "Project": r.project,
                "FER": f"{r.fer:.2f}" if r.fer is not None else "N/A",
                "FER Tier": r.fer_tier,
                "Criticality %ile": f"{r.criticality_pct:.0f}th",
                "Funding %ile": f"{r.funding_pct:.0f}th",
                "Narrative": r.narrative,
            }
            for r in underfunded
        ]
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
    else:
        st.success("No underfunded critical infrastructure detected.")


def run_dashboard(
    snapshot=None,
    gate_results: Optional[list] = None,
    mds_entries: Optional[list] = None,
    fer_results: Optional[list] = None,
) -> None:
    """
    Launch the PG Atlas Streamlit dashboard.

    Four-page dashboard with sidebar navigation. Renders ecosystem overview,
    maintenance debt surface, metric gate results, and funding efficiency.

    Args:
        snapshot:     EcosystemSnapshot (if None, shows placeholder).
        gate_results: List of MetricGateResult.
        mds_entries:  List of MaintenanceDebtEntry.
        fer_results:  List of FundingEfficiencyResult.

    Raises:
        ImportError: If streamlit is not installed.
    """
    if not HAS_STREAMLIT:
        raise ImportError("streamlit is required: pip install streamlit")

    gate_results = gate_results or []
    mds_entries = mds_entries or []
    fer_results = fer_results or []

    st.set_page_config(
        page_title="PG Atlas — SCF Governance Dashboard",
        page_icon="",
        layout="wide",
    )

    st.title("PG Atlas — SCF Public Goods Governance Dashboard")
    st.caption("Layer 1 Metric Gate for the Stellar Community Fund")

    page = st.sidebar.selectbox(
        "Navigate",
        [
            "Ecosystem Overview",
            "Maintenance Debt",
            "Metric Gate",
            "Funding Efficiency",
        ],
    )

    if snapshot is None:
        st.warning(
            "No ecosystem snapshot provided. Run generate_governance_report() first."
        )
        return

    if page == "Ecosystem Overview":
        _render_ecosystem_overview(snapshot, gate_results)
    elif page == "Maintenance Debt":
        _render_maintenance_debt(mds_entries)
    elif page == "Metric Gate":
        _render_metric_gate(gate_results)
    elif page == "Funding Efficiency":
        _render_funding_efficiency(fer_results)


if __name__ == "__main__":
    # When run via `streamlit run dashboard.py`, execute with placeholder data.
    run_dashboard()
