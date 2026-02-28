"""
pg_atlas/metrics/pony_factor.py — A9: Pony Factor / HHI / Shannon Entropy.

Translated from the validated prototype:
  06_demos/01_active_subgraph_prototype/build_notebook.py (Section 7)

CRITICAL BUG FIX: The prototype contained a duplicate keyword argument 'hhi='
in the ContributorRiskResult constructor (line ~887), which is a Python
SyntaxError. This production module corrects that by constructing the dataclass
with each field exactly once.

The pony factor measures how concentrated a project's maintenance is in a
single contributor. If one person accounts for the majority of commits, the
project is at risk: if they disappear, maintenance stops.

Three complementary metrics:
    1. Binary Pony Factor: Flag = 1 if any contributor accounts for >= 50% of commits.
    2. HHI (Herfindahl-Hirschman Index): Continuous score 0–10,000.
       HHI = sum(commit_share_i^2) × 10,000
       Borrowed from economics (market concentration analysis).
    3. Shannon Entropy: Information-theoretic contributor diversity.
       H = -sum(p_i × ln(p_i))
       Maximized for uniform distribution (all contributors equal).

Risk tiers (configurable via PGAtlasConfig):
    HHI < 1,500            → 'healthy'       (well-distributed)
    1,500 <= HHI < 2,500   → 'moderate'      (some concentration)
    2,500 <= HHI < 5,000   → 'concentrated'  (high risk)
    HHI >= 5,000           → 'critical'      (near-single-contributor)

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import logging
from dataclasses import dataclass

import networkx as nx
import numpy as np

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig

logger = logging.getLogger(__name__)


@dataclass
class ContributorRiskResult:
    """
    Pony factor analysis result for a single repository.

    Fields:
        repo:                   Node ID of the Repo in the graph.
        pony_factor:            Binary flag — 1 = single contributor >= threshold.
        hhi:                    Herfindahl-Hirschman Index (0–10,000).
                                Higher = more concentrated maintenance.
        shannon_entropy:        Shannon entropy of commit share distribution.
                                Higher = more diverse (lower risk).
        top_contributor:        Node ID of the contributor with the most commits.
        top_contributor_share:  Fraction of total commits by top_contributor (0.0–1.0).
        total_contributors:     Number of distinct contributors to this repo.
        total_commits:          Total commit count across all contributors.
        risk_tier:              'healthy' | 'moderate' | 'concentrated' | 'critical'
    """
    repo: str
    pony_factor: int
    hhi: float
    shannon_entropy: float
    top_contributor: str
    top_contributor_share: float
    total_contributors: int
    total_commits: int
    risk_tier: str


def compute_pony_factors(
    G_active: nx.DiGraph,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> dict[str, ContributorRiskResult]:
    """
    Compute binary pony factor, HHI, and Shannon Entropy for every Repo node.

    Algorithm:
        For each Repo node in the active subgraph:
        1. Collect all in-edges with edge_type='contributed_to' and a 'commits' attribute.
        2. Compute commit shares (each contributor's fraction of total commits).
        3. Compute binary pony factor: 1 if max(share) >= config.pony_factor_threshold.
        4. Compute HHI: sum(share_i^2) × 10,000.
        5. Compute Shannon entropy: -sum(share_i × ln(share_i)) for share_i > 0.
        6. Assign risk tier based on HHI thresholds from config.

    Args:
        G_active: Active subgraph from active_subgraph_projection().
                  Contributor → Repo edges must carry 'commits' attribute
                  and edge_type='contributed_to'.
        config:   PGAtlasConfig. Uses:
                    config.pony_factor_threshold  (default 0.50)
                    config.hhi_moderate           (default 1500.0)
                    config.hhi_concentrated       (default 2500.0)
                    config.hhi_critical           (default 5000.0)

    Returns:
        results: Dict mapping repo node_id → ContributorRiskResult.
                 Repos with no contributor data are omitted.

    Notes:
        - External repos (ExternalRepo nodes) are excluded from this analysis
          since contributor data is only available for Repo nodes with git history.
        - Repos with total_commits == 0 are skipped to avoid division by zero.

    Reference:
        Prototype: build_notebook.py Section 7, compute_pony_factors()
        Bug fixed: duplicate 'hhi=' keyword in ContributorRiskResult constructor.
    """
    results: dict[str, ContributorRiskResult] = {}

    repo_nodes = [
        n for n, d in G_active.nodes(data=True) if d.get("node_type") == "Repo"
    ]

    for repo in repo_nodes:
        # Collect (contributor_node, commit_count) for all in-edges.
        contributors = [
            (u, d["commits"])
            for u, v, d in G_active.in_edges(repo, data=True)
            if d.get("edge_type") == "contributed_to" and "commits" in d
        ]

        if not contributors:
            continue

        total_commits = sum(c for _, c in contributors)
        if total_commits == 0:
            continue

        # Compute commit shares and sort descending.
        shares = [
            (contrib, commits / total_commits)
            for contrib, commits in contributors
        ]
        shares.sort(key=lambda x: x[1], reverse=True)

        top_contrib, top_share = shares[0]

        # ── Binary pony factor ────────────────────────────────────────────────
        pony_flag: int = 1 if top_share >= config.pony_factor_threshold else 0

        # ── HHI: sum of squared shares × 10,000 ──────────────────────────────
        hhi: float = sum(s ** 2 for _, s in shares) * 10_000

        # ── Shannon Entropy: -sum(p * ln(p)) ─────────────────────────────────
        shannon_entropy: float = -sum(
            s * np.log(s) for _, s in shares if s > 0
        )

        # ── Risk tier (from config thresholds) ───────────────────────────────
        if hhi < config.hhi_moderate:
            risk_tier = "healthy"
        elif hhi < config.hhi_concentrated:
            risk_tier = "moderate"
        elif hhi < config.hhi_critical:
            risk_tier = "concentrated"
        else:
            risk_tier = "critical"

        # ── Construct result (each field exactly once — bug fix applied) ──────
        results[repo] = ContributorRiskResult(
            repo=repo,
            pony_factor=pony_flag,
            hhi=round(hhi, 1),
            shannon_entropy=round(shannon_entropy, 3),
            top_contributor=top_contrib,
            top_contributor_share=round(top_share, 3),
            total_contributors=len(contributors),
            total_commits=total_commits,
            risk_tier=risk_tier,
        )

    logger.debug(
        "Pony factor computed for %d repos. Pony-flagged: %d.",
        len(results),
        sum(1 for r in results.values() if r.pony_factor == 1),
    )
    return results
