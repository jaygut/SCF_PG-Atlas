"""
Integration tests for PG Atlas ingestion clients against real APIs.

These tests make actual HTTP requests to external services:
    - deps.dev (no auth required) — package metadata, dependencies, project enrichment
    - crates.io (no auth required) — download counts, reverse dependencies
    - npmjs.org (no auth required) — npm download counts
    - pypistats.org (no auth required) — PyPI download counts
    - GitHub REST API (GITHUB_TOKEN required) — git log parsing

How to run:
    # All integration tests (GitHub tests skipped without GITHUB_TOKEN):
    python -m pytest pg_atlas/tests/test_integration_real_api.py -m integration --run-integration -v

    # With GitHub tests:
    GITHUB_TOKEN=ghp_... python -m pytest pg_atlas/tests/test_integration_real_api.py -m integration --run-integration -v

    # Only deps.dev tests:
    python -m pytest pg_atlas/tests/test_integration_real_api.py::TestDepsDotDevClient -m integration --run-integration -v

Credentials needed:
    - GITHUB_TOKEN (optional): GitHub personal access token for git log parser tests.
      Without it, TestGitLogParser and TestFullIngestionSample are skipped entirely.

Expected runtime:
    - Without GitHub tests: ~30-60 seconds (rate limits on crates.io/npm/pypi)
    - With GitHub tests: ~60-120 seconds (depends on repo sizes and rate limits)

Author: Jay Gutierrez, PhD | SCF #41 -- Building the Backbone
"""

import csv
import os
import tempfile
import time

import pytest

from pg_atlas.ingestion.deps_dev_client import (
    DepsDependencyEdge,
    DepsProjectEnrichment,
    DepsDotDevClient,
    DepsVersion,
)
from pg_atlas.ingestion.crates_io_client import (
    CratesDownloadData,
    CratesIoClient,
    CratesReverseDep,
)
from pg_atlas.ingestion.npm_downloads_client import get_npm_downloads
from pg_atlas.ingestion.pypi_downloads_client import get_pypi_downloads
from pg_atlas.ingestion.git_log_parser import (
    parse_repo_contributions,
    parse_all_repos,
    results_to_contribution_edges,
    RepoContributionResult,
)
from pg_atlas.graph.builder import build_graph_from_csv, enrich_graph_with_ingestion


# ── Helpers ───────────────────────────────────────────────────────────────────

_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

requires_github_token = pytest.mark.skipif(
    not _GITHUB_TOKEN,
    reason="GITHUB_TOKEN environment variable not set -- skipping GitHub API tests",
)

# First 5 GitHub URLs from A7_submission_github_repos.csv for multi-repo tests
_A7_CSV_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "01_data", "processed",
    "A7_submission_github_repos.csv",
)


def _read_first_n_github_urls(n: int = 5) -> list[str]:
    """Read the first N github_url values from the A7 CSV."""
    urls: list[str] = []
    with open(_A7_CSV_PATH, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            url = row.get("github_url", "").strip()
            if url:
                urls.append(url)
            if len(urls) >= n:
                break
    return urls


def _write_temp_csv(urls: list[str]) -> str:
    """Write a temporary CSV file with the given GitHub URLs.

    The CSV matches the schema expected by parse_all_repos:
    round, submission_title, github_url, total_awarded_usd, use_soroban, tranche_completion
    """
    fd, path = tempfile.mkstemp(suffix=".csv", prefix="test_integration_")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["round", "submission_title", "github_url",
                        "total_awarded_usd", "use_soroban", "tranche_completion"],
        )
        writer.writeheader()
        for i, url in enumerate(urls):
            writer.writerow({
                "round": "SCF #99",
                "submission_title": f"Test Project {i}",
                "github_url": url,
                "total_awarded_usd": "1000.0",
                "use_soroban": "",
                "tranche_completion": "",
            })
    return path


# ── TestDepsDotDevClient ─────────────────────────────────────────────────────

@pytest.mark.integration
class TestDepsDotDevClient:
    """Integration tests for the deps.dev REST API client.

    These tests call the public deps.dev API (no auth required, 100 req/min).
    They validate that the Stellar ecosystem NPM and Cargo packages are
    resolvable and return well-formed metadata and dependency edges.
    """

    def test_get_version_npm_stellar_sdk(self):
        """Fetch version metadata for @stellar/stellar-sdk from deps.dev.

        Validates that the deps.dev API returns a DepsVersion object with the
        correct package name, ecosystem, a non-empty version string, and a
        source repo URL pointing to GitHub.

        Failure indicates: deps.dev API is down, the package was removed from
        npm, or the response schema has changed.
        """
        client = DepsDotDevClient()
        result = client.get_version("NPM", "@stellar/stellar-sdk")

        assert result is not None, (
            "get_version returned None -- deps.dev may be unreachable or "
            "@stellar/stellar-sdk may have been removed from the registry"
        )
        assert isinstance(result, DepsVersion), (
            f"Expected DepsVersion, got {type(result).__name__}"
        )
        assert result.name == "@stellar/stellar-sdk", (
            f"Expected name '@stellar/stellar-sdk', got '{result.name}'"
        )
        assert result.ecosystem == "NPM", (
            f"Expected ecosystem 'NPM', got '{result.ecosystem}'"
        )
        assert isinstance(result.version, str) and len(result.version) > 0, (
            f"Expected non-empty version string, got '{result.version}'"
        )
        assert result.source_repo_url is not None and result.source_repo_url.startswith("https://github.com"), (
            f"Expected source_repo_url starting with 'https://github.com', "
            f"got '{result.source_repo_url}'"
        )

    def test_get_dependencies_npm_stellar_sdk(self):
        """Fetch dependency edges for @stellar/stellar-sdk from deps.dev.

        First resolves the default version, then fetches its direct dependencies.
        Validates that the result is a non-empty list of DepsDependencyEdge objects
        with at least one DIRECT relation and non-empty to_name fields.

        Failure indicates: deps.dev dependencies endpoint changed, the package
        has no declared dependencies, or the response schema has changed.
        """
        client = DepsDotDevClient()
        version_info = client.get_version("NPM", "@stellar/stellar-sdk")
        assert version_info is not None, (
            "Cannot test dependencies -- get_version returned None"
        )

        deps = client.get_dependencies("NPM", "@stellar/stellar-sdk", version_info.version)

        assert isinstance(deps, list), (
            f"Expected list of dependencies, got {type(deps).__name__}"
        )
        assert len(deps) > 0, (
            "Expected non-empty dependency list for @stellar/stellar-sdk"
        )
        for edge in deps:
            assert isinstance(edge, DepsDependencyEdge), (
                f"Expected DepsDependencyEdge, got {type(edge).__name__}"
            )

        direct_edges = [e for e in deps if e.relation == "DIRECT"]
        assert len(direct_edges) >= 1, (
            "Expected at least one DIRECT dependency edge"
        )

        for edge in deps:
            assert isinstance(edge.to_name, str) and len(edge.to_name) > 0, (
                f"Expected non-empty to_name, got '{edge.to_name}'"
            )

    def test_get_project_enrichment_stellar_sdk(self):
        """Fetch project enrichment (stars, forks) for js-stellar-sdk from deps.dev.

        Validates that the deps.dev project endpoint returns a DepsProjectEnrichment
        object with positive star count and non-negative fork count.

        Failure indicates: deps.dev projects endpoint changed, the repository was
        moved/deleted, or the response schema has changed.
        """
        client = DepsDotDevClient()
        result = client.get_project_enrichment("https://github.com/stellar/js-stellar-sdk")

        assert result is not None, (
            "get_project_enrichment returned None -- deps.dev projects endpoint "
            "may be unreachable or the repo may have moved"
        )
        assert isinstance(result, DepsProjectEnrichment), (
            f"Expected DepsProjectEnrichment, got {type(result).__name__}"
        )
        assert result.stars > 0, (
            f"Expected stars > 0 for stellar/js-stellar-sdk, got {result.stars}"
        )
        assert result.forks >= 0, (
            f"Expected forks >= 0, got {result.forks}"
        )

    def test_cargo_package_dependencies(self):
        """Fetch dependencies for the soroban-sdk Cargo package from deps.dev.

        Gets the default version of soroban-sdk, then fetches its dependency edges.
        Validates that the result is a list (possibly empty -- deps.dev has a known
        Cargo blind spot where dependentCount=0 for all Cargo packages, but
        forward dependencies should still resolve).

        Failure indicates: deps.dev cannot resolve soroban-sdk at all (not just
        the dependentCount blind spot), or the Cargo ecosystem endpoint has changed.
        """
        client = DepsDotDevClient()
        version_info = client.get_version("CARGO", "soroban-sdk")
        # soroban-sdk may or may not resolve on deps.dev; skip gracefully
        if version_info is None:
            pytest.skip(
                "soroban-sdk not found on deps.dev -- Cargo blind spot may "
                "prevent version resolution entirely"
            )

        deps = client.get_dependencies("CARGO", "soroban-sdk", version_info.version)
        assert isinstance(deps, list), (
            f"Expected list of dependencies (possibly empty), got {type(deps).__name__}"
        )
        # Note: deps.dev returns dependentCount=0 for ALL Cargo packages (the
        # Cargo blind spot documented in CLAUDE.md). Forward dependencies may
        # still be available, but an empty list is acceptable.

    def test_bootstrap_stellar_graph_returns_data(self):
        """Run full bootstrap ingestion for STELLAR_SEED_PACKAGES from deps.dev.

        Validates that bootstrap_stellar_graph() returns a tuple of (metadata, edges)
        where metadata has at least 3 items (some packages may not resolve) and edges
        has at least 1 item. Also validates types of returned objects.

        Failure indicates: deps.dev is unreachable, most Stellar packages have been
        removed from their registries, or the bootstrap logic has a bug.
        """
        client = DepsDotDevClient()
        metadata, edges = client.bootstrap_stellar_graph()

        assert isinstance(metadata, list), (
            f"Expected metadata to be a list, got {type(metadata).__name__}"
        )
        assert isinstance(edges, list), (
            f"Expected edges to be a list, got {type(edges).__name__}"
        )
        assert len(metadata) >= 3, (
            f"Expected at least 3 resolved packages in metadata, got {len(metadata)}. "
            f"deps.dev may be partially unavailable."
        )
        assert len(edges) >= 1, (
            f"Expected at least 1 dependency edge, got {len(edges)}. "
            f"All resolved packages may have 0 dependencies (unlikely)."
        )

        for item in metadata:
            assert isinstance(item, DepsVersion), (
                f"Expected DepsVersion in metadata, got {type(item).__name__}"
            )
        for edge in edges:
            assert isinstance(edge, DepsDependencyEdge), (
                f"Expected DepsDependencyEdge in edges, got {type(edge).__name__}"
            )


# ── TestCratesIoClient ───────────────────────────────────────────────────────

@pytest.mark.integration
class TestCratesIoClient:
    """Integration tests for the crates.io API client.

    These tests call the public crates.io API (1 req/sec rate limit, mandatory
    User-Agent header). They validate that the Soroban core crates are
    resolvable and have real download and reverse dependency data.
    """

    def test_get_downloads_soroban_sdk(self):
        """Fetch download statistics for soroban-sdk from crates.io.

        Validates that the crates.io API returns a CratesDownloadData object
        with the correct crate name and a positive total download count.

        Failure indicates: crates.io is down, soroban-sdk was yanked/removed,
        or the API response schema has changed.
        """
        client = CratesIoClient()
        result = client.get_downloads("soroban-sdk")

        assert isinstance(result, CratesDownloadData), (
            f"Expected CratesDownloadData, got {type(result).__name__}"
        )
        assert result.crate_name == "soroban-sdk", (
            f"Expected crate_name 'soroban-sdk', got '{result.crate_name}'"
        )
        assert result.total_downloads > 0, (
            f"Expected total_downloads > 0, got {result.total_downloads}. "
            f"soroban-sdk should have real downloads on crates.io."
        )

    def test_get_reverse_dependencies_soroban_sdk(self):
        """Fetch reverse dependencies for soroban-sdk from crates.io.

        Validates that the crates.io reverse dependencies endpoint returns a
        non-empty list of CratesReverseDep objects. soroban-sdk is a core
        Soroban crate and should have at least one dependent.

        Failure indicates: crates.io reverse deps endpoint changed, soroban-sdk
        lost all dependents (unlikely), or the response parsing is broken.
        """
        client = CratesIoClient()
        # Rate limit: the client handles 1 req/sec internally
        result = client.get_reverse_dependencies("soroban-sdk")

        assert isinstance(result, list), (
            f"Expected list of reverse dependencies, got {type(result).__name__}"
        )
        assert len(result) >= 1, (
            "Expected at least 1 reverse dependency for soroban-sdk. "
            "This is a core Soroban crate -- 0 dependents would be very unusual."
        )
        for dep in result:
            assert isinstance(dep, CratesReverseDep), (
                f"Expected CratesReverseDep instance, got {type(dep).__name__}"
            )

    def test_rate_limit_respected(self):
        """Verify that the CratesIoClient respects the 1 req/sec rate limit.

        Makes 3 sequential get_downloads() calls for different crates and
        measures the wall-clock time. The total elapsed time should be at least
        1.8 seconds (0.9s between each pair of consecutive calls, accounting
        for minor timing jitter).

        Failure indicates: the rate limiting logic in CratesIoClient._get()
        is broken or was bypassed.
        """
        client = CratesIoClient()
        crates = ["soroban-sdk", "stellar-xdr", "stellar-strkey"]
        timestamps: list[float] = []

        for crate in crates:
            t_start = time.monotonic()
            client.get_downloads(crate)
            timestamps.append(t_start)

        # Check that there was at least ~0.9s between consecutive calls
        # (allowing 0.1s tolerance for timing jitter)
        total_elapsed = time.monotonic() - timestamps[0]
        assert total_elapsed >= 1.8, (
            f"Expected at least 1.8s for 3 sequential crates.io calls "
            f"(1 req/sec rate limit), but only {total_elapsed:.2f}s elapsed. "
            f"Rate limiting may be broken."
        )


# ── TestNPMDownloadsClient ───────────────────────────────────────────────────

@pytest.mark.integration
class TestNPMDownloadsClient:
    """Integration tests for the npm downloads API client.

    These tests call the public npmjs.org downloads API (generous rate limit).
    They validate download counts for real Stellar packages and graceful
    handling of nonexistent packages.
    """

    def test_get_stellar_sdk_downloads(self):
        """Fetch download count for @stellar/stellar-sdk from npm.

        Validates that get_npm_downloads returns a positive integer for a
        well-known, actively maintained npm package.

        Failure indicates: npmjs.org API is down, @stellar/stellar-sdk was
        unpublished, or the response schema has changed.
        """
        result = get_npm_downloads("@stellar/stellar-sdk")

        assert result is not None, (
            "get_npm_downloads returned None -- npmjs.org API may be unreachable "
            "or @stellar/stellar-sdk may have been unpublished"
        )
        assert isinstance(result, int), (
            f"Expected int, got {type(result).__name__}"
        )
        assert result > 0, (
            f"Expected positive download count, got {result}. "
            f"@stellar/stellar-sdk should have real downloads."
        )

    def test_nonexistent_package_returns_none(self):
        """Verify graceful handling of a nonexistent npm package.

        Calls get_npm_downloads with a deliberately nonexistent package name.
        The function should return None without raising any exception.

        Failure indicates: error handling in get_npm_downloads is broken and
        it raises instead of returning None for 404 responses.
        """
        result = get_npm_downloads("@stellar/this-package-does-not-exist-xyzzy123")

        assert result is None, (
            f"Expected None for nonexistent package, got {result!r}. "
            f"get_npm_downloads should return None for 404 responses."
        )


# ── TestPyPIDownloadsClient ──────────────────────────────────────────────────

@pytest.mark.integration
class TestPyPIDownloadsClient:
    """Integration tests for the PyPI downloads API client.

    These tests call the public pypistats.org API (courtesy rate limit of
    1 req/sec). They validate download counts for real Stellar packages and
    graceful handling of nonexistent packages.
    """

    def test_get_stellar_sdk_pypi_downloads(self):
        """Fetch download count for stellar-sdk from PyPI.

        Validates that get_pypi_downloads returns a positive integer for the
        official Stellar Python SDK.

        Failure indicates: pypistats.org API is down, stellar-sdk was removed
        from PyPI, or the response schema has changed.
        """
        result = get_pypi_downloads("stellar-sdk")

        assert result is not None, (
            "get_pypi_downloads returned None -- pypistats.org API may be "
            "unreachable or stellar-sdk may have been removed from PyPI"
        )
        assert isinstance(result, int), (
            f"Expected int, got {type(result).__name__}"
        )
        assert result > 0, (
            f"Expected positive download count, got {result}. "
            f"stellar-sdk should have real downloads on PyPI."
        )

    def test_nonexistent_package_returns_none(self):
        """Verify graceful handling of a nonexistent PyPI package.

        Calls get_pypi_downloads with a deliberately nonexistent package name.
        The function should return None without raising any exception.

        Failure indicates: error handling in get_pypi_downloads is broken and
        it raises instead of returning None for 404 responses.
        """
        result = get_pypi_downloads("stellar-this-does-not-exist-xyzzy456")

        assert result is None, (
            f"Expected None for nonexistent package, got {result!r}. "
            f"get_pypi_downloads should return None for 404 responses."
        )


# ── TestGitLogParser ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestGitLogParser:
    """Integration tests for the A7 git log parser (GitHub REST API).

    These tests require a GITHUB_TOKEN environment variable for authentication.
    Without it, all tests in this class are skipped. The tests validate that
    the parser correctly fetches commit history, handles inaccessible repos,
    and produces well-formed output data structures.
    """

    @requires_github_token
    def test_parse_single_well_known_repo(self):
        """Parse contributor stats for stellar/js-stellar-sdk via GitHub API.

        Validates that parse_repo_contributions returns an accessible result
        with positive commit count, at least one contributor, and a non-empty
        latest_commit_date.

        Failure indicates: GITHUB_TOKEN is invalid, the repo was deleted,
        GitHub API changed its commits endpoint, or the parsing logic is broken.
        """
        result = parse_repo_contributions(
            "https://github.com/stellar/js-stellar-sdk",
            github_token=_GITHUB_TOKEN,
        )

        assert isinstance(result, RepoContributionResult), (
            f"Expected RepoContributionResult, got {type(result).__name__}"
        )
        assert result.accessible is True, (
            f"Expected accessible=True for stellar/js-stellar-sdk, "
            f"got accessible=False with error: {result.error}"
        )
        assert result.total_commits_in_window > 0, (
            f"Expected total_commits_in_window > 0, got {result.total_commits_in_window}. "
            f"stellar/js-stellar-sdk should have recent commits."
        )
        assert len(result.contributors) >= 1, (
            f"Expected at least 1 contributor, got {len(result.contributors)}"
        )
        for contrib in result.contributors:
            assert contrib.commits_in_window > 0, (
                f"Expected commits_in_window > 0 for contributor "
                f"'{contrib.display_name}', got {contrib.commits_in_window}"
            )
        assert result.latest_commit_date != "", (
            "Expected non-empty latest_commit_date for an accessible repo"
        )

    @requires_github_token
    def test_parse_repo_returns_days_since_commit(self):
        """Verify that days_since_latest_commit is computed correctly.

        Validates that the result has a reasonable days_since_latest_commit
        value: >= 0 (cannot be in the future) and < 365 (the Stellar SDK
        should have commits within the last year).

        Failure indicates: the date parsing logic in parse_repo_contributions
        is broken, or the repo has gone stale for over a year.
        """
        result = parse_repo_contributions(
            "https://github.com/stellar/js-stellar-sdk",
            github_token=_GITHUB_TOKEN,
        )

        assert result.accessible is True, (
            f"Cannot test days_since_commit -- repo inaccessible: {result.error}"
        )
        assert result.days_since_latest_commit >= 0, (
            f"Expected days_since_latest_commit >= 0, "
            f"got {result.days_since_latest_commit}"
        )
        assert result.days_since_latest_commit < 365, (
            f"Expected days_since_latest_commit < 365 for an active repo, "
            f"got {result.days_since_latest_commit}. stellar/js-stellar-sdk "
            f"should have had a commit in the last year."
        )

    @requires_github_token
    def test_inaccessible_repo_fails_gracefully(self):
        """Verify graceful handling of a nonexistent GitHub repository.

        Calls parse_repo_contributions with a deliberately nonexistent repo URL.
        The function should return a result with accessible=False and a non-empty
        error string, without raising any exception.

        Failure indicates: error handling in the GitHub API layer is broken
        and 404s are not caught properly.
        """
        result = parse_repo_contributions(
            "https://github.com/stellar/this-repo-definitely-does-not-exist-xyzzy",
            github_token=_GITHUB_TOKEN,
        )

        assert isinstance(result, RepoContributionResult), (
            f"Expected RepoContributionResult, got {type(result).__name__}"
        )
        assert result.accessible is False, (
            "Expected accessible=False for a nonexistent repo"
        )
        assert result.error is not None and len(result.error) > 0, (
            f"Expected non-empty error message, got '{result.error}'"
        )

    @requires_github_token
    def test_parse_5_repos_from_csv(self):
        """Parse 5 repos from a temp CSV using parse_all_repos.

        Writes a temporary CSV with the first 5 GitHub URLs from
        A7_submission_github_repos.csv, then calls parse_all_repos with
        max_workers=2. Validates that all 5 are processed and at least 2
        are accessible (some repos may be private/deleted/moved).

        Failure indicates: the CSV reading logic is broken, the
        ThreadPoolExecutor logic fails, or most Stellar repos have become
        inaccessible.
        """
        urls = _read_first_n_github_urls(5)
        assert len(urls) >= 5, (
            f"Expected at least 5 URLs from A7 CSV, got {len(urls)}"
        )
        temp_csv = _write_temp_csv(urls[:5])

        try:
            results = parse_all_repos(
                repos_csv_path=temp_csv,
                github_token=_GITHUB_TOKEN,
                window_days=90,
                max_workers=2,
            )

            assert isinstance(results, list), (
                f"Expected list of results, got {type(results).__name__}"
            )
            assert len(results) == 5, (
                f"Expected 5 results (one per URL), got {len(results)}"
            )

            accessible_count = sum(1 for r in results if r.accessible)
            assert accessible_count >= 2, (
                f"Expected at least 2 accessible repos out of 5, "
                f"got {accessible_count}. Errors: "
                + "; ".join(
                    f"{r.repo_url}: {r.error}"
                    for r in results
                    if not r.accessible
                )
            )
        finally:
            os.unlink(temp_csv)

    @requires_github_token
    def test_results_to_edges_produces_valid_schema(self):
        """Convert parse_all_repos output to contribution edge dicts.

        Runs parse_all_repos on 3 repos, then passes the results to
        results_to_contribution_edges(). Validates that the output is a list
        of dicts, each with the required keys (contributor, repo, commits)
        and positive commit counts.

        Failure indicates: the edge conversion logic in
        results_to_contribution_edges() has a bug or schema mismatch.
        """
        urls = _read_first_n_github_urls(3)
        assert len(urls) >= 3, (
            f"Expected at least 3 URLs from A7 CSV, got {len(urls)}"
        )
        temp_csv = _write_temp_csv(urls[:3])

        try:
            results = parse_all_repos(
                repos_csv_path=temp_csv,
                github_token=_GITHUB_TOKEN,
                window_days=90,
                max_workers=2,
            )

            edges = results_to_contribution_edges(results)

            assert isinstance(edges, list), (
                f"Expected list of edge dicts, got {type(edges).__name__}"
            )

            # We may get 0 edges if all 3 repos are inaccessible or have 0 commits.
            # But at least some should produce edges.
            if any(r.accessible and r.total_commits_in_window > 0 for r in results):
                assert len(edges) > 0, (
                    "Expected at least 1 contribution edge from accessible repos "
                    "with commits, got 0"
                )

            required_keys = {"contributor", "repo", "commits"}
            for edge in edges:
                assert isinstance(edge, dict), (
                    f"Expected dict, got {type(edge).__name__}"
                )
                missing = required_keys - set(edge.keys())
                assert not missing, (
                    f"Edge dict is missing required keys: {missing}. "
                    f"Got keys: {set(edge.keys())}"
                )
                assert edge["commits"] > 0, (
                    f"Expected commits > 0, got {edge['commits']} "
                    f"for contributor '{edge.get('contributor')}'"
                )
        finally:
            os.unlink(temp_csv)


# ── TestFullIngestionSample ──────────────────────────────────────────────────

@pytest.mark.integration
class TestFullIngestionSample:
    """End-to-end integration test: build graph from CSV, enrich with real data.

    Requires GITHUB_TOKEN for the git log parsing step. Validates that the full
    ingestion pipeline (CSV graph + contribution edges) produces a graph with
    Contributor nodes and contributed_to edges.
    """

    @requires_github_token
    def test_enrich_graph_with_real_sample(self):
        """Build CSV graph, parse 3 repos, and enrich with contribution edges.

        This is the most comprehensive integration test. It exercises:
        1. build_graph_from_csv() with real seed CSVs
        2. parse_all_repos() against 3 real GitHub repos
        3. results_to_contribution_edges() for schema conversion
        4. enrich_graph_with_ingestion() to merge contributor data into the graph

        Validates that the graph grew (new nodes added), contains at least one
        Contributor node, and has at least one contributed_to edge.

        Failure indicates: a mismatch between the ingestion pipeline outputs
        and the graph enrichment function's expected input format.
        """
        # Step 1: Build the base graph from CSVs
        base = "/Users/jaygut/Desktop/SCF_PG-Atlas/01_data/processed"
        G = build_graph_from_csv(
            seed_list_path=os.path.join(base, "A5_pg_candidate_seed_list.csv"),
            orgs_path=os.path.join(base, "A6_github_orgs_seed.csv"),
            repos_path=os.path.join(base, "A7_submission_github_repos.csv"),
        )
        initial_node_count = G.number_of_nodes()
        initial_edge_count = G.number_of_edges()

        assert initial_node_count > 0, (
            "Base graph has 0 nodes -- build_graph_from_csv may have failed"
        )

        # Step 2: Parse 3 repos for contribution data
        urls = _read_first_n_github_urls(3)
        assert len(urls) >= 3, (
            f"Expected at least 3 URLs from A7 CSV, got {len(urls)}"
        )
        temp_csv = _write_temp_csv(urls[:3])

        try:
            results = parse_all_repos(
                repos_csv_path=temp_csv,
                github_token=_GITHUB_TOKEN,
                window_days=90,
                max_workers=2,
            )
            contrib_edges = results_to_contribution_edges(results)

            # Step 3: Enrich the graph
            G = enrich_graph_with_ingestion(
                G,
                dep_edges=[],            # no dependency edges for this test
                contrib_edges=contrib_edges,
                adoption_data={},        # no adoption data for this test
                activity_data={},        # no activity data for this test
            )

            # Step 4: Validate enrichment
            if len(contrib_edges) > 0:
                assert G.number_of_nodes() > initial_node_count, (
                    f"Expected graph to grow after enrichment "
                    f"(was {initial_node_count}, still {G.number_of_nodes()})"
                )

                contributor_nodes = [
                    n for n, d in G.nodes(data=True)
                    if d.get("node_type") == "Contributor"
                ]
                assert len(contributor_nodes) >= 1, (
                    "Expected at least 1 Contributor node after enrichment, got 0"
                )

                contributed_to_edges = [
                    (u, v) for u, v, d in G.edges(data=True)
                    if d.get("edge_type") == "contributed_to"
                ]
                assert len(contributed_to_edges) >= 1, (
                    "Expected at least 1 contributed_to edge after enrichment, got 0"
                )
            else:
                # All repos were inaccessible or had no commits -- still valid
                pytest.skip(
                    "No contribution edges produced (all repos may be "
                    "inaccessible or have 0 commits in the window)"
                )
        finally:
            os.unlink(temp_csv)
