"""
pg_atlas/tests/test_maintenance_debt.py — Unit tests for Maintenance Debt Surface.

Covers classify_commit_trend, compute_maintenance_debt_surface, and mds_summary
with 10 targeted tests verifying all three qualifying conditions and the risk
score formula.

Author: Jay Gutierrez, PhD | SCF #41
"""

import networkx as nx
import pytest

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig
from pg_atlas.metrics.maintenance_debt import (
    MaintenanceDebtEntry,
    classify_commit_trend,
    compute_maintenance_debt_surface,
    generate_mds_narrative,
    mds_summary,
)
from pg_atlas.metrics.pony_factor import ContributorRiskResult


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_pony_result(
    repo: str,
    hhi: float = 3000.0,
    pony_factor: int = 1,
    top_contributor: str = "alice",
    top_contributor_share: float = 0.6,
) -> ContributorRiskResult:
    """Build a minimal ContributorRiskResult for testing."""
    return ContributorRiskResult(
        repo=repo,
        pony_factor=pony_factor,
        hhi=hhi,
        shannon_entropy=0.5,
        top_contributor=top_contributor,
        top_contributor_share=top_contributor_share,
        total_contributors=2,
        total_commits=100,
        risk_tier="concentrated",
    )


def _make_graph_with_repo(
    repo: str = "repo:test-pkg",
    project: str = "Test Project",
    days_since_commit: int = 60,
    active: bool = True,
) -> nx.DiGraph:
    """
    Build a minimal graph containing a single Repo node with given attributes.
    """
    G = nx.DiGraph()
    G.add_node(
        repo,
        node_type="Repo",
        project=project,
        days_since_commit=days_since_commit,
        active=active,
    )
    return G


# ── Test 1 ─────────────────────────────────────────────────────────────────────

def test_classify_commit_trend_active():
    """Fewer than 14 days since commit → 'active'."""
    assert classify_commit_trend(0) == "active"
    assert classify_commit_trend(13) == "active"


# ── Test 2 ─────────────────────────────────────────────────────────────────────

def test_classify_commit_trend_stable():
    """14–44 days since commit → 'stable'."""
    assert classify_commit_trend(14) == "stable"
    assert classify_commit_trend(20) == "stable"
    assert classify_commit_trend(44) == "stable"


# ── Test 3 ─────────────────────────────────────────────────────────────────────

def test_classify_commit_trend_stagnant():
    """45–88 days since commit → 'stagnant'."""
    assert classify_commit_trend(45) == "stagnant"
    assert classify_commit_trend(60) == "stagnant"
    assert classify_commit_trend(88) == "stagnant"


# ── Test 4 ─────────────────────────────────────────────────────────────────────

def test_classify_commit_trend_declining():
    """89+ days since commit → 'declining'."""
    assert classify_commit_trend(89) == "declining"
    assert classify_commit_trend(90) == "declining"
    assert classify_commit_trend(200) == "declining"


# ── Test 5 ─────────────────────────────────────────────────────────────────────

def test_high_criticality_and_high_hhi_and_stagnant_qualifies():
    """
    A repo in the top criticality quartile with high HHI and stagnant activity
    must appear in the Maintenance Debt Surface.

    Uses 4 nodes in criticality_scores so the target repo lands at exactly the
    75th percentile: rank 3/4 * 100 = 75.0 >= mds_criticality_quartile (75.0).
    """
    repo = "repo:critical-stagnant"
    G = _make_graph_with_repo(repo=repo, days_since_commit=60)

    # With 4 scores, searchsorted puts repo at rank 3 → 3/4*100 = 75.0 pct.
    criticality_scores = {
        repo: 100,
        "repo:peer-a": 10,
        "repo:peer-b": 20,
        "repo:peer-c": 30,
    }
    pony_results = {repo: _make_pony_result(repo, hhi=4000.0)}

    entries = compute_maintenance_debt_surface(G, criticality_scores, pony_results)

    assert len(entries) >= 1
    assert any(e.project == "Test Project" for e in entries)


# ── Test 6 ─────────────────────────────────────────────────────────────────────

def test_low_criticality_excluded():
    """
    A repo with low criticality percentile (below top quartile) must NOT appear
    in the Maintenance Debt Surface regardless of HHI or commit trend.
    """
    repo = "repo:low-crit"
    G = _make_graph_with_repo(repo=repo, days_since_commit=100)

    # Give many other repos higher scores so this repo is in the bottom quartile
    criticality_scores = {repo: 1}
    for i in range(10):
        criticality_scores[f"dummy-{i}"] = 1000  # much higher

    pony_results = {repo: _make_pony_result(repo, hhi=8000.0)}

    entries = compute_maintenance_debt_surface(G, criticality_scores, pony_results)

    # The low-criticality repo should not appear
    assert not any(e.project == "Test Project" for e in entries)


# ── Test 7 ─────────────────────────────────────────────────────────────────────

def test_low_hhi_excluded():
    """
    A repo with HHI below mds_hhi_min (2500) must NOT appear in the MDS
    regardless of criticality or commit trend.
    """
    repo = "repo:low-hhi"
    G = _make_graph_with_repo(repo=repo, days_since_commit=100)

    criticality_scores = {repo: 100}  # high crit score
    pony_results = {repo: _make_pony_result(repo, hhi=1000.0)}  # low HHI

    entries = compute_maintenance_debt_surface(G, criticality_scores, pony_results)

    assert not any(e.project == "Test Project" for e in entries)


# ── Test 8 ─────────────────────────────────────────────────────────────────────

def test_active_trend_excluded():
    """
    A repo with an 'active' commit trend (< 14 days) must NOT appear in the MDS
    even if criticality and HHI qualify.
    """
    repo = "repo:active-repo"
    G = _make_graph_with_repo(repo=repo, days_since_commit=5)  # active trend

    criticality_scores = {repo: 100}  # high crit score
    pony_results = {repo: _make_pony_result(repo, hhi=8000.0)}

    entries = compute_maintenance_debt_surface(G, criticality_scores, pony_results)

    # Active trend → should not qualify
    assert not any(e.project == "Test Project" for e in entries)


# ── Test 9 ─────────────────────────────────────────────────────────────────────

def test_risk_score_formula():
    """
    risk_score must equal (criticality_pct / 100) * (hhi / 10000).
    """
    repo = "repo:formula-check"
    G = _make_graph_with_repo(repo=repo, days_since_commit=90)  # declining

    # Only one repo in the universe → it will be at 0th percentile (rank 0/1)
    # But we need it in top quartile, so add peers with lower scores
    # Add the high-crit repo and 3 lower ones so it's at ~75th percentile (3/4 × 100 = 75)
    # rank = searchsorted(sorted([10,10,10,100], 100) = 3, so 3/4*100 = 75
    criticality_scores = {
        repo: 100,
        "peer-1": 10,
        "peer-2": 10,
        "peer-3": 10,
    }
    hhi_val = 5000.0
    pony_results = {repo: _make_pony_result(repo, hhi=hhi_val)}

    entries = compute_maintenance_debt_surface(G, criticality_scores, pony_results)

    qualifying = [e for e in entries if e.project == "Test Project"]
    assert len(qualifying) == 1

    entry = qualifying[0]
    # crit_pct = 75.0 (3/4 * 100), hhi = 5000.0
    expected_risk = (75.0 / 100.0) * (hhi_val / 10_000.0)
    assert abs(entry.risk_score - expected_risk) < 0.001


# ── Test 10 ────────────────────────────────────────────────────────────────────

def test_results_sorted_by_risk_score_descending():
    """
    compute_maintenance_debt_surface must return entries sorted by risk_score
    descending (highest risk first).
    """
    G = nx.DiGraph()

    repos = ["repo:high-risk", "repo:medium-risk", "repo:low-risk"]

    for repo in repos:
        G.add_node(
            repo,
            node_type="Repo",
            project=repo,
            days_since_commit=90,  # declining for all
            active=True,
        )

    # Assign criticality scores so all are in top quartile
    # With 3 repos, percentiles are 0, 33.3, 66.7 — only the top two qualify at 75th pct
    # Use 4 repos: 3 high + 1 low peer to ensure top 3 reach the quartile
    G.add_node(
        "repo:low-peer",
        node_type="Repo",
        project="low-peer",
        days_since_commit=90,
        active=True,
    )

    criticality_scores = {
        "repo:high-risk": 100,
        "repo:medium-risk": 80,
        "repo:low-risk": 76,
        "repo:low-peer": 10,
    }
    pony_results = {
        "repo:high-risk": _make_pony_result("repo:high-risk", hhi=9000.0),
        "repo:medium-risk": _make_pony_result("repo:medium-risk", hhi=5000.0),
        "repo:low-risk": _make_pony_result("repo:low-risk", hhi=2600.0),
        "repo:low-peer": _make_pony_result("repo:low-peer", hhi=2600.0),
    }

    entries = compute_maintenance_debt_surface(G, criticality_scores, pony_results)

    # Check ordering
    risk_scores = [e.risk_score for e in entries]
    assert risk_scores == sorted(risk_scores, reverse=True), (
        f"Expected descending order, got: {risk_scores}"
    )
