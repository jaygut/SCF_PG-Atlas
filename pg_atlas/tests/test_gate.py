"""
Tests for the Layer 1 Metric Gate — the core output of PG Atlas.
"""

import pandas as pd
import pytest

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig
from pg_atlas.metrics.gate import (
    GateSignalResult,
    MetricGateResult,
    evaluate_all_projects,
    evaluate_project,
    gate_summary,
)


def test_all_three_fail_returns_failed():
    """Project failing all 3 signals → passed=False, signals_passed=0."""
    r = evaluate_project("test-pkg", 0, 0.0, 9999.0, "alice", 0.99, 0.0)
    assert r.passed == False
    assert r.signals_passed == 0


def test_exactly_two_pass_returns_passed():
    """Passing exactly 2 signals (minimum) → passed=True, borderline=True."""
    r = evaluate_project("test-pkg", 50, 60.0, 9999.0, "alice", 0.99, 50.0)
    # criticality PASS (60 >= 50), pony FAIL (9999 >= 2500), adoption PASS (50 >= 40)
    assert r.passed == True
    assert r.signals_passed == 2
    assert r.borderline == True


def test_all_three_pass_returns_passed_not_borderline():
    """Passing all 3 signals → passed=True, borderline=False."""
    r = evaluate_project("test-pkg", 100, 90.0, 500.0, "alice", 0.30, 80.0)
    assert r.passed == True
    assert r.signals_passed == 3
    assert r.borderline == False


def test_gate_narratives_are_non_empty():
    """Every signal narrative must be non-empty."""
    r = evaluate_project("test-pkg", 30, 25.0, 7000.0, "alice", 0.95, 20.0)
    assert len(r.criticality.narrative) > 0
    assert len(r.pony_factor.narrative) > 0
    assert len(r.adoption.narrative) > 0
    assert len(r.gate_explanation) > 0


def test_gate_explanation_references_project_name():
    """gate_explanation must mention the project name."""
    r = evaluate_project("my-special-project", 0, 0.0, 9999.0, "x", 1.0, 0.0)
    assert "my-special-project" in r.gate_explanation


def test_thresholds_snapshot_in_result():
    """thresholds_snapshot must be a non-empty dict."""
    r = evaluate_project("pkg", 50, 50.0, 1000.0, "alice", 0.4, 50.0)
    assert isinstance(r.thresholds_snapshot, dict)
    assert len(r.thresholds_snapshot) > 0


def test_custom_config_changes_outcome():
    """Raising criticality threshold from 50 to 80 should turn a pass into a fail."""
    r_default = evaluate_project("pkg", 50, 60.0, 500.0, "alice", 0.3, 50.0)
    config_strict = PGAtlasConfig(criticality_pass_percentile=80.0)
    r_strict = evaluate_project("pkg", 50, 60.0, 500.0, "alice", 0.3, 50.0, config_strict)
    assert r_default.criticality.passed == True
    assert r_strict.criticality.passed == False


def test_evaluate_all_projects_returns_list():
    """evaluate_all_projects returns a list of MetricGateResults."""
    df = pd.DataFrame([
        {
            "project": "a",
            "criticality_raw": 10,
            "criticality_pct": 60.0,
            "hhi": 500.0,
            "top_contributor": "x",
            "top_contributor_share": 0.3,
            "adoption_score": 50.0,
        },
        {
            "project": "b",
            "criticality_raw": 1,
            "criticality_pct": 5.0,
            "hhi": 8000.0,
            "top_contributor": "y",
            "top_contributor_share": 0.95,
            "adoption_score": 5.0,
        },
    ])
    results = evaluate_all_projects(df)
    assert len(results) == 2
    assert all(isinstance(r, MetricGateResult) for r in results)


def test_gate_summary_structure():
    """gate_summary returns required keys."""
    df = pd.DataFrame([
        {
            "project": "a",
            "criticality_raw": 10,
            "criticality_pct": 60.0,
            "hhi": 500.0,
            "top_contributor": "x",
            "top_contributor_share": 0.3,
            "adoption_score": 50.0,
        },
    ])
    results = evaluate_all_projects(df)
    summary = gate_summary(results)
    required_keys = {
        "total_projects",
        "passed",
        "failed",
        "borderline",
        "pass_rate",
        "signal_pass_rates",
        "failure_breakdown",
    }
    assert required_keys.issubset(summary.keys())


def test_failed_projects_come_first():
    """evaluate_all_projects sorts failed projects before passed ones."""
    df = pd.DataFrame([
        {
            "project": "passing",
            "criticality_raw": 50,
            "criticality_pct": 80.0,
            "hhi": 200.0,
            "top_contributor": "x",
            "top_contributor_share": 0.2,
            "adoption_score": 80.0,
        },
        {
            "project": "failing",
            "criticality_raw": 1,
            "criticality_pct": 2.0,
            "hhi": 9000.0,
            "top_contributor": "y",
            "top_contributor_share": 0.99,
            "adoption_score": 1.0,
        },
    ])
    results = evaluate_all_projects(df)
    assert results[0].project == "failing"
    assert results[1].project == "passing"


# ── Additional tests to meet the 14-test requirement ──────────────────────────

def test_project_passes_with_criticality_and_adoption_pony_fails():
    """Criticality and adoption pass, pony fails → overall PASS (2/3)."""
    result = evaluate_project(
        project="pkg-extra-A",
        criticality_raw=10,
        criticality_pct=75.0,   # >= 50 → PASS
        hhi=3000.0,              # >= 2500 → pony FAILS
        top_contributor="alice",
        top_contributor_share=0.6,
        adoption_score=60.0,    # >= 40 → PASS
    )
    assert result.passed is True
    assert result.signals_passed == 2
    assert result.pony_factor.passed is False


def test_pony_narrative_mentions_contributor_name_on_fail():
    """Pony narrative must include the top_contributor name when the signal fails."""
    result = evaluate_project(
        project="pkg-extra-B",
        criticality_raw=10,
        criticality_pct=60.0,
        hhi=4500.0,              # pony FAILS
        top_contributor="heidi-dev",
        top_contributor_share=0.75,
        adoption_score=50.0,
    )
    assert "heidi-dev" in result.pony_factor.narrative
    assert "[FAIL]" in result.pony_factor.narrative


def test_adoption_narrative_contains_percentile():
    """Adoption narrative must include the adoption score value."""
    result = evaluate_project(
        project="pkg-extra-C",
        criticality_raw=10,
        criticality_pct=60.0,
        hhi=500.0,
        top_contributor="ivan",
        top_contributor_share=0.2,
        adoption_score=73.0,
    )
    assert "73" in result.adoption.narrative


def test_borderline_projects_float_to_top_of_passed_group():
    """
    Among passing projects, borderline (exactly 2/3) must appear before
    non-borderline (3/3) in the sorted result list.
    """
    rows = [
        # 3/3 pass — NOT borderline
        {
            "project": "all-three-pass",
            "criticality_raw": 30,
            "criticality_pct": 90.0,
            "hhi": 800.0,
            "top_contributor": "a",
            "top_contributor_share": 0.2,
            "adoption_score": 80.0,
        },
        # 2/3 pass — borderline (pony fails)
        {
            "project": "borderline-pass",
            "criticality_raw": 15,
            "criticality_pct": 60.0,
            "hhi": 3500.0,       # pony fails
            "top_contributor": "b",
            "top_contributor_share": 0.65,
            "adoption_score": 55.0,
        },
        # FAIL — should be first in the overall list
        {
            "project": "fail-project",
            "criticality_raw": 1,
            "criticality_pct": 5.0,
            "hhi": 8000.0,
            "top_contributor": "c",
            "top_contributor_share": 0.95,
            "adoption_score": 5.0,
        },
    ]
    df = pd.DataFrame(rows)
    results = evaluate_all_projects(df, DEFAULT_CONFIG)

    # First entry must be the failed project
    assert results[0].passed is False

    # Among passing projects, borderline comes first
    passed = [r for r in results if r.passed]
    assert len(passed) == 2
    assert passed[0].borderline is True
    assert passed[0].project == "borderline-pass"
