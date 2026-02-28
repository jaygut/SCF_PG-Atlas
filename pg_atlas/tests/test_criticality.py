"""
pg_atlas/tests/test_criticality.py — Tests for A9 criticality scoring.

Tests verify:
- Hub packages score higher than leaf packages.
- Leaf packages (no active dependents) score 0.
- Percentile ranks are in [0, 100].
- Temporal decay criticality <= base criticality for all nodes.
- compute_percentile_ranks output is correctly bounded.
"""

import networkx as nx
import numpy as np
import pytest

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig
from pg_atlas.metrics.criticality import (
    compute_criticality_scores,
    compute_decay_criticality,
    compute_percentile_ranks,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_hub_leaf_graph() -> nx.DiGraph:
    """
    Build a small graph with a clear hub-leaf structure:

        leaf-a ──┐
        leaf-b ──┼──► hub-pkg ──► deep-dep
        leaf-c ──┘
        isolate (no edges)

    All are Repo or ExternalRepo nodes, all active.
    """
    G = nx.DiGraph()
    G.add_node("hub-pkg", node_type="ExternalRepo", active=True, days_since_commit=1)
    G.add_node("deep-dep", node_type="ExternalRepo", active=True, days_since_commit=5)
    G.add_node("leaf-a", node_type="Repo", active=True, days_since_commit=10, project="P1")
    G.add_node("leaf-b", node_type="Repo", active=True, days_since_commit=20, project="P2")
    G.add_node("leaf-c", node_type="Repo", active=True, days_since_commit=30, project="P3")
    G.add_node("isolate", node_type="Repo", active=True, days_since_commit=5, project="P4")

    G.add_edge("leaf-a", "hub-pkg", edge_type="depends_on")
    G.add_edge("leaf-b", "hub-pkg", edge_type="depends_on")
    G.add_edge("leaf-c", "hub-pkg", edge_type="depends_on")
    G.add_edge("hub-pkg", "deep-dep", edge_type="depends_on")
    return G


def make_dormant_dependent_graph() -> nx.DiGraph:
    """Graph where a package has dependents but they are NOT active."""
    G = nx.DiGraph()
    G.add_node("dep-pkg", node_type="ExternalRepo", active=True, days_since_commit=1)
    # Dormant dependents (active=False)
    G.add_node("dormant-a", node_type="Repo", active=False, days_since_commit=200, project="P1")
    G.add_node("dormant-b", node_type="Repo", active=False, days_since_commit=300, project="P2")
    G.add_edge("dormant-a", "dep-pkg", edge_type="depends_on")
    G.add_edge("dormant-b", "dep-pkg", edge_type="depends_on")
    return G


# ── compute_criticality_scores tests ─────────────────────────────────────────

def test_hub_scores_higher_than_leaf():
    """Hub package depended on by 3 leaves must score higher than any leaf."""
    G = make_hub_leaf_graph()
    crit = compute_criticality_scores(G)
    assert crit["hub-pkg"] > crit["leaf-a"]
    assert crit["hub-pkg"] > crit["leaf-b"]
    assert crit["hub-pkg"] > crit["leaf-c"]


def test_hub_score_equals_number_of_active_transitive_dependents():
    """hub-pkg has 3 active transitive dependents (leaf-a, b, c)."""
    G = make_hub_leaf_graph()
    crit = compute_criticality_scores(G)
    assert crit["hub-pkg"] == 3


def test_deep_dep_scores_highest_in_chain():
    """deep-dep is transitively depended on by all 3 leaves + hub-pkg → score = 4."""
    G = make_hub_leaf_graph()
    crit = compute_criticality_scores(G)
    assert crit["deep-dep"] == 4


def test_leaf_scores_zero():
    """Leaf packages with no active dependents score 0."""
    G = make_hub_leaf_graph()
    crit = compute_criticality_scores(G)
    assert crit["leaf-a"] == 0
    assert crit["leaf-b"] == 0
    assert crit["leaf-c"] == 0


def test_isolate_scores_zero():
    """Isolated node with no in-edges scores 0."""
    G = make_hub_leaf_graph()
    crit = compute_criticality_scores(G)
    assert crit["isolate"] == 0


def test_dormant_dependents_not_counted():
    """Packages depended on only by dormant nodes score 0."""
    G = make_dormant_dependent_graph()
    crit = compute_criticality_scores(G)
    # dep-pkg is in an active subgraph but its dependents are inactive.
    assert crit["dep-pkg"] == 0


def test_all_scores_non_negative():
    """All criticality scores must be >= 0."""
    G = make_hub_leaf_graph()
    crit = compute_criticality_scores(G)
    for node, score in crit.items():
        assert score >= 0, f"Node {node} has negative score {score}"


def test_returns_dict():
    G = make_hub_leaf_graph()
    crit = compute_criticality_scores(G)
    assert isinstance(crit, dict)


def test_only_repo_and_externalrepo_in_results():
    """Only Repo and ExternalRepo nodes should appear in results."""
    G = make_hub_leaf_graph()
    G.add_node("MyProject", node_type="Project")
    G.add_node("alice", node_type="Contributor")
    crit = compute_criticality_scores(G)
    assert "MyProject" not in crit
    assert "alice" not in crit


# ── compute_decay_criticality tests ──────────────────────────────────────────

def test_decay_criticality_lte_base():
    """Decay-weighted score must be <= base score for every node."""
    G = make_hub_leaf_graph()
    base = compute_criticality_scores(G)
    decay = compute_decay_criticality(G, base, DEFAULT_CONFIG)
    for node in base:
        assert decay.get(node, 0.0) <= base[node] + 1e-9, (
            f"Node {node}: decay={decay.get(node)} > base={base[node]}"
        )


def test_decay_score_zero_for_no_dependents():
    """Nodes with zero base criticality have decay score 0."""
    G = make_hub_leaf_graph()
    base = compute_criticality_scores(G)
    decay = compute_decay_criticality(G, base, DEFAULT_CONFIG)
    assert decay.get("leaf-a", 0.0) == 0.0
    assert decay.get("isolate", 0.0) == 0.0


def test_decay_uses_config_halflife():
    """Shorter halflife → lower decay scores for the same graph."""
    G = make_hub_leaf_graph()
    base = compute_criticality_scores(G)
    config_short = PGAtlasConfig(decay_halflife_days=1.0)
    config_long = PGAtlasConfig(decay_halflife_days=365.0)
    decay_short = compute_decay_criticality(G, base, config_short)
    decay_long = compute_decay_criticality(G, base, config_long)
    # Hub with recent dependents: long halflife should give higher score.
    # (Longer halflife → less decay → higher weights for same days_since_commit)
    hub_short = decay_short.get("hub-pkg", 0.0)
    hub_long = decay_long.get("hub-pkg", 0.0)
    assert hub_long >= hub_short


def test_decay_returns_floats():
    G = make_hub_leaf_graph()
    base = compute_criticality_scores(G)
    decay = compute_decay_criticality(G, base, DEFAULT_CONFIG)
    for node, score in decay.items():
        assert isinstance(score, float), f"Node {node} decay score is {type(score)}"


# ── compute_percentile_ranks tests ────────────────────────────────────────────

def test_percentile_ranks_in_0_100():
    """All percentile rank values must be in [0, 100]."""
    G = make_hub_leaf_graph()
    crit = compute_criticality_scores(G)
    pcts = compute_percentile_ranks(crit)
    for node, pct in pcts.items():
        assert 0.0 <= pct <= 100.0, f"Node {node} has percentile {pct} out of range"


def test_percentile_ranks_monotone():
    """Higher score → higher or equal percentile."""
    G = make_hub_leaf_graph()
    crit = compute_criticality_scores(G)
    pcts = compute_percentile_ranks(crit)
    # deep-dep has highest score → highest percentile
    assert pcts["deep-dep"] >= pcts["hub-pkg"]
    assert pcts["hub-pkg"] >= pcts["leaf-a"]


def test_percentile_returns_dict_same_keys():
    """compute_percentile_ranks returns a dict with the same keys as input."""
    scores = {"a": 10, "b": 5, "c": 0, "d": 20}
    pcts = compute_percentile_ranks(scores)
    assert set(pcts.keys()) == set(scores.keys())


def test_percentile_empty_input():
    """compute_percentile_ranks on empty dict returns empty dict."""
    result = compute_percentile_ranks({})
    assert result == {}


def test_percentile_uniform_scores():
    """When all scores are equal, percentile is 0 (nothing is strictly below)."""
    scores = {"a": 5, "b": 5, "c": 5}
    pcts = compute_percentile_ranks(scores)
    for pct in pcts.values():
        assert pct == 0.0


def test_percentile_min_node_gets_zero():
    """The node with the minimum score gets percentile 0."""
    scores = {"a": 0, "b": 5, "c": 10}
    pcts = compute_percentile_ranks(scores)
    assert pcts["a"] == 0.0


# ── Integration with synthetic graph ─────────────────────────────────────────

def test_synthetic_criticality_hub_packages_score_high(active_subgraph):
    """Known hub packages like soroban-sdk must score in the top half."""
    crit = compute_criticality_scores(active_subgraph)
    pcts = compute_percentile_ranks(crit)
    # soroban-sdk is a hub with hub_bias=5 — it should be highly critical.
    if "soroban-sdk" in pcts:
        assert pcts["soroban-sdk"] >= 50.0, (
            f"soroban-sdk at {pcts['soroban-sdk']:.1f}th percentile — expected >= 50"
        )


def test_synthetic_percentile_all_in_range(active_subgraph):
    """All percentile values in synthetic active subgraph are in [0, 100]."""
    crit = compute_criticality_scores(active_subgraph)
    pcts = compute_percentile_ranks(crit)
    for node, pct in pcts.items():
        assert 0.0 <= pct <= 100.0
