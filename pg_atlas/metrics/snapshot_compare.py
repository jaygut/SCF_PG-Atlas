"""
pg_atlas/metrics/snapshot_compare.py — Longitudinal delta analytics.

Compares EcosystemSnapshot JSON objects across SCF funding rounds to track
whether investments are reducing fragility over time.

Provides:
    - SnapshotDelta dataclass: structured delta between two snapshots
    - compare_snapshots(): compute all deltas from two snapshot dicts
    - generate_comparison_report(): Markdown round-over-round report
    - generate_trend_figure(): multi-panel matplotlib trend chart

Author: Jay Gutierrez, PhD | SCF #41
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SnapshotDelta:
    """Structured delta between two EcosystemSnapshot JSON objects."""

    snapshot_a_date: str
    snapshot_b_date: str
    scf_round_a: str
    scf_round_b: str
    # Gate health (positive delta = improving)
    gate_pass_rate_delta: float
    gate_borderline_count_delta: int
    # Maintenance risk (negative delta = improving)
    pony_factor_rate_delta: float
    mean_hhi_delta: float
    median_hhi_delta: float
    maintenance_debt_surface_delta: int
    # Graph size
    active_repos_delta: int
    active_projects_delta: int
    total_dependency_edges_delta: int
    bridge_edge_count_delta: int
    # Contributors
    keystone_contributor_delta: int
    # Narrative
    summary_narrative: str


def compare_snapshots(snap_a: dict, snap_b: dict) -> SnapshotDelta:
    """
    Compute all deltas between two EcosystemSnapshot dicts (snap_b - snap_a).

    Args:
        snap_a: Earlier snapshot dict (baseline).
        snap_b: Later snapshot dict (comparison point).

    Returns:
        SnapshotDelta with all field deltas and auto-generated narrative.
    """
    gate_delta = snap_b["gate_pass_rate"] - snap_a["gate_pass_rate"]
    hhi_delta = snap_b["mean_hhi"] - snap_a["mean_hhi"]
    pony_delta = snap_b["pony_factor_rate"] - snap_a["pony_factor_rate"]
    mds_delta = (
        snap_b["maintenance_debt_surface_size"]
        - snap_a["maintenance_debt_surface_size"]
    )

    # Build summary narrative
    round_a = snap_a.get("scf_round") or snap_a["snapshot_date"]
    round_b = snap_b.get("scf_round") or snap_b["snapshot_date"]
    parts = []

    if gate_delta > 0:
        parts.append(
            f"Gate pass rate improved by +{gate_delta * 100:.1f}pp."
        )
    elif gate_delta < 0:
        parts.append(
            f"Gate pass rate declined by {gate_delta * 100:.1f}pp."
        )
    else:
        parts.append("Gate pass rate unchanged.")

    if hhi_delta < 0:
        parts.append(
            f"Mean HHI declined by {abs(hhi_delta):.0f} points (lower concentration)."
        )
    elif hhi_delta > 0:
        parts.append(
            f"Mean HHI increased by {hhi_delta:.0f} points (higher concentration risk)."
        )

    if pony_delta < 0:
        parts.append(
            f"Pony factor rate declined by {abs(pony_delta) * 100:.1f}pp (improving)."
        )
    elif pony_delta > 0:
        parts.append(
            f"Pony factor rate increased by {pony_delta * 100:.1f}pp (worsening)."
        )

    if mds_delta > 0:
        parts.append(
            f"The Maintenance Debt Surface grew by {mds_delta} "
            f"{'entry' if mds_delta == 1 else 'entries'}, requiring attention."
        )
    elif mds_delta < 0:
        parts.append(
            f"The Maintenance Debt Surface shrank by {abs(mds_delta)} "
            f"{'entry' if abs(mds_delta) == 1 else 'entries'}."
        )

    narrative = f"Between {round_a} and {round_b}, " + " ".join(parts)

    return SnapshotDelta(
        snapshot_a_date=snap_a["snapshot_date"],
        snapshot_b_date=snap_b["snapshot_date"],
        scf_round_a=round_a,
        scf_round_b=round_b,
        gate_pass_rate_delta=gate_delta,
        gate_borderline_count_delta=(
            snap_b["gate_borderline_count"] - snap_a["gate_borderline_count"]
        ),
        pony_factor_rate_delta=pony_delta,
        mean_hhi_delta=hhi_delta,
        median_hhi_delta=snap_b["median_hhi"] - snap_a["median_hhi"],
        maintenance_debt_surface_delta=mds_delta,
        active_repos_delta=(
            snap_b["total_active_repos"] - snap_a["total_active_repos"]
        ),
        active_projects_delta=(
            snap_b["total_active_projects"] - snap_a["total_active_projects"]
        ),
        total_dependency_edges_delta=(
            snap_b["total_dependency_edges"] - snap_a["total_dependency_edges"]
        ),
        bridge_edge_count_delta=(
            snap_b["bridge_edge_count"] - snap_a["bridge_edge_count"]
        ),
        keystone_contributor_delta=(
            snap_b["keystone_contributor_count"]
            - snap_a["keystone_contributor_count"]
        ),
        summary_narrative=narrative,
    )


def _format_direction(delta: float, lower_is_better: bool = False) -> str:
    """Return arrow indicator for delta direction."""
    if delta == 0:
        return "--"
    if lower_is_better:
        return "\u2193 (improving)" if delta < 0 else "\u2191 (worsening)"
    return "\u2191 (improving)" if delta > 0 else "\u2193 (worsening)"


def generate_comparison_report(
    delta: SnapshotDelta,
    snap_a: dict,
    snap_b: dict,
    output_path: str,
) -> str:
    """
    Write a Markdown round-over-round comparison report.

    Args:
        delta:       SnapshotDelta from compare_snapshots().
        snap_a:      Earlier snapshot dict.
        snap_b:      Later snapshot dict.
        output_path: Path to write the .md file.

    Returns:
        output_path after writing.
    """
    round_a = snap_a.get("scf_round") or snap_a["snapshot_date"]
    round_b = snap_b.get("scf_round") or snap_b["snapshot_date"]
    today = datetime.now().strftime("%Y-%m-%d")

    lines = [
        "# PG Atlas \u2014 Round-over-Round Comparison",
        "",
        f"**{round_a} \u2192 {round_b}**",
        f"Generated: {today}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        delta.summary_narrative,
        "",
        "## Key Metric Deltas",
        "",
        f"| Metric | {round_a} | {round_b} | Delta | Direction |",
        "|--------|---------|---------|-------|-----------|",
        (
            f"| Gate Pass Rate | {snap_a['gate_pass_rate']:.1%} "
            f"| {snap_b['gate_pass_rate']:.1%} "
            f"| {delta.gate_pass_rate_delta:+.1%} "
            f"| {_format_direction(delta.gate_pass_rate_delta)} |"
        ),
        (
            f"| Mean HHI | {snap_a['mean_hhi']:.0f} "
            f"| {snap_b['mean_hhi']:.0f} "
            f"| {delta.mean_hhi_delta:+.0f} "
            f"| {_format_direction(delta.mean_hhi_delta, lower_is_better=True)} |"
        ),
        (
            f"| Pony Factor Rate | {snap_a['pony_factor_rate']:.1%} "
            f"| {snap_b['pony_factor_rate']:.1%} "
            f"| {delta.pony_factor_rate_delta:+.1%} "
            f"| {_format_direction(delta.pony_factor_rate_delta, lower_is_better=True)} |"
        ),
        (
            f"| Active Repos | {snap_a['total_active_repos']} "
            f"| {snap_b['total_active_repos']} "
            f"| {delta.active_repos_delta:+d} "
            f"| {_format_direction(delta.active_repos_delta)} |"
        ),
        (
            f"| Bridge Edges | {snap_a['bridge_edge_count']} "
            f"| {snap_b['bridge_edge_count']} "
            f"| {delta.bridge_edge_count_delta:+d} "
            f"| {_format_direction(delta.bridge_edge_count_delta, lower_is_better=True)} |"
        ),
        (
            f"| MDS Entries | {snap_a['maintenance_debt_surface_size']} "
            f"| {snap_b['maintenance_debt_surface_size']} "
            f"| {delta.maintenance_debt_surface_delta:+d} "
            f"| {_format_direction(delta.maintenance_debt_surface_delta, lower_is_better=True)} |"
        ),
        "",
    ]

    # Top Critical Packages — snap_a
    lines += [
        f"## Top Critical Packages \u2014 {round_a}",
        "",
    ]
    top_a = snap_a.get("top_10_critical_packages", [])
    if top_a:
        lines += [
            "| Package | Dependents | Percentile | Ecosystem |",
            "|---------|-----------|------------|-----------|",
        ]
        for pkg in top_a:
            lines.append(
                f"| {pkg['name']} | {pkg['criticality']} "
                f"| {pkg['pct']:.0f}th | {pkg.get('ecosystem', 'unknown')} |"
            )
        lines.append("")
    else:
        lines += ["_No critical packages recorded._", ""]

    # Top Critical Packages — snap_b
    lines += [
        f"## Top Critical Packages \u2014 {round_b}",
        "",
    ]
    top_b = snap_b.get("top_10_critical_packages", [])
    if top_b:
        lines += [
            "| Package | Dependents | Percentile | Ecosystem |",
            "|---------|-----------|------------|-----------|",
        ]
        for pkg in top_b:
            lines.append(
                f"| {pkg['name']} | {pkg['criticality']} "
                f"| {pkg['pct']:.0f}th | {pkg.get('ecosystem', 'unknown')} |"
            )
        lines.append("")
    else:
        lines += ["_No critical packages recorded._", ""]

    # Top Keystone Contributors — snap_b
    lines += [
        f"## Top Keystone Contributors \u2014 {round_b}",
        "",
    ]
    top_kci = snap_b.get("top_5_keystone_contributors", [])
    if top_kci:
        lines += [
            "| Contributor | KCI | Dominant Repos | At-Risk Downstream |",
            "|-------------|-----|----------------|--------------------|",
        ]
        for c in top_kci:
            lines.append(
                f"| {c['name']} | {c['kci']:.1f} "
                f"| {c['repos']} | {c['downstream']} |"
            )
        lines.append("")
    else:
        lines += ["_No keystone contributors identified._", ""]

    lines += [
        "---",
        "",
        "_Report generated by PG Atlas \u2014 SCF #41 Building the Backbone_",
        "",
    ]

    markdown = "\n".join(lines)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown)
    logger.info("Comparison report saved to: %s", output_path)

    return output_path


def generate_trend_figure(
    snapshots: list,
    output_path: str,
) -> str:
    """
    Generate a 3-panel trend figure from a list of snapshot dicts.

    Panels:
        1. Gate Pass Rate (%) — teal line
        2. Pony Factor Rate (%) — coral line (lower is better)
        3. Mean HHI — amber line (lower is better)

    Args:
        snapshots: List of EcosystemSnapshot dicts (chronological order).
        output_path: Path to save the PNG figure.

    Returns:
        output_path after saving.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bg_color = "#0D1B2A"
    teal = "#00C8D4"
    coral = "#FF6B47"
    amber = "#F2B134"

    x_labels = [
        s.get("scf_round") or s["snapshot_date"] for s in snapshots
    ]
    gate_rates = [s["gate_pass_rate"] * 100 for s in snapshots]
    pony_rates = [s["pony_factor_rate"] * 100 for s in snapshots]
    mean_hhis = [s["mean_hhi"] for s in snapshots]

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), facecolor=bg_color)

    panel_configs = [
        (axes[0], gate_rates, teal, "Gate Pass Rate (%)"),
        (axes[1], pony_rates, coral, "Pony Factor Rate (%) \u2014 lower is better"),
        (axes[2], mean_hhis, amber, "Mean HHI \u2014 lower is better"),
    ]

    xs = list(range(len(snapshots)))

    for ax, values, color, title in panel_configs:
        ax.set_facecolor(bg_color)
        ax.plot(xs, values, color=color, linewidth=2, zorder=3)
        ax.scatter(xs, values, s=80, color=color, edgecolors="white",
                   linewidths=0.8, zorder=4)

        if len(snapshots) == 1:
            ax.annotate(
                "Baseline", (xs[0], values[0]),
                textcoords="offset points", xytext=(10, 10),
                color="white", fontsize=9,
            )

        ax.set_title(title, color="white", fontsize=12, pad=8)
        ax.set_xticks(xs)
        ax.set_xticklabels(x_labels, rotation=30, ha="right", color="white",
                           fontsize=9)
        ax.tick_params(axis="y", colors="white")
        ax.grid(True, color="white", alpha=0.2, linewidth=0.5)
        for spine in ax.spines.values():
            spine.set_color("white")
            spine.set_alpha(0.3)

    fig.suptitle(
        "PG Atlas \u2014 Ecosystem Health Trend\nSCF Longitudinal Governance Instrument",
        color="white", fontsize=14, fontweight="bold", y=0.98,
    )
    fig.text(
        0.02, 0.01, "PG Atlas \u00b7 SCF #41",
        color="white", alpha=0.4, fontsize=8,
    )

    plt.tight_layout(rect=[0, 0.03, 1, 0.94])

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=150, facecolor=bg_color,
                bbox_inches="tight")
    plt.close(fig)
    logger.info("Trend figure saved to: %s", output_path)

    return output_path
