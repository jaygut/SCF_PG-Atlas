"""
pg_atlas/tests/test_keystone_contributor.py — Unit tests for Keystone Contributor Index.

Covers compute_keystone_contributors and kci_summary with 8 targeted tests
verifying the KCI formula, union semantics, sorting, and narrative generation.

Author: Jay Gutierrez, PhD | SCF #41
"""

import networkx as nx
import pytest

from pg_atlas.metrics.keystone_contributor import (
    KeystoneContributorResult,
    compute_keystone_contributors,
    compute_transitive_union,
    generate_kci_narrative,
    kci_summary,
)
from pg_atlas.metrics.pony_factor import ContributorRiskResult


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_pony_result(
    repo: str,
    top_contributor: str = "alice",
    pony_factor: int = 1,
    hhi: float = 8000.0,
    top_contributor_share: float = 0.8,
) -> ContributorRiskResult:
    """Build a minimal ContributorRiskResult."""
    return ContributorRiskResult(
        repo=repo,
        pony_factor=pony_factor,
        hhi=hhi,
        shannon_entropy=0.2,
        top_contributor=top_contributor,
        top_contributor_share=top_contributor_share,
        total_contributors=1,
        total_commits=100,
        risk_tier="critical",
    )


def _make_graph_with_deps(
    repos: list[str],
    contributor_edges: list[tuple] = None,
    dep_edges: list[tuple] = None,
) -> nx.DiGraph:
    """
    Build a minimal graph with Repo nodes and optional contributor/dep edges.
    """
    G = nx.DiGraph()
    for repo in repos:
        G.add_node(repo, node_type="Repo", project=repo, active=True, days_since_commit=5)

    if contributor_edges:
        for contrib, repo, commits in contributor_edges:
            if contrib not in G:
                G.add_node(contrib, node_type="Contributor", active=True)
            G.add_edge(contrib, repo, edge_type="contributed_to", commits=commits)

    if dep_edges:
        for src, tgt in dep_edges:
            G.add_edge(src, tgt, edge_type="depends_on")

    return G


# ── Test 1 ─────────────────────────────────────────────────────────────────────

def test_contributor_with_one_dominant_pony_repo_has_kci_equal_to_criticality_score():
    """
    A contributor who is top_contributor+PF=1 in exactly one repo should have
    KCI score equal to that repo's criticality score.
    """
    repo = "repo:pkg-A"
    G = _make_graph_with_deps([repo])
    criticality_scores = {repo: 42}
    pony_results = {repo: _make_pony_result(repo, top_contributor="alice", pony_factor=1)}

    results = compute_keystone_contributors(G, criticality_scores, pony_results)

    assert len(results) == 1
    assert results[0].contributor == "alice"
    assert results[0].kci_score == pytest.approx(42.0)


# ── Test 2 ─────────────────────────────────────────────────────────────────────

def test_contributor_with_no_pony_repos_not_in_results():
    """
    A contributor who has pony_factor=0 in all repos must NOT appear in the
    KCI results (KCI = 0 for them).
    """
    repo = "repo:pkg-B"
    G = _make_graph_with_deps([repo])
    criticality_scores = {repo: 50}
    pony_results = {
        repo: _make_pony_result(repo, top_contributor="bob", pony_factor=0)
    }

    results = compute_keystone_contributors(G, criticality_scores, pony_results)

    contributor_names = [r.contributor for r in results]
    assert "bob" not in contributor_names


# ── Test 3 ─────────────────────────────────────────────────────────────────────

def test_kci_aggregates_across_multiple_repos():
    """
    A contributor who is dominant (PF=1) in multiple repos should have
    KCI = sum of criticality scores across all those repos.
    """
    repos = ["repo:pkg-C1", "repo:pkg-C2", "repo:pkg-C3"]
    G = _make_graph_with_deps(repos)
    criticality_scores = {
        "repo:pkg-C1": 10,
        "repo:pkg-C2": 20,
        "repo:pkg-C3": 30,
    }
    pony_results = {
        "repo:pkg-C1": _make_pony_result("repo:pkg-C1", top_contributor="carol", pony_factor=1),
        "repo:pkg-C2": _make_pony_result("repo:pkg-C2", top_contributor="carol", pony_factor=1),
        "repo:pkg-C3": _make_pony_result("repo:pkg-C3", top_contributor="carol", pony_factor=1),
    }

    results = compute_keystone_contributors(G, criticality_scores, pony_results)

    carol_results = [r for r in results if r.contributor == "carol"]
    assert len(carol_results) == 1
    assert carol_results[0].kci_score == pytest.approx(60.0)
    assert carol_results[0].total_dominant_repos == 3


# ── Test 4 ─────────────────────────────────────────────────────────────────────

def test_at_risk_downstream_uses_union_not_sum():
    """
    If two repos share a downstream dependent, at_risk_downstream should count
    that dependent only once (union semantics, not sum).
    """
    # dep-A depends on both repo:X and repo:Y
    # So at_risk_downstream for a contributor dominant in both should be 1, not 2
    G = nx.DiGraph()
    G.add_node("repo:X", node_type="Repo", project="X", active=True, days_since_commit=5)
    G.add_node("repo:Y", node_type="Repo", project="Y", active=True, days_since_commit=5)
    G.add_node("dep-A", node_type="Repo", project="dep-A", active=True, days_since_commit=5)
    G.add_edge("dep-A", "repo:X", edge_type="depends_on")
    G.add_edge("dep-A", "repo:Y", edge_type="depends_on")

    criticality_scores = {"repo:X": 10, "repo:Y": 10, "dep-A": 0}
    pony_results = {
        "repo:X": _make_pony_result("repo:X", top_contributor="dave", pony_factor=1),
        "repo:Y": _make_pony_result("repo:Y", top_contributor="dave", pony_factor=1),
    }

    results = compute_keystone_contributors(G, criticality_scores, pony_results)

    dave_results = [r for r in results if r.contributor == "dave"]
    assert len(dave_results) == 1
    # dep-A depends on both X and Y → should be counted once (union)
    assert dave_results[0].at_risk_downstream == 1


# ── Test 5 ─────────────────────────────────────────────────────────────────────

def test_results_sorted_by_kci_score_descending():
    """compute_keystone_contributors must return results sorted by kci_score desc."""
    repos = ["repo:p1", "repo:p2", "repo:p3"]
    G = _make_graph_with_deps(repos)
    criticality_scores = {
        "repo:p1": 5,
        "repo:p2": 50,
        "repo:p3": 25,
    }
    pony_results = {
        "repo:p1": _make_pony_result("repo:p1", top_contributor="low-kci", pony_factor=1),
        "repo:p2": _make_pony_result("repo:p2", top_contributor="high-kci", pony_factor=1),
        "repo:p3": _make_pony_result("repo:p3", top_contributor="mid-kci", pony_factor=1),
    }

    results = compute_keystone_contributors(G, criticality_scores, pony_results)

    kci_scores = [r.kci_score for r in results]
    assert kci_scores == sorted(kci_scores, reverse=True), (
        f"Expected descending order, got: {kci_scores}"
    )


# ── Test 6 ─────────────────────────────────────────────────────────────────────

def test_narrative_contains_contributor_name():
    """The generated risk narrative must contain the contributor's name."""
    repo = "repo:pkg-narr"
    G = _make_graph_with_deps([repo])
    criticality_scores = {repo: 30}
    pony_results = {
        repo: _make_pony_result(repo, top_contributor="frank-the-dev", pony_factor=1)
    }

    results = compute_keystone_contributors(G, criticality_scores, pony_results)

    assert len(results) == 1
    assert "frank-the-dev" in results[0].risk_narrative


# ── Test 7 ─────────────────────────────────────────────────────────────────────

def test_kci_summary_counts_keystone_contributors():
    """kci_summary must accurately report total_keystone_contributors."""
    repos = ["repo:a", "repo:b"]
    G = _make_graph_with_deps(repos)
    criticality_scores = {"repo:a": 20, "repo:b": 30}
    pony_results = {
        "repo:a": _make_pony_result("repo:a", top_contributor="alice", pony_factor=1),
        "repo:b": _make_pony_result("repo:b", top_contributor="bob", pony_factor=1),
    }

    results = compute_keystone_contributors(G, criticality_scores, pony_results)
    summary = kci_summary(results)

    assert summary["total_keystone_contributors"] == 2
    assert isinstance(summary["top_5"], list)
    assert len(summary["top_5"]) <= 5


# ── Test 8 ─────────────────────────────────────────────────────────────────────

def test_empty_pony_results_returns_empty_list():
    """
    When pony_results is empty (no contributor data), the KCI function
    must return an empty list without raising.
    """
    G = _make_graph_with_deps(["repo:lonely"])
    criticality_scores = {"repo:lonely": 10}
    pony_results = {}

    results = compute_keystone_contributors(G, criticality_scores, pony_results)

    assert results == []
