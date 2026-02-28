# SCF #41 — PG Atlas | Jay Gutierrez Workspace

**Project**: Building the Backbone: SCF Public Goods Maintenance
**Vote window**: Feb 23 – Mar 1, 2026 | **Budget**: $150K | **Jay's stake**: ~$40–45K

---

## 🌍 Platform Overview

The Stellar Community Fund's Public Goods Award has funded open-source tools, libraries, and infrastructure in the Stellar/Soroban ecosystem. Historically, funding decisions have relied on noisy, subjective signals. **PG Atlas** is the solution: an objective, graph-derived metrics backbone that provides transparent, verifiable signals for funding decisions.

PG Atlas powers the **Layer 1 Metric Gate** in the SCF's new three-layer decision stack (Metrics → Expert Review → Community Vote). By parsing the software dependency graph of the ecosystem, PG Atlas answers critical questions mathematically:
- Which packages are structural linchpins? (Criticality)
- Which packages are maintained by a single person who could disappear tomorrow? (Pony Factor)
- Which packages have the highest community adoption? (Adoption Signals)

> 📘 **Executive Summary**: For a detailed technical breakdown of the topological algorithms and the graph intelligence prototype, please read the [PG Atlas: Graph Intelligence Prototype Report](06_demos/01_active_subgraph_prototype/TEAM_REPORT.md).

---

## Directory Map

```
00_context/          Proposal PDF, full project brief, Jay's role & scope doc
01_data/raw/         Original Airtable CSVs (do not modify)
01_data/processed/   Cleaned extracts ready for use in deliverables
01_data/real/        ★ Real API output CSVs (contributor_stats, dependency_edges, adoption_signals)
02_analysis/         Intelligence briefs — deps.dev, data exploitation
03_deliverables/     Per-deliverable design docs (A6, A7, A9, A10)
04_implementation/   Production algorithm code + snapshots
04_implementation/snapshots/  ★ Governance reports + EcosystemSnapshot JSON
05_strategy/         NORTH_STAR.md — strategic compass
06_demos/            Interactive prototypes and CLI tools (e.g., A6 graph simulation)
pg_atlas/            ★ Production Python package (50 modules, 208 unit tests)
```

## Key Files

| File | Purpose |
|---|---|
| `00_context/Project_Full_Context.md` | Complete 14-deliverable map, timeline, team dynamic |
| `00_context/PG_Atlas_Jay_Role_Scope.md` | Jay's deliverables, effort estimates, architecture |
| `00_context/q2-experiment-proposal.pdf` | Official SCF #41 proposal (source of truth) |
| `02_analysis/Data_Source_Intelligence_Brief.md` | deps.dev API capabilities, Cargo gap, 5-phase bootstrap playbook |
| `02_analysis/Airtable_Data_Exploitation_Brief.md` | Strategic analysis of SCF Airtable → PG Atlas pipeline |
| `01_data/processed/A5_pg_candidate_seed_list.csv` | **86 PG candidates** ready for A5 OpenGrants bootstrapper |
| `01_data/processed/A5_all_active_with_github.csv` | 271 active projects with GitHub (broader graph seed) |
| `01_data/processed/A6_github_orgs_seed.csv` | 78 GitHub orgs — root nodes for A6 registry crawlers |
| `01_data/processed/A7_submission_github_repos.csv` | 338 submission-level repos for A7 git log parser |
| `pg_atlas/WHAT_WAS_BUILT.md` | Complete technical reference for the production package |

## Quick Start

```bash
# Install dependencies (Python 3.12)
source .venv/bin/activate

# Run the full pipeline (reads GITHUB_TOKEN from .env automatically)
python -m pg_atlas run --scf-round "SCF Q2 2026"

# Check output status
python -m pg_atlas status

# Run all unit tests
python -m pytest pg_atlas/tests/ -x -q --ignore=pg_atlas/tests/test_integration_real_api.py
```

## Jay's Deliverables & Status

| Deliverable | Tranche | Deadline | Status |
|---|---|---|---|
| A6 — Active Subgraph Projection | T2 | Mar 22 | **Complete** — `pg_atlas/graph/active_subgraph.py`, 19 tests, verified on 304 real repos |
| A7 — Git Log Parser & Contributor Statistics | T2 | Mar 22 | **Complete** — `pg_atlas/ingestion/git_log_parser.py`, 21 tests, 304 repos parsed, 161 contribution edges |
| A9 — Criticality Scores + Pony Factor | T3 | Apr 12 | **Complete** — `pg_atlas/metrics/criticality.py` + `pony_factor.py`, 45 tests, 42 repos scored |
| A10 — Adoption Signals Aggregation | T3 | Apr 12 | **Complete** — `pg_atlas/metrics/adoption.py`, 15 tests, npm/PyPI/GitHub signals normalized |

**Bonus deliverables built:**
- Layer 1 Metric Gate (2-of-3 voting with audit narratives)
- Maintenance Debt Surface, Keystone Contributor Index, Funding Efficiency Ratio
- EcosystemSnapshot governance report (longitudinal, JSON + Markdown export)
- Interactive Plotly force-directed graph + Streamlit dashboard (stubs)
- FastAPI analytics endpoints (8 endpoints, stub)
- Checkpoint/resume ingestion orchestrator
- 208 unit tests + 18 integration tests

## Real Pipeline Results (2026-02-27, SCF Q2 2026)

| Metric | Value |
|---|---|
| Repos parsed (A7) | 304 |
| Contribution edges | 161 |
| Dependency edges (crates.io) | 149 |
| Active nodes (90-day window) | 262 |
| Dormant nodes pruned | 372 |
| Repos scored on all metrics | 42 |
| Gate PASSED | **4 / 40 (10%)** |
| Pony factor flagged | **34 / 40 (85%)** |

**North Star Answer:** *The Metric Gate passes 10% of projects (4/40) for Expert Review. Pony factor risk is prevalent across 85% of active repos — a critical finding for SCF funding decisions in the Soroban ecosystem.*

## Critical Dependency

**A2 (PostgreSQL schema, Alex's deliverable) must be locked before production PostgreSQL integration can be completed.**
The graph builder stub (`pg_atlas/graph/builder.py::build_graph_from_db()`) and sync module (`pg_atlas/graph/sync.py`) are ready to be wired to Alex's schema. Until then, all metric computation runs from CSV seed data + real API ingestion.
