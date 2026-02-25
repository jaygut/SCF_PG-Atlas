# SCF #41 — Building the Backbone: Full Project Context
**Jay Gutierrez Reference Document** | February 2026

---

## ⚡ Status: LIVE VOTE — Feb 23 through Mar 1, 2026

The proposal is in **active community voting right now**. This is the SCF Pilot vote that determines
whether the $150K engagement is approved. If it passes, the clock starts immediately — T1 closes
**March 8**, T2 closes **March 22**, and PG Atlas v0 must be operational before the Q2 Public Goods
Award voting round opens in **April 2026**.

---

## The Full Project in One Frame

This is a **$150,000, 7-week build** producing two complementary systems:

1. **Tansu** (existing governance platform) gets enhanced with NQG score integration and soulbound
   NFT credentials — this is primarily Pamphile (tupui) and Progress (Koxy).
2. **PG Atlas** (new system, built from scratch) becomes the objective metrics backbone for all
   public goods funding decisions — this is primarily Alex and Jay.

The deadline is non-negotiable: PG Atlas v0 must serve the April 2026 Q2 voting round. That is the
experiment's success criterion.

---

## The Fourteen Deliverables — Complete Map

### Tranche 1 — 19% (~$28.5K) | Closes March 8

| ID | Deliverable | Budget | Owner | Jay's Role |
|---|---|---|---|---|
| T1 | SCF Governance Space (Tansu) | $2K | Pamphile | None |
| A1 | Repo Scaffolding & CI/CD | $3K | Alex | Recipient (repos Jay will work in) |
| A2 | PostgreSQL Schema & Hosting | $5K | Alex | **Input** — Jay's NetworkX layer depends on schema |
| A3 | FastAPI App Scaffold + SBOM Webhook | $9K | Alex | **Input** — Jay's API endpoints extend this scaffold |
| A4 | SBOM GitHub Action | $6K | Alex/Koxy | None |
| A5 | OpenGrants Project Bootstrapper | $4K | Alex | None (but seeds Jay's graph) |

**Jay in T1**: No direct deliverable ownership, but A2 (schema) is the most critical dependency to
watch — the PostgreSQL vertex/edge schema is the foundation Jay's NetworkX graph layer builds on.
T1 is the period to align with Alex on the data model interface contract.

### Tranche 2 — 33% (~$49.5K) | Closes March 22

| ID | Deliverable | Budget | Owner | Jay's Role |
|---|---|---|---|---|
| T2 | NQG Score Integration (Tansu) | $15K | Pamphile | None |
| **A6** | **Registry Crawlers + Active Subgraph Projection** | **$16K** | **Alex + Jay** | **CO-LEAD** |
| **A7** | **Git Log Parser & Contributor Statistics** | **$10K** | **Jay** | **PRIMARY OWNER** |
| A8 | SBOM Processing Pipeline | $8K | Alex | **Contributor** (graph reload after SBOM ingest) |

**Jay in T2**: Two deliverables, one owned outright. This is the first tranche where Jay is on the
critical path.

**A6 — Registry Crawlers + Active Subgraph Projection ($16K)**

Note that A6 bundles two things: the registry crawlers AND the active subgraph projection algorithm.
The scoping assumed 4 separate crawlers: npm, crates.io, PyPI, Go proxy. The deps.dev intelligence
brief shows this can be significantly simplified:

- **npm**: deps.dev `GetDependencies` replaces a custom npm crawler for forward deps. Saves ~3-4
  days of crawler work.
- **PyPI**: Same — deps.dev covers it.
- **crates.io**: deps.dev handles forward dependencies but NOT reverse (who uses soroban-sdk). A
  targeted crates.io API call is still needed for the reverse direction.
- **Go proxy**: deps.dev covers Go modules.

The active subgraph projection (BFS from active leaves on reversed graph) is Jay's algorithm. It is
the prerequisite for everything in T3. It must be solid by March 22.

**A7 — Git Log Parser ($10K) — Jay Primary**

Acceptance criteria from the proposal:
1. Runs against all Stellar public goods repos (plus others on request)
2. Populates `Contributor` vertices and `contributed_to` edges with commit counts, first/last dates
3. Updates `Repo.latest_commit_date` for all processed repos
4. Handles inaccessible repos gracefully (logged, not fatal)

Implementation note from the ingestion doc: reuse patterns from
[Scientific Python devstats](https://devstats.scientific-python.org/_generated/scipy/) — Pamphile
maintains SciPy and will have direct knowledge of this codebase.

### Tranche 3 — 48% (~$72K) | Closes ~April 12

| ID | Deliverable | Budget | Owner | Jay's Role |
|---|---|---|---|---|
| T3 | NQG Soulbound NFT (SEP-50) | $15K | Koxy | None |
| **A9** | **Criticality Scores + Pony Factor Materialization** | ~$12K est. | **Jay** | **PRIMARY OWNER** |
| **A10** | **Adoption Signals Aggregation** | ~$8K est. | **Jay** | **PRIMARY OWNER** |
| **A11** | **REST API + TypeScript SDK** | $15K | Alex + Jay | **Contributor** (analytics endpoints) |
| **A12** | **React Dashboard** | $15K | Alex | **Contributor** (graph viz component) |
| A13 | Deployment & Operations | $10K | Alex | Contributor |
| A14 | Community Feedback Mechanisms | $3K | Alex | None |

**Jay in T3**: The entire analytical layer is Jay's. A9 and A10 are the headline deliverables that
determine whether PG Atlas can serve the April voting round. If these aren't done, the Metric Gate
has no signal.

**A9 — Criticality Scores + Pony Factor ($12K est.) — Jay Primary**

Acceptance criteria (inferred from spec):
1. Criticality score materialized on every `Repo` row (transitive active dependent count)
2. Project-level criticality = SUM of repo criticality scores
3. Pony factor materialized on every `Repo` row (min contributors for ≥50% commits)
4. Project-level pony factor = pony factor computed over union of unique contributors across all project repos
5. Both metrics visible via API and triggering risk flags in dashboard (pony_factor = 1 → red)

**A10 — Adoption Signals ($8K est.) — Jay Primary**

Acceptance criteria (inferred from spec):
1. `adoption_downloads` populated from npm/crates.io/PyPI registry APIs (last 30 days)
2. `adoption_stars` and `adoption_forks` populated from deps.dev `GetProject` calls
3. Per-repo adoption score normalized (percentile rank or log-scale) across all repos
4. Project-level `adoption_score` aggregated from repo-level signals

---

## Jay's Complete Deliverable Stack

Reading across all three tranches:

| Deliverable | Tranche | Budget | Type |
|---|---|---|---|
| A6 — Active Subgraph Projection (within Registry Crawlers) | T2 | Part of $16K | Primary Algorithm |
| A7 — Git Log Parser & Contributor Statistics | T2 | $10K | Primary Owner |
| A8 — SBOM Processing: NetworkX graph reload | T2 | Part of $8K | Contributor |
| A9 — Criticality Scores & Pony Factor | T3 | ~$12K | Primary Owner |
| A10 — Adoption Signals | T3 | ~$8K | Primary Owner |
| A11 — REST API: Analytics Endpoints | T3 | Part of $15K | Contributor |
| A12 — Dashboard: Graph Visualization | T3 | Part of $15K | Contributor |
| **Estimated Jay Total** | | **~$40–45K** | |

---

## Jay's Formal Bio in the Proposal

The proposal contains two versions of Jay's profile:

**Short (public-facing)**:
> "Jay Gutierrez, PhD, is a computational systems scientist specializing in graph-based intelligence.
> He's operated knowledge graphs with 30M+ nodes using network science like k-core decomposition and
> centrality analysis. His expertise covers algorithms (NetworkX, igraph), databases (Neo4j), and
> pipelines (GraphRAG, LangGraph) in Python for scalable risk quantification in public goods."

**Long (technical)**:
> "Jay has built and operated production-scale knowledge graphs exceeding 30 million nodes and 170
> million relationships, applying network science methods including k-core decomposition, cascade
> modeling, centrality analysis, and probabilistic link inference across complex, multi-domain
> systems. His full-stack graph proficiency spans algorithmic design (NetworkX, igraph, ggraph)
> through graph database engineering (Neo4j, Cypher) to agentic reasoning pipelines (GraphRAG,
> LangGraph), with production implementations across Python and R. He specializes in translating
> abstract network topology into decision-grade intelligence, formally encoding domain knowledge as
> bridge axioms between systems, enabling risk quantification, scenario modeling, and cross-domain
> pattern recognition at scale. His core differentiator is the ability to simultaneously hold the
> mathematical structure of a system and its real-world consequence: treating any complex domain,
> e.g., ecological, financial, biological, organizational, as an interconnected network whose
> structural properties reveal what aggregate metrics conceal."

This is the exact framing the team is using to position Jay publicly. His deliverables (A9, A10,
active subgraph in A6) need to deliver precisely on this framing — decision-grade graph intelligence,
not just metric calculation.

---

## The Airtable — What It Actually Is

The URL `https://communityfund.stellar.org/dashboard/submissions/recC2cGO6rZSYudtq` is itself
structured around an Airtable record ID (`recC2cGO6rZSYudtq`). The SCF community fund dashboard is
**built on top of Airtable** — it's the proposal management system. The shared Airtable view Jay was
given likely shows the **existing funded PG projects** — the current roster of public goods that need
to be bootstrapped as `Project` vertices in PG Atlas.

This means:
- The Airtable is **the ground truth source of the seed project list** (>150 projects per A5
  acceptance criteria)
- It requires human access (SCF team) to export — not a programmatic pipeline
- The bridge to programmatic access is OpenGrants (A5 handles this)
- The Airtable's `git_org_url` fields are the keys that unlock Repo discovery in the reference graph
  bootstrap

---

## deps.dev Strategic Impact on A6 Budget

The $16K scoped for A6 assumed building 4 separate registry crawlers from scratch. The deps.dev
intelligence work revealed:

| Crawler | deps.dev replaces? | Remaining work | Effort saved |
|---|---|---|---|
| npm forward deps | ✅ `GetDependencies` endpoint | Download counts only (npm API) | ~3–4 days |
| PyPI forward deps | ✅ `GetDependencies` endpoint | Download counts only (pypistats) | ~2–3 days |
| crates.io forward deps | ✅ `GetDependencies` endpoint | Reverse deps (crates.io API) | ~1–2 days |
| Go proxy | ✅ `GetDependencies` endpoint | — | ~1 day |
| Repo enrichment (stars, forks) | ✅ `GetProject` endpoint | — | ~1 day |
| OpenSSF activity signal | ✅ `Maintained` check via `GetProject` | — | Bonus |

**Total scope reduction on A6**: ~8–11 days of crawler work eliminated, replaced by one clean deps.dev
API client. The $16K can deliver more — with remaining effort going into the active subgraph
projection algorithm and the crates.io reverse-dep path for Soroban packages.

**The one gap that requires direct registry access**: `adoption_downloads` — deps.dev does not expose
download counts. These need three separate calls:
- npm: `api.npmjs.org/downloads/point/last-month/{package}`
- PyPI: `pypistats.org/api/packages/{package}/recent`
- Cargo: `crates.io/api/v1/crates/{crate}` (includes `downloads` field)

This is ~1 day of work per registry, and naturally belongs in A10 (Adoption Signals) rather than A6.

---

## Critical Path and Timeline

```
Now (Feb 24)  ──►  Mar 8 (T1) ──►  Mar 22 (T2) ──►  Apr 12 (T3/v0) ──►  Q2 Vote
    │                  │                 │                  │
    │             Schema done        Crawlers +         Metrics +
    │             API scaffold       Git parser +       API + Dashboard
    │             OpenGrants         Active subgraph    LIVE
    │             seeded             projection
    │
  VOTE
  active
  now
```

**Jay's two hard deadlines:**
- **March 22**: A7 (git log parser) fully passing acceptance criteria. Active subgraph projection
  within A6 producing correct output.
- **April 12**: A9 (criticality + pony factor) materialized. A10 (adoption signals) populated.
  Both surfaced in dashboard. Both accessible via API.

---

## The Team Dynamic — Who Does What

| Pilot | Strength | Owns | Jay's interface with them |
|---|---|---|---|
| **Alex Olieman** | Data infrastructure, knowledge graphs, API design | A1, A2, A3, A4, A5, A8, A11, A12, A13 | Daily — shared schema, API contracts, graph sync |
| **Pamphile Roy** | Scientific Python, SciPy devstats, Tansu governance | T1, T2 | Git log patterns — Pamphile knows devstats deeply |
| **Progress (Koxy)** | Rust/Soroban, smart contracts, DevRel | T3 | Minimal — Koxy handles on-chain layer |
| **Jay Gutierrez** | Graph algorithms, network science, risk scoring | A6 (active subgraph), A7, A9, A10 | — |

**Most important early conversation**: Alex on A2 schema finalization. The `Repo`, `ExternalRepo`,
and `depends_on` edge table definitions must be locked before Jay can implement the NetworkX graph
construction layer, which is the foundation for the active subgraph projection (A6) and everything
downstream.

**Second most important**: Pamphile on the git log parser (A7). Pamphile has direct experience with
[Scientific Python devstats](https://devstats.scientific-python.org/_generated/scipy/) which the
architecture doc explicitly references as the implementation model. Borrowing that code pattern
directly could cut A7 development time in half.

---

## Open Questions That Affect Jay's Work

1. **Cargo reverse deps strategy for A6**: deps.dev can't answer "who uses soroban-sdk?" —
   does the team want (a) crates.io API direct call, (b) SBOM-first strategy for Rust packages,
   or (c) defer Cargo reverse graph to post-v0? This affects A6 scope materially.

2. **deps.dev as primary bootstrap mechanism**: Jay should propose using `GetDependencies` + batch
   endpoints as the npm/PyPI/Go crawler, rather than building custom registry crawlers. This is a
   significant scope reduction for A6 that should be surfaced to Alex immediately.

3. **PostgreSQL schema lock date**: Jay cannot implement the NetworkX graph construction layer until
   the schema is finalized. What is Alex's target date for A2 completion? Every day of delay on A2
   compresses Jay's T2 window.

4. **Active subgraph projection ownership**: A6 bundles crawlers AND active subgraph projection.
   The crawlers are data engineering (Alex's domain); the active subgraph projection algorithm is
   graph analytics (Jay's domain). Should these be split into separate PRs/modules with clear
   ownership boundaries?

5. **Adoption signals placement**: The $16K for A6 vs. the adoption signals in A10 — download
   counts naturally belong with A10, but the architecture may route them differently. Clarify with
   Alex whether `adoption_downloads` lives in A6 (ingestion) or A10 (computation).

---

*Document prepared February 24, 2026 | Sources: SCF #41 proposal (PDF), pg-atlas.md, ingestion.md,
storage.md, metric-computation.md, api.md, deps.dev live API calls, SCF community fund dashboard*
