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
02_analysis/         Intelligence briefs — deps.dev, data exploitation
03_deliverables/     Per-deliverable design docs (A6, A7, A9, A10)
04_implementation/   Algorithm sketches, prototype code
06_demos/            Interactive prototypes and CLI tools (e.g., A6 graph simulation)
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

## Jay's Deliverables & Deadlines

| Deliverable | Tranche | Deadline | Status |
|---|---|---|---|
| A6 — Active Subgraph Projection (algorithm) | T2 | Mar 22 | Prototyped (`06_demos/01_active_subgraph_prototype`) |
| A7 — Git Log Parser & Contributor Statistics | T2 | Mar 22 | Not started |
| A9 — Criticality Scores + Pony Factor | T3 | Apr 12 | Prototyped (`06_demos/01_active_subgraph_prototype`) |
| A10 — Adoption Signals Aggregation | T3 | Apr 12 | Prototyped (`06_demos/01_active_subgraph_prototype`) |

## Critical Dependency

**A2 (PostgreSQL schema, Alex's deliverable) must be locked before Jay can write any production graph code.**
The `Repo`, `ExternalRepo`, and `depends_on` edge table definitions are the foundation for all of Jay's work.
