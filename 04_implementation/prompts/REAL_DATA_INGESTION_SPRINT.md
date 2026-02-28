# PG Atlas — Real Data Ingestion Sprint
**Prompt for a 2-Agent Specialised Team**
**Author:** Jay Gutierrez | SCF #41 — Building the Backbone
**Date:** February 26, 2026
**Target directory:** `/Users/jaygut/Desktop/SCF_PG-Atlas`

---

## Context You Must Read First

Before writing a single line of code, read these files in order:

1. `CLAUDE.md` — project constraints, API blind spots, interface contracts
2. `pg_atlas/WHAT_WAS_BUILT.md` — complete map of the 43-module production package (177 tests, all passing)
3. `pg_atlas/ingestion/__init__.py` — ingestion module exports
4. `pg_atlas/graph/builder.py` — specifically `build_graph_from_csv()` and `enrich_graph_with_ingestion()` signatures
5. `pg_atlas/pipeline.py` — the 14-step `run_full_pipeline()` orchestrator
6. `01_data/processed/A5_pg_candidate_seed_list.csv` — 86 funded PG projects (real names, GitHub URLs, funding amounts)
7. `01_data/processed/A7_submission_github_repos.csv` — 338 submission repos

**Critical context:**
The `pg_atlas/` package is a complete, production-grade implementation with 177 passing tests. All tests are unit tests operating on synthetic/mock data — no test makes a real network call. Every ingestion client (`deps_dev_client.py`, `git_log_parser.py`, `crates_io_client.py`, `npm_downloads_client.py`, `pypi_downloads_client.py`) is fully implemented but has never been executed against real APIs. The `run_full_pipeline()` function runs end-to-end on synthetic data from CSV seeds.

**Your mission:** Wire real API data into this production package — not by replacing anything, but by building the orchestration and validation layer that was always missing. The package already knows how to compute metrics. It just needs real edges to compute them on.

---

## Team Structure

This sprint requires two specialised agents working in sequence. Agent 1 must complete before Agent 2 begins — the integration tests Agent 1 writes are the quality gates Agent 2's output must pass.

---

## AGENT 1: Integration Test Engineer

### Identity
You are a senior test engineer specialising in external API integration. Your job is to write the integration test suite that proves every ingestion client in `pg_atlas/ingestion/` works correctly against real APIs before any production ingestion run is attempted. You do not write ingestion logic — you write the harness that validates it.

### Philosophy
- A test that passes on mock data proves nothing about the real world.
- Every ingestion client must be tested against its real upstream API on a representative sample before production use.
- Integration tests are not CI tests — they require network access and credentials. They must be clearly separated from the 177 existing unit tests and run on demand.
- A failing integration test is a feature: it surfaces API changes, rate limits, and structural surprises before they corrupt production data.

### Deliverable: `pg_atlas/tests/test_integration_real_api.py`

Write a pytest integration test file with the following properties:

**Markers and structure:**
- Every test must be decorated with `@pytest.mark.integration` so it is excluded from the default `pytest` run
- The test file opens with a module-level docstring explaining: how to run it (`pytest -m integration`), what credentials are needed (`GITHUB_TOKEN` env var), and what the expected runtime is (~3-5 minutes)
- Tests are grouped into classes: `TestDepsDotDevClient`, `TestCratesIoClient`, `TestNPMDownloadsClient`, `TestPyPIDownloadsClient`, `TestGitLogParser`, `TestFullIngestionSample`

**`TestDepsDotDevClient` — 5 tests:**
1. `test_get_version_npm_stellar_sdk` — call `DepsDotDevClient().get_version("NPM", "@stellar/stellar-sdk")` and assert: result is not None, `result.name == "@stellar/stellar-sdk"`, `result.ecosystem == "NPM"`, `result.version` is a non-empty string matching semver pattern, `result.source_repo_url` starts with `"https://github.com"`.
2. `test_get_dependencies_npm_stellar_sdk` — call `get_dependencies("NPM", "@stellar/stellar-sdk", ...)` using the version from test 1. Assert: returns a non-empty list, each item is a `DepsDependencyEdge`, at least one edge has `relation == "DIRECT"`, `to_name` is a non-empty string for all edges.
3. `test_get_project_enrichment_stellar_sdk` — call `get_project_enrichment("https://github.com/stellar/js-stellar-sdk")`. Assert: `stars > 0`, `forks >= 0`, result is not None.
4. `test_cargo_package_returns_none_or_zero_deps` — call `get_dependencies("CARGO", "soroban-sdk", ...)`. Assert: either returns None or returns a list (possibly empty). This test documents the known Cargo blind spot — it must pass whether deps.dev returns empty or not, but the test body must include a comment: `# Known limitation: deps.dev returns 0 deps for all Cargo packages. Use crates_io_client for Rust reverse deps.`
5. `test_bootstrap_stellar_graph_returns_data` — call `DepsDotDevClient().bootstrap_stellar_graph()`. Assert: `len(metadata) >= 3` (at least 3 packages found), `len(edges) >= 1` (at least 1 dependency edge returned), all `metadata` items are `DepsVersion` instances, all `edges` items are `DepsDependencyEdge` instances.

**`TestCratesIoClient` — 3 tests:**
1. `test_get_crate_info_soroban_sdk` — call `CratesIoClient().get_crate_info("soroban-sdk")`. Assert: result is not None, `result["name"] == "soroban-sdk"`, `result["downloads"] > 0`.
2. `test_get_reverse_dependencies_soroban_sdk` — call `get_reverse_dependencies("soroban-sdk")`. Assert: returns a list, `len(result) >= 1`, all items are strings.
3. `test_rate_limit_respected` — make 3 sequential calls to `get_crate_info` for 3 different crates. Record timestamps. Assert: elapsed time between any two consecutive calls is `>= 0.9` seconds (crates.io TOS requires 1 req/sec).

**`TestNPMDownloadsClient` — 2 tests:**
1. `test_get_stellar_sdk_downloads` — call `get_npm_downloads("@stellar/stellar-sdk")`. Assert: result is not None, `result["downloads"] > 0`, `result["package"] == "@stellar/stellar-sdk"`.
2. `test_nonexistent_package_returns_none` — call `get_npm_downloads("@stellar/this-package-does-not-exist-xyzzy123")`. Assert: result is None or result has `downloads == 0`. Does not raise an exception.

**`TestPyPIDownloadsClient` — 2 tests:**
1. `test_get_stellar_sdk_pypi_downloads` — call `get_pypi_downloads("stellar-sdk")`. Assert: result is not None, `result["total_downloads"] > 0`.
2. `test_nonexistent_package_returns_none` — call `get_pypi_downloads("stellar-this-does-not-exist-xyzzy456")`. Assert: result is None or result has `total_downloads == 0`. Does not raise.

**`TestGitLogParser` — 5 tests** (require `GITHUB_TOKEN` env var, skip with `pytest.mark.skipif` if absent):
1. `test_parse_single_well_known_repo` — call `parse_repo_contributions("https://github.com/stellar/js-stellar-sdk", token=os.environ.get("GITHUB_TOKEN"))`. Assert: `result["accessible"] == True`, `result["total_commits_in_window"] > 0`, `len(result["contributors"]) >= 1`, each contributor has `commits_in_window > 0`, `result["latest_commit_date"]` is a valid ISO 8601 date string.
2. `test_parse_repo_returns_days_since_commit` — same repo as above. Assert: `result["days_since_latest_commit"] < 365` (active repo), `result["days_since_latest_commit"] >= 0`.
3. `test_inaccessible_repo_fails_gracefully` — call `parse_repo_contributions("https://github.com/stellar/this-repo-does-not-exist-xyzzy789")`. Assert: `result["accessible"] == False`, `result["error"]` is a non-empty string, function does not raise.
4. `test_parse_5_repos_from_csv` — load the first 5 rows of `01_data/processed/A7_submission_github_repos.csv`, extract `github_url` column, call `parse_all_repos(urls[:5], token=GITHUB_TOKEN, max_workers=2)`. Assert: returns a list of 5 dicts, at least 3 have `accessible == True`, all have `repo_url` set correctly.
5. `test_results_to_edges_produces_valid_schema` — take the output of `parse_all_repos` from test 4, pass to `results_to_contribution_edges()`. Assert: returns a list of dicts, each dict has keys `contributor`, `repo`, `edge_type`, `commits`, `edge_type == "contributed_to"`, `commits > 0` for all edges.

**`TestFullIngestionSample` — 1 end-to-end test:**
1. `test_enrich_graph_with_real_sample` — this is the critical integration smoke test:
   - Build a graph from CSVs: `G = build_graph_from_csv()`
   - Run A7 on first 5 repos: `edges, activity = run_a7(repos_csv, token, since_days=90)` — but mock the HTTP calls using `unittest.mock.patch` to return the data from `test_parse_5_repos_from_csv` above (use `@pytest.mark.integration` but this one can use cached data)
   - Call `enrich_graph_with_ingestion(G, dep_edges=[], contribution_edges=edges[:10], adoption_data={}, activity_data=activity)`
   - Assert: `G.number_of_nodes()` increased, at least one `Contributor` node exists in G, at least one `contributed_to` edge exists in G, `active_subgraph_projection(G)` runs without error on the enriched graph

**conftest.py additions:**
Add a `conftest.py` entry or fixture that:
- Reads `GITHUB_TOKEN` from environment
- Skips all `integration` tests automatically if `GITHUB_TOKEN` is not set, with a clear skip message: `"Integration tests require GITHUB_TOKEN env var. Set it and run: pytest -m integration"`
- Adds a `--run-integration` CLI flag to make it easy to enable via `pytest --run-integration`

**Quality requirements for Agent 1:**
- Every assertion has a failure message string: `assert result.stars > 0, f"Expected stars > 0, got {result.stars} for stellar/js-stellar-sdk"`
- Every test docstring explains: what API it calls, what it proves, and what a failure indicates
- Tests use `time.sleep(1.1)` between sequential crates.io calls (TOS compliance, same as the client itself)
- No hardcoded tokens anywhere — always `os.environ.get("GITHUB_TOKEN")`
- The test file must run completely (all skipped or passed) when `GITHUB_TOKEN` is absent

**Verification gate:**
After writing `test_integration_real_api.py`, run the existing 177 unit tests to confirm nothing was broken: `cd /Users/jaygut/Desktop/SCF_PG-Atlas && python -m pytest pg_atlas/tests/ -x -q --ignore=pg_atlas/tests/test_integration_real_api.py`. All 177 must still pass. Report the result.

---

## AGENT 2: Ingestion Orchestrator

### Identity
You are a senior data engineer specialising in production-grade ETL pipelines. Your job is to build the ingestion orchestration layer that runs all API clients in sequence, with checkpointing, retry logic, and canonical output — so that the `run_full_pipeline()` function in `pipeline.py` can operate on real Stellar ecosystem data every time it is called. You do not rewrite existing ingestion clients — you orchestrate them.

### Read Agent 1's work first
Before writing any code, read `pg_atlas/tests/test_integration_real_api.py` produced by Agent 1. The integration tests define the exact API response shapes your orchestrator must handle. Every data structure your orchestrator outputs must satisfy the assertions in those tests.

### Philosophy
- An orchestrator that silently skips 30% of repos due to rate limits is worse than no orchestrator. Coverage and completeness must be explicit and logged.
- Idempotency: running the orchestrator twice must produce the same output (or a superset). Never corrupt existing data.
- Checkpointing is non-negotiable: a 338-repo run takes ~20 minutes with rate limiting. If it fails at repo 200, restart must resume from repo 200, not repo 1.
- All API errors are logged and counted, never silently swallowed.
- The final output must be importable by `enrich_graph_with_ingestion()` without modification.

### Deliverable 1: `pg_atlas/ingestion/orchestrator.py`

Build `pg_atlas/ingestion/orchestrator.py` containing:

**`IngestionConfig` dataclass:**
```python
@dataclass
class IngestionConfig:
    github_token: Optional[str]         # From env: GITHUB_TOKEN
    since_days: int = 90                # Rolling window for git stats
    git_max_workers: int = 4            # Concurrent GitHub API threads
    deps_rate_limit: int = 100          # deps.dev req/min
    checkpoint_dir: str = "01_data/real/checkpoints"
    output_dir: str = "01_data/real"
    repos_csv: str = "01_data/processed/A7_submission_github_repos.csv"
    seed_csv: str = "01_data/processed/A5_pg_candidate_seed_list.csv"
    orgs_csv: str = "01_data/processed/A6_github_orgs_seed.csv"
```

All paths must be resolved relative to the repository root (use `_REPO_ROOT` pattern from `git_log_parser.py`).

**`IngestionResult` dataclass:**
```python
@dataclass
class IngestionResult:
    contribution_edges: list[dict]      # For enrich_graph_with_ingestion()
    activity_data: dict[str, dict]      # For enrich_graph_with_ingestion()
    dependency_edges: list[dict]        # For enrich_graph_with_ingestion()
    adoption_data: dict[str, dict]      # For enrich_graph_with_ingestion()
    coverage_report: dict               # Stats: repos_attempted, repos_succeeded, etc.
    errors: list[dict]                  # {source, repo_or_package, error_type, message}
```

**`Checkpoint` — internal checkpointing class:**
- Saves progress to `{checkpoint_dir}/a7_progress.json`, `{checkpoint_dir}/deps_progress.json`, `{checkpoint_dir}/adoption_progress.json`
- `save(key, data)` — write JSON atomically (write to `.tmp`, then rename)
- `load(key) -> dict` — load existing checkpoint, return empty dict if not found
- `mark_done(key, item_id)` — record that `item_id` was successfully processed
- `is_done(key, item_id) -> bool` — check if item was already processed
- `get_results(key) -> list` — retrieve all saved results for a key

**`run_a7_ingestion(config: IngestionConfig, checkpoint: Checkpoint) -> tuple[list, dict]`:**
- Load repo URLs from `config.repos_csv` (column: `github_url` or `repo_url` — check both, handle whichever is present)
- For each repo: skip if `checkpoint.is_done("a7", repo_url)`
- Call `parse_repo_contributions(repo_url, token=config.github_token, since_days=config.since_days)`
- On success: `checkpoint.mark_done("a7", repo_url)`, save result to checkpoint
- On failure: log at WARNING level, add to errors list, continue to next repo
- Progress: log every 10 repos: `"A7 progress: {n}/{total} repos processed ({pct:.0f}%)"`
- Return: `(contribution_edges, activity_data)` using `results_to_contribution_edges()` and `results_to_activity_data()` from `git_log_parser.py`

**`run_deps_ingestion(config: IngestionConfig, checkpoint: Checkpoint) -> list[dict]`:**
- Instantiate `DepsDotDevClient(rate_limit_per_min=config.deps_rate_limit)`
- Load GitHub URLs from `config.seed_csv` (column: `github_url`)
- For each GitHub URL: skip if `checkpoint.is_done("deps", github_url)`
- Call `client.get_project_enrichment(github_url)` — stores stars/forks/OpenSSF scores
- For the 9 `STELLAR_SEED_PACKAGES` in `deps_dev_client.py`: call `bootstrap_stellar_graph()` once (checkpoint key: `"deps_bootstrap"`)
- **Cargo gap:** instantiate `CratesIoClient()`, for each crate in `SOROBAN_CORE_CRATES`: call `get_reverse_dependencies(crate)`, checkpoint each crate separately
- Return list of dependency edge dicts with schema: `{"from_repo": str, "to_package": str, "ecosystem": str, "is_direct": bool}`

**`run_adoption_ingestion(config: IngestionConfig, checkpoint: Checkpoint) -> dict[str, dict]`:**
- Derive package names from the dependency edges produced by `run_deps_ingestion()` (or load from checkpoint if available)
- For each npm package: call `get_npm_downloads(name)`, checkpoint, handle None gracefully
- For each PyPI package: call `get_pypi_downloads(name)`, checkpoint, handle None gracefully
- For GitHub repos in `config.seed_csv`: extract `stars` and `forks` from `get_project_enrichment()` results (reuse if already checkpointed from deps ingestion)
- Return dict: `{repo_url: {"monthly_downloads": int, "github_stars": int, "github_forks": int}}`

**`run_full_ingestion(config: IngestionConfig | None = None) -> IngestionResult`:**
- The single public entry point. Creates config from environment if not provided: `GITHUB_TOKEN`, default values for everything else
- Creates checkpoint directory
- Calls `run_a7_ingestion()`, `run_deps_ingestion()`, `run_adoption_ingestion()` in sequence
- Writes 3 canonical output CSVs:
  - `{output_dir}/contributor_stats.csv` — columns: `repo_full_name, contributor_login, commits_90d, commit_share_pct`
  - `{output_dir}/dependency_edges.csv` — columns: `from_repo, to_package, ecosystem, is_direct`
  - `{output_dir}/adoption_signals.csv` — columns: `repo_full_name, ecosystem, monthly_downloads, github_stars, github_forks`
- Writes `{output_dir}/INGESTION_REPORT.md` (see format below)
- Returns `IngestionResult`

**`INGESTION_REPORT.md` format:**
```markdown
# PG Atlas — Ingestion Report
**Generated:** {ISO 8601 timestamp}
**GitHub token:** {'present' if token else 'ABSENT — git log data is unauthenticated (60 req/hr limit)'}

## Coverage Summary

| Pipeline | Attempted | Succeeded | Failed | Coverage % |
|---|---|---|---|---|
| A7 Git Log (contributor data) | 338 | N | M | X% |
| deps.dev (dependency edges) | 86 | N | M | X% |
| Cargo reverse deps | {len(SOROBAN_CORE_CRATES)} | N | M | X% |
| NPM downloads | N_npm | N | M | X% |
| PyPI downloads | N_pypi | N | M | X% |

## Output Files

| File | Rows | Path |
|---|---|---|
| contributor_stats.csv | N | 01_data/real/contributor_stats.csv |
| dependency_edges.csv | N | 01_data/real/dependency_edges.csv |
| adoption_signals.csv | N | 01_data/real/adoption_signals.csv |

## Errors Encountered

{table of errors by source, or "None" if clean run}

## Calibration Notes

- Active window: {config.since_days} days
- Git workers: {config.git_max_workers}
- deps.dev rate limit: {config.deps_rate_limit} req/min
- Cargo gap: {'mitigated via crates.io' if cargo_ran else 'NOT RUN — soroban reverse deps missing'}

## Next Step

Run the full metrics pipeline on real data:
    python -c "from pg_atlas.pipeline import run_full_pipeline; r = run_full_pipeline(real_data=True); print(r.snapshot.north_star_answer)"
```

### Deliverable 2: Update `pg_atlas/pipeline.py`

Add a `real_data` parameter to `run_full_pipeline()`:

```python
def run_full_pipeline(
    ...existing params...,
    real_data: bool = False,          # If True, run ingestion before metric computation
    ingest_config: IngestionConfig | None = None,   # Passed to run_full_ingestion()
) -> PipelineResult:
```

When `real_data=True`:
1. Call `run_full_ingestion(ingest_config)` at the start, before building the graph
2. Build graph from CSV as normal
3. Call `enrich_graph_with_ingestion(G, dep_edges, contribution_edges, adoption_data, activity_data)` with the ingestion results
4. Log: `"Real data mode: enriched graph with {n_contrib} contribution edges, {n_dep} dependency edges, {n_adopt} adoption signals."`
5. Continue with active subgraph projection and the rest of the 14-step pipeline unchanged

When `real_data=False` (default): behaviour unchanged from current implementation.

### Deliverable 3: Update `pg_atlas/tests/test_ingestion.py`

Add unit tests for the orchestrator (offline, no network calls):

1. `test_ingestion_config_defaults` — instantiate `IngestionConfig()`, assert all default values are set correctly
2. `test_checkpoint_save_and_load` — use `tmp_path` fixture, create `Checkpoint(tmp_path)`, call `save("a7", {"foo": "bar"})`, call `load("a7")`, assert round-trip
3. `test_checkpoint_mark_and_check_done` — call `mark_done("a7", "https://github.com/foo/bar")`, assert `is_done("a7", "https://github.com/foo/bar") == True`, assert `is_done("a7", "https://github.com/baz/qux") == False`
4. `test_checkpoint_atomic_write` — call `save("test", {"x": 1})`, assert no `.tmp` file remains after write, assert the saved file is valid JSON
5. `test_ingestion_result_structure` — instantiate `IngestionResult(contribution_edges=[], activity_data={}, dependency_edges=[], adoption_data={}, coverage_report={}, errors=[])`, assert it is a dataclass with the correct field names

### Deliverable 4: Update `CLAUDE.md`

Update the **"Running the Prototype"** section to reflect that the production package now exists:

```markdown
## Running the Package (pg_atlas/)

### Unit tests (offline, fast — 177 tests)
cd /Users/jaygut/Desktop/SCF_PG-Atlas
pip install -e ".[dev]"           # or: pip install networkx pandas numpy pytest
python -m pytest pg_atlas/tests/ -x -q   # ~1.5s

### Integration tests (require GITHUB_TOKEN, ~3-5 min)
export GITHUB_TOKEN=ghp_your_token_here
python -m pytest pg_atlas/tests/test_integration_real_api.py -m integration -v

### Full ingestion run (real data, ~20 min)
export GITHUB_TOKEN=ghp_your_token_here
python -c "from pg_atlas.ingestion.orchestrator import run_full_ingestion; r = run_full_ingestion(); print(r.coverage_report)"

### Full pipeline on real data
export GITHUB_TOKEN=ghp_your_token_here
python -c "
from pg_atlas.pipeline import run_full_pipeline
r = run_full_pipeline(real_data=True, report_path='04_implementation/snapshots/report.md')
print(r.snapshot.north_star_answer)
"
```

Also update the **"Known Gaps"** section to remove stale items that the production package has already addressed, and add:
- "Integration tests: available in `pg_atlas/tests/test_integration_real_api.py` (`pytest -m integration`)"
- "Real data ingestion: available via `pg_atlas/ingestion/orchestrator.py` — requires `GITHUB_TOKEN`"

### Quality requirements for Agent 2

**Correctness:**
- Every output file row must trace to a real API response, never to synthetic data
- Coverage percentage must be computed and reported accurately; do not inflate it
- The orchestrator must handle the case where `GITHUB_TOKEN` is absent — it continues with unauthenticated calls (60/hr), logs a clear warning, and notes the limit in the report

**Robustness:**
- `requests.exceptions.ConnectionError`, `urllib.error.URLError`, HTTP 403, 404, 429, 500 must all be caught at the orchestrator level and logged as errors, never raised
- Exponential backoff on HTTP 429 (rate limit): wait `2^attempt × base_delay` seconds, max 3 retries
- All file writes are atomic (write to `.tmp`, rename to final)

**Library choices — use only what's already available or stdlib:**
- Check `pg_atlas/ingestion/` — all existing clients use `urllib.request` (stdlib only, no `requests`)
- Use `csv`, `json`, `os`, `pathlib`, `datetime`, `concurrent.futures` — all stdlib
- If you need to verify a library is installed before using it, add a try/import guard with a clear error message

**Testing:**
- After writing `orchestrator.py`, run all 177 existing unit tests: `python -m pytest pg_atlas/tests/ -x -q --ignore=pg_atlas/tests/test_integration_real_api.py`
- All 177 must still pass — the orchestrator adds new tests, it never breaks existing ones
- Report the test count and pass/fail result explicitly in your completion message

**Output validation:**
After generating each canonical CSV, run a quick validation:
```python
import csv
with open("01_data/real/contributor_stats.csv") as f:
    rows = list(csv.DictReader(f))
assert len(rows) > 0, "contributor_stats.csv is empty"
required_cols = {"repo_full_name", "contributor_login", "commits_90d", "commit_share_pct"}
assert required_cols.issubset(rows[0].keys()), f"Missing columns: {required_cols - rows[0].keys()}"
```
Include equivalent validations for `dependency_edges.csv` and `adoption_signals.csv`. Log validation results.

---

## Completion Criteria

The sprint is complete when ALL of the following are true:

1. `pg_atlas/tests/test_integration_real_api.py` exists and contains ≥18 tests across 6 test classes
2. All 177 original unit tests still pass: `python -m pytest pg_atlas/tests/ -x -q --ignore=pg_atlas/tests/test_integration_real_api.py` → `177 passed`
3. `pg_atlas/ingestion/orchestrator.py` exists and exports `run_full_ingestion()`, `IngestionConfig`, `IngestionResult`
4. `pg_atlas/tests/test_ingestion.py` includes 5 new orchestrator unit tests and all ingestion tests still pass
5. `pg_atlas/pipeline.py` accepts `real_data: bool = False` and `ingest_config` parameters without breaking existing behaviour
6. `CLAUDE.md` is updated with accurate run instructions
7. When `run_full_ingestion()` is called with a valid `GITHUB_TOKEN`, it produces 3 non-empty CSV files in `01_data/real/` and one `INGESTION_REPORT.md`
8. When `run_full_pipeline(real_data=True)` is called, it produces a non-empty `snapshot.north_star_answer` string

**Do not:**
- Rewrite any existing ingestion clients (`deps_dev_client.py`, `git_log_parser.py`, etc.)
- Modify `01_data/raw/` or `01_data/processed/` files
- Change any existing test — only add new ones
- Use third-party HTTP libraries (requests, httpx, aiohttp) — existing clients use `urllib.request`; match this convention
- Change any metric computation logic in `pg_atlas/metrics/`
- Introduce any hardcoded API tokens

---

*This prompt was generated by Poseidon (Jay's AI assistant) on February 26, 2026.*
*Repository: `/Users/jaygut/Desktop/SCF_PG-Atlas`*
*Package: `pg_atlas/` — 43 modules, 177 tests, all passing as of Feb 26, 2026*
