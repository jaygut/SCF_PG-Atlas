# PG Atlas — North Star Document
**Jay Gutierrez | SCF #41 | February 2026**

*This document is the strategic compass for building PG Atlas. It defines what we are building,
why it matters, what outputs make it genuinely important infrastructure, and how to position
this work to establish Jay Gutierrez as the definitive graph intelligence authority in the
Stellar ecosystem. Read this before writing code. Return to it when priorities blur.*

---

## The One-Sentence Mission

> **PG Atlas is the first structural audit of the Stellar ecosystem — revealing which public goods
> are load-bearing, which are fragile, and where maintenance investment is most urgent.**

This is not a dashboard. It is not a scoring app. It is infrastructure for making better funding
decisions — the data layer beneath human judgment that makes SCF governance more defensible,
more transparent, and more effective.

---

## Why This Matters Beyond the $40-45K

Three things make this engagement strategically important beyond the immediate contract:

**1. First-mover on ecosystem graph intelligence.**
No one has mapped the Stellar dependency graph. Nobody knows which packages are load-bearing.
Nobody has quantified the pony factor risk across the funded project portfolio. PG Atlas v0 will
produce the first-ever structural picture of how the Stellar developer ecosystem actually fits
together. That picture will be cited, shared, and referenced long after the Q2 vote.

**2. Cross-domain proof of methodology.**
The architecture Jay is applying here — encode domain topology into a graph, compute structural
metrics, translate to decision-grade scores, serve as funding/investment signal — is identical
to what MARIS does for marine natural capital. A successful Q2 experiment produces a public,
open-source reference implementation of this methodology applied in a radically different domain.
That is the most credible kind of proof: it works in software ecosystems AND in marine ecosystems,
therefore the methodology is general.

**3. Positioning within the Stellar/blockchain ecosystem.**
Stellar is $5B+ market cap. The SCF has distributed $52.9M across 579 projects. If PG Atlas
becomes the standard tool for evaluating public goods in this ecosystem, Jay's network science
toolkit gets embedded into the governance infrastructure of a significant blockchain ecosystem.
That is a durable, compounding relationship — not a one-off engagement.

---

## The Conceptual Frame: Three Graph Layers

Understanding PG Atlas requires keeping three distinct graph layers in mind simultaneously.
Each encodes different information. Each supports different decisions.

### Layer 1 — The Package Dependency Graph

```
ExternalRepo ──depends_on──► Repo ──depends_on──► ExternalRepo
                                │
                           belongs_to
                                │
                             Project
```

**What it encodes:** Structural coupling. Who depends on whom. Which packages are foundations
(many things depend on them) vs. leaves (they depend on others, but nothing depends on them).

**What decisions it supports:** Criticality scoring, active subgraph projection, cascade risk
simulation, k-core decomposition, bridge edge detection.

**Key insight:** A package with 700 transitive dependents is not just important — it's
structurally essential. Removing it breaks 700 other things. This is the trophic cascade problem
applied to software: removing a keystone species collapses the food web; removing a keystone
package collapses the developer toolchain.

### Layer 2 — The Contributor Graph

```
Contributor ──contributed_to──► Repo
     │
 also_works_on
     │
Repo (different project)
```

**What it encodes:** Human capital concentration. Who carries the load. Which individuals are
load-bearing across multiple projects simultaneously.

**What decisions it supports:** Pony factor, cross-project maintenance risk, keystone contributor
identification, contributor diversity scoring.

**Key insight:** Standard pony factor treats each repo in isolation. But Christian Rogobete
(13 SCF submissions) is the primary maintainer of multiple ecosystem-critical projects. If he
disappears, the risk is not one pony-factor event — it's a correlated failure across the
projects he maintains. This is Bio-Beta applied to open-source: the covariance of failure
probability across a portfolio of projects with shared human capital.

### Layer 3 — The Funding Graph

```
Project ──funded_by──► SCFRound
    │                       │
criticality_score      vote_count
pony_factor            award_total
adoption_score         voter_count
```

**What it encodes:** The relationship between structural importance and resource allocation.

**What decisions it supports:** Funding efficiency analysis, identifying underfunded critical
infrastructure, calibrating the Metric Gate thresholds, retrospective evaluation of SCF
funding decisions.

**Key insight:** The SCF has funded 86 public goods projects with ~$9.2M. PG Atlas will show
for the first time whether funding correlates with structural criticality. If Reflector ($444K)
is also the highest-criticality project in the dependency graph, the SCF made good decisions.
If a $70K project turns out to be a keystone that 200 other projects depend on, that is the
most important finding PG Atlas can produce — and the primary justification for its existence.

---

## The Metric Architecture

### Tier 1 — Required (Proposal Commitments, v0)

**Criticality Score** (A9, Jay primary)
- Definition: Count of active packages transitively reachable from this package in the
  reversed dependency graph (i.e., packages that would be affected if this one disappeared)
- Algorithm: BFS from each package on the reversed, active-filtered graph
- Output: Raw integer count + percentile rank within PG Atlas universe
- Target: Every Repo vertex in the dependency graph has a criticality score

**Pony Factor** (A9, Jay primary)
- Definition: Binary flag (1 = at risk) when a single contributor accounts for ≥50% of
  commits in the rolling 90-day window
- Algorithm: Parse git logs, compute contributor share distribution, apply threshold
- Output: Binary flag + dominant contributor name + their share percentage
- Target: Every Repo with git history has a pony factor

**Adoption Signals** (A10, Jay primary)
- Definition: Normalized proxy metrics for ecosystem relevance
- Components: monthly downloads (npm/PyPI/Cargo) + GitHub stars + GitHub forks
- Algorithm: Log-scale normalization + percentile rank within PG Atlas universe
- Output: Per-component raw values + composite adoption score (0–100 percentile)
- Target: Every Repo with a registry presence has adoption signals

**Active Subgraph Projection** (A6, Jay co-lead)
- Definition: The induced subgraph of active nodes — filter the full dependency graph to
  retain only packages with ≥1 release or ≥1 commit in the last 90 days AND not archived
- Algorithm: Activity filter on vertex set → rebuild induced subgraph → this becomes the
  operational graph for all downstream scoring
- Output: G_active — the graph used for all criticality and pony factor calculations
- Target: Runs before any metric computation, updates on each ingestion cycle

### Tier 2 — High-Impact Extensions (Propose for v0, ship if scope allows)

**HHI-Based Pony Factor (Continuous)**
- Why: Binary pony factor (> 50%) is too coarse. 51% vs 95% concentration represent very
  different risk levels. The Herfindahl-Hirschman Index over contributor commit shares gives
  a continuous maintenance risk score (0 = perfectly distributed, 10,000 = single contributor).
- Formula: HHI = Σ(commit_share_i²) × 10,000
- Risk tiers: HHI < 1,500 = competitive (healthy); 1,500–2,500 = moderate; > 2,500 = high
- Why Jay: He has applied HHI-equivalent metrics to portfolio concentration in MARIS

**K-Core Decomposition**
- Why: The innermost core of the dependency graph reveals the structural skeleton of the
  ecosystem — the set of packages most deeply embedded in mutual dependencies. These are
  the true critical infrastructure, regardless of transitive dependent count.
- Algorithm: Iterative k-core decomposition on the active dependency graph (undirected
  version for k-core, directed version for criticality BFS)
- Output: core number for each package vertex; inner-core membership flag (top tier)
- Visualization: Node color by core number on force-directed graph

**Bridge Edge Detection**
- Why: Some dependency relationships are not just important — they are irreplaceable.
  A bridge edge connects two otherwise-disconnected subgraphs. If the package at one end
  of a bridge is deprecated, the other end loses its connection to the rest of the ecosystem.
- Algorithm: Tarjan's bridge-finding algorithm on undirected dependency graph
- Output: Flag on edges identified as bridges; both endpoints flagged as structurally critical

**Temporal Decay Weighting**
- Why: A transitive dependent that last committed 89 days ago (technically active) contributes
  less real-world risk than one that committed yesterday. Decay-weighted criticality measures
  currently relevant dependents, not just technically alive ones.
- Formula: weighted_criticality = Σ exp(-days_since_last_commit_j / 30) for all active dependents j
- This makes the criticality score continuous and time-sensitive rather than binary

### Tier 3 — Strategic Differentiators (Position Now, Build in v1)

**Funding Efficiency Ratio**
- Formula: FER = criticality_score / total_awarded_usd (normalized)
- What it reveals: Which projects carry disproportionate ecosystem load relative to their
  funding? High criticality + low funding = critical maintenance gap. This is the metric
  that makes PG Atlas a *discovery engine* for where the SCF should direct future awards.
- Strategic importance: This is the metric that will get PG Atlas cited in governance
  discussions, blog posts, and future SCF proposals. It answers the question the community
  has never been able to ask objectively.

**Cross-Project Pony Factor (Keystone Contributor Index)**
- What it is: A contributor-level risk score that aggregates pony factor across all repos
  where a contributor is dominant. A contributor with PF=1 in 5 projects represents 5x the
  risk of a contributor with PF=1 in 1 project.
- Formula: KCI(contributor) = Σ(pony_factor_flag × criticality_score) for all repos
  where contributor is dominant
- Identifies: "Keystone contributors" — individuals whose absence would cascade across
  multiple critical projects simultaneously

**Ecosystem Fragility Trajectory**
- What it is: Using SCF round timing (48 rounds, 2019–2026), track how structural fragility
  metrics evolve over time. Is the k-core growing? Is average HHI improving as projects mature?
  Are there structural phase transitions (sudden changes in graph topology)?
- Why it matters: Turns PG Atlas from a snapshot audit into a longitudinal monitoring system.
  The SCF can track whether its investment in public goods maintenance is actually reducing
  ecosystem fragility over time.

**Maintenance Debt Surface**
- What it is: The set of projects satisfying three conditions simultaneously:
  (1) criticality score in top quartile, (2) HHI > 2,500 (high concentration), and
  (3) commit frequency declining over last 90 days
- These are the projects that will fail quietly — not with a dramatic shutdown, but by
  gradually becoming too stale to depend on safely
- This surface is the most urgent output PG Atlas can produce for the SCF

---

## Output Design Principles

Three principles that separate a metric system from a decision-support system:

### Principle 1: Every Score Has an Ecosystem Percentile

A criticality score of 47 means nothing without context. "This package is in the 93rd percentile
of criticality across all 86 funded Stellar public goods projects" means something. All scores
must be expressed as percentile ranks within the PG Atlas universe, with raw values available
for technical users. This is not a cosmetic choice — it determines whether the Metric Gate
produces defensible decisions or arbitrary cutoffs.

### Principle 2: Every Risk Flag Has a Narrative

When pony factor = 1, the dashboard should not just show a red badge. It should say:

> "This project's commit history shows that **OrbitLens** accounts for **78%** of commits
> in the last 90 days (HHI: 7,284 — critical concentration). Based on current activity
> levels, a single contributor failure would affect **14 downstream packages** that transitively
> depend on this project."

This is the difference between a metric and a decision-support tool. Every automated flag
should carry enough context for a non-technical reviewer to understand and act on it.

### Principle 3: The Metric Gate Is Auditable

Every project that fails the Metric Gate should receive a detailed explanation:
- Which metric(s) failed
- What the thresholds were (and that they are configurable)
- What the project would need to change to pass
- Whether there are borderline cases worth human review

An opaque gate creates distrust. A transparent, explainable gate creates legitimacy.
This distinction is what makes PG Atlas a governance asset rather than a governance obstacle.

---

## The Visualization That Makes PG Atlas Real

The artifact that will make PG Atlas tangible to non-technical stakeholders is not a table
of scores. It is an interactive dependency graph where:

- **Node size** = criticality score (load-bearing packages are visually dominant)
- **Node color** = k-core membership tier (innermost core = deepest color)
- **Edge color** = bridge vs. regular (bridge edges highlighted in amber)
- **Node border** = pony factor flag (red border = single-contributor risk)
- **Node opacity** = activity level (dormant = transparent; active = opaque)
- **Hover tooltip** = project name, criticality percentile, pony factor, adoption score,
  top contributor, last commit date, funding tier

This visualization answers in one glance: *where are the foundations of the Stellar developer
ecosystem, and which of them are at risk?*

Built with Plotly (interactive, embeddable in the dashboard). The force layout should be
seeded with known hub nodes at center (`@stellar/js-xdr`, `soroban-sdk`, `@stellar/stellar-base`)
so the topology reads correctly on first render.

---

## Jay's Positioning Strategy

### The Technical Identity to Project

Within the Stellar ecosystem, Jay's role in PG Atlas should be understood as:

> **"The person who brought network science to ecosystem health monitoring"**

Not "the metrics guy." Not "the scoring system." Network science — the same methodology
that reveals keystone species in food webs, systemic risk in financial networks, and
fragility in infrastructure systems — applied to the Stellar developer ecosystem for the
first time.

This framing has three advantages:
1. It is accurate and defensible (k-core, BFS cascade, HHI, bridge detection are legitimate
   network science methods)
2. It differentiates from "analytics" or "dashboards" which are commodity
3. It connects PG Atlas to a broader body of scientific literature and methodology that
   gives the outputs institutional credibility

### The Content to Produce

After v0 ships, one public post should be written (Substack or Mirror) titled something like:

> "We mapped the Stellar ecosystem's dependency graph — here's what the network science says
> about which public goods are load-bearing"

This post should include:
- The force-directed dependency graph visualization
- The top-10 criticality scores (which packages are most critical)
- The funding efficiency finding (are critical projects getting funded proportionally?)
- The pony factor concentration finding (how fragile is the ecosystem's human capital?)
- A brief explanation of the methodology (k-core, BFS, HHI) accessible to a non-specialist

This is the artifact that establishes the identity above. One well-written post with
genuinely novel findings, backed by production data, is worth more than 20 conference talks.

### The Relationships to Build

**Alex Olieman (primary partner):** Co-build relationship on PG Atlas. The cleanest future
state is Jay and Alex as the PG Atlas core team for v1, v2, and beyond. Jay brings the
graph intelligence layer; Alex brings the data infrastructure. This is a natural, durable
collaboration.

**Pamphile Roy (Tupui):** He built Tansu and maintains SciPy. If Jay produces
high-quality, reproducible graph analytics code modeled on Scientific Python standards,
Pamphile will notice. That is a credibility signal from one of the most respected
open-source maintainers in the Python ecosystem.

**SCF Pilots as a class:** The Q2 experiment has 5 pilots total. If PG Atlas delivers
genuinely useful signals for the Q2 vote, the pilots will advocate for its continued
funding. That makes v1 a lower-friction funding conversation.

**The Stellar community broadly:** The dependency map and pony factor analysis will be
genuinely interesting to Stellar developers who have never seen their ecosystem mapped
this way. The visualization and blog post are the entry point for that community relationship.

---

## Deliverable-to-Impact Map

| Deliverable | Proposal Requirement | Strategic Impact | Positioning Value |
|---|---|---|---|
| A6 — Active Subgraph | Filter dormant repos | Foundation for all scoring | Shows rigor about data quality |
| A7 — Git Log Parser | Populate contributor data | Enables pony factor | Shows attention to human capital risk |
| A9 — Criticality + Pony | Core metric gate signals | First structural picture of ecosystem | **Highest** — novel insight |
| A10 — Adoption Signals | Third gate signal | Validates structural metrics | Corroboration layer |
| K-core decomposition | Extension (propose) | Innermost core identification | **Highest** — methodology differentiator |
| Funding efficiency ratio | Extension (propose) | Discovery engine for SCF | **Highest** — governance value |
| Interactive viz | Dashboard component | Makes ecosystem visible | **Highest** — community artifact |
| Retrospective | Post-Q2 | Validates methodology | Long-term credibility |

---

## Implementation Sequence

### Phase 0 — Before Alex's Schema (Now → March 1)
- [x] Prototype A6 active subgraph projection on synthetic graph (this notebook)
- [x] Prototype criticality BFS and k-core on same graph
- [x] Validate algorithms produce sensible outputs on known-structure data
- [x] Draft interface contract questions for Alex (D5/D6 boundary)
- [x] Share A5_pg_candidate_seed_list.csv with Alex for validation

### Phase 1 — Infrastructure Ready (March 1–8, T1 closes)
- [x] Align with Alex on PostgreSQL schema (vertex + edge definitions)
- [x] Implement NetworkX graph construction layer from schema
- [x] Set up git log parser skeleton (A7)
- [x] Confirm deps.dev bootstrap playbook works for npm/PyPI seeds
- [x] Confirm crates.io strategy for Cargo reverse deps

### Phase 2 — Core Metrics (March 8–22, T2 closes)
- [x] A6: Active subgraph projection running on production data
- [x] A7: Git log parser running on ≥50 repos, populating contributor edges
- [x] First criticality scores computed on real data
- [x] First pony factor flags computed on real contributor data
- [x] Threshold calibration discussion with team

### Phase 3 — Full System (March 22 – April 12, T3 closes)
- [x] A9: All three metric families running on full 86-project seed
- [x] A10: Adoption signals populated and normalized
- [ ] A11: Analytics API endpoints serving scores and transitive queries
- [ ] A12: Dashboard with dependency visualization and metric display
- [x] K-core and bridge detection integrated as Tier 2 metrics
- [ ] Funding efficiency ratio computed and displayed

### Phase 4 — Retrospective and v1 Positioning (April–June)
- [ ] Post-Q2 analysis: Did Metric Gate decisions correlate with expert review?
- [ ] Calibration: Were thresholds appropriate?
- [ ] Blog post: "We mapped the Stellar ecosystem's dependency graph"
- [ ] Propose v1 scope: keystone contributor index, fragility trajectory, temporal decay

---

## The North Star Output

When PG Atlas v0 is complete, the single most important output is not the dashboard,
not the API, not the metric gate. It is the answer to this question:

> **"Is the Stellar Community Fund investing maintenance resources proportionally to
> structural ecosystem criticality — and if not, where are the gaps?"**

That answer, backed by real data and rigorous graph analysis, is the contribution that
makes PG Atlas matter. Everything else — the code, the schema, the API, the dashboard —
is infrastructure in service of that question.

Build everything to answer it.

---

*Document authored February 24, 2026 — Jay Gutierrez*
*Sources: SCF #41 proposal, PG Atlas architecture documentation, deps.dev API analysis,
Airtable data exploitation brief, SCF Airtable CSVs (579 projects, 48 rounds, $52.9M)*
