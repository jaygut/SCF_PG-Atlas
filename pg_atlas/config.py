"""
pg_atlas/config.py — All tunable parameters for PG Atlas.

No threshold should ever be hardcoded in a metric module. Every gate threshold,
decay constant, and rate limit lives here so that calibration changes are a
single-file diff.

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PGAtlasConfig:
    """
    Immutable configuration for the PG Atlas metric pipeline.

    All fields have documented defaults matching the NORTH_STAR spec.
    Override by constructing a new PGAtlasConfig with the desired values.
    """

    # ── Active Subgraph (A6) ──────────────────────────────────────────────────
    active_window_days: int = 90
    # Repos with last commit > this many days ago are classified as dormant
    # and excluded from the active subgraph projection.
    # Calibration note: 90 days matches one SCF round cycle.

    # ── Criticality Thresholds (A9) ───────────────────────────────────────────
    criticality_pass_percentile: float = 50.0
    # Gate passes if project criticality_percentile >= this value.
    # Default 50th percentile: project must be in the top half of the universe.

    decay_halflife_days: float = 30.0
    # Temporal decay half-life for compute_decay_criticality().
    # A dependent that committed 30 days ago contributes exp(-1) ≈ 0.37 weight.
    # A dependent that committed 90 days ago contributes exp(-3) ≈ 0.05 weight.

    # ── Pony Factor Thresholds (A9) ───────────────────────────────────────────
    pony_factor_threshold: float = 0.50
    # Single contributor share that triggers pony_factor = 1 (binary flag).
    # Default 50%: if one person made half or more of commits → at-risk flag.

    hhi_moderate: float = 1500.0
    # HHI tier boundary: below this = 'healthy' (well-distributed contributions).

    hhi_concentrated: float = 2500.0
    # HHI tier boundary: 1500–2500 = 'moderate', above this = 'concentrated'.

    hhi_critical: float = 5000.0
    # HHI tier boundary: 2500–5000 = 'concentrated', above this = 'critical'.
    # HHI = 10,000 means a single contributor made all commits.

    pony_pass_hhi_max: float = 2500.0
    # Gate passes if project HHI < this value.
    # Default: projects below 'concentrated' tier pass the pony factor gate.

    # ── Adoption Thresholds (A10) ─────────────────────────────────────────────
    adoption_pass_percentile: float = 40.0
    # Gate passes if composite adoption score >= this percentile.
    # Default 40th percentile: project must be in the top 60% on
    # combined downloads + stars + forks signals.

    # ── Maintenance Debt Surface (NORTH_STAR Tier 3) ──────────────────────────
    mds_criticality_quartile: float = 75.0
    # Minimum criticality percentile to enter the MDS watch list.
    # Top 25%: only the most structurally important projects are tracked.

    mds_hhi_min: float = 2500.0
    # Minimum HHI to qualify for the MDS watch list.
    # Projects below 'concentrated' tier are not in maintenance debt.

    mds_commit_decline_window_days: int = 90
    # Rolling window used to detect commit activity decline in MDS.

    # ── Gate Logic ────────────────────────────────────────────────────────────
    gate_signals_required: int = 2
    # Minimum number of signals that must pass for a project to clear the
    # Layer 1 Metric Gate. Default 2-of-3 (criticality, pony factor, adoption).

    # ── API Rate Limits ───────────────────────────────────────────────────────
    deps_dev_rate_limit_per_min: int = 100
    # deps.dev enforces 100 req/min per IP.
    # 86 projects × ~5 requests ≈ 430 total → distributes over ~5 minutes.

    crates_io_rate_limit_per_sec: float = 1.0
    # crates.io requires at most 1 request per second.
    # Must include User-Agent header per crates.io TOS.

    github_api_rate_limit_per_hr: int = 5000
    # GitHub REST API: 5000 req/hr authenticated, 60/hr unauthenticated.
    # A7 git log parser uses authenticated mode (GITHUB_TOKEN env var).

    # ── Data Paths ────────────────────────────────────────────────────────────
    processed_data_dir: str = "01_data/processed"
    # Relative to the repository root. Cleaned seed data ready for deliverables.

    raw_data_dir: str = "01_data/raw"
    # Relative to the repository root. Original Airtable CSVs — do not modify.


# Singleton default — import this everywhere instead of constructing anew.
DEFAULT_CONFIG = PGAtlasConfig()
