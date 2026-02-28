"""
pg_atlas/metrics/funding_efficiency.py — Tier 3 Strategic Metric.

Funding Efficiency Ratio: criticality_percentile / funding_percentile.

This is the strategic metric that answers the North Star question:
"Is the SCF investing maintenance resources proportionally to structural
ecosystem criticality — and if not, where are the gaps?"

FER > 1.5 → underfunded critical infrastructure (PG Award priority)
FER ~= 1.0 → funding matches criticality (well-calibrated)
FER < 0.5 → overfunded relative to criticality (may warrant review)

Author: Jay Gutierrez, PhD | SCF #41
"""

import logging
from dataclasses import dataclass
from typing import Optional

import networkx as nx
import numpy as np
import pandas as pd

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig
from pg_atlas.metrics.criticality import compute_percentile_ranks

logger = logging.getLogger(__name__)


@dataclass
class FundingEfficiencyResult:
    """
    Funding Efficiency Ratio result for a single project.

    Fields:
        project:          Project name.
        criticality_raw:  Aggregate criticality score (sum across all repos).
        criticality_pct:  Criticality percentile within PG Atlas universe.
        funding_usd:      Total USD awarded to this project.
        funding_pct:      Funding percentile within PG Atlas universe.
        fer:              FER = criticality_pct / funding_pct. None if funding_usd == 0.
        fer_tier:         'critically_underfunded' | 'underfunded' | 'balanced' |
                          'overfunded' | 'significantly_overfunded' | 'unfunded'
        pony_flag:        True if any repo in this project has pony_factor == 1.
        pony_risk_repos:  Count of repos with pony_factor == 1.
        narrative:        Human-readable explanation of the FER result.
    """

    project: str
    criticality_raw: float
    criticality_pct: float
    funding_usd: float
    funding_pct: float
    fer: Optional[float]
    fer_tier: str
    pony_flag: bool
    pony_risk_repos: int
    narrative: str


def compute_fer_tier(fer: Optional[float]) -> str:
    """
    Map FER value to a descriptive tier string.

    Tier boundaries:
        None         → 'unfunded'             (funding_usd == 0)
        fer > 2.0    → 'critically_underfunded'
        fer > 1.3    → 'underfunded'
        fer > 0.7    → 'balanced'
        fer > 0.4    → 'overfunded'
        fer <= 0.4   → 'significantly_overfunded'

    Args:
        fer: Funding Efficiency Ratio value, or None if the project has no funding.

    Returns:
        Tier label string.
    """
    if fer is None:
        return "unfunded"
    elif fer > 2.0:
        return "critically_underfunded"
    elif fer > 1.3:
        return "underfunded"
    elif fer > 0.7:
        return "balanced"
    elif fer > 0.4:
        return "overfunded"
    else:
        return "significantly_overfunded"


def generate_fer_narrative(result: FundingEfficiencyResult) -> str:
    """
    Generate a human-readable narrative for a FER result.

    Examples:
        Critically underfunded:
            "This project is in the 87th criticality percentile but only the
             23rd funding percentile (FER=3.78) — a critically underfunded
             load-bearing package."
        Balanced:
            "Funding is well-calibrated to structural importance (FER=0.95)."
        Overfunded:
            "This project receives above-average funding (64th percentile) relative
             to its structural criticality (28th percentile, FER=0.44)."
        Unfunded:
            "This project has received no SCF funding to date. Its structural
             criticality (Xth percentile) may warrant consideration."

    Args:
        result: FundingEfficiencyResult with all fields populated except narrative.

    Returns:
        Human-readable narrative string.
    """
    tier = result.fer_tier
    crit_pct_int = int(round(result.criticality_pct))
    fund_pct_int = int(round(result.funding_pct))
    fer_val = result.fer

    if tier == "unfunded":
        return (
            f"This project has received no SCF funding to date. "
            f"Its structural criticality ({crit_pct_int}th percentile) "
            f"may warrant consideration."
        )
    elif tier == "critically_underfunded":
        return (
            f"This project is in the {crit_pct_int}th criticality percentile "
            f"but only the {fund_pct_int}th funding percentile (FER={fer_val:.2f}) — "
            f"a critically underfunded load-bearing package."
        )
    elif tier == "underfunded":
        return (
            f"This project is in the {crit_pct_int}th criticality percentile "
            f"but only the {fund_pct_int}th funding percentile (FER={fer_val:.2f}) — "
            f"underfunded relative to its structural importance."
        )
    elif tier == "balanced":
        return (
            f"Funding is well-calibrated to structural importance (FER={fer_val:.2f}). "
            f"Criticality: {crit_pct_int}th percentile. Funding: {fund_pct_int}th percentile."
        )
    elif tier == "overfunded":
        return (
            f"This project receives above-average funding ({fund_pct_int}th percentile) "
            f"relative to its structural criticality ({crit_pct_int}th percentile, "
            f"FER={fer_val:.2f})."
        )
    else:  # significantly_overfunded
        return (
            f"This project receives significantly above-average funding "
            f"({fund_pct_int}th percentile) relative to its structural criticality "
            f"({crit_pct_int}th percentile, FER={fer_val:.2f}). "
            f"May warrant review."
        )


def compute_funding_efficiency(
    G_active: nx.DiGraph,
    criticality_scores: dict[str, int],
    pony_results: dict,
    df_projects: pd.DataFrame,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> list[FundingEfficiencyResult]:
    """
    Compute Funding Efficiency Ratio for all projects.

    Algorithm:
        1. Aggregate repo-level criticality scores to project level (sum).
           Each Repo node carries a 'project' attribute linking it to a parent project.
        2. Aggregate pony factor flags to project level (any repo with PF=1 → project pony_flag=True).
        3. Compute percentile ranks for both aggregate criticality and funding.
        4. FER = criticality_pct / funding_pct (or None if funding_usd == 0 or funding_pct == 0).
        5. Assign tier via compute_fer_tier() and generate narrative for each project.

    Args:
        G_active:           Active subgraph from active_subgraph_projection().
                            Repo nodes must carry 'project' attribute.
        criticality_scores: Output of compute_criticality_scores().
        pony_results:       Output of compute_pony_factors() — maps repo → ContributorRiskResult.
        df_projects:        DataFrame with columns: title, total_awarded_usd (at minimum).
        config:             PGAtlasConfig (reserved for future threshold use).

    Returns:
        List of FundingEfficiencyResult sorted by FER descending
        (most underfunded / unfunded first; None FER appears at the top).
    """
    # ── Step 1: Aggregate criticality to project level ────────────────────────
    project_criticality: dict[str, float] = {}
    project_pony_flags: dict[str, int] = {}  # pony_risk_repos count
    project_pony_any: dict[str, bool] = {}

    for node, data in G_active.nodes(data=True):
        if data.get("node_type") != "Repo":
            continue
        project_name = data.get("project")
        if not project_name:
            continue

        crit = float(criticality_scores.get(node, 0))
        project_criticality[project_name] = (
            project_criticality.get(project_name, 0.0) + crit
        )

        pony_result = pony_results.get(node)
        if pony_result is not None:
            pf = pony_result.pony_factor
            project_pony_flags[project_name] = (
                project_pony_flags.get(project_name, 0) + pf
            )
            if pf == 1:
                project_pony_any[project_name] = True
        else:
            if project_name not in project_pony_flags:
                project_pony_flags[project_name] = 0

    if not project_criticality:
        logger.warning("compute_funding_efficiency: no Repo nodes with 'project' attribute found.")
        return []

    # ── Step 2: Build project funding map ────────────────────────────────────
    df_projects = df_projects.copy()
    df_projects["total_awarded_usd"] = pd.to_numeric(
        df_projects.get("total_awarded_usd", 0), errors="coerce"
    ).fillna(0)

    funding_map: dict[str, float] = {}
    if "title" in df_projects.columns:
        funding_map = dict(zip(df_projects["title"], df_projects["total_awarded_usd"]))

    # Collect all projects appearing in graph OR in df_projects
    all_projects = set(project_criticality.keys()) | set(funding_map.keys())

    # ── Step 3: Compute percentile ranks ──────────────────────────────────────
    # Build unified dicts for percentile computation
    crit_for_pct = {p: project_criticality.get(p, 0.0) for p in all_projects}
    funding_for_pct = {p: funding_map.get(p, 0.0) for p in all_projects}

    crit_percentiles = compute_percentile_ranks(crit_for_pct)

    # For funding percentiles, only compute among projects with funding > 0
    funded_projects = {p: v for p, v in funding_for_pct.items() if v > 0}
    if funded_projects:
        funded_pcts_raw = compute_percentile_ranks(funded_projects)
        # All unfunded projects get percentile 0
        fund_percentiles: dict[str, float] = {p: 0.0 for p in all_projects}
        fund_percentiles.update(funded_pcts_raw)
    else:
        fund_percentiles = {p: 0.0 for p in all_projects}

    # ── Step 4: Build FundingEfficiencyResult for each project ────────────────
    fer_results: list[FundingEfficiencyResult] = []

    for project in sorted(all_projects):
        crit_raw = crit_for_pct.get(project, 0.0)
        crit_pct = crit_percentiles.get(project, 0.0)
        funding_usd = funding_for_pct.get(project, 0.0)
        funding_pct = fund_percentiles.get(project, 0.0)

        pony_flag = project_pony_any.get(project, False)
        pony_risk_repos = project_pony_flags.get(project, 0)

        # FER = criticality_pct / funding_pct; None if unfunded
        if funding_usd == 0 or funding_pct == 0:
            fer: Optional[float] = None
        else:
            fer = round(crit_pct / funding_pct, 4) if funding_pct > 0 else None

        fer_tier = compute_fer_tier(fer)

        # Build partial result to pass to narrative generator
        result = FundingEfficiencyResult(
            project=project,
            criticality_raw=round(crit_raw, 2),
            criticality_pct=round(crit_pct, 1),
            funding_usd=funding_usd,
            funding_pct=round(funding_pct, 1),
            fer=round(fer, 4) if fer is not None else None,
            fer_tier=fer_tier,
            pony_flag=pony_flag,
            pony_risk_repos=pony_risk_repos,
            narrative="",  # placeholder
        )
        result.narrative = generate_fer_narrative(result)
        fer_results.append(result)

    # ── Step 5: Sort by FER descending (None/unfunded first, then high FER) ───
    def fer_sort_key(r: FundingEfficiencyResult):
        # None FER (unfunded) → sort first (use infinity)
        return -(r.fer if r.fer is not None else float("inf"))

    fer_results.sort(key=fer_sort_key)

    logger.info(
        "Funding Efficiency: computed FER for %d projects. "
        "Critically underfunded: %d, Balanced: %d, Unfunded: %d.",
        len(fer_results),
        sum(1 for r in fer_results if r.fer_tier == "critically_underfunded"),
        sum(1 for r in fer_results if r.fer_tier == "balanced"),
        sum(1 for r in fer_results if r.fer_tier == "unfunded"),
    )
    return fer_results


def fer_summary(results: list[FundingEfficiencyResult]) -> dict:
    """
    Return distribution summary of FER results.

    Returns:
        {tier: count} dict for all six tiers, plus
        'top_underfunded': list of top 5 critically_underfunded projects
                           (sorted by FER descending).

    Args:
        results: List of FundingEfficiencyResult from compute_funding_efficiency().

    Returns:
        Summary dict with tier counts and top underfunded list.
    """
    tier_counts: dict[str, int] = {
        "critically_underfunded": 0,
        "underfunded": 0,
        "balanced": 0,
        "overfunded": 0,
        "significantly_overfunded": 0,
        "unfunded": 0,
    }
    for r in results:
        if r.fer_tier in tier_counts:
            tier_counts[r.fer_tier] += 1

    # Top critically underfunded — sorted by FER descending
    critically_underfunded = [
        r for r in results if r.fer_tier == "critically_underfunded"
    ]
    critically_underfunded.sort(key=lambda r: r.fer if r.fer is not None else 0, reverse=True)

    return {
        **tier_counts,
        "top_underfunded": [
            {
                "project": r.project,
                "fer": r.fer,
                "criticality_pct": r.criticality_pct,
                "funding_pct": r.funding_pct,
            }
            for r in critically_underfunded[:5]
        ],
    }
