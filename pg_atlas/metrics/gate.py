"""
pg_atlas/metrics/gate.py — The Layer 1 Metric Gate.

The 2-of-3 voting gate that determines which projects advance to Expert Review.
Every gate decision is fully auditable with human-readable narratives.

Gate Logic:
    A project PASSES if >= config.gate_signals_required (default: 2) of the
    three signals pass their respective thresholds.

    Signal 1 (Criticality): criticality_pct >= config.criticality_pass_percentile
    Signal 2 (Pony Factor): hhi < config.pony_pass_hhi_max
    Signal 3 (Adoption):    adoption_score >= config.adoption_pass_percentile

Design Principle (from NORTH_STAR):
    "An opaque gate creates distrust. A transparent, explainable gate creates
    legitimacy." — Every gate result includes a complete audit narrative.

Author: Jay Gutierrez, PhD | SCF #41
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig

logger = logging.getLogger(__name__)


@dataclass
class GateSignalResult:
    """
    Result for a single gate signal evaluation.

    Fields:
        signal_name:    'criticality' | 'pony_factor' | 'adoption'
        raw_value:      Raw metric value (score or HHI).
        percentile:     Percentile within PG Atlas universe.
        passed:         True if signal met its threshold.
        threshold_used: Threshold applied (from config).
        narrative:      Human-readable explanation.
    """

    signal_name: str
    raw_value: float
    percentile: float
    passed: bool
    threshold_used: float
    narrative: str


@dataclass
class MetricGateResult:
    """
    Complete gate evaluation result for a single project.

    Fields:
        project:              Project name.
        passed:               True if signals_passed >= signals_required.
        signals_passed:       Number of signals that cleared their thresholds.
        signals_required:     From config (default 2).
        criticality:          GateSignalResult for criticality signal.
        pony_factor:          GateSignalResult for pony factor signal.
        adoption:             GateSignalResult for adoption signal.
        gate_explanation:     Full audit narrative.
        borderline:           True if signals_passed == signals_required (worth human review).
        thresholds_snapshot:  Config thresholds used for this evaluation.
    """

    project: str
    passed: bool
    signals_passed: int
    signals_required: int
    criticality: GateSignalResult
    pony_factor: GateSignalResult
    adoption: GateSignalResult
    gate_explanation: str
    borderline: bool
    thresholds_snapshot: dict


def _build_criticality_narrative(
    raw: float,
    pct: float,
    threshold: float,
    passed: bool,
) -> str:
    """
    Build narrative for criticality signal.

    Pass:
        "Criticality: {N} transitive active dependents ({pct:.0f}th percentile) —
         above the {threshold:.0f}th percentile gate threshold. [PASS]"
    Fail:
        "Criticality: {N} transitive active dependents ({pct:.0f}th percentile) —
         below the {threshold:.0f}th percentile gate threshold. This package has
         limited downstream ecosystem impact in the current active graph. [FAIL]"

    Args:
        raw:       Raw criticality score (transitive dependent count).
        pct:       Percentile rank within the PG Atlas universe.
        threshold: Gate threshold from config.
        passed:    True if this signal passed.

    Returns:
        Human-readable narrative string.
    """
    raw_int = int(round(raw))
    if passed:
        return (
            f"Criticality: {raw_int} transitive active dependents ({pct:.0f}th percentile) — "
            f"above the {threshold:.0f}th percentile gate threshold. [PASS]"
        )
    else:
        return (
            f"Criticality: {raw_int} transitive active dependents ({pct:.0f}th percentile) — "
            f"below the {threshold:.0f}th percentile gate threshold. This package has "
            f"limited downstream ecosystem impact in the current active graph. [FAIL]"
        )


def _build_pony_factor_narrative(
    hhi: float,
    top_contributor: str,
    top_share: float,
    threshold: float,
    passed: bool,
) -> str:
    """
    Build narrative for pony factor signal (NORTH_STAR Principle 2 format).

    Pass:
        "Maintenance Health: HHI = {hhi:.0f} — below the {threshold:.0f}
         concentration threshold. Commit distribution is sufficiently diversified. [PASS]"
    Fail:
        "Maintenance Health: {top_contributor} accounts for {top_share:.0%} of
         commits in the last 90 days (HHI: {hhi:.0f} — {risk_tier} concentration).
         HHI exceeds the {threshold:.0f} gate threshold. Single-contributor
         failure risk is elevated. [FAIL]"

    Args:
        hhi:             HHI value (0–10,000).
        top_contributor: Name/ID of the dominant contributor.
        top_share:       Fraction of commits held by top contributor (0.0–1.0).
        threshold:       Gate threshold from config (pony_pass_hhi_max).
        passed:          True if HHI < threshold.

    Returns:
        Human-readable narrative string.
    """
    if passed:
        return (
            f"Maintenance Health: HHI = {hhi:.0f} — below the {threshold:.0f} "
            f"concentration threshold. Commit distribution is sufficiently diversified. [PASS]"
        )
    else:
        # Determine risk tier label for context
        if hhi >= 5000:
            risk_tier = "critical"
        elif hhi >= 2500:
            risk_tier = "concentrated"
        else:
            risk_tier = "moderate"

        return (
            f"Maintenance Health: {top_contributor} accounts for {top_share:.0%} of "
            f"commits in the last 90 days (HHI: {hhi:.0f} — {risk_tier} concentration). "
            f"HHI exceeds the {threshold:.0f} gate threshold. Single-contributor "
            f"failure risk is elevated. [FAIL]"
        )


def _build_adoption_narrative(
    score: float,
    threshold: float,
    passed: bool,
) -> str:
    """
    Build narrative for adoption signal.

    Pass:
        "Adoption: {score:.0f}th percentile on combined download/star/fork signals —
         above the {threshold:.0f}th percentile gate threshold. [PASS]"
    Fail:
        "Adoption: {score:.0f}th percentile on combined download/star/fork signals —
         below the {threshold:.0f}th percentile gate threshold. Limited ecosystem
         uptake signal in current data. [FAIL]"

    Args:
        score:     Composite adoption score (0–100 percentile).
        threshold: Gate threshold from config (adoption_pass_percentile).
        passed:    True if adoption_score >= threshold.

    Returns:
        Human-readable narrative string.
    """
    if passed:
        return (
            f"Adoption: {score:.0f}th percentile on combined download/star/fork signals — "
            f"above the {threshold:.0f}th percentile gate threshold. [PASS]"
        )
    else:
        return (
            f"Adoption: {score:.0f}th percentile on combined download/star/fork signals — "
            f"below the {threshold:.0f}th percentile gate threshold. Limited ecosystem "
            f"uptake signal in current data. [FAIL]"
        )


def evaluate_project(
    project: str,
    criticality_raw: float,
    criticality_pct: float,
    hhi: float,
    top_contributor: str,
    top_contributor_share: float,
    adoption_score: float,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> MetricGateResult:
    """
    Apply the 2-of-3 metric gate to a single project.

    Signal thresholds (from config):
        criticality_pct >= config.criticality_pass_percentile  → criticality PASSES
        hhi < config.pony_pass_hhi_max                         → pony_factor PASSES
        adoption_score >= config.adoption_pass_percentile      → adoption PASSES

    A project PASSES if signals_passed >= config.gate_signals_required (default 2).
    A result is borderline if signals_passed == signals_required exactly.

    gate_explanation format:
        "PG Atlas Metric Gate — {project}

        Result: PASS / FAIL ({signals_passed}/{signals_required} signals)

        [Criticality narrative]
        [Pony Factor narrative]
        [Adoption narrative]

        'This result is borderline — recommended for human review.' (if borderline)"

    Args:
        project:               Project or repo identifier.
        criticality_raw:       Raw transitive dependent count.
        criticality_pct:       Criticality percentile within the PG Atlas universe.
        hhi:                   Herfindahl-Hirschman Index (0–10,000).
        top_contributor:       Dominant contributor name/ID.
        top_contributor_share: Fraction of commits by top contributor (0.0–1.0).
        adoption_score:        Composite adoption percentile score (0–100).
        config:                PGAtlasConfig with gate thresholds.

    Returns:
        MetricGateResult with full audit trail.
    """
    # ── Evaluate each signal ──────────────────────────────────────────────────
    crit_passed = criticality_pct >= config.criticality_pass_percentile
    pony_passed = hhi < config.pony_pass_hhi_max
    adopt_passed = adoption_score >= config.adoption_pass_percentile

    # ── Build per-signal narratives ───────────────────────────────────────────
    crit_narrative = _build_criticality_narrative(
        criticality_raw, criticality_pct, config.criticality_pass_percentile, crit_passed
    )
    pony_narrative = _build_pony_factor_narrative(
        hhi, top_contributor, top_contributor_share, config.pony_pass_hhi_max, pony_passed
    )
    adopt_narrative = _build_adoption_narrative(
        adoption_score, config.adoption_pass_percentile, adopt_passed
    )

    # ── Aggregate signals ─────────────────────────────────────────────────────
    signals_passed = int(crit_passed) + int(pony_passed) + int(adopt_passed)
    passed = signals_passed >= config.gate_signals_required
    borderline = signals_passed == config.gate_signals_required

    # ── Build GateSignalResult objects ────────────────────────────────────────
    criticality_signal = GateSignalResult(
        signal_name="criticality",
        raw_value=criticality_raw,
        percentile=criticality_pct,
        passed=crit_passed,
        threshold_used=config.criticality_pass_percentile,
        narrative=crit_narrative,
    )
    pony_signal = GateSignalResult(
        signal_name="pony_factor",
        raw_value=hhi,
        percentile=hhi,  # HHI is the raw signal; percentile field reused for raw HHI
        passed=pony_passed,
        threshold_used=config.pony_pass_hhi_max,
        narrative=pony_narrative,
    )
    adopt_signal = GateSignalResult(
        signal_name="adoption",
        raw_value=adoption_score,
        percentile=adoption_score,
        passed=adopt_passed,
        threshold_used=config.adoption_pass_percentile,
        narrative=adopt_narrative,
    )

    # ── Build thresholds snapshot ─────────────────────────────────────────────
    thresholds_snapshot = {
        "criticality_pass_percentile": config.criticality_pass_percentile,
        "pony_pass_hhi_max": config.pony_pass_hhi_max,
        "adoption_pass_percentile": config.adoption_pass_percentile,
        "gate_signals_required": config.gate_signals_required,
    }

    # ── Build full gate explanation ───────────────────────────────────────────
    result_label = "PASS" if passed else "FAIL"
    explanation_lines = [
        f"PG Atlas Metric Gate — {project}",
        "",
        f"Result: {result_label} ({signals_passed}/{config.gate_signals_required} signals)",
        "",
        crit_narrative,
        pony_narrative,
        adopt_narrative,
    ]
    if borderline and passed:
        explanation_lines.append("")
        explanation_lines.append(
            "This result is borderline — recommended for human review."
        )
    gate_explanation = "\n".join(explanation_lines)

    logger.debug(
        "Gate evaluated for '%s': %s (%d/%d signals).",
        project,
        result_label,
        signals_passed,
        config.gate_signals_required,
    )

    return MetricGateResult(
        project=project,
        passed=passed,
        signals_passed=signals_passed,
        signals_required=config.gate_signals_required,
        criticality=criticality_signal,
        pony_factor=pony_signal,
        adoption=adopt_signal,
        gate_explanation=gate_explanation,
        borderline=borderline,
        thresholds_snapshot=thresholds_snapshot,
    )


def evaluate_all_projects(
    df_scores: pd.DataFrame,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> list[MetricGateResult]:
    """
    Apply the gate to all projects in df_scores DataFrame.

    Required columns in df_scores:
        project, criticality_raw, criticality_pct, hhi, top_contributor,
        top_contributor_share, adoption_score

    Returns results sorted: FAILED projects first (descending criticality_pct within
    each group), then PASSED projects. Borderline results float to the top of the
    PASSED group. This ordering ensures human reviewers see the most critical
    failures first.

    Args:
        df_scores: DataFrame with one row per project/repo.
        config:    PGAtlasConfig with gate thresholds.

    Returns:
        List of MetricGateResult objects, sorted as described above.
    """
    results: list[MetricGateResult] = []

    for _, row in df_scores.iterrows():
        result = evaluate_project(
            project=str(row["project"]),
            criticality_raw=float(row.get("criticality_raw", 0)),
            criticality_pct=float(row.get("criticality_pct", 0.0)),
            hhi=float(row.get("hhi", 0.0)),
            top_contributor=str(row.get("top_contributor", "unknown")),
            top_contributor_share=float(row.get("top_contributor_share", 0.0)),
            adoption_score=float(row.get("adoption_score", 0.0)),
            config=config,
        )
        results.append(result)

    # Sort: failed first (descending criticality_pct), then passed
    # Within passed, borderline floats to top
    def sort_key(r: MetricGateResult):
        # Primary: failed before passed (False=0 < True=1, so not passed → lower = earlier)
        # Secondary within failed: descending criticality (negate for ascending sort)
        # Secondary within passed: borderline first (True=1 > False=0, negate → borderline first)
        if not r.passed:
            return (0, -r.criticality.percentile)
        else:
            # borderline first in the passed group: negate borderline (True→-1 sorts before False→0)
            return (1, 0 if r.borderline else 1, -r.criticality.percentile)

    results.sort(key=sort_key)

    logger.info(
        "Gate evaluated for %d projects: %d passed, %d failed, %d borderline.",
        len(results),
        sum(1 for r in results if r.passed),
        sum(1 for r in results if not r.passed),
        sum(1 for r in results if r.borderline),
    )
    return results


def gate_summary(results: list[MetricGateResult]) -> dict:
    """
    Compute distribution summary across all gate results.

    Returns:
        {
          'total_projects': int,
          'passed': int,
          'failed': int,
          'borderline': int,
          'pass_rate': float,
          'signal_pass_rates': {
              'criticality': float,
              'pony_factor': float,
              'adoption': float,
          },
          'failure_breakdown': {
              'all_three_failed': int,
              'criticality_only_failed': int,
              'pony_only_failed': int,
              'adoption_only_failed': int,
              'two_failed': int,
          }
        }

    Args:
        results: List of MetricGateResult from evaluate_all_projects().

    Returns:
        Summary dict with counts and rates.
    """
    if not results:
        return {
            "total_projects": 0,
            "passed": 0,
            "failed": 0,
            "borderline": 0,
            "pass_rate": 0.0,
            "signal_pass_rates": {
                "criticality": 0.0,
                "pony_factor": 0.0,
                "adoption": 0.0,
            },
            "failure_breakdown": {
                "all_three_failed": 0,
                "criticality_only_failed": 0,
                "pony_only_failed": 0,
                "adoption_only_failed": 0,
                "two_failed": 0,
            },
        }

    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    failed_count = total - passed_count
    borderline_count = sum(1 for r in results if r.borderline)

    # Signal pass rates
    crit_pass = sum(1 for r in results if r.criticality.passed)
    pony_pass = sum(1 for r in results if r.pony_factor.passed)
    adopt_pass = sum(1 for r in results if r.adoption.passed)

    # Failure breakdown
    all_three_failed = sum(
        1 for r in results
        if not r.criticality.passed and not r.pony_factor.passed and not r.adoption.passed
    )
    # "only" means exactly that one signal failed and the project failed overall
    failed_results = [r for r in results if not r.passed]

    crit_only_failed = sum(
        1 for r in failed_results
        if not r.criticality.passed and r.pony_factor.passed and r.adoption.passed
    )
    pony_only_failed = sum(
        1 for r in failed_results
        if r.criticality.passed and not r.pony_factor.passed and r.adoption.passed
    )
    adopt_only_failed = sum(
        1 for r in failed_results
        if r.criticality.passed and r.pony_factor.passed and not r.adoption.passed
    )
    two_failed = sum(
        1 for r in failed_results
        if sum([not r.criticality.passed, not r.pony_factor.passed, not r.adoption.passed]) == 2
    )

    return {
        "total_projects": total,
        "passed": passed_count,
        "failed": failed_count,
        "borderline": borderline_count,
        "pass_rate": passed_count / total if total > 0 else 0.0,
        "signal_pass_rates": {
            "criticality": crit_pass / total if total > 0 else 0.0,
            "pony_factor": pony_pass / total if total > 0 else 0.0,
            "adoption": adopt_pass / total if total > 0 else 0.0,
        },
        "failure_breakdown": {
            "all_three_failed": all_three_failed,
            "criticality_only_failed": crit_only_failed,
            "pony_only_failed": pony_only_failed,
            "adoption_only_failed": adopt_only_failed,
            "two_failed": two_failed,
        },
    }
