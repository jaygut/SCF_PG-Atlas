# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

---

## Project Context

This is the **Jay Gutierrez workspace** for SCF #41 — *Building the Backbone: SCF Public Goods Maintenance*. PG Atlas is an objective, graph-derived metrics backbone for the Stellar Community Fund's public goods funding decisions. It powers the **Layer 1 Metric Gate** in SCF's three-layer decision stack (Metrics → Expert Review → Community Vote).

Jay's deliverables:
- **A6** — Active Subgraph Projection (co-lead with Alex Olieman) — T2, due Mar 22
- **A7** — Git Log Parser & Contributor Statistics — T2, due Mar 22
- **A9** — Criticality Scores + Pony Factor — T3, due ~Apr 12
- **A10** — Adoption Signals Aggregation — T3, due ~Apr 12

**Critical blocker**: A2 (PostgreSQL schema, owned by Alex) must be locked before production graph code can be written. PostgreSQL integration is stubbed in `pg_atlas/graph/sync.py` and `pg_atlas/graph/builder.py::build_graph_from_db()`.

---

## Running the Prototype (Demo Notebook)

```bash
source .venv/bin/activate
cd 06_demos/01_active_subgraph_prototype/
python build_notebook.py
jupyter notebook PG_Atlas_A6_Prototype.ipynb
```

---

## Running the Production Package — CLI

The production package has a full CLI entry point (`python -m pg_atlas`). GITHUB_TOKEN is auto-loaded from `.env` in the repo root.

```bash
source .venv/bin/activate

# Full pipeline — ingestion + metrics + gate + report (~10s on subsequent runs, ~3min first run)
python -m pg_atlas run --scf-round "SCF Q2 2026"

# Ingestion only (A7 git log + deps.dev + crates.io + npm + PyPI)
python -m pg_atlas ingest

# Metrics only — uses existing 01_data/real/ CSVs, runs in ~2s
python -m pg_atlas metrics --report-path 04_implementation/snapshots/my_report.md

# Check status of output files and checkpoints (no API calls)
python -m pg_atlas status

# Force full re-ingestion (clears all checkpoints)
python -m pg_atlas run --fresh --scf-round "SCF Q2 2026"

# Unit tests (208 tests, <2s, no network)
python -m pytest pg_atlas/tests/ -x -q --ignore=pg_atlas/tests/test_integration_real_api.py

# Integration tests against real APIs
python -m pytest pg_atlas/tests/test_integration_real_api.py --run-integration -v
```

The `.venv` (Python 3.12) includes NetworkX, pandas, numpy, matplotlib, and Jupyter.

---

## Repository Structure

```
00_context/          Proposal context, Jay's role/scope, full 14-deliverable map
01_data/raw/         Original Airtable CSVs — do not modify
01_data/processed/   Cleaned seed data ready for deliverables
02_analysis/         Intelligence briefs on deps.dev API and Airtable data
03_deliverables/     Deliverable artifacts (currently one .docx report)
04_implementation/   Planned location for production algorithm code
05_strategy/         NORTH_STAR.md — strategic compass
06_demos/            Prototype code and figures
```

Key files to read before building anything:
- `05_strategy/NORTH_STAR.md` — metric architecture, design rationale, implementation sequence
- `00_context/PG_Atlas_Jay_Role_Scope.md` — Jay's deliverables, effort estimates, interface contracts with Alex
- `00_context/Project_Full_Context.md` — complete team map, timeline, tranche breakdown
- `02_analysis/Data_Source_Intelligence_Brief.md` — deps.dev API capabilities and the critical Cargo/Rust blind spot
- `06_demos/01_active_subgraph_prototype/TEAM_REPORT.md` — methodological validation of all core algorithms

---

## Architecture

### Three Graph Layers

The system encodes three concurrent graph layers over a PostgreSQL backend (D5, Alex's schema):

**Layer 1 — Package Dependency Graph**
- Vertices: `Repo`, `ExternalRepo`
- Edges: `depends_on`
- Source: SBOM files, deps.dev API, crates.io API (for Rust/Cargo)
- Supports: Criticality scoring, k-core decomposition, bridge edge detection

**Layer 2 — Contributor Graph**
- Vertices: `Contributor`, `Repo`
- Edges: `contributed_to`
- Source: Git log parser (A7)
- Supports: Pony Factor (binary), HHI (continuous concentration), Shannon entropy (tail diversity)

**Layer 3 — Funding Graph**
- Vertices: `Project`, `SCFRound`
- Edges: `funded_by`
- Source: Airtable CSVs (already processed in `01_data/processed/`)
- Supports: Funding efficiency ratio, underfunded critical infrastructure discovery

### Metric Computation Pipeline (D6)

```
PostgreSQL (persistent store)
    ↓  graph construction
NetworkX DiGraph (in-memory)
    ↓  A6: active subgraph projection (filter: ≥1 release/commit in 90d OR not archived)
Filtered active subgraph
    ↓  A9: criticality BFS (transitive dependent count) + pony factor + HHI + Shannon entropy
    ↓  A10: adoption signals (registry downloads + GitHub stars/forks, percentile-normalized)
    ↓  Gate logic: 2-of-3 signal voting (criticality ∩ pony factor ∩ adoption)
Project pass/fail + percentile scores → written back to PostgreSQL
```

All metrics are expressed as **percentile ranks** within the PG Atlas universe, not raw values.

### Interface Contract (Jay ↔ Alex)

- Alex owns: PostgreSQL schema, ingestion pipeline, API server framework (FastAPI)
- Jay owns: NetworkX graph construction layer, all metric algorithms, analytics API endpoints, force-directed graph visualization component (D8)
- Jay's code reads from and writes back to the schema Alex defines in A2/D5

### Metric Definitions

| Metric | Type | Definition |
|---|---|---|
| Criticality Score | Continuous | BFS transitive dependent count in active subgraph |
| Pony Factor | Binary flag | Single contributor ≥50% of commits |
| HHI | Continuous (0–10K) | Herfindahl-Hirschman Index on contributor commit shares |
| Shannon Entropy | Continuous | Information-theoretic contributor diversity |
| Adoption | Composite | Percentile of (registry downloads + GitHub stars + forks) |
| K-Core | Integer | Core number in k-core decomposition |

**Gate logic**: A project advances if ≥2 of {Criticality, Pony Factor, Adoption} exceed threshold.

---

## Seed Data

| File | Contents |
|---|---|
| `01_data/processed/A5_pg_candidate_seed_list.csv` | 86 PG candidates with GitHub URLs, funding, categories |
| `01_data/processed/A5_all_active_with_github.csv` | 271 active projects with GitHub presence |
| `01_data/processed/A6_github_orgs_seed.csv` | 78 GitHub orgs — root nodes for dependency crawler |
| `01_data/processed/A7_submission_github_repos.csv` | 338 submission repos for git log parser |

Raw Airtable CSVs in `01_data/raw/` must not be modified.

---

## Key Constraints & Known Gaps

- **Cargo/Rust blind spot**: deps.dev returns `dependentCount=0` for all Cargo packages. The Soroban ecosystem is 100% Rust. Reverse dependencies for Rust packages require direct crates.io API calls.
- **deps.dev rate limit**: 100 req/min per IP. 86 projects × ~5 requests = ~430 total, distributes over ~5 minutes. Requires batching logic.
- **Active subgraph threshold**: ≥1 release or commit in last 90 days OR repo not archived. This is a calibration decision — document any changes with rationale.
- **Metric thresholds are configurable**: No constants should be hardcoded. All gate thresholds must be tunable parameters with documented defaults.
- **Integration tests available**: 18 integration tests in `pg_atlas/tests/test_integration_real_api.py` validate all ingestion clients against real APIs. Skipped by default; run with `--run-integration`.
- **Real data ingestion available**: `pg_atlas/ingestion/orchestrator.py` provides `run_full_ingestion()` to collect live data from GitHub, deps.dev, crates.io, npm, and PyPI. Supports checkpoint/resume and writes canonical CSVs to `01_data/real/`. The pipeline supports `real_data=True` to run ingestion before metric computation.

---

## Planned Production Stack (Not Yet Built)

When A2 (PostgreSQL schema) is locked, the production system will add:
- `psycopg2` / `asyncpg` — PostgreSQL client
- `FastAPI` — API layer (D7)
- `Streamlit` or `Dash` — dashboard (D8)
- GitHub API client — for A7 git log parsing and repo enumeration
- crates.io API client — for Rust reverse dependency lookups
