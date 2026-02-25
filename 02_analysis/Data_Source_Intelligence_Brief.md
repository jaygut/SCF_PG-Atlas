# PG Atlas — Data Source Intelligence Brief
**deps.dev + Airtable SCF Registry** | February 2026

---

## Executive Summary

This brief assesses the two external data sources Jay was directed to evaluate before building the
ingestion layer for PG Atlas. The central finding is significant: **deps.dev is not the "optional
enrichment" the architecture doc implies — it is a production-ready shadow graph bootstrap engine
for npm and PyPI, covering ~70–80% of the Stellar frontend/tooling ecosystem with a single API
endpoint per package.** However, it has a confirmed, severe blind spot: **Cargo/Rust dependents
return zero across all packages**, including ecosystem-wide standards like `serde`. This is not a
data sparsity issue — it is a structural API gap. Soroban's native smart contract ecosystem, written
almost entirely in Rust, is invisible to deps.dev's reverse dependency graph.

The Airtable is the current SCF public goods intake system — not directly accessible via API or
scraping due to JavaScript rendering, but its data flows into OpenGrants (the machine-readable
project registry that the ingestion doc already names as the primary source for `Project` vertices).
The Airtable matters strategically as the seed list of who needs coverage first, not as a data
pipeline source.

---

## Source 1: deps.dev (Open Source Insights by Google)

### What It Is

deps.dev is Google's open-source package intelligence platform. It indexes package registries,
resolves dependency graphs, ingests OpenSSF Scorecard data, and exposes everything through a
public REST/gRPC API and a BigQuery dataset. No authentication. No cost.

### API Coverage Matrix

| Capability | npm | PyPI | Cargo | Go | Maven |
|---|---|---|---|---|---|
| Package metadata | ✅ | ✅ | ✅ | ✅ | ✅ |
| Version list + `isDefault` + `publishedAt` | ✅ | ✅ | ✅ | ✅ | ✅ |
| Resolved dependency tree (transitive) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Dependents count** | ✅ | ✅ | ❌ (returns 0) | ❌ | ❌ |
| Source repo + GitHub link | ✅ | ✅ | ✅ | ✅ | ✅ |
| OpenSSF Scorecard (15 checks) | ✅ | ✅ | ✅ | ✅ | ✅ |
| License data | ✅ | ✅ | ✅ | ✅ | ✅ |
| Advisory / CVE data | ✅ | ✅ | ✅ | ✅ | ✅ |
| PURL lookup (for SBOM matching) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Batch endpoint (up to 5,000) | ✅ | ✅ | ✅ | ✅ | ✅ |

**Confirmed via live API calls on Stellar packages, February 2026.**

### The Cargo Dependents Gap — Confirmed

This is not a configuration issue or data sparsity problem. Testing against the most widely-depended
Cargo crate in existence:

```
CARGO/serde@1.0.228 → dependentCount: 0
CARGO/soroban-sdk@25.1.1 → dependentCount: 0
```

For comparison:
```
npm/lodash@4.17.21 → dependentCount: 29,761
PyPI/requests@2.32.3 → dependentCount: 2,168
```

The BigQuery `Dependents` table documentation claims Cargo coverage, but the API does not serve it.
This gap means **you cannot use deps.dev to reverse-crawl the Soroban smart contract dependency
graph** — i.e., you cannot ask "who uses `soroban-sdk`?" via this API. For the Stellar ecosystem,
this is a critical missing piece because Soroban contracts are the native smart contract layer and
are written entirely in Rust.

### What deps.dev CAN Do for PG Atlas

#### 1. Shadow Graph Bootstrap (npm + PyPI) — Near-Complete

The `GetDependencies` endpoint returns the **fully resolved transitive dependency tree** as a list
of `{versionKey, relation: DIRECT|INDIRECT}` nodes and `{fromNode, toNode, requirement}` edges.
One API call per package gives you the entire subgraph. Live result for `stellar-sdk@13.3.0`:

```
Nodes returned: ~50+ transitive dependencies
Direct deps: @stellar/stellar-base, axios, eventsource, ...
Indirect deps: @stellar/js-xdr, asynckit, available-typed-arrays, ...
```

This is the shadow graph bootstrap for the JavaScript layer. No npm registry crawler needed for the
forward-dependency direction.

#### 2. Repo Vertex Enrichment — Free and Complete

`GetVersion` returns everything needed to populate a `Repo` vertex in one call:

| Repo Field | deps.dev source | Example |
|---|---|---|
| `canonical_id` | `purl` | `pkg:npm/stellar-sdk@13.3.0` |
| `latest_version` | `versionKey.version` where `isDefault=true` | `13.3.0` |
| `repo_url` | `links[label=SOURCE_REPO].url` | `github.com/stellar/js-stellar-sdk` |
| `metadata.license` | `licenses[]` | `Apache-2.0` |
| `latest_release_date` | `publishedAt` | `2025-04-21T22:34:03Z` |
| `metadata.advisories` | `advisoryKeys[]` | CVE list |

#### 3. OpenSSF Scorecard — Direct "Maintained" Signal

`GetProject` for a GitHub repo returns a full 15-check OpenSSF Scorecard. The `Maintained` check
directly reports: "N commit(s) and M issue activity found in the last 90 days." This is a
machine-readable activity signal that maps almost directly to the `activity_status` logic in PG Atlas.

Live result for `github.com/stellar/js-stellar-sdk`:
```
Maintained: 10/10 — "30 commit(s) and 0 issue activity found in the last 90 days"
Vulnerabilities: 0/10 — "21 existing vulnerabilities detected"
Code-Review: 10/10 — "all changesets reviewed"
```

The `Maintained` score can be used as a triangulation signal for `activity_status` without cloning
the repo. This is a significant shortcut for the initial bootstrap.

#### 4. Adoption Signals — Partial

- **Stars and forks**: Available via `GetProject` (starsCount, forksCount, openIssuesCount)
- **Download counts**: NOT available via API — must still query npm/crates.io/PyPI APIs for this

#### 5. PURL Lookup — SBOM Matching

The `PurlLookup` and `PurlLookupBatch` endpoints accept PURLs exactly as they appear in CycloneDX
and SPDX SBOMs. This means SBOM ingestion can resolve `pkg:npm/stellar-sdk@13.3.0` to full version
metadata in one call instead of hitting the npm registry directly.

### Live Stellar Ecosystem Sample

Packages confirmed present and queryable in deps.dev:

| Package | Ecosystem | Default Version | Dependents | Notes |
|---|---|---|---|---|
| `stellar-sdk` | npm | 13.3.0 | 15 (direct) | Deprecated in favor of `@stellar/stellar-sdk` |
| `@stellar/stellar-base` | npm | 14.0.4 | **463** | Major hub node |
| `@stellar/js-xdr` | npm | 3.1.2 | **693** | Highest dependent count found |
| `soroban-client` | npm | 1.0.1 | 9 | Deprecated |
| `@stellar/freighter-api` | npm | 6.0.1 | 3 | Wallet integration |
| `stellar-sdk` | PyPI | 13.2.1 | 14 | Python ecosystem |
| `soroban-sdk` | Cargo | 25.1.1 | **0 (gap)** | Rust — dependents blind spot |
| `stellar-xdr` | Cargo | 25.0.0 | **0 (gap)** | Rust — dependents blind spot |

**Key observation**: `@stellar/js-xdr` has 693 dependents (687 indirect), making it the highest-criticality
node visible via deps.dev. `@stellar/stellar-base` has 463. These are the natural hub nodes for the
initial graph bootstrap — packages with many dependents reveal the graph structure fastest.

### Rate Limits & Operational Constraints

- **100 requests/minute per IP** — same as PG Atlas API target
- **Batch endpoint**: Up to 5,000 packages per request (crucial for bulk bootstrap)
- **No authentication required**
- **No data download / bulk export via API** — BigQuery is the bulk path but requires GCP credentials
- **Update frequency**: Periodic snapshots; not real-time

### What deps.dev Eliminates

Before this assessment, the architecture doc mentioned potentially needing "4 or 5 separate package
registry crawlers." Here is the updated picture:

| Registry | deps.dev replaces? | What still needs direct registry access |
|---|---|---|
| npm | ✅ **Fully** for dependencies + metadata | Download counts (npm downloads API) |
| PyPI | ✅ **Fully** for dependencies + metadata | Download counts (pypistats.org) |
| Cargo/crates.io | ⚠️ **Partial** — forward dependencies only | **Dependents** (who uses soroban-sdk) — need crates.io |
| Go proxy | ✅ Covered for Go modules | May need direct for unusual paths |
| Maven | ✅ Covered for Java | — |

**Bottom line**: For npm and PyPI, deps.dev eliminates the need for custom crawlers for everything
except download counts. For Cargo, it handles forward dependencies but cannot tell you who depends
on `soroban-sdk` — you need a direct crates.io API call for that.

---

## Source 2: Airtable SCF Project Registry

### What It Is

The Airtable at the provided URL is the **current intake database for SCF Public Goods Award
proposals** — the existing system that teams submit to for quarterly funding consideration. Based on
the award round documentation, this table tracks:

- Project names and teams
- GitHub organization URLs (the critical field for PG Atlas's `git_org_url`)
- Project categories (SDK, wallet, dev tools, infrastructure, etc.)
- Funding amounts requested and awarded
- Proposal status (approved, pending, under review)
- Deliverable links and completion tracking

### Accessibility Verdict

**Not programmatically accessible.** The Airtable renders exclusively via JavaScript, and the shared
view URL (`shrrNA24K1e0v5Q0R`) does not expose a CSV export or API endpoint without authentication.
No HTML data is returned — only JS initialization code.

### Why It Still Matters Strategically

The Airtable is **the seed list** — the ground truth of which projects need to be in PG Atlas first.
But the machine-readable path to that data is not the Airtable itself. It flows like this:

```
Airtable (intake) → SCF Impact Survey → OpenGrants → PG Atlas Project vertices
```

The ingestion doc already accounts for this: "Bootstrap Project vertices from OpenGrants." OpenGrants
(`opengrants.daostar.org/system/scf`) is the structured, standards-compliant export of the same data
the Airtable tracks, following the DAOIP-5 URI format that PG Atlas uses for `canonical_id`.

The Airtable is operationally relevant because:
1. The **activity_status** bootstrapping logic depends on SCF Impact Survey data — which is curated
   from Airtable responses
2. It is the **community-facing interface** where new project submissions are initially captured
3. The `git_org_url` field it contains is the primary pointer from a `Project` vertex to its repos

### Practical Implication

Jay does not need to build an Airtable connector. The data path is:
- **OpenGrants API** → `Project` vertices (names, types, org URLs, DAOIP-5 URIs)
- **SCF Impact Survey** → `activity_status` initial values
- **Airtable** → human-readable reference only, used by team members who curate the seed list manually

---

## Cross-Map: Sources Against PG Atlas D4/D5 Requirements

### D4 — Ingestion Pipeline: What Each Source Feeds

| D4 Sub-task | Data Source | Format | Status |
|---|---|---|---|
| Bootstrap `Project` vertices | OpenGrants (not Airtable) | API / JSON-LD | Needs integration |
| Bootstrap `Repo` vertices | deps.dev `GetVersion` | JSON | ✅ Ready now |
| Forward dep edges (npm/PyPI) | deps.dev `GetDependencies` | JSON, nodes + edges | ✅ Ready now |
| Forward dep edges (Cargo) | deps.dev `GetDependencies` | JSON, nodes + edges | ✅ Works |
| **Reverse dep crawl (npm/PyPI)** | deps.dev `GetDependents` (counts) → iterate known packages | JSON | ⚠️ Count only, not list |
| **Reverse dep crawl (Cargo)** | crates.io API | REST | ❌ deps.dev gap — need separate |
| SBOM ingestion | Direct webhook (CycloneDX/SPDX) + PURL lookup via deps.dev | JSON | deps.dev accelerates |
| Git contributor logs (pony factor) | Direct git clone | git log | No external shortcut |
| Adoption: download counts | npm downloads API + pypistats.org + crates.io | REST | Separate from deps.dev |
| Adoption: stars/forks | deps.dev `GetProject` | JSON | ✅ Ready now |
| OpenSSF scorecard / activity signal | deps.dev `GetProject` | JSON | ✅ Ready now — valuable |

### D5 — Storage: How deps.dev Maps to the Schema

#### `Repo` Vertex ← deps.dev `GetVersion` (direct field mapping)

| Repo column | deps.dev field | Notes |
|---|---|---|
| `canonical_id` | `purl` | Format: `pkg:npm/stellar-sdk@13.3.0` |
| `display_name` | `versionKey.name` | Package name |
| `latest_version` | `versionKey.version` where `isDefault=true` | |
| `repo_url` | `links[label=SOURCE_REPO].url` | GitHub URL |
| `metadata.license` | `licenses[]` | SPDX identifier |
| `releases` (JSONB) | All versions from `GetPackage` | `publishedAt` per version |
| `adoption_stars` | `GetProject → starsCount` | Requires second call |
| `adoption_forks` | `GetProject → forksCount` | Requires second call |

#### `depends_on` Edge ← deps.dev `GetDependencies`

| Edge property | deps.dev field | Notes |
|---|---|---|
| `in_vertex` | Parent package PURL | The requesting package |
| `out_vertex` | `nodes[].versionKey` (PURL) | Each dependency node |
| `version_range` | `edges[].requirement` | Semver range |
| `confidence` | — | Set to `inferred_shadow` (not from SBOM) |

Direct vs. indirect: the `relation` field (`DIRECT` vs `INDIRECT`) lets you distinguish first-hop
from transitive edges — valuable for loading only the direct edges per package to avoid duplication
when building the graph from multiple seed packages.

---

## Implementation Path: The deps.dev Bootstrap Playbook

Given the above, here is the optimal shadow graph bootstrap sequence for Jay to propose to Alex:

**Phase 1 — Seed Package Discovery (Day 1)**
Use deps.dev `GetPackage` for each known Stellar/Soroban root package to get all versions and
confirm they're indexed. Starting seed list (confirmed present):
`stellar-sdk (npm)`, `@stellar/stellar-base`, `@stellar/js-xdr`, `@stellar/freighter-api`,
`soroban-client`, `stellar-sdk (PyPI)`, `soroban-sdk (Cargo)`, `stellar-xdr (Cargo)`

**Phase 2 — Forward Dependency Graph (Days 2–3)**
Call `GetDependencies` for each seed's default version. This gives you the transitive graph
downstream. Load nodes as `Repo` or `ExternalRepo` vertices, load edges as `depends_on` edges with
`confidence=inferred_shadow`. For npm/PyPI, this is largely complete. For Cargo, forward deps work.

**Phase 3 — Reverse Discovery (Days 4–5)**
For npm/PyPI: Use `GetDependents` counts to identify which packages have dependents, then use the
reverse — for packages in your graph that have `dependentCount > 0`, crawl the npm/PyPI registry
reverse-dep APIs to get the actual list of who depends on them.
For Cargo: Hit crates.io reverse-dependency API directly:
`GET https://crates.io/api/v1/crates/{crate}/reverse_dependencies`

**Phase 4 — Enrichment (Days 6–7)**
For each `Repo` vertex in the graph, call `GetProject` to attach:
- Stars, forks, issues
- OpenSSF Maintained score → triangulate `activity_status`
- Vulnerability count

**Phase 5 — Download Counts (Day 8)**
For npm: `https://api.npmjs.org/downloads/point/last-month/{package}`
For PyPI: `https://pypistats.org/api/packages/{package}/recent`
For Cargo: `https://crates.io/api/v1/crates/{crate}` (includes `downloads` field)

---

## Critical Questions This Analysis Raises for Alex

1. **Cargo dependents strategy**: Since deps.dev can't answer "who uses soroban-sdk?", how does Alex
   plan to bootstrap the Rust/Soroban layer of the graph? Options: (a) crates.io reverse-dep API, (b)
   SBOM-first approach (rely on project submissions rather than shadow crawl), (c) defer Cargo reverse
   graph to post-v0.

2. **Dependents list vs. count**: deps.dev `GetDependents` returns only a count, not a list of which
   packages depend on the target. To get the actual list (needed to build edges in the reverse
   direction), you either crawl forward from all known packages and invert, or use the BigQuery dataset
   with GCP credentials. Does the team have BigQuery access? This determines whether the shadow graph
   can be built purely via API or requires a batch job against the BigQuery dataset.

3. **Conflation of Repo versions**: deps.dev returns per-version data. PG Atlas models repos as
   single vertices with a `latest_version` field. When loading from deps.dev, does Alex want to
   deduplicate to latest-only, or store version history in the `releases` JSONB field? The answer
   determines how Jay structures the NetworkX graph load — one node per package or one node per
   package+version.

---

## Summary Verdict

| Source | Utility for PG Atlas | What It Gives | What It Misses |
|---|---|---|---|
| **deps.dev API** | **High — use immediately** | npm/PyPI dep graph, Repo metadata, OpenSSF scorecard, PURL resolution | Cargo dependents, download counts |
| **deps.dev BigQuery** | Medium — requires GCP | Bulk Cargo dependents (possibly), full graph dumps | Auth/GCP overhead |
| **Airtable** | Low as pipeline, High as reference | Ground truth seed list (via team access only) | Not API-accessible |
| **OpenGrants** | High — primary Project source | DAOIP-5 Project vertices | Partial coverage of newer projects |
| **crates.io API** | High for Cargo layer | Rust package metadata + reverse deps | Slower, rate-limited |

*Document prepared February 2026 | Based on live API calls to deps.dev, GitHub API, and full review of PG Atlas architecture documentation*
