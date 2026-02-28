"""
pg_atlas/metrics/maintenance_debt.py — Tier 3 Strategic Metric.

The Maintenance Debt Surface: projects that satisfy all THREE conditions:
  (1) Criticality in top quartile (high structural importance)
  (2) HHI >= mds_hhi_min (high contributor concentration = fragile human capital)
  (3) Commit trend is 'declining' or 'stagnant' (activity is fading)

These are the projects that will fail quietly — not with a dramatic shutdown,
but by gradually becoming too stale to safely depend on.

This surface is the most urgent output PG Atlas can produce for the SCF.

Author: Jay Gutierrez, PhD | SCF #41
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
import numpy as np

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig
from pg_atlas.metrics.criticality import compute_percentile_ranks

logger = logging.getLogger(__name__)


@dataclass
class MaintenanceDebtEntry:
    """
    A single entry on the Maintenance Debt Surface.

    A repo qualifies if ALL THREE conditions are met:
      (1) criticality_pct >= config.mds_criticality_quartile
      (2) hhi >= config.mds_hhi_min
      (3) commit_trend in ('stagnant', 'declining')

    Fields:
        project:                Parent project name (from node 'project' attr).
        criticality_percentile: Criticality percentile rank within PG Atlas universe.
        hhi:                    Herfindahl-Hirschman Index for the repo.
        hhi_tier:               'concentrated' | 'critical'
        commit_trend:           'declining' | 'stagnant' | 'stable'
        days_since_last_commit: Days since last recorded commit.
        transitive_dependents:  Raw transitive dependent count (criticality score).
        top_contributor:        Dominant contributor name/ID.
        top_contributor_share:  Fraction of commits by top contributor.
        risk_score:             (criticality_pct/100) * (hhi/10000), normalized.
        urgency_narrative:      Full human-readable escalation message.
    """

    project: str
    criticality_percentile: float
    hhi: float
    hhi_tier: str
    commit_trend: str
    days_since_last_commit: int
    transitive_dependents: int
    top_contributor: str
    top_contributor_share: float
    risk_score: float
    urgency_narrative: str


def classify_commit_trend(
    days_since_commit: int,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> str:
    """
    Classify activity trend from days_since_commit.

    Thresholds:
        < 14 days   → 'active'
        14–45 days  → 'stable'
        45–89 days  → 'stagnant'  (still within window but slowing)
        >= 89 days  → 'declining' (approaching or at dormancy threshold)

    Note: In production with real git history, this would compare commit
    velocity in last 30d vs prior 60d. For now uses days_since_commit proxy.

    Args:
        days_since_commit: Days since the last recorded commit on the repo.
        config:            PGAtlasConfig (reserved for future velocity-based thresholds).

    Returns:
        Trend classification string: 'active' | 'stable' | 'stagnant' | 'declining'.
    """
    if days_since_commit < 14:
        return "active"
    elif days_since_commit < 45:
        return "stable"
    elif days_since_commit < 89:
        return "stagnant"
    else:
        return "declining"


def generate_mds_narrative(entry: MaintenanceDebtEntry) -> str:
    """
    Generate urgency narrative for a Maintenance Debt Surface entry.

    Template:
        "{project} is in the {X}th criticality percentile — {N} packages
        transitively depend on it. Its primary maintainer ({contributor}) accounts for
        {share:.0%} of commits (HHI: {hhi:.0f} — {tier} concentration). Activity is
        {trend}: last commit was {days} days ago. This project is at elevated risk of
        silent failure."

    Args:
        entry: MaintenanceDebtEntry (all fields populated except urgency_narrative).

    Returns:
        Human-readable urgency narrative string.
    """
    pct_ordinal = f"{entry.criticality_percentile:.0f}th"
    return (
        f"{entry.project} is in the {pct_ordinal} criticality percentile — "
        f"{entry.transitive_dependents} packages transitively depend on it. "
        f"Its primary maintainer ({entry.top_contributor}) accounts for "
        f"{entry.top_contributor_share:.0%} of commits "
        f"(HHI: {entry.hhi:.0f} — {entry.hhi_tier} concentration). "
        f"Activity is {entry.commit_trend}: last commit was "
        f"{entry.days_since_last_commit} days ago. "
        f"This project is at elevated risk of silent failure."
    )


def compute_maintenance_debt_surface(
    G_active: nx.DiGraph,
    criticality_scores: dict[str, int],
    pony_results: dict,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> list[MaintenanceDebtEntry]:
    """
    Identify the Maintenance Debt Surface.

    A repo qualifies if ALL THREE conditions are met:
      (1) criticality_pct >= config.mds_criticality_quartile (top quartile)
      (2) hhi >= config.mds_hhi_min (high concentration)
      (3) commit_trend in ('stagnant', 'declining')

    This operates at the REPO level (each Repo is evaluated independently).

    Algorithm:
        1. Compute criticality percentile ranks from criticality_scores.
        2. For each active Repo node, check all three conditions using node
           attributes (days_since_commit) and pony_results (hhi, contributor data).
        3. Build MaintenanceDebtEntry for qualifying nodes.
        4. Compute risk_score = (criticality_pct/100) * (hhi/10000).
        5. Sort by risk_score descending.

    Args:
        G_active:           Active subgraph from active_subgraph_projection().
        criticality_scores: Output of compute_criticality_scores().
        pony_results:       Output of compute_pony_factors() — maps repo → ContributorRiskResult.
        config:             PGAtlasConfig with MDS thresholds.

    Returns:
        List of MaintenanceDebtEntry sorted by risk_score descending (highest risk first).
    """
    # ── Step 1: Compute criticality percentile ranks ──────────────────────────
    percentile_ranks = compute_percentile_ranks(criticality_scores)

    entries: list[MaintenanceDebtEntry] = []

    # ── Step 2: Check conditions for each active Repo ─────────────────────────
    for node, data in G_active.nodes(data=True):
        if data.get("node_type") != "Repo":
            continue

        # Skip if no criticality data
        if node not in criticality_scores:
            continue

        crit_pct = percentile_ranks.get(node, 0.0)
        crit_raw = criticality_scores[node]

        # Condition 1: criticality in top quartile
        if crit_pct < config.mds_criticality_quartile:
            continue

        # Need pony/HHI data — skip if not available
        if node not in pony_results:
            continue

        pony_result = pony_results[node]
        hhi = pony_result.hhi

        # Condition 2: high contributor concentration
        if hhi < config.mds_hhi_min:
            continue

        # Condition 3: declining or stagnant activity
        days_since = data.get("days_since_commit", 0)
        trend = classify_commit_trend(days_since, config)

        if trend not in ("stagnant", "declining"):
            continue

        # ── Determine HHI tier ────────────────────────────────────────────────
        if hhi >= config.hhi_critical:
            hhi_tier = "critical"
        else:
            hhi_tier = "concentrated"

        # ── Compute risk score ────────────────────────────────────────────────
        risk_score = (crit_pct / 100.0) * (hhi / 10_000.0)

        # ── Build partial entry to generate narrative ─────────────────────────
        project_name = data.get("project", node)
        entry = MaintenanceDebtEntry(
            project=project_name,
            criticality_percentile=round(crit_pct, 1),
            hhi=hhi,
            hhi_tier=hhi_tier,
            commit_trend=trend,
            days_since_last_commit=int(days_since),
            transitive_dependents=crit_raw,
            top_contributor=pony_result.top_contributor,
            top_contributor_share=pony_result.top_contributor_share,
            risk_score=round(risk_score, 4),
            urgency_narrative="",  # placeholder — filled below
        )
        entry.urgency_narrative = generate_mds_narrative(entry)
        entries.append(entry)

    # ── Step 5: Sort by risk_score descending ─────────────────────────────────
    entries.sort(key=lambda e: e.risk_score, reverse=True)

    logger.info(
        "Maintenance Debt Surface: %d qualifying repos identified "
        "(criticality >= %.0fth pct, HHI >= %.0f, trend stagnant/declining).",
        len(entries),
        config.mds_criticality_quartile,
        config.mds_hhi_min,
    )
    return entries


def mds_summary(entries: list[MaintenanceDebtEntry]) -> dict:
    """
    Compute a summary of the Maintenance Debt Surface.

    Returns:
        {
          'total': int,
          'top_entries': list of top 5 as dicts,
          'critical_hhi_count': int,   # HHI tier == 'critical' (HHI > 5000)
          'declining_count': int,      # commit_trend == 'declining'
        }

    Args:
        entries: List of MaintenanceDebtEntry from compute_maintenance_debt_surface().

    Returns:
        Summary dict.
    """
    return {
        "total": len(entries),
        "top_entries": [
            {
                "project": e.project,
                "criticality_percentile": e.criticality_percentile,
                "hhi": e.hhi,
                "hhi_tier": e.hhi_tier,
                "commit_trend": e.commit_trend,
                "days_since_last_commit": e.days_since_last_commit,
                "risk_score": e.risk_score,
            }
            for e in entries[:5]
        ],
        "critical_hhi_count": sum(1 for e in entries if e.hhi_tier == "critical"),
        "declining_count": sum(1 for e in entries if e.commit_trend == "declining"),
    }
