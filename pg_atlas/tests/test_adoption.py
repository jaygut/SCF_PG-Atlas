"""
pg_atlas/tests/test_adoption.py — Tests for A10 adoption signals aggregation.

Tests verify:
- All percentile values are in [0, 100].
- Composite adoption score is mean of three component percentiles.
- Returns correct types (DataFrame + dict).
- Nodes with higher raw signals receive higher percentile scores.
"""

import pandas as pd
import networkx as nx
import pytest

from pg_atlas.metrics.adoption import compute_adoption_scores


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_adoption_graph() -> nx.DiGraph:
    """
    Build a small graph with known adoption signals.

    star/fork/download rankings:
        repo-popular: highest in all three → highest score
        repo-mid:     middle values
        repo-zero:    all zeros → lowest percentile
        ext-pkg:      ExternalRepo with signals
    """
    G = nx.DiGraph()
    G.add_node(
        "repo-popular", node_type="Repo", active=True,
        stars=1000, forks=200, downloads=500000,
    )
    G.add_node(
        "repo-mid", node_type="Repo", active=True,
        stars=100, forks=20, downloads=50000,
    )
    G.add_node(
        "repo-zero", node_type="Repo", active=True,
        stars=0, forks=0, downloads=0,
    )
    G.add_node(
        "ext-pkg", node_type="ExternalRepo", active=True,
        stars=500, forks=80, downloads=200000,
    )
    # Project node — should NOT appear in adoption results
    G.add_node("MyProject", node_type="Project")
    # Contributor node — should NOT appear in adoption results
    G.add_node("alice", node_type="Contributor")
    return G


def make_no_signals_graph() -> nx.DiGraph:
    """Graph where all nodes have zero adoption signals."""
    G = nx.DiGraph()
    G.add_node("r1", node_type="Repo", active=True, stars=0, forks=0, downloads=0)
    G.add_node("r2", node_type="Repo", active=True, stars=0, forks=0, downloads=0)
    return G


# ── Return type tests ─────────────────────────────────────────────────────────

def test_returns_tuple_of_dataframe_and_dict():
    """compute_adoption_scores must return (pd.DataFrame, dict)."""
    G = make_adoption_graph()
    result = compute_adoption_scores(G)
    assert isinstance(result, tuple)
    assert len(result) == 2
    df, scores = result
    assert isinstance(df, pd.DataFrame)
    assert isinstance(scores, dict)


def test_dataframe_has_required_columns():
    """DataFrame must have all expected columns."""
    G = make_adoption_graph()
    df, _ = compute_adoption_scores(G)
    required = {"node", "node_type", "stars", "forks", "downloads",
                "stars_pct", "forks_pct", "downloads_pct", "adoption_score"}
    assert required.issubset(set(df.columns)), (
        f"Missing columns: {required - set(df.columns)}"
    )


def test_only_repo_and_externalrepo_in_results():
    """Project and Contributor nodes must not appear in adoption output."""
    G = make_adoption_graph()
    df, scores = compute_adoption_scores(G)
    node_types_in_df = set(df["node_type"].unique())
    assert "Project" not in node_types_in_df
    assert "Contributor" not in node_types_in_df
    assert "MyProject" not in scores
    assert "alice" not in scores


# ── Percentile range tests ────────────────────────────────────────────────────

def test_all_percentile_columns_in_0_100():
    """stars_pct, forks_pct, downloads_pct must all be in [0, 100]."""
    G = make_adoption_graph()
    df, _ = compute_adoption_scores(G)
    for col in ["stars_pct", "forks_pct", "downloads_pct"]:
        assert df[col].min() >= 0.0, f"{col} min < 0"
        assert df[col].max() <= 100.0, f"{col} max > 100"


def test_adoption_score_in_0_100():
    """Composite adoption_score must be in [0, 100] for all nodes."""
    G = make_adoption_graph()
    df, scores = compute_adoption_scores(G)
    assert df["adoption_score"].min() >= 0.0
    assert df["adoption_score"].max() <= 100.0
    for node, score in scores.items():
        assert 0.0 <= score <= 100.0, f"Node {node} has adoption_score={score}"


# ── Composite score correctness tests ────────────────────────────────────────

def test_adoption_score_is_mean_of_three_components():
    """adoption_score must equal mean(stars_pct, forks_pct, downloads_pct)."""
    G = make_adoption_graph()
    df, _ = compute_adoption_scores(G)
    for _, row in df.iterrows():
        expected_mean = (row["stars_pct"] + row["forks_pct"] + row["downloads_pct"]) / 3.0
        assert abs(row["adoption_score"] - expected_mean) < 1e-9, (
            f"Node {row['node']}: adoption_score={row['adoption_score']:.4f}, "
            f"expected mean={expected_mean:.4f}"
        )


def test_popular_node_higher_score_than_zero_node():
    """Node with high signals must have higher adoption score than all-zero node."""
    G = make_adoption_graph()
    df, scores = compute_adoption_scores(G)
    assert scores["repo-popular"] > scores["repo-zero"]


def test_mid_node_between_popular_and_zero():
    """Middle-signal node must score between popular and zero nodes."""
    G = make_adoption_graph()
    _, scores = compute_adoption_scores(G)
    assert scores["repo-popular"] >= scores["repo-mid"] >= scores["repo-zero"]


# ── Graph side-effect tests ───────────────────────────────────────────────────

def test_adoption_score_written_to_graph():
    """compute_adoption_scores must write adoption_score to G_active nodes."""
    G = make_adoption_graph()
    _, scores = compute_adoption_scores(G)
    for node_id, score in scores.items():
        assert "adoption_score" in G.nodes[node_id], (
            f"Node {node_id} missing adoption_score attribute in graph"
        )
        assert abs(G.nodes[node_id]["adoption_score"] - score) < 1e-9


# ── Edge case tests ───────────────────────────────────────────────────────────

def test_all_zero_signals_still_returns_results():
    """Nodes with all-zero signals should still appear in results."""
    G = make_no_signals_graph()
    df, scores = compute_adoption_scores(G)
    assert len(df) == 2
    assert "r1" in scores
    assert "r2" in scores


def test_empty_graph_returns_empty_results():
    """Graph with no Repo/ExternalRepo nodes returns empty DataFrame and dict."""
    G = nx.DiGraph()
    G.add_node("MyProject", node_type="Project")
    df, scores = compute_adoption_scores(G)
    assert len(scores) == 0


def test_single_node_graph():
    """Single Repo node gets 100th percentile rank (pandas rank(pct=True))."""
    G = nx.DiGraph()
    G.add_node("lone-repo", node_type="Repo", active=True, stars=100, forks=10, downloads=1000)
    df, scores = compute_adoption_scores(G)
    assert "lone-repo" in scores
    # Single node → all ranks = 1.0 × 100 = 100.0
    assert abs(scores["lone-repo"] - 100.0) < 0.01


def test_missing_signals_default_to_zero():
    """Nodes without stars/forks/downloads attributes are treated as zeros."""
    G = nx.DiGraph()
    G.add_node("r1", node_type="Repo", active=True)  # no adoption attrs
    G.add_node("r2", node_type="Repo", active=True, stars=100, forks=10, downloads=5000)
    df, scores = compute_adoption_scores(G)
    # r1 has no signals → scores at or below r2
    assert scores["r2"] >= scores["r1"]


# ── Integration with synthetic graph ─────────────────────────────────────────

def test_synthetic_adoption_all_in_range(active_subgraph):
    """All adoption scores from synthetic active subgraph are in [0, 100]."""
    df, scores = compute_adoption_scores(active_subgraph)
    assert df["adoption_score"].min() >= 0.0
    assert df["adoption_score"].max() <= 100.0


def test_synthetic_adoption_returns_all_repo_nodes(active_subgraph):
    """Number of rows in df must equal number of Repo + ExternalRepo nodes."""
    expected_count = sum(
        1 for _, d in active_subgraph.nodes(data=True)
        if d.get("node_type") in ("Repo", "ExternalRepo")
    )
    df, _ = compute_adoption_scores(active_subgraph)
    assert len(df) == expected_count


def test_synthetic_adoption_score_is_mean_of_components(active_subgraph):
    """adoption_score = mean(stars_pct, forks_pct, downloads_pct) for all rows."""
    df, _ = compute_adoption_scores(active_subgraph)
    for _, row in df.iterrows():
        expected = (row["stars_pct"] + row["forks_pct"] + row["downloads_pct"]) / 3.0
        assert abs(row["adoption_score"] - expected) < 1e-9
