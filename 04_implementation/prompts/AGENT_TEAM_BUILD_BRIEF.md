# PG Atlas — Agent Team Build Brief
## Production `pg_atlas/` Package: From Prototype to World-Class Governance Instrument

**Author:** Jay Gutierrez, PhD | **Date:** February 2026 | **Project:** SCF #41
**Purpose:** Complete technical specification for the multi-agent build of PG Atlas v0 production code

---

## 0. Mission & Framing for Agents

You are building **PG Atlas** — the first objective, graph-derived metrics backbone for the Stellar
Community Fund's public goods funding decisions. This is not a dashboard or a scoring app. It is
decision-grade infrastructure. The single output that matters:

> **"Is the SCF investing maintenance resources proportionally to structural ecosystem criticality —
> and if not, where are the gaps?"**

Everything you build serves that answer. The system powers the **Layer 1 Metric Gate** in SCF's
three-layer funding stack (Metrics → Expert Review → Community Vote).

### Codebase State You Are Starting From

A validated algorithmic prototype exists in:
`06_demos/01_active_subgraph_prototype/build_notebook.py`

The algorithms are **mathematically correct**. What doesn't exist yet:
- Production Python package (`pg_atlas/`) with proper modules
- Real data ingestion (all prototype data is synthetic)
- A7 Git Log Parser (Jay's primary T2 deliverable — $10K, due March 22)
- Metric Gate function (the final pass/fail output — missing from the POC)
- Interactive visualization (static matplotlib figures only)
- Test suite

### Critical Bug to Fix in the Existing POC

In `build_notebook.py` (line ~887), `ContributorRiskResult` is constructed with `hhi` keyword
passed twice — a Python `SyntaxError`. Fix this as part of any cell that touches pony factor:

```python
# BROKEN (as-is in build_notebook.py):
results[repo] = ContributorRiskResult(
    hhi=round(hhi, 1),
    shannon_entropy=round(shannon_entropy, 3),
    hhi=round(hhi, 1),  # ← REMOVE this duplicate line
    ...
)
```

### Real Data Available in `01_data/processed/`

| File | Columns | Records |
|---|---|---|
| `A5_pg_candidate_seed_list.csv` | title, category, integration_status, github_url, website, total_awarded_usd, open_source, description | 86 |
| `A5_all_active_with_github.csv` | (same schema) | 271 |
| `A6_github_orgs_seed.csv` | github_org, project_count | 78 |
| `A7_submission_github_repos.csv` | round, submission_title, github_url, total_awarded_usd, use_soroban, tranche_completion | 338 |

**Do not modify any file in `01_data/raw/`.** Read-only.

---

## 1. Target Package Architecture

Build the following structure under the repo root. Every module listed is a required deliverable.

```
pg_atlas/
├── __init__.py
├── config.py                        # All thresholds, API settings, constants
│
├── graph/
│   ├── __init__.py
│   ├── builder.py                   # NetworkX graph construction (from CSV or PostgreSQL)
│   ├── active_subgraph.py           # A6: Active subgraph projection
│   └── sync.py                      # Delta update from PostgreSQL on re-ingestion
│
├── metrics/
│   ├── __init__.py
│   ├── criticality.py               # A9: BFS criticality + temporal decay variant
│   ├── pony_factor.py               # A9: Binary PF + HHI + Shannon entropy
│   ├── adoption.py                  # A10: Download counts + stars + forks + percentile
│   ├── kcore.py                     # Tier 2: K-core decomposition
│   ├── bridges.py                   # Tier 2: Bridge edge detection (Tarjan's)
│   ├── funding_efficiency.py        # Tier 3: Funding Efficiency Ratio (FER)
│   ├── keystone_contributor.py      # Tier 3: Keystone Contributor Index (KCI)
│   ├── maintenance_debt.py          # Tier 3: Maintenance Debt Surface
│   └── gate.py                      # THE METRIC GATE: 2-of-3 signal with narratives
│
├── ingestion/
│   ├── __init__.py
│   ├── deps_dev_client.py           # deps.dev REST API wrapper (rate-limited)
│   ├── crates_io_client.py          # crates.io API for Cargo reverse dependencies
│   ├── git_log_parser.py            # A7: Git contributor log parser (Jay's primary T2)
│   ├── npm_downloads_client.py      # npm downloads API client
│   ├── pypi_downloads_client.py     # pypistats.org API client
│   └── opengrants_client.py         # OpenGrants DAOIP-5 project bootstrapper
│
├── storage/
│   ├── __init__.py
│   ├── schema.py                    # PostgreSQL DDL + migration helpers (Alex interface)
│   └── postgres.py                  # psycopg2 connection layer (stub until A2 locked)
│
├── api/
│   ├── __init__.py
│   └── endpoints.py                 # FastAPI analytics endpoints (D7/A11 contribution)
│
├── viz/
│   ├── __init__.py
│   ├── dashboard.py                 # Streamlit interactive dashboard
│   └── plotly_graph.py              # Interactive force-directed Plotly dependency graph
│
├── reports/
│   ├── __init__.py
│   └── governance_report.py         # Longitudinal governance report generator
│
└── tests/
    ├── __init__.py
    ├── conftest.py                  # Shared fixtures (synthetic graph from POC)
    ├── test_active_subgraph.py
    ├── test_criticality.py
    ├── test_pony_factor.py
    ├── test_adoption.py
    ├── test_gate.py
    ├── test_git_log_parser.py
    └── test_ingestion.py
```

---

## 2. Agent Roles and Ownership

### Agent Alpha — Package Architect & Algorithm Translator
**Primary mission:** Scaffold the `pg_atlas/` package, translate POC algorithms into production
modules, fix the existing bug, and wire the test suite.

**Owns:**
- `pg_atlas/__init__.py`, `pg_atlas/config.py`
- All modules in `pg_atlas/graph/`
- All modules in `pg_atlas/metrics/` *except* `gate.py`
- `pg_atlas/tests/conftest.py` and all test files *except* `test_git_log_parser.py`

**Must complete before:** Agent Beta (needs builder.py interface), Agent Gamma (needs metrics
modules to write gate.py against)

---

### Agent Beta — Data Ingestion Specialist (A7 Lead)
**Primary mission:** Build all real-data ingestion clients. A7 is Jay's primary T2 deliverable
and the highest-priority item in this entire brief.

**Owns:**
- All modules in `pg_atlas/ingestion/`
- `pg_atlas/tests/test_git_log_parser.py`
- `pg_atlas/tests/test_ingestion.py`

**Must complete before:** Agent Alpha (graph/builder.py needs real data to load), Agent Gamma
(adoption.py and maintenance_debt.py depend on real ingestion outputs)

---

### Agent Gamma — Metric Gate & Strategic Analytics
**Primary mission:** Implement the Metric Gate (the missing core output), narrative generation,
and the three Tier 3 strategic analytics modules. These produce the "outstanding" outputs.

**Owns:**
- `pg_atlas/metrics/gate.py`
- `pg_atlas/metrics/funding_efficiency.py`
- `pg_atlas/metrics/keystone_contributor.py`
- `pg_atlas/metrics/maintenance_debt.py`
- `pg_atlas/reports/governance_report.py`
- `pg_atlas/tests/test_gate.py`

**Depends on:** Agent Alpha completing `criticality.py`, `pony_factor.py`, `adoption.py`

---

### Agent Delta — Visualization & Dashboard
**Primary mission:** Port static matplotlib figures to interactive Plotly, build the Streamlit
dashboard, and implement the force-directed graph component for D8/A12.

**Owns:**
- All modules in `pg_atlas/viz/`
- `pg_atlas/api/endpoints.py`

**Depends on:** Agent Alpha completing all metrics modules, Agent Gamma completing gate.py

---

## 3. Phase-by-Phase Execution Plan

### Phase 0 — Immediate (Days 1–2) | All Agents in Parallel

**Agent Alpha:**
1. Create `pg_atlas/` package scaffold with all `__init__.py` files
2. Write `pg_atlas/config.py` (see spec below)
3. Translate POC algorithms into `pg_atlas/graph/active_subgraph.py` (verbatim port with
   clean public API)
4. Write `pg_atlas/tests/conftest.py` with the synthetic graph fixture from the POC
   (this is the shared baseline for all tests)
5. Fix the HHI duplicate keyword bug in `06_demos/01_active_subgraph_prototype/build_notebook.py`

**Agent Beta:**
1. Scaffold all `pg_atlas/ingestion/` files with docstrings and placeholder classes
2. Begin `git_log_parser.py` implementation (see full spec in Section 4)

---

### Phase 1 — Core Data Layer (Days 3–7) | Beta leads, Alpha supports

**Agent Beta:**
1. Complete `git_log_parser.py` (A7 — March 22 hard deadline)
2. Complete `deps_dev_client.py`
3. Complete `crates_io_client.py`
4. Complete download clients (npm, PyPI)

**Agent Alpha:**
1. Complete `graph/builder.py` — the NetworkX graph construction layer
   - Must support two backends: CSV (from `01_data/processed/`) and PostgreSQL (stub)
   - CSV mode must be runnable immediately from real seed data
2. Complete all `metrics/` modules except gate.py (direct ports from POC)

---

### Phase 2 — Gate & Strategic Analytics (Days 8–14) | Gamma leads

**Agent Gamma:**
1. Implement `metrics/gate.py` in full (see Section 5 spec)
2. Implement `metrics/maintenance_debt.py` (see Section 6 spec)
3. Implement `metrics/keystone_contributor.py` (see Section 7 spec)
4. Implement `metrics/funding_efficiency.py` (port from POC, add narrative)
5. Begin `reports/governance_report.py`

---

### Phase 3 — Visualization & API (Days 14–21) | Delta leads

**Agent Delta:**
1. Implement `viz/plotly_graph.py` (interactive force-directed graph)
2. Implement `viz/dashboard.py` (Streamlit app)
3. Implement `api/endpoints.py` (FastAPI analytics endpoints)

---

### Phase 4 — Integration & Validation (Days 21–25) | All Agents

1. Run the full pipeline on real data from `01_data/processed/`
2. Replace synthetic signals with real deps.dev + git log outputs
3. Calibrate gate thresholds against reference projects
4. Complete test suite (all tests must pass)
5. Update `06_demos/01_active_subgraph_prototype/build_notebook.py` to import from
   `pg_atlas` modules instead of inline implementations

---

## 4. Module Specifications

### `pg_atlas/config.py`

All tunable parameters live here. No threshold should ever be hardcoded in a metric module.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class PGAtlasConfig:
    # Active subgraph
    active_window_days: int = 90          # Repos with last commit > this are dormant

    # Criticality thresholds
    criticality_pass_percentile: float = 50.0   # Gate pass if criticality_pct >= this
    decay_halflife_days: float = 30.0           # Temporal decay half-life

    # Pony factor thresholds
    pony_factor_threshold: float = 0.50   # Single contributor share that triggers PF=1
    hhi_moderate: float = 1500.0          # HHI tier boundaries
    hhi_concentrated: float = 2500.0
    hhi_critical: float = 5000.0
    pony_pass_hhi_max: float = 2500.0     # Gate pass if HHI < this

    # Adoption thresholds
    adoption_pass_percentile: float = 40.0  # Gate pass if adoption_score >= this

    # Maintenance Debt Surface
    mds_criticality_quartile: float = 75.0  # Top quartile threshold (percentile)
    mds_hhi_min: float = 2500.0             # Minimum HHI to qualify
    mds_commit_decline_window_days: int = 90  # Rolling window for decline detection

    # Gate logic
    gate_signals_required: int = 2          # Minimum signals to pass (2-of-3)

    # API settings
    deps_dev_rate_limit_per_min: int = 100
    crates_io_rate_limit_per_sec: float = 1.0
    github_api_rate_limit_per_hr: int = 5000

    # Data paths
    processed_data_dir: str = "01_data/processed"
    raw_data_dir: str = "01_data/raw"

DEFAULT_CONFIG = PGAtlasConfig()
```

---

### `pg_atlas/graph/builder.py`

Builds a NetworkX DiGraph from either real CSV seed data or PostgreSQL (once Alex's schema
is locked). The CSV mode must work immediately from `01_data/processed/`.

**Required public interface:**

```python
import networkx as nx
from pg_atlas.config import PGAtlasConfig

def build_graph_from_csv(
    seed_list_path: str,
    orgs_path: str,
    repos_path: str,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> nx.DiGraph:
    """
    Build the initial graph from the Airtable CSV extracts.

    Loads 86 PG seed projects as Project nodes, their GitHub repos as Repo nodes,
    and constructs edges from real ingestion data where available.

    Node types created:
        - Project (from A5_pg_candidate_seed_list.csv)
        - Repo    (from A7_submission_github_repos.csv — one Repo per github_url)

    Edge types:
        - belongs_to: Repo → Project

    Dependency and contributor edges are populated separately by:
        - ingestion.deps_dev_client  → depends_on edges
        - ingestion.git_log_parser   → contributed_to edges

    Node attributes on Project:
        title, category, integration_status, github_url, website,
        total_awarded_usd, open_source, description, node_type='Project'

    Node attributes on Repo:
        github_url, ecosystem (inferred), project (parent project title),
        node_type='Repo', active=None (set by active_subgraph projection),
        days_since_commit=None (set by git log parser)

    Returns:
        G: nx.DiGraph with Project + Repo nodes and belongs_to edges
    """

def build_graph_from_db(conn, config: PGAtlasConfig = DEFAULT_CONFIG) -> nx.DiGraph:
    """
    Build the operational graph from PostgreSQL (D5 schema by Alex Olieman).

    STUB: Returns an empty graph until Alex's A2 schema is locked.
    When schema is available, implement queries for:
        - repo table → Repo nodes
        - external_repo table → ExternalRepo nodes
        - depends_on table → dependency edges
        - contributor table → Contributor nodes
        - contributed_to table → contribution edges

    Anticipated schema (update when Alex finalizes A2):
        repo(id, project_id, ecosystem, latest_commit_date, archived,
             adoption_stars, adoption_forks, adoption_downloads)
        depends_on(from_repo, to_repo, version_range, confidence)
        contributor(id, display_name, email_aliases)
        contributed_to(contributor_id, repo_id, commits,
                      first_commit_date, last_commit_date)
    """

def enrich_graph_with_ingestion(
    G: nx.DiGraph,
    dep_edges: list[dict],
    contrib_edges: list[dict],
    adoption_data: dict[str, dict],
    activity_data: dict[str, dict],
) -> nx.DiGraph:
    """
    Enrich an existing graph with ingestion outputs.

    dep_edges:      list of {from_repo, to_repo, ecosystem, confidence}
    contrib_edges:  list of {contributor, repo, commits, first_date, last_date}
    adoption_data:  {repo_url: {stars, forks, downloads}}
    activity_data:  {repo_url: {days_since_commit, archived}}

    Returns the same graph G mutated in-place (also returned for chaining).
    """
```

---

### `pg_atlas/ingestion/git_log_parser.py` (A7 — Jay's Primary T2 Deliverable)

**Acceptance criteria (verbatim from project spec):**
1. Runs against all repos in `01_data/processed/A7_submission_github_repos.csv`
2. Populates `Contributor` vertex data and `contributed_to` edge data with:
   commit counts, first commit date, last commit date
3. Determines `Repo.latest_commit_date` and `Repo.days_since_commit`
4. Handles inaccessible repos gracefully (logged at WARNING level, not fatal)

**Implementation requirements:**

Use the GitHub REST API (`/repos/{owner}/{repo}/commits`) rather than cloning repos.
This avoids disk space issues for 338 repos and respects the 90-day window naturally.

For alias deduplication (same person with multiple email addresses), use a heuristic:
normalize email domain, compare display names with fuzzy matching (`difflib.SequenceMatcher`),
and track a `email_aliases` list on each contributor.

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class ContributorStats:
    display_name: str
    email_aliases: list[str]
    commits_90d: int              # Commits in last 90 days
    first_commit_date: str        # ISO 8601
    last_commit_date: str         # ISO 8601
    repos: list[str]              # All repos this contributor touched

@dataclass
class RepoContributionResult:
    repo_url: str
    repo_github_path: str         # e.g. "stellar/js-stellar-sdk"
    latest_commit_date: str       # ISO 8601
    days_since_latest_commit: int
    total_commits_90d: int
    contributors: list[ContributorStats]
    accessible: bool              # False if repo is private, 404, or rate-limited
    error: str | None             # Error message if not accessible

def parse_repo_contributions(
    github_url: str,
    github_token: str | None = None,
    window_days: int = 90,
) -> RepoContributionResult:
    """
    Fetch commit history for a single repo from GitHub API.

    Uses /repos/{owner}/{repo}/commits with since= parameter.
    Paginates up to 10 pages (1000 commits max per repo).
    Returns gracefully if repo is private, deleted, or rate-limited.
    """

def parse_all_repos(
    repos_csv_path: str,
    github_token: str | None = None,
    window_days: int = 90,
    max_workers: int = 4,
) -> list[RepoContributionResult]:
    """
    Parse all repos from A7_submission_github_repos.csv in parallel.

    Respects GitHub API rate limits (5000/hr authenticated, 60/hr unauthenticated).
    Uses ThreadPoolExecutor with max_workers=4 to avoid rate-limit exhaustion.
    Logs progress: "Processing repo N/338: {url}"
    Logs WARNING (not error) for inaccessible repos.
    """

def results_to_contribution_edges(
    results: list[RepoContributionResult],
) -> list[dict]:
    """
    Convert RepoContributionResult list to edge dicts for graph.enrich_graph_with_ingestion().

    Returns: list of {contributor, repo, commits, first_date, last_date}
    """

def results_to_activity_data(
    results: list[RepoContributionResult],
) -> dict[str, dict]:
    """
    Returns: {repo_url: {days_since_commit, latest_commit_date, accessible}}
    """
```

---

### `pg_atlas/ingestion/deps_dev_client.py`

```python
import time
from typing import Generator

BASE_URL = "https://api.deps.dev/v3alpha"

@dataclass
class DepsDependencyEdge:
    from_purl: str
    to_purl: str
    to_name: str
    to_version: str
    ecosystem: str          # NPM | CARGO | PYPI | GO
    relation: str           # DIRECT | INDIRECT
    version_requirement: str
    confidence: str = "inferred_shadow"

@dataclass
class DepsRepoMetadata:
    purl: str
    name: str
    version: str
    ecosystem: str
    source_repo_url: str | None
    latest_version: str
    published_at: str
    license: str
    is_default: bool
    stars: int
    forks: int
    open_issues: int
    openssf_maintained_score: float | None  # 0–10 from GetProject
    openssf_maintained_detail: str | None   # "N commit(s) found in last 90 days"

class DepsDotDevClient:
    """
    Rate-limited client for the deps.dev REST API.

    Rate limit: 100 requests/minute per IP (enforced via token bucket).
    """

    def get_version(self, ecosystem: str, name: str, version: str = "") -> DepsRepoMetadata:
        """GetVersion: package metadata + source repo + license."""

    def get_dependencies(
        self, ecosystem: str, name: str, version: str
    ) -> list[DepsDependencyEdge]:
        """
        GetDependencies: resolved transitive dependency tree.

        Returns only DIRECT edges (relation='DIRECT') to avoid duplication
        when building the graph from multiple seed packages.

        NOTE: Cargo packages work for forward deps; dependentCount=0 for all
        Cargo packages (confirmed deps.dev limitation — use crates_io_client.py
        for Cargo reverse dependencies).
        """

    def get_project_enrichment(self, github_url: str) -> dict:
        """
        GetProject: stars, forks, OpenSSF scorecard.

        Maps github.com URLs to deps.dev project format:
        "github.com/stellar/js-stellar-sdk"
        """

    def batch_enrich_repos(
        self, repo_urls: list[str]
    ) -> dict[str, dict]:
        """
        Enrich multiple repos via GetProject in batches.
        Respects rate limit. Returns {repo_url: enrichment_dict}.
        """

    def bootstrap_stellar_graph(
        self, seed_packages: list[dict]
    ) -> tuple[list[DepsRepoMetadata], list[DepsDependencyEdge]]:
        """
        Execute the full 5-phase shadow graph bootstrap playbook:

        Phase 1: GetPackage for each seed → confirm indexed, get versions
        Phase 2: GetDependencies for each seed → forward dependency graph
        Phase 3: GetDependents counts → identify packages with dependents
                 (NOTE: NPM/PyPI only; Cargo always returns 0)
        Phase 4: GetProject for each Repo → enrich with stars/forks/OpenSSF
        Phase 5: Return structured output for graph enrichment

        Seed packages format:
          [{"ecosystem": "NPM", "name": "@stellar/js-xdr"},
           {"ecosystem": "CARGO", "name": "soroban-sdk"}, ...]
        """
```

**Confirmed Stellar hub seeds to use in bootstrap_stellar_graph:**
```python
STELLAR_SEED_PACKAGES = [
    {"ecosystem": "NPM",   "name": "@stellar/js-xdr"},          # 693 dependents
    {"ecosystem": "NPM",   "name": "@stellar/stellar-base"},     # 463 dependents
    {"ecosystem": "NPM",   "name": "@stellar/stellar-sdk"},
    {"ecosystem": "NPM",   "name": "@stellar/freighter-api"},
    {"ecosystem": "NPM",   "name": "soroban-client"},
    {"ecosystem": "PYPI",  "name": "stellar-sdk"},
    {"ecosystem": "CARGO", "name": "soroban-sdk"},               # blind spot — use crates.io
    {"ecosystem": "CARGO", "name": "stellar-xdr"},
    {"ecosystem": "CARGO", "name": "stellar-strkey"},
]
```

---

### `pg_atlas/ingestion/crates_io_client.py`

Critical for the Soroban/Rust ecosystem. deps.dev returns `dependentCount=0` for ALL Cargo
packages — this client provides the reverse dependency graph that deps.dev cannot.

```python
CRATES_IO_BASE = "https://crates.io/api/v1"
CRATES_IO_RATE_LIMIT = 1.0  # req/sec (enforced by time.sleep)
CRATES_IO_USER_AGENT = "pg-atlas/0.1 (contact: scf-public-goods)"  # Required by crates.io TOS

@dataclass
class CratesReverseDep:
    crate_name: str          # The crate that depends on the target
    version: str
    downloads: int           # Total download count (lifetime)
    recent_downloads: int    # Downloads in last 90 days

class CratesIoClient:
    def get_reverse_dependencies(
        self, crate_name: str, max_pages: int = 10
    ) -> list[CratesReverseDep]:
        """
        GET /api/v1/crates/{crate}/reverse_dependencies
        Paginates (100 per page) up to max_pages.
        """

    def get_downloads(self, crate_name: str) -> dict:
        """
        GET /api/v1/crates/{crate} → downloads field.
        Returns {total_downloads, recent_downloads, version}.
        """

    def bootstrap_soroban_reverse_graph(
        self, soroban_crates: list[str] | None = None
    ) -> list[dict]:
        """
        Fetch reverse dependencies for all key Soroban crates.

        Defaults to: ["soroban-sdk", "stellar-xdr", "stellar-strkey",
                       "soroban-env-host", "soroban-env-common"]

        Returns edge dicts compatible with graph.enrich_graph_with_ingestion().
        """
```

---

### `pg_atlas/metrics/gate.py` (THE MISSING CORE OUTPUT)

This is the single most critical missing piece. The Metric Gate is what makes PG Atlas a
governance instrument. Every design decision here must prioritize auditability.

```python
from dataclasses import dataclass
from pg_atlas.config import PGAtlasConfig

@dataclass
class GateSignalResult:
    signal_name: str              # 'criticality' | 'pony_factor' | 'adoption'
    raw_value: float              # Raw metric value
    percentile: float             # Percentile within PG Atlas universe
    passed: bool                  # True if signal passed its threshold
    threshold_used: float         # The threshold applied (from config)
    narrative: str                # Human-readable explanation (see Principle 2)

@dataclass
class MetricGateResult:
    project_title: str
    passed: bool                  # True if >= gate_signals_required signals passed
    signals_passed: int           # Count of passing signals
    signals_required: int         # From config (default 2)
    criticality: GateSignalResult
    pony_factor: GateSignalResult
    adoption: GateSignalResult
    gate_explanation: str         # Full audit narrative for this project
    borderline: bool              # True if signals_passed == gate_signals_required
                                  # (worth human review even if passing)
    thresholds_applied: dict      # Snapshot of config thresholds used

def evaluate_project(
    project_title: str,
    criticality_percentile: float,
    hhi: float,
    adoption_score: float,
    top_contributor: str,
    top_contributor_share: float,
    transitive_dependents: int,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> MetricGateResult:
    """
    Apply the 2-of-3 metric gate to a single project.

    Criticality signal passes if: criticality_percentile >= config.criticality_pass_percentile
    Pony factor signal passes if:  hhi < config.pony_pass_hhi_max
    Adoption signal passes if:     adoption_score >= config.adoption_pass_percentile

    Narratives must follow the NORTH_STAR Principle 2 format. Example:

    CRITICALITY narrative (if failed):
    "This project's packages have 0 active transitive dependents in the current
     ecosystem graph (0th percentile). The criticality gate requires ≥50th percentile."

    PONY FACTOR narrative (if failed):
    "This project's commit history shows that {top_contributor} accounts for
     {top_contributor_share:.0%} of commits in the last 90 days (HHI: {hhi:.0f} —
     {risk_tier} concentration). The gate requires HHI < {threshold:.0f}."

    ADOPTION narrative (if failed):
    "This project scores in the {adoption_score:.0f}th percentile on combined
     download/star/fork signals across the PG Atlas universe. The gate requires
     ≥{threshold}th percentile."
    """

def evaluate_all_projects(
    df_scores: pd.DataFrame,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> list[MetricGateResult]:
    """
    Apply the gate to all projects in df_scores.

    df_scores must have columns:
        project, criticality_pct, hhi, adoption_score,
        top_contributor, top_contributor_share, transitive_dependents

    Returns results sorted by: failed first (most urgent review), then by criticality desc.
    """

def gate_summary(results: list[MetricGateResult]) -> dict:
    """
    Aggregate gate results into a summary dict.

    Returns:
        {
          "total_projects": int,
          "passed": int,
          "failed": int,
          "pass_rate": float,
          "borderline": int,
          "failure_reasons": {"criticality_only": int, "pony_only": int, ...},
          "signal_pass_rates": {"criticality": float, "pony_factor": float, "adoption": float},
        }
    """
```

---

### `pg_atlas/metrics/maintenance_debt.py` (NORTH_STAR's Highest-Value Output)

> *"The set of projects that will fail quietly — not with a dramatic shutdown, but by gradually
> becoming too stale to depend on safely."*

```python
@dataclass
class MaintenanceDebtEntry:
    project_title: str
    criticality_percentile: float     # Must be >= mds_criticality_quartile
    hhi: float                        # Must be >= mds_hhi_min
    commit_trend: str                 # 'declining' | 'stable' | 'growing'
    days_since_last_commit: int
    transitive_dependents: int        # Absolute count of affected downstream packages
    top_contributor: str
    top_contributor_share: float
    risk_score: float                 # Composite: criticality * (hhi/10000) * decline_factor
    urgency_narrative: str            # Human-readable escalation message

def compute_maintenance_debt_surface(
    df_scores: pd.DataFrame,
    pony_results: dict,
    config: PGAtlasConfig = DEFAULT_CONFIG,
) -> list[MaintenanceDebtEntry]:
    """
    Identify the Maintenance Debt Surface: projects satisfying ALL THREE conditions:
      (1) criticality_pct >= config.mds_criticality_quartile (top quartile)
      (2) hhi >= config.mds_hhi_min (high contributor concentration)
      (3) commit_trend == 'declining' (activity is falling, not rising)

    Commit trend is computed from activity_data: compare last 30d vs prior 60d commit rate.

    Sort by risk_score descending. These are the projects most likely to fail quietly.
    This is the watchlist the SCF should prioritize for proactive maintenance funding.
    """
```

---

### `pg_atlas/metrics/keystone_contributor.py` (Cross-Project Pony Factor)

> *"Christian Rogobete (13 submissions) is the primary maintainer of multiple ecosystem-critical
> projects. If he disappears, the risk is not one pony-factor event — it's a correlated failure
> across the projects he maintains."*

```python
@dataclass
class KeystoneContributorResult:
    contributor_name: str
    dominant_repos: list[str]           # Repos where this contributor has PF=1
    total_pony_factor_repos: int
    aggregate_criticality: float        # Sum of criticality scores across dominant repos
    aggregate_criticality_pct: float    # Percentile of aggregate_criticality
    correlated_failure_score: float     # KCI = Σ(PF_flag × criticality_score)
    at_risk_downstream_packages: int    # Union of transitive dependents across all repos
    risk_narrative: str                 # "If {name} disappears, {N} packages across
                                        #  {M} projects would lose their primary maintainer,
                                        #  affecting {K} transitive dependents."

def compute_keystone_contributor_index(
    pony_results: dict,
    criticality_scores: dict,
    G_active,
) -> list[KeystoneContributorResult]:
    """
    Identify contributors whose absence would cascade across multiple critical projects.

    Algorithm:
      1. For each contributor, collect all repos where they have PF=1
      2. KCI = Σ(criticality_score[repo]) for those repos
      3. Compute union of transitive dependents across all dominant repos
      4. Sort by KCI descending

    The top result is likely christian-rogobete or orbitLens based on Airtable data.
    """
```

---

### `pg_atlas/reports/governance_report.py` (The Longitudinal Governance Instrument)

This is what makes PG Atlas a longitudinal governance instrument, not a one-shot analysis.
Each time the system runs, it generates a versioned, structured report that can be compared
against previous runs to track ecosystem fragility over time.

```python
@dataclass
class EcosystemSnapshot:
    """
    A complete, timestamped snapshot of the ecosystem's structural health.
    Serializable to JSON for longitudinal comparison.
    """
    snapshot_date: str                         # ISO 8601
    scf_round: str | None                      # e.g. "SCF #42" if run for a voting round
    total_active_projects: int
    total_active_repos: int
    max_kcore: int
    mean_hhi: float
    median_criticality: float
    pony_factor_rate: float                    # % of repos with PF=1
    maintenance_debt_surface_size: int         # Projects on the MDS
    gate_pass_rate: float
    top_critical_packages: list[dict]          # Top 10 by criticality
    keystone_contributors: list[dict]          # Top 5 KCI
    funding_efficiency_summary: dict           # FER tier distribution

def generate_governance_report(
    G_active,
    gate_results: list[MetricGateResult],
    mds: list[MaintenanceDebtEntry],
    kci: list[KeystoneContributorResult],
    df_scores: pd.DataFrame,
    pony_results: dict,
    config: PGAtlasConfig = DEFAULT_CONFIG,
    scf_round: str | None = None,
) -> EcosystemSnapshot:
    """
    Generate a complete ecosystem health snapshot.

    Saves snapshot to:
        04_implementation/snapshots/{date}_{scf_round}.json

    Returns the snapshot for immediate use.
    """

def compare_snapshots(
    snapshot_a: EcosystemSnapshot,
    snapshot_b: EcosystemSnapshot,
) -> dict:
    """
    Compute the delta between two snapshots.

    Returns a dict with:
        - metrics that improved / degraded
        - new entries on the Maintenance Debt Surface
        - contributors who became / left the keystone list
        - gate pass rate trend (up/down/stable)

    This enables the SCF to track whether investments are reducing fragility over time.
    """

def export_report_markdown(snapshot: EcosystemSnapshot, output_path: str) -> str:
    """
    Generate a human-readable Markdown governance report.

    Template structure:
    1. Executive Summary (2-3 sentences — answer the North Star question)
    2. Ecosystem Health Dashboard (key metrics table)
    3. Maintenance Debt Surface (watchlist — the most urgent output)
    4. Keystone Contributor Risk (who carries the ecosystem)
    5. Funding Efficiency Analysis (are critical projects proportionally funded?)
    6. Metric Gate Results (pass/fail with narratives)
    7. Appendix: Full metric tables
    """
```

---

### `pg_atlas/viz/plotly_graph.py` (Interactive D8 Component)

Port the static Figure 4 (dependency network map) from the POC to Plotly.
This is the artifact that makes PG Atlas tangible to non-technical stakeholders.

Visual encoding spec (from NORTH_STAR):
- **Node size** = criticality score (load-bearing packages are visually dominant)
- **Node color** = k-core membership tier (innermost core = darkest blue)
- **Node border / marker symbol** = pony factor flag (diamond = PF risk, circle = healthy)
- **Node opacity** = activity level (dormant = 0.3, active = 0.9)
- **Edge color** = bridge vs. regular (bridge edges = `#d29922` amber, others = `#484f58`)
- **Hover tooltip** = project name, criticality percentile, HHI, adoption score,
  top contributor, top contributor share, k-core number, last commit date

```python
import plotly.graph_objects as go
import networkx as nx

def build_dependency_figure(
    G_active: nx.DiGraph,
    criticality_scores: dict[str, int],
    pony_results: dict,
    core_numbers: dict[str, int],
    bridges: list[tuple],
    adoption_scores: dict[str, float],
    config: PGAtlasConfig = DEFAULT_CONFIG,
    title: str = "Stellar Ecosystem — Active Dependency Network",
    max_nodes: int = 300,
) -> go.Figure:
    """
    Build an interactive Plotly force-directed dependency graph.

    Uses NetworkX spring_layout for positions, seeded so known hub nodes
    (@stellar/js-xdr, @stellar/stellar-base, soroban-sdk) land near center.

    Returns a Plotly Figure suitable for embedding in Streamlit or the React dashboard.
    """

def export_graph_json(
    G_active: nx.DiGraph,
    criticality_scores: dict,
    pony_results: dict,
    core_numbers: dict,
) -> dict:
    """
    Export the dependency graph as a JSON-serializable dict for the React dashboard.

    Format:
    {
      "nodes": [{"id": str, "type": str, "criticality": int, "pct": float,
                 "hhi": float, "kcore": int, "adoption": float, ...}],
      "edges": [{"source": str, "target": str, "type": str, "is_bridge": bool}]
    }
    """
```

---

### `pg_atlas/viz/dashboard.py` (Streamlit MVP)

```python
def run_dashboard(
    snapshot: EcosystemSnapshot,
    gate_results: list[MetricGateResult],
    G_active,
    criticality_scores: dict,
    pony_results: dict,
    core_numbers: dict,
    bridges: list,
    df_scores: pd.DataFrame,
) -> None:
    """
    Streamlit dashboard with four pages:

    Page 1: Ecosystem Overview
        - Key metric KPIs (active repos, pony factor rate, gate pass rate)
        - Interactive dependency network graph (from plotly_graph.py)
        - Threshold sliders (adjusts gate results live)

    Page 2: Maintenance Debt Surface
        - Sortable table of MDS projects with urgency narrative
        - Drill-down: click project → see full contributor breakdown

    Page 3: Metric Gate Results
        - Filterable table: pass / fail / borderline
        - Per-project gate audit cards (full narrative)
        - Download CSV of gate decisions

    Page 4: Funding Efficiency
        - Criticality vs. Funding scatter (Figure 2 from POC, interactive)
        - Keystone Contributor Index table
        - North Star answer: text summary of funding alignment / misalignment

    Run with: streamlit run -m pg_atlas.viz.dashboard
    """
```

---

### `pg_atlas/api/endpoints.py` (FastAPI contribution for D7/A11)

```python
from fastapi import FastAPI, HTTPException
app = FastAPI(title="PG Atlas Analytics API", version="0.1.0")

@app.get("/scores/{project_id}")
def get_scores(project_id: str):
    """Return criticality, pony factor, adoption, k-core for a project."""

@app.get("/gate/{project_id}")
def get_gate_result(project_id: str):
    """Return the full MetricGateResult for a project including narratives."""

@app.get("/dependents/{package_purl}")
def get_dependents(package_purl: str, transitive: bool = False):
    """Return dependents of a package. transitive=true returns full BFS set."""

@app.get("/subgraph")
def get_active_subgraph(format: str = "edge_list"):
    """Return active subgraph as edge_list or node_link JSON."""

@app.get("/maintenance-debt")
def get_maintenance_debt_surface():
    """Return the current Maintenance Debt Surface watchlist."""

@app.get("/keystone-contributors")
def get_keystone_contributors():
    """Return the top Keystone Contributor Index results."""

@app.get("/snapshots")
def list_snapshots():
    """List all historical EcosystemSnapshots for longitudinal comparison."""

@app.get("/snapshots/compare")
def compare_snapshots(snapshot_a: str, snapshot_b: str):
    """Compare two snapshots and return the fragility delta."""
```

---

## 5. Test Suite Requirements

### `pg_atlas/tests/conftest.py`

```python
import pytest
import networkx as nx
from pg_atlas.config import DEFAULT_CONFIG

@pytest.fixture(scope="session")
def synthetic_graph():
    """
    Deterministic synthetic graph from the POC (SEED=41).
    Used as the shared baseline for all metric tests.
    Reproducible: same graph every time.
    """

@pytest.fixture(scope="session")
def active_subgraph(synthetic_graph):
    from pg_atlas.graph.active_subgraph import active_subgraph_projection
    G_active, _ = active_subgraph_projection(synthetic_graph, DEFAULT_CONFIG)
    return G_active
```

### Required test cases (minimum — add more as appropriate):

**test_active_subgraph.py**
- Dormant nodes (days_since_commit > 90) are excluded
- Active nodes (days_since_commit <= 90) are retained
- Project and Contributor nodes are always retained regardless of activity
- Induced subgraph preserves edge types correctly
- `active_window_days` parameter changes the output deterministically

**test_criticality.py**
- Hub packages (@stellar/js-xdr equivalent) score highest
- Leaf packages (no dependents) score 0
- Criticality monotonically increases with more active dependents
- Temporal decay criticality <= base criticality for all nodes
- Percentile ranks are in [0, 100]

**test_pony_factor.py**
- Repo where contributor has 80% of commits → PF=1, HHI > 6400
- Repo with 5 equal contributors → PF=0, HHI = 2000
- Shannon entropy is maximized for uniform distribution
- Risk tiers map correctly to HHI thresholds in config

**test_adoption.py**
- All percentile values in [0, 100]
- Composite adoption score is mean of component percentiles
- Node with highest downloads does not necessarily have highest composite score
  (validates that forks/stars contribute)

**test_gate.py**
- Project failing all 3 signals → passed=False, signals_passed=0
- Project passing exactly 2 → passed=True, borderline=True
- Project passing all 3 → passed=True, borderline=False
- Each GateSignalResult narrative is non-empty
- gate_explanation references specific metric values
- Changing config thresholds changes gate outcomes deterministically

---

## 6. Code Standards

**Python version:** 3.12+

**Style:** Follow PEP 8. Use type hints everywhere. Use `dataclasses` for structured outputs.

**No hardcoded constants** outside `config.py`. If a number appears in a metric module that
isn't an algorithm constant (e.g., 10_000 in the HHI formula), it belongs in config.py.

**Logging:** Use Python's `logging` module. INFO for progress. WARNING for recoverable failures
(e.g., inaccessible repos in A7). Never suppress exceptions silently.

**Error handling:** External API calls (deps.dev, GitHub, crates.io) must handle:
- Rate limit responses (429) → exponential backoff, max 3 retries
- Not found (404) → log WARNING, return None/empty result
- Network timeout → log WARNING, mark as inaccessible

**Documentation:** Every public function has a docstring with:
- What it computes/returns (not just what it does mechanically)
- Algorithm reference (e.g., "BFS on reversed dependency graph — equivalent to trophic cascade
  reachability in ecological networks")
- Parameter descriptions for non-obvious params
- Complexity annotation for any O(V²) or worse algorithm

**Imports:** All `pg_atlas` modules import config via:
```python
from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig
```
Never import config values directly — always pass config as a parameter to enable testing
with alternative thresholds.

---

## 7. Interface Contract with Alex Olieman (D5)

The `pg_atlas/storage/schema.py` and `pg_atlas/graph/builder.py` must be designed to accept
Alex's PostgreSQL schema once A2 is locked (target: March 8). Until then:

- `build_graph_from_db()` returns an empty graph with a log message: "PostgreSQL schema
  not yet locked (A2 pending). Use build_graph_from_csv() for prototype operations."
- All metric computation, gate logic, and visualization must work on the CSV-built graph

**Anticipated schema interface (update when Alex finalizes A2):**

```sql
-- Repo vertex (Alex's D5 schema — pending)
repo (
    id            TEXT PRIMARY KEY,   -- PURL: pkg:npm/stellar-sdk@13.3.0
    project_id    TEXT,               -- FK → project.id
    ecosystem     TEXT,               -- npm | cargo | pypi | go
    latest_commit_date  TIMESTAMP,
    archived      BOOL DEFAULT FALSE,
    adoption_stars      INT,
    adoption_forks      INT,
    adoption_downloads  BIGINT,
    criticality_score   INT,          -- Written back by Jay's D6
    pony_factor         INT,          -- Written back by Jay's D6
    hhi                 FLOAT,        -- Written back by Jay's D6
    adoption_score      FLOAT         -- Written back by Jay's D6
);

-- Contributor vertex
contributor (
    id            TEXT PRIMARY KEY,
    display_name  TEXT,
    email_aliases TEXT[]
);

-- Dependency edge
depends_on (
    from_repo     TEXT REFERENCES repo(id),
    to_repo       TEXT,
    version_range TEXT,
    confidence    TEXT    -- 'inferred_shadow' | 'sbom_direct'
);

-- Contribution edge
contributed_to (
    contributor_id   TEXT REFERENCES contributor(id),
    repo_id          TEXT REFERENCES repo(id),
    commits          INT,
    first_commit_date DATE,
    last_commit_date  DATE,
    PRIMARY KEY (contributor_id, repo_id)
);
```

**Jay's write-back pattern (after D6 computation):**
```python
def write_scores_to_db(conn, criticality_scores, pony_results, adoption_scores):
    """
    Write computed metric scores back to repo table.
    Called after each full metric computation cycle.
    """
```

---

## 8. Retrospective Design (The Longitudinal Instrument)

Before the Q2 vote opens, define and record the validation methodology so results can be
measured post-vote. This is what makes PG Atlas a longitudinal instrument.

**Pre-Q2 (April):** For each project that applies to the Q2 Public Goods Award:
1. Record the MetricGateResult (pass/fail, which signals, all metric values)
2. Save as an `EcosystemSnapshot` via `generate_governance_report(scf_round="SCF Q2 2026")`

**Post-Q2 (June):** Run `compare_snapshots()` against the pre-vote snapshot and compare:
- Gate pass/fail decisions vs. expert review outcomes
- Gate pass/fail decisions vs. community vote outcomes
- Borderline cases: were they treated correctly by human reviewers?
- False positives/negatives: which gate failures did experts override, and why?

**Calibration output:** Adjust `PGAtlasConfig` thresholds based on retrospective analysis and
document the calibration rationale in `05_strategy/CALIBRATION_LOG.md`.

**Fragility trajectory:** Compare ecosystem-level metrics (pony_factor_rate, mean_hhi,
maintenance_debt_surface_size) between the pre-Q2 and post-Q2 snapshots to answer:
*"Did the SCF's Q2 investment in public goods maintenance reduce ecosystem fragility?"*

---

## 9. Acceptance Criteria Checklist

### A7 — Git Log Parser (Due March 22)
- [ ] Runs against all 338 repos in `A7_submission_github_repos.csv` without crashing
- [ ] Handles inaccessible repos gracefully (WARNING log, continues processing)
- [ ] Outputs structured `RepoContributionResult` for each repo
- [ ] Computes days_since_latest_commit for all accessible repos
- [ ] Produces contributor edges consumable by `graph.enrich_graph_with_ingestion()`
- [ ] Test: `test_git_log_parser.py` passes

### A6 — Active Subgraph Projection (Due March 22)
- [ ] `active_subgraph_projection()` in `pg_atlas.graph.active_subgraph` matches POC behavior
- [ ] Graph built from real CSV data (not synthetic)
- [ ] Activity signals sourced from real git log parser output
- [ ] Configurable via `config.active_window_days`
- [ ] Test: `test_active_subgraph.py` passes

### A9 — Criticality + Pony Factor (Due April 12)
- [ ] Criticality scores computed on real dependency graph (deps.dev + crates.io)
- [ ] Pony factor computed on real contributor data (A7 output)
- [ ] HHI and Shannon entropy populated for all repos
- [ ] Both metrics visible in Streamlit dashboard
- [ ] Both metrics accessible via `/scores/{project_id}` API endpoint
- [ ] Test: `test_criticality.py` and `test_pony_factor.py` pass

### A10 — Adoption Signals (Due April 12)
- [ ] `adoption_downloads` from real npm/PyPI/crates.io API calls
- [ ] `adoption_stars` and `adoption_forks` from deps.dev `GetProject`
- [ ] Percentile normalization produces values in [0, 100]
- [ ] Composite adoption score accessible via API
- [ ] Test: `test_adoption.py` passes

### Metric Gate (Due April 12 — required for Q2 vote)
- [ ] `evaluate_project()` produces MetricGateResult with full narrative
- [ ] `evaluate_all_projects()` runs against all 86 seed projects
- [ ] Gate explanation is non-empty for every result
- [ ] Thresholds are configurable (no hardcoding)
- [ ] `gate_summary()` reports pass rate and failure reasons
- [ ] Test: `test_gate.py` passes

### Maintenance Debt Surface (Due April 12)
- [ ] Correctly identifies projects satisfying all 3 conditions
- [ ] Urgency narrative is populated for each entry
- [ ] Accessible via `/maintenance-debt` API endpoint
- [ ] Surfaced prominently in Streamlit dashboard Page 2

### Strategic Outputs (Due April 12)
- [ ] Keystone Contributor Index computed and sorted by KCI
- [ ] Funding Efficiency Ratio computed for all funded projects
- [ ] Governance report exports to Markdown (`export_report_markdown()`)
- [ ] `EcosystemSnapshot` saves to JSON for future comparison

---

## 10. Execution Order Summary

```
DAY 1-2  │ Alpha: scaffold + config + POC bug fix + conftest
         │ Beta:  A7 git_log_parser start
         │
DAY 3-7  │ Alpha: builder.py (CSV mode) + all metrics/* ports
         │ Beta:  A7 complete + deps_dev_client + crates_io_client
         │
DAY 8-14 │ Gamma: gate.py + maintenance_debt + keystone_contributor + FER + reports/
         │ Alpha: tests (all except git_log_parser)
         │
DAY 14-21│ Delta: plotly_graph + dashboard + endpoints
         │
DAY 21-25│ All: integration on real data + calibration + test suite green
```

---

*Brief authored February 2026 — Jay Gutierrez, PhD*
*SCF #41 — Building the Backbone: PG Atlas*
*North Star: "We mapped the Stellar ecosystem's dependency graph — here's what the network
science says about which public goods are load-bearing."*
