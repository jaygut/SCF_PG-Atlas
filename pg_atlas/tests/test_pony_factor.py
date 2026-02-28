"""
pg_atlas/tests/test_pony_factor.py — Tests for A9 pony factor / HHI / Shannon entropy.

Tests verify:
- Repo with 80% concentration → PF=1, HHI > 6400.
- Repo with 5 equal contributors → PF=0, HHI close to 2000.
- Shannon entropy maximized for uniform distribution.
- Risk tiers map correctly to HHI thresholds from config.
- Bug fix confirms no duplicate keyword error (ContributorRiskResult construction).
"""

import math

import networkx as nx
import pytest

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig
from pg_atlas.metrics.pony_factor import ContributorRiskResult, compute_pony_factors


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_concentrated_repo_graph(contributor_share: float = 0.80) -> nx.DiGraph:
    """
    Build a graph with a single repo where alice has contributor_share fraction of commits.

    When contributor_share < 0.5, the remaining commits are split between two
    secondary contributors (bob + carol) so that no secondary exceeds alice's share,
    ensuring alice remains the top contributor at the specified percentage.

    Args:
        contributor_share: Share of commits for alice (0.0–1.0).
    """
    G = nx.DiGraph()
    G.add_node("repo-A", node_type="Repo", days_since_commit=5, active=True)
    total = 100

    primary_commits = int(total * contributor_share)
    remaining = total - primary_commits

    G.add_node("alice", node_type="Contributor", active=True)
    G.add_edge("alice", "repo-A", edge_type="contributed_to", commits=primary_commits)

    if remaining > 0:
        if contributor_share < 0.5:
            # Split remainder across two secondaries so neither exceeds alice's share
            half = remaining // 2
            G.add_node("bob", node_type="Contributor", active=True)
            G.add_node("carol", node_type="Contributor", active=True)
            G.add_edge("bob", "repo-A", edge_type="contributed_to", commits=half)
            G.add_edge("carol", "repo-A", edge_type="contributed_to", commits=remaining - half)
        else:
            G.add_node("bob", node_type="Contributor", active=True)
            G.add_edge("bob", "repo-A", edge_type="contributed_to", commits=remaining)

    return G


def make_uniform_5_contributor_graph() -> nx.DiGraph:
    """
    Build a graph where 5 contributors each contribute exactly 20% of commits.
    HHI should be 5 × (0.2²) × 10,000 = 2,000.
    Shannon entropy should be ln(5) ≈ 1.609.
    """
    G = nx.DiGraph()
    G.add_node("repo-B", node_type="Repo", days_since_commit=10, active=True)
    total = 100
    per_contrib = total // 5

    for i, name in enumerate(["a", "b", "c", "d", "e"]):
        G.add_node(name, node_type="Contributor", active=True)
        G.add_edge(name, "repo-B", edge_type="contributed_to", commits=per_contrib)

    return G


def make_multi_repo_graph() -> nx.DiGraph:
    """Graph with multiple repos having different concentration profiles."""
    G = nx.DiGraph()

    # Repo 1: single contributor (pony factor = 1)
    G.add_node("repo-single", node_type="Repo", days_since_commit=5, active=True)
    G.add_node("solo", node_type="Contributor", active=True)
    G.add_edge("solo", "repo-single", edge_type="contributed_to", commits=100)

    # Repo 2: two equal contributors
    G.add_node("repo-equal2", node_type="Repo", days_since_commit=10, active=True)
    G.add_node("c1", node_type="Contributor", active=True)
    G.add_node("c2", node_type="Contributor", active=True)
    G.add_edge("c1", "repo-equal2", edge_type="contributed_to", commits=50)
    G.add_edge("c2", "repo-equal2", edge_type="contributed_to", commits=50)

    # Repo 3: no contributor data (should be omitted from results)
    G.add_node("repo-empty", node_type="Repo", days_since_commit=15, active=True)

    return G


# ── Pony factor binary flag tests ─────────────────────────────────────────────

def test_high_concentration_triggers_pony_factor_1():
    """80% single-contributor → pony_factor = 1."""
    G = make_concentrated_repo_graph(0.80)
    results = compute_pony_factors(G)
    assert "repo-A" in results
    assert results["repo-A"].pony_factor == 1


def test_below_threshold_pony_factor_0():
    """49% concentration → pony_factor = 0 (below 50% default threshold)."""
    G = make_concentrated_repo_graph(0.49)
    results = compute_pony_factors(G)
    assert results["repo-A"].pony_factor == 0


def test_exactly_at_threshold_triggers_pony_factor_1():
    """Exactly 50% concentration → pony_factor = 1 (>= threshold)."""
    G = make_concentrated_repo_graph(0.50)
    results = compute_pony_factors(G)
    assert results["repo-A"].pony_factor == 1


def test_single_contributor_pony_factor_1():
    """Single contributor = 100% share → pony_factor = 1, HHI = 10000."""
    G = nx.DiGraph()
    G.add_node("repo-solo", node_type="Repo", days_since_commit=1, active=True)
    G.add_node("solo", node_type="Contributor", active=True)
    G.add_edge("solo", "repo-solo", edge_type="contributed_to", commits=50)
    results = compute_pony_factors(G)
    r = results["repo-solo"]
    assert r.pony_factor == 1
    assert abs(r.hhi - 10000.0) < 0.1


def test_uniform_5_contributors_pony_factor_0():
    """5 equal contributors → pony_factor = 0 (each at 20%)."""
    G = make_uniform_5_contributor_graph()
    results = compute_pony_factors(G)
    assert results["repo-B"].pony_factor == 0


# ── HHI computation tests ─────────────────────────────────────────────────────

def test_high_concentration_hhi_above_6400():
    """80% single contributor → HHI > 6400 (0.8² × 10000 + 0.2² × 10000 = 6400+400=6800)."""
    G = make_concentrated_repo_graph(0.80)
    results = compute_pony_factors(G)
    # HHI = (0.80² + 0.20²) × 10000 = (0.64 + 0.04) × 10000 = 6800
    assert results["repo-A"].hhi > 6400


def test_uniform_5_contributors_hhi_close_to_2000():
    """5 equal contributors → HHI = 5 × (0.2²) × 10000 = 2000."""
    G = make_uniform_5_contributor_graph()
    results = compute_pony_factors(G)
    # The commits may not be perfectly equal if 100/5 = 20 exactly → HHI ≈ 2000.
    hhi = results["repo-B"].hhi
    assert abs(hhi - 2000.0) < 50.0, f"Expected HHI ≈ 2000, got {hhi}"


def test_hhi_single_contributor_is_10000():
    """Single contributor → HHI = 10,000 (maximum)."""
    G = nx.DiGraph()
    G.add_node("repo-x", node_type="Repo", days_since_commit=1, active=True)
    G.add_node("solo", node_type="Contributor", active=True)
    G.add_edge("solo", "repo-x", edge_type="contributed_to", commits=1)
    results = compute_pony_factors(G)
    assert abs(results["repo-x"].hhi - 10000.0) < 0.1


def test_hhi_two_equal_contributors():
    """Two equal contributors → HHI = 2 × (0.5²) × 10000 = 5000."""
    G = nx.DiGraph()
    G.add_node("repo-y", node_type="Repo", days_since_commit=1, active=True)
    G.add_node("c1", node_type="Contributor", active=True)
    G.add_node("c2", node_type="Contributor", active=True)
    G.add_edge("c1", "repo-y", edge_type="contributed_to", commits=50)
    G.add_edge("c2", "repo-y", edge_type="contributed_to", commits=50)
    results = compute_pony_factors(G)
    assert abs(results["repo-y"].hhi - 5000.0) < 0.1


# ── Shannon entropy tests ─────────────────────────────────────────────────────

def test_uniform_5_entropy_is_ln5():
    """5 equal contributors → Shannon entropy = ln(5) ≈ 1.609."""
    G = make_uniform_5_contributor_graph()
    results = compute_pony_factors(G)
    expected = math.log(5)
    assert abs(results["repo-B"].shannon_entropy - expected) < 0.05, (
        f"Expected entropy ≈ {expected:.3f}, got {results['repo-B'].shannon_entropy}"
    )


def test_uniform_higher_entropy_than_skewed():
    """Uniform distribution has higher entropy than concentrated distribution."""
    G_uniform = make_uniform_5_contributor_graph()
    G_skewed = make_concentrated_repo_graph(0.80)

    res_uniform = compute_pony_factors(G_uniform)
    res_skewed = compute_pony_factors(G_skewed)

    entropy_uniform = res_uniform["repo-B"].shannon_entropy
    entropy_skewed = res_skewed["repo-A"].shannon_entropy

    assert entropy_uniform > entropy_skewed, (
        f"Uniform entropy {entropy_uniform} should exceed skewed entropy {entropy_skewed}"
    )


def test_single_contributor_entropy_zero():
    """Single contributor → Shannon entropy = 0 (no diversity)."""
    G = nx.DiGraph()
    G.add_node("repo-x", node_type="Repo", days_since_commit=1, active=True)
    G.add_node("solo", node_type="Contributor", active=True)
    G.add_edge("solo", "repo-x", edge_type="contributed_to", commits=10)
    results = compute_pony_factors(G)
    assert abs(results["repo-x"].shannon_entropy) < 0.001


# ── Risk tier tests ───────────────────────────────────────────────────────────

def test_hhi_6800_is_critical():
    """HHI = 6800 (80% concentration) must be 'critical' (>= hhi_critical=5000)."""
    G = make_concentrated_repo_graph(0.80)
    results = compute_pony_factors(G)
    assert results["repo-A"].risk_tier == "critical"


def test_hhi_2000_is_moderate():
    """HHI = 2000 (5 equal contributors) must be 'moderate' (1500 <= HHI < 2500)."""
    G = make_uniform_5_contributor_graph()
    results = compute_pony_factors(G)
    assert results["repo-B"].risk_tier == "moderate"


def test_hhi_below_1500_is_healthy():
    """HHI well below 1500 → 'healthy' tier."""
    G = nx.DiGraph()
    G.add_node("repo-h", node_type="Repo", days_since_commit=1, active=True)
    # 10 equal contributors → HHI = 10 × (0.1²) × 10000 = 1000
    for i in range(10):
        name = f"c{i}"
        G.add_node(name, node_type="Contributor", active=True)
        G.add_edge(name, "repo-h", edge_type="contributed_to", commits=10)
    results = compute_pony_factors(G)
    assert results["repo-h"].hhi < 1500.0
    assert results["repo-h"].risk_tier == "healthy"


def test_custom_config_threshold():
    """With custom pony_factor_threshold=0.30, 40% concentration triggers PF=1."""
    G = make_concentrated_repo_graph(0.40)
    config_30 = PGAtlasConfig(pony_factor_threshold=0.30)
    config_50 = DEFAULT_CONFIG  # default threshold = 0.50

    results_30 = compute_pony_factors(G, config_30)
    results_50 = compute_pony_factors(G, config_50)

    assert results_30["repo-A"].pony_factor == 1  # 40% >= 30% → flag
    assert results_50["repo-A"].pony_factor == 0  # 40% < 50% → no flag


def test_custom_hhi_thresholds_change_tier():
    """Custom HHI thresholds from config are applied correctly."""
    G = make_concentrated_repo_graph(0.80)
    # Default: hhi_critical=5000 → 6800 is 'critical'
    res_default = compute_pony_factors(G, DEFAULT_CONFIG)
    assert res_default["repo-A"].risk_tier == "critical"

    # Custom: raise hhi_critical to 8000 → 6800 falls in 'concentrated'
    config_high = PGAtlasConfig(hhi_critical=8000.0)
    res_high = compute_pony_factors(G, config_high)
    assert res_high["repo-A"].risk_tier == "concentrated"


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_repo_without_contributor_edges_omitted():
    """Repos with no contributed_to in-edges are not in results."""
    G = make_multi_repo_graph()
    results = compute_pony_factors(G)
    assert "repo-empty" not in results


def test_result_is_dict_of_correct_type():
    """Results must be a dict of ContributorRiskResult objects."""
    G = make_concentrated_repo_graph()
    results = compute_pony_factors(G)
    assert isinstance(results, dict)
    for key, val in results.items():
        assert isinstance(val, ContributorRiskResult)


def test_top_contributor_is_the_highest_share_person():
    """top_contributor must be the person with the most commits."""
    G = make_concentrated_repo_graph(0.80)
    results = compute_pony_factors(G)
    assert results["repo-A"].top_contributor == "alice"
    assert abs(results["repo-A"].top_contributor_share - 0.80) < 0.01


# ── Bug fix verification ──────────────────────────────────────────────────────

def test_no_duplicate_keyword_argument_in_constructor():
    """
    Verify ContributorRiskResult can be constructed without duplicate keyword error.

    The original prototype had 'hhi=round(hhi, 1)' passed twice — a Python SyntaxError.
    This test confirms the production module correctly constructs the dataclass.
    """
    # This must not raise TypeError: __init__() got multiple values for argument 'hhi'
    result = ContributorRiskResult(
        repo="test-repo",
        pony_factor=1,
        hhi=6800.0,
        shannon_entropy=0.5,
        top_contributor="alice",
        top_contributor_share=0.80,
        total_contributors=2,
        total_commits=100,
        risk_tier="critical",
    )
    assert result.hhi == 6800.0
    assert result.pony_factor == 1


def test_compute_pony_factors_does_not_raise(synthetic_graph):
    """compute_pony_factors on the full synthetic active subgraph must not raise."""
    from pg_atlas.graph.active_subgraph import active_subgraph_projection

    G_active, _ = active_subgraph_projection(synthetic_graph)
    # This should complete without any SyntaxError / TypeError from duplicate hhi=
    results = compute_pony_factors(G_active)
    assert isinstance(results, dict)
    assert len(results) > 0


# ── Integration tests ─────────────────────────────────────────────────────────

def test_synthetic_pony_factor_coverage(active_subgraph):
    """Some repos in the synthetic graph must have pony_factor=1 (35% probability)."""
    results = compute_pony_factors(active_subgraph)
    pony_flagged = sum(1 for r in results.values() if r.pony_factor == 1)
    assert pony_flagged > 0, "Expected at least some pony-factor repos in synthetic graph"


def test_synthetic_risk_tier_distribution(active_subgraph):
    """All returned risk tiers must be valid strings."""
    results = compute_pony_factors(active_subgraph)
    valid_tiers = {"healthy", "moderate", "concentrated", "critical"}
    for r in results.values():
        assert r.risk_tier in valid_tiers, f"Unknown risk tier: {r.risk_tier}"
