"""
pg_atlas/reports/governance_report.py — Longitudinal Governance Instrument.

Captures complete ecosystem health snapshots and enables comparison across
SCF voting rounds to track whether investments reduce fragility over time.

Each run produces an EcosystemSnapshot that:
  - Answers the North Star question with data
  - Can be compared against previous snapshots (compare_snapshots)
  - Exports to a human-readable Markdown governance report

Author: Jay Gutierrez, PhD | SCF #41
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

import networkx as nx

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig

logger = logging.getLogger(__name__)


@dataclass
class EcosystemSnapshot:
    """
    Complete timestamped snapshot of ecosystem structural health.

    Each field captures a key dimension of the PG Atlas analysis, enabling
    longitudinal comparison across SCF funding rounds.
    """

    snapshot_date: str                      # ISO 8601 date string
    scf_round: Optional[str]               # e.g. "SCF Q2 2026"

    # Graph topology
    total_active_projects: int
    total_active_repos: int
    total_dependency_edges: int
    max_kcore: int
    bridge_edge_count: int

    # Health metrics (ecosystem-level)
    mean_hhi: float
    median_hhi: float
    pony_factor_rate: float                 # % repos with PF=1
    mean_criticality: float
    median_criticality: float

    # Gate results
    gate_pass_rate: float
    gate_borderline_count: int

    # Strategic surfaces
    maintenance_debt_surface_size: int
    keystone_contributor_count: int         # Contributors with KCI > 0

    # Top findings
    top_10_critical_packages: list          # [{name, criticality, pct, ecosystem}]
    top_5_keystone_contributors: list       # [{name, kci, repos, downstream}]
    funding_efficiency_summary: dict        # fer_tier distribution

    # North Star answer
    north_star_answer: str                  # Generated text answering the core question


def generate_north_star_answer(
    fer_results: list,
    mds_entries: list,
    kci_results: list,
    gate_results: list,
) -> str:
    """
    Generate the answer to: "Is the SCF investing proportionally to criticality?"

    Synthesizes FER distribution, MDS size, and gate pass rate into 2-3 sentences.

    Example:
    "Of 86 SCF-funded public goods projects, 23 are critically or underfunded relative
    to their structural ecosystem importance (FER > 1.3). The Maintenance Debt Surface
    contains 8 high-criticality projects with concentrated human capital and declining
    activity — these represent the highest-risk silent failures. The Metric Gate passes
    61% of projects for Expert Review."

    Args:
        fer_results:  List of FundingEfficiencyResult from compute_funding_efficiency().
        mds_entries:  List of MaintenanceDebtEntry from compute_maintenance_debt_surface().
        kci_results:  List of KeystoneContributorResult from compute_keystone_contributors().
        gate_results: List of MetricGateResult from evaluate_all_projects().

    Returns:
        2-3 sentence narrative string.
    """
    total_fer = len(fer_results)
    underfunded_count = sum(
        1 for r in fer_results
        if hasattr(r, "fer_tier") and r.fer_tier in ("critically_underfunded", "underfunded")
    )
    mds_count = len(mds_entries)
    gate_total = len(gate_results)
    gate_pass = sum(1 for r in gate_results if r.passed) if gate_results else 0
    gate_pass_pct = round(gate_pass / gate_total * 100) if gate_total > 0 else 0

    parts = []

    if total_fer > 0:
        parts.append(
            f"Of {total_fer} SCF-tracked public goods projects, {underfunded_count} are "
            f"critically or underfunded relative to their structural ecosystem importance "
            f"(FER > 1.3)."
        )
    else:
        parts.append("No funding efficiency data available for this snapshot.")

    if mds_count > 0:
        parts.append(
            f"The Maintenance Debt Surface contains {mds_count} high-criticality "
            f"{'project' if mds_count == 1 else 'projects'} with concentrated human capital "
            f"and declining activity — "
            f"{'this represents' if mds_count == 1 else 'these represent'} the highest-risk "
            f"silent failures."
        )
    else:
        parts.append(
            "No projects currently qualify for the Maintenance Debt Surface — "
            "a positive signal for ecosystem health."
        )

    if gate_total > 0:
        parts.append(
            f"The Metric Gate passes {gate_pass_pct}% of projects ({gate_pass}/{gate_total}) "
            f"for Expert Review."
        )

    return " ".join(parts)


def generate_governance_report(
    G_active: nx.DiGraph,
    gate_results: list,
    mds_entries: list,
    kci_results: list,
    fer_results: list,
    pony_results: dict,
    criticality_scores: dict,
    core_numbers: dict,
    bridges: list,
    config: PGAtlasConfig = DEFAULT_CONFIG,
    scf_round: Optional[str] = None,
    output_dir: str = "04_implementation/snapshots",
) -> "EcosystemSnapshot":
    """
    Generate a complete ecosystem snapshot and save to JSON.

    Aggregates all metric outputs into a single EcosystemSnapshot, writes it
    to a timestamped JSON file, and returns the snapshot for immediate use.

    Creates output_dir if it doesn't exist.
    Filename: {date}_{scf_round or 'snapshot'}.json

    Args:
        G_active:           Active subgraph from active_subgraph_projection().
        gate_results:       Output of evaluate_all_projects().
        mds_entries:        Output of compute_maintenance_debt_surface().
        kci_results:        Output of compute_keystone_contributors().
        fer_results:        Output of compute_funding_efficiency().
        pony_results:       Output of compute_pony_factors().
        criticality_scores: Output of compute_criticality_scores().
        core_numbers:       Output of kcore_analysis() — {node: k_number}.
        bridges:            Output of find_bridge_edges() — list of (u, v) tuples.
        config:             PGAtlasConfig.
        scf_round:          Optional SCF round label, e.g. "SCF Q2 2026".
        output_dir:         Directory path to write the JSON snapshot.

    Returns:
        EcosystemSnapshot with all fields populated.
    """
    snapshot_date = datetime.utcnow().strftime("%Y-%m-%d")

    # ── Graph topology ────────────────────────────────────────────────────────
    active_projects = {
        n for n, d in G_active.nodes(data=True)
        if d.get("node_type") == "Project"
    }
    active_repos = {
        n for n, d in G_active.nodes(data=True)
        if d.get("node_type") == "Repo" and d.get("active", False)
    }
    dep_edges = [
        (u, v) for u, v, d in G_active.edges(data=True)
        if d.get("edge_type") == "depends_on"
    ]
    max_kcore = max(core_numbers.values(), default=0) if core_numbers else 0
    bridge_count = len(bridges) if bridges else 0

    # ── Health metrics (ecosystem-level) ─────────────────────────────────────
    import statistics as _stats

    hhi_values = [r.hhi for r in pony_results.values()] if pony_results else []
    mean_hhi = round(_stats.mean(hhi_values), 1) if hhi_values else 0.0
    median_hhi = round(_stats.median(hhi_values), 1) if hhi_values else 0.0
    pony_flagged = sum(1 for r in pony_results.values() if r.pony_factor == 1)
    pony_rate = round(pony_flagged / len(pony_results), 4) if pony_results else 0.0

    crit_values = list(criticality_scores.values()) if criticality_scores else []
    mean_crit = round(_stats.mean(crit_values), 2) if crit_values else 0.0
    median_crit = round(_stats.median(crit_values), 2) if crit_values else 0.0

    # ── Gate metrics ──────────────────────────────────────────────────────────
    gate_pass = sum(1 for r in gate_results if r.passed) if gate_results else 0
    gate_total = len(gate_results)
    gate_pass_rate = round(gate_pass / gate_total, 4) if gate_total > 0 else 0.0
    gate_borderline = sum(1 for r in gate_results if r.borderline) if gate_results else 0

    # ── Strategic surfaces ────────────────────────────────────────────────────
    mds_size = len(mds_entries)
    kci_count = len(kci_results)

    # ── Top findings ──────────────────────────────────────────────────────────
    # Top 10 critical packages by criticality score
    from pg_atlas.metrics.criticality import compute_percentile_ranks
    crit_pcts = compute_percentile_ranks(criticality_scores) if criticality_scores else {}

    sorted_crit = sorted(
        ((node, score) for node, score in criticality_scores.items() if score > 0),
        key=lambda x: x[1],
        reverse=True,
    )[:10]
    top_10_critical = [
        {
            "name": node,
            "criticality": score,
            "pct": round(crit_pcts.get(node, 0.0), 1),
            "ecosystem": G_active.nodes[node].get("ecosystem", "unknown")
            if node in G_active.nodes else "unknown",
        }
        for node, score in sorted_crit
    ]

    # Top 5 keystone contributors
    top_5_kci = [
        {
            "name": r.contributor,
            "kci": r.kci_score,
            "repos": r.total_dominant_repos,
            "downstream": r.at_risk_downstream,
        }
        for r in kci_results[:5]
    ]

    # FER tier distribution
    from pg_atlas.metrics.funding_efficiency import fer_summary
    fer_dist = fer_summary(fer_results) if fer_results else {}

    # ── North Star answer ─────────────────────────────────────────────────────
    north_star = generate_north_star_answer(fer_results, mds_entries, kci_results, gate_results)

    snapshot = EcosystemSnapshot(
        snapshot_date=snapshot_date,
        scf_round=scf_round,
        total_active_projects=len(active_projects),
        total_active_repos=len(active_repos),
        total_dependency_edges=len(dep_edges),
        max_kcore=max_kcore,
        bridge_edge_count=bridge_count,
        mean_hhi=mean_hhi,
        median_hhi=median_hhi,
        pony_factor_rate=pony_rate,
        mean_criticality=mean_crit,
        median_criticality=median_crit,
        gate_pass_rate=gate_pass_rate,
        gate_borderline_count=gate_borderline,
        maintenance_debt_surface_size=mds_size,
        keystone_contributor_count=kci_count,
        top_10_critical_packages=top_10_critical,
        top_5_keystone_contributors=top_5_kci,
        funding_efficiency_summary=fer_dist,
        north_star_answer=north_star,
    )

    # ── Persist to JSON ───────────────────────────────────────────────────────
    os.makedirs(output_dir, exist_ok=True)
    round_slug = (scf_round or "snapshot").lower().replace(" ", "_")
    filename = f"{snapshot_date}_{round_slug}.json"
    filepath = os.path.join(output_dir, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(snapshot), f, indent=2, default=str)
        logger.info("Ecosystem snapshot saved to: %s", filepath)
    except OSError as e:
        logger.error("Failed to write snapshot to %s: %s", filepath, e)

    return snapshot


def compare_snapshots(
    snapshot_a: EcosystemSnapshot,
    snapshot_b: EcosystemSnapshot,
) -> dict:
    """
    Compute the delta between two ecosystem snapshots.

    Compares key health metrics between snapshot_a (earlier) and snapshot_b
    (later) to determine whether the ecosystem's fragility is improving or
    degrading over the measured period.

    Improvement criteria:
        - pony_factor_rate: decrease = improvement (less concentration)
        - mean_hhi: decrease = improvement
        - gate_pass_rate: increase = improvement
        - maintenance_debt_surface_size: decrease = improvement
        - keystone_contributor_count: decrease = improvement

    Args:
        snapshot_a: Earlier snapshot (the baseline).
        snapshot_b: Later snapshot (the comparison point).

    Returns:
        {
          'period': "{date_a} -> {date_b}",
          'metrics_improved': list of metric names that got better,
          'metrics_degraded': list of metric names that got worse,
          'pony_factor_rate_delta': float,    # negative = improvement
          'mean_hhi_delta': float,
          'gate_pass_rate_delta': float,
          'mds_size_delta': int,
          'keystone_count_delta': int,
          'fragility_trend': 'improving' | 'degrading' | 'stable',
          'narrative': str,
        }
    """
    pony_delta = snapshot_b.pony_factor_rate - snapshot_a.pony_factor_rate
    hhi_delta = snapshot_b.mean_hhi - snapshot_a.mean_hhi
    gate_delta = snapshot_b.gate_pass_rate - snapshot_a.gate_pass_rate
    mds_delta = snapshot_b.maintenance_debt_surface_size - snapshot_a.maintenance_debt_surface_size
    kci_delta = snapshot_b.keystone_contributor_count - snapshot_a.keystone_contributor_count

    improved: list[str] = []
    degraded: list[str] = []

    # pony_factor_rate: lower = better
    if pony_delta < -0.01:
        improved.append("pony_factor_rate")
    elif pony_delta > 0.01:
        degraded.append("pony_factor_rate")

    # mean_hhi: lower = better
    if hhi_delta < -50:
        improved.append("mean_hhi")
    elif hhi_delta > 50:
        degraded.append("mean_hhi")

    # gate_pass_rate: higher = better
    if gate_delta > 0.01:
        improved.append("gate_pass_rate")
    elif gate_delta < -0.01:
        degraded.append("gate_pass_rate")

    # mds_size: lower = better
    if mds_delta < 0:
        improved.append("maintenance_debt_surface_size")
    elif mds_delta > 0:
        degraded.append("maintenance_debt_surface_size")

    # keystone_count: lower = better
    if kci_delta < 0:
        improved.append("keystone_contributor_count")
    elif kci_delta > 0:
        degraded.append("keystone_contributor_count")

    # Determine overall trend
    if len(improved) > len(degraded):
        trend = "improving"
    elif len(degraded) > len(improved):
        trend = "degrading"
    else:
        trend = "stable"

    # Build narrative
    period = f"{snapshot_a.snapshot_date} -> {snapshot_b.snapshot_date}"
    if trend == "improving":
        narrative = (
            f"Between {period}, the Stellar public goods ecosystem shows improving "
            f"structural health: {len(improved)} metrics improved vs {len(degraded)} degraded. "
            f"Pony factor rate changed by {pony_delta:+.1%}; "
            f"gate pass rate changed by {gate_delta:+.1%}."
        )
    elif trend == "degrading":
        narrative = (
            f"Between {period}, the Stellar public goods ecosystem shows degrading "
            f"structural health: {len(degraded)} metrics worsened vs {len(improved)} improved. "
            f"The Maintenance Debt Surface {'grew' if mds_delta > 0 else 'shrank'} by "
            f"{abs(mds_delta)} entries. Immediate attention recommended."
        )
    else:
        narrative = (
            f"Between {period}, ecosystem structural health is stable: "
            f"{len(improved)} metrics improved and {len(degraded)} metrics degraded, "
            f"yielding no net directional change."
        )

    return {
        "period": period,
        "metrics_improved": improved,
        "metrics_degraded": degraded,
        "pony_factor_rate_delta": round(pony_delta, 4),
        "mean_hhi_delta": round(hhi_delta, 1),
        "gate_pass_rate_delta": round(gate_delta, 4),
        "mds_size_delta": mds_delta,
        "keystone_count_delta": kci_delta,
        "fragility_trend": trend,
        "narrative": narrative,
    }


def export_report_markdown(
    snapshot: EcosystemSnapshot,
    gate_results: list,
    mds_entries: list,
    kci_results: list,
    fer_results: list,
    output_path: str,
    figure_paths: "dict[str, str] | None" = None,
) -> str:
    """
    Export a complete human-readable Markdown governance report.

    Structure:
        # PG Atlas — Ecosystem Health Report
        **Date:** {date} | **SCF Round:** {round}

        ## Executive Summary
        {north_star_answer}

        ## Ecosystem Health Dashboard
        | Metric | Value |
        (table of key metrics)

        ## Maintenance Debt Surface (Priority Watchlist)
        (top entries with urgency narratives)

        ## Keystone Contributor Risk
        (top contributors with KCI and narrative)

        ## Funding Efficiency Analysis
        (FER tier distribution + top underfunded projects)

        ## Metric Gate Results
        (pass/fail summary + full audit for failed projects)

        ## Appendix: Full Metric Tables
        (complete tables for all metrics)

    Writes the file to output_path and returns the Markdown string.

    Args:
        snapshot:     EcosystemSnapshot from generate_governance_report().
        gate_results: List of MetricGateResult.
        mds_entries:  List of MaintenanceDebtEntry.
        kci_results:  List of KeystoneContributorResult.
        fer_results:  List of FundingEfficiencyResult.
        output_path:  Full path to the output .md file.

    Returns:
        The complete Markdown document as a string.
    """
    scf_round_label = snapshot.scf_round or "N/A"
    lines: list[str] = []

    # ── Title ─────────────────────────────────────────────────────────────────
    lines += [
        "# PG Atlas — Ecosystem Health Report",
        "",
        f"**Date:** {snapshot.snapshot_date} | **SCF Round:** {scf_round_label}",
        "",
        "---",
        "",
    ]

    # ── Executive Summary ─────────────────────────────────────────────────────
    lines += [
        "## Executive Summary",
        "",
        snapshot.north_star_answer,
        "",
    ]

    # ── Ecosystem Health Dashboard ────────────────────────────────────────────
    lines += [
        "## Ecosystem Health Dashboard",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Active Projects | {snapshot.total_active_projects} |",
        f"| Active Repos | {snapshot.total_active_repos} |",
        f"| Dependency Edges | {snapshot.total_dependency_edges} |",
        f"| Max K-Core | {snapshot.max_kcore} |",
        f"| Bridge Edges | {snapshot.bridge_edge_count} |",
        f"| Mean HHI | {snapshot.mean_hhi:.0f} |",
        f"| Median HHI | {snapshot.median_hhi:.0f} |",
        f"| Pony Factor Rate | {snapshot.pony_factor_rate:.1%} |",
        f"| Mean Criticality | {snapshot.mean_criticality:.2f} |",
        f"| Gate Pass Rate | {snapshot.gate_pass_rate:.1%} |",
        f"| Gate Borderline | {snapshot.gate_borderline_count} |",
        f"| Maintenance Debt Surface | {snapshot.maintenance_debt_surface_size} repos |",
        f"| Keystone Contributors | {snapshot.keystone_contributor_count} |",
        "",
    ]

    # ── Maintenance Debt Surface ──────────────────────────────────────────────
    lines += [
        "## Maintenance Debt Surface (Priority Watchlist)",
        "",
    ]
    if mds_entries:
        lines += [
            "These projects are in the top criticality quartile with high contributor "
            "concentration AND declining/stagnant activity — the highest-risk silent failures.",
            "",
        ]
        for entry in mds_entries[:10]:
            lines += [
                f"### {entry.project}",
                "",
                entry.urgency_narrative,
                "",
                f"- **Risk Score:** {entry.risk_score:.4f}",
                f"- **Criticality Percentile:** {entry.criticality_percentile:.0f}th",
                f"- **HHI:** {entry.hhi:.0f} ({entry.hhi_tier})",
                f"- **Commit Trend:** {entry.commit_trend} ({entry.days_since_last_commit} days since last commit)",
                "",
            ]
    else:
        lines += [
            "_No projects currently qualify for the Maintenance Debt Surface._",
            "",
        ]

    # ── Keystone Contributor Risk ─────────────────────────────────────────────
    lines += [
        "## Keystone Contributor Risk",
        "",
    ]
    if kci_results:
        lines += [
            "| Contributor | KCI Score | Dominant Repos | At-Risk Downstream |",
            "|-------------|-----------|----------------|--------------------|",
        ]
        for r in kci_results[:10]:
            lines.append(
                f"| {r.contributor} | {r.kci_score:.1f} | {r.total_dominant_repos} | "
                f"{r.at_risk_downstream} |"
            )
        lines.append("")
        lines.append("### Risk Narratives")
        lines.append("")
        for r in kci_results[:5]:
            lines += [f"**{r.contributor}:** {r.risk_narrative}", ""]
    else:
        lines += ["_No keystone contributors identified._", ""]

    # ── Funding Efficiency Analysis ───────────────────────────────────────────
    lines += [
        "## Funding Efficiency Analysis",
        "",
    ]
    if fer_results:
        fer_dist = snapshot.funding_efficiency_summary
        lines += [
            "| FER Tier | Count |",
            "|----------|-------|",
        ]
        for tier in [
            "critically_underfunded", "underfunded", "balanced",
            "overfunded", "significantly_overfunded", "unfunded"
        ]:
            count = fer_dist.get(tier, 0)
            if isinstance(count, int):
                lines.append(f"| {tier.replace('_', ' ').title()} | {count} |")
        lines.append("")

        # Top underfunded
        top_under = fer_dist.get("top_underfunded", [])
        if top_under:
            lines += [
                "### Top Underfunded Projects (FER > 2.0)",
                "",
                "| Project | FER | Criticality % | Funding % |",
                "|---------|-----|---------------|-----------|",
            ]
            for item in top_under:
                lines.append(
                    f"| {item['project']} | {item['fer']:.2f} | "
                    f"{item['criticality_pct']:.0f}th | {item['funding_pct']:.0f}th |"
                )
            lines.append("")

        # Full FER table (top 20)
        lines += [
            "### FER Narratives (Top Underfunded)",
            "",
        ]
        underfunded = [
            r for r in fer_results
            if hasattr(r, "fer_tier") and r.fer_tier in ("critically_underfunded", "underfunded")
        ]
        for r in underfunded[:5]:
            lines += [f"**{r.project}:** {r.narrative}", ""]
    else:
        lines += ["_No funding efficiency data available._", ""]

    # ── Metric Gate Results ───────────────────────────────────────────────────
    lines += [
        "## Metric Gate Results",
        "",
    ]
    if gate_results:
        passed_count = sum(1 for r in gate_results if r.passed)
        failed_count = len(gate_results) - passed_count
        borderline_count = sum(1 for r in gate_results if r.borderline)

        lines += [
            f"**Total:** {len(gate_results)} | **Passed:** {passed_count} | "
            f"**Failed:** {failed_count} | **Borderline:** {borderline_count}",
            f"**Gate Pass Rate:** {snapshot.gate_pass_rate:.1%}",
            "",
            "### Failed Projects (by Criticality)",
            "",
        ]
        failed = [r for r in gate_results if not r.passed]
        for r in failed[:10]:
            lines += [
                f"#### {r.project}",
                "",
                f"```",
                r.gate_explanation,
                f"```",
                "",
            ]

        if borderline_count > 0:
            lines += [
                "### Borderline Projects (Recommended for Human Review)",
                "",
            ]
            borderline = [r for r in gate_results if r.borderline]
            for r in borderline[:10]:
                lines += [f"- **{r.project}** — {r.signals_passed}/{r.signals_required} signals"]
            lines.append("")
    else:
        lines += ["_No gate results available._", ""]

    # ── Appendix: Full Metric Tables ──────────────────────────────────────────
    lines += [
        "## Appendix: Full Metric Tables",
        "",
        "### Top 10 Critical Packages",
        "",
        "| Package | Transitive Dependents | Criticality % | Ecosystem |",
        "|---------|----------------------|---------------|-----------|",
    ]
    for pkg in snapshot.top_10_critical_packages:
        lines.append(
            f"| {pkg['name']} | {pkg['criticality']} | {pkg['pct']:.0f}th | {pkg['ecosystem']} |"
        )
    lines.append("")

    # Full gate table
    lines += [
        "### Complete Gate Results",
        "",
        "| Project | Passed | Signals | Borderline |",
        "|---------|--------|---------|------------|",
    ]
    for r in gate_results:
        passed_label = "PASS" if r.passed else "FAIL"
        borderline_label = "Yes" if r.borderline else ""
        lines.append(
            f"| {r.project} | {passed_label} | {r.signals_passed}/{r.signals_required} | "
            f"{borderline_label} |"
        )
    lines.append("")

    # ── Visual Analysis (if figures were generated) ────────────────────────
    if figure_paths:
        report_dir = os.path.dirname(os.path.abspath(output_path))
        _rel = lambda abs_p: os.path.relpath(abs_p, report_dir)

        # Map filename prefixes to figure metadata
        _figure_map = {
            "fig1_": (
                "Contributor Concentration Distribution",
                "Distribution of top contributor commit share across all repos.",
                "contributor_health",
            ),
            "fig3_": (
                "Per-Repo Contributor Concentration",
                "Repos ranked by top contributor share; gold = >=70% pony-dominant.",
                "contributor_health",
            ),
            "fig6_": (
                "Maintenance Health Tiers",
                "Repos grouped by concentration risk tier (healthy/moderate/concentrated/critical).",
                "contributor_health",
            ),
            "fig2_": (
                "Layer 1 Metric Gate -- Pass Rate",
                f"{snapshot.gate_pass_rate:.0%} pass rate; {snapshot.gate_borderline_count} borderline repos for expert review.",
                "gate_adoption",
            ),
            "fig5_": (
                "GitHub Adoption Signals -- Stars vs Forks",
                "Stars vs. forks scatter coloured by gate pass/fail status.",
                "gate_adoption",
            ),
            "fig4_": (
                "Soroban Dependency Hub Bar Chart",
                "Reverse dependency count per core Soroban package.",
                "ecosystem",
            ),
            "net1_": (
                "Soroban Ecosystem Dependency Network",
                "Force-directed graph -- node size = dependent count, edge colour = target package.",
                "ecosystem",
            ),
            "net2_": (
                "Contributor-Repo Bipartite Network",
                "Edge colour = commit concentration risk; gold stars = cross-repo keystone contributors.",
                "ecosystem",
            ),
        }

        # Group figures by section
        contributor_figs = []
        gate_figs = []
        ecosystem_figs = []

        for fname, abs_path in sorted(figure_paths.items()):
            for prefix, (alt, caption, section) in _figure_map.items():
                if fname.startswith(prefix):
                    entry = (alt, caption, _rel(abs_path))
                    if section == "contributor_health":
                        contributor_figs.append(entry)
                    elif section == "gate_adoption":
                        gate_figs.append(entry)
                    elif section == "ecosystem":
                        ecosystem_figs.append(entry)
                    break

        lines += [
            "---",
            "",
            "## Visual Analysis",
            "",
            "*Generated figures from the PG Atlas pipeline. Paths are relative to this report file.*",
            "",
        ]

        if contributor_figs:
            lines += ["### Contributor Health & Maintenance Risk", ""]
            for alt, caption, rel_path in contributor_figs:
                lines += [
                    f"![{alt}]({rel_path})",
                    f"*{caption}*",
                    "",
                ]

        if gate_figs:
            lines += ["### Gate & Adoption Signals", ""]
            for alt, caption, rel_path in gate_figs:
                lines += [
                    f"![{alt}]({rel_path})",
                    f"*{caption}*",
                    "",
                ]

        if ecosystem_figs:
            lines += ["### Ecosystem Structure", ""]
            for alt, caption, rel_path in ecosystem_figs:
                lines += [
                    f"![{alt}]({rel_path})",
                    f"*{caption}*",
                    "",
                ]

    lines += [
        "---",
        "",
        "_Report generated by PG Atlas — SCF #41 Building the Backbone_",
        f"_Author: Jay Gutierrez, PhD_",
        "",
    ]

    markdown = "\n".join(lines)

    # Write to file
    try:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        logger.info("Governance report exported to: %s", output_path)
    except OSError as e:
        logger.error("Failed to write report to %s: %s", output_path, e)

    return markdown
