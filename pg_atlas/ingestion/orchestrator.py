"""
pg_atlas/ingestion/orchestrator.py — Ingestion orchestration layer.

Wires all real API data sources (GitHub, deps.dev, crates.io, npm, PyPI)
into a single entry point that produces canonical CSVs and an IngestionResult
compatible with the graph enrichment layer.

Features:
    - Checkpoint/resume: atomic JSON checkpoint files enable restart after
      partial failures (network outage, rate-limit exhaustion, etc.)
    - Robust error handling: all HTTP errors caught at orchestrator level,
      individual failures do not abort the run
    - Canonical CSV output: contributor_stats.csv, dependency_edges.csv,
      adoption_signals.csv written atomically to output_dir

Usage:
    from pg_atlas.ingestion.orchestrator import run_full_ingestion
    result = run_full_ingestion()

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import csv
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Resolve repo root relative to this file:
# orchestrator.py -> ingestion/ -> pg_atlas/ -> repo root
_THIS_FILE = os.path.abspath(__file__)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class IngestionConfig:
    """Configuration for a full ingestion run.

    All paths are resolved relative to the repository root.

    Attributes:
        github_token:   GitHub PAT for higher rate limits (from GITHUB_TOKEN env).
        since_days:     Rolling window in days for git commit stats.
        git_max_workers: Concurrent GitHub API threads for A7 parsing.
        deps_rate_limit: deps.dev requests per minute.
        checkpoint_dir: Directory for checkpoint JSON files.
        output_dir:     Directory for canonical CSV outputs.
        repos_csv:      Path to A7_submission_github_repos.csv.
        seed_csv:       Path to A5_pg_candidate_seed_list.csv.
        orgs_csv:       Path to A6_github_orgs_seed.csv.
    """

    github_token: Optional[str] = None
    since_days: int = 90
    git_max_workers: int = 4
    deps_rate_limit: int = 100
    checkpoint_dir: str = "01_data/real/checkpoints"
    output_dir: str = "01_data/real"
    repos_csv: str = "01_data/processed/A7_submission_github_repos.csv"
    seed_csv: str = "01_data/processed/A5_pg_candidate_seed_list.csv"
    orgs_csv: str = "01_data/processed/A6_github_orgs_seed.csv"


@dataclass
class IngestionResult:
    """Complete output of a full ingestion run.

    Attributes:
        contribution_edges: Edge dicts for graph enrichment (contributor -> repo).
        activity_data:      Per-repo activity metadata keyed by repo URL.
        dependency_edges:   Dependency edge dicts for graph enrichment.
        adoption_data:      Adoption signals keyed by repo URL or package name.
        coverage_report:    Summary statistics about what was ingested.
        errors:             List of error dicts recording individual failures.
    """

    contribution_edges: list[dict] = field(default_factory=list)
    activity_data: dict[str, dict] = field(default_factory=dict)
    dependency_edges: list[dict] = field(default_factory=list)
    adoption_data: dict[str, dict] = field(default_factory=dict)
    coverage_report: dict = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Checkpoint — atomic save/load for resume-after-failure
# ---------------------------------------------------------------------------

class Checkpoint:
    """Atomic checkpoint storage for resumable ingestion.

    Each checkpoint is a JSON file at ``{checkpoint_dir}/{key}_progress.json``.
    Writes use a ``.tmp`` intermediate to guarantee atomicity (write-then-rename).

    Args:
        checkpoint_dir: Absolute path to the checkpoint directory.
    """

    def __init__(self, checkpoint_dir: str) -> None:
        self._dir = checkpoint_dir
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(self._dir, f"{key}_progress.json")

    def save(self, key: str, data: dict) -> None:
        """Write *data* to the checkpoint file atomically (write .tmp, rename)."""
        target = self._path(key)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, target)

    def load(self, key: str) -> dict:
        """Load checkpoint data.  Returns empty dict if not found."""
        path = self._path(key)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            logger.warning("Corrupt checkpoint %s — starting fresh", path)
            return {}

    def mark_done(self, key: str, item_id: str) -> None:
        """Record *item_id* as completed in the *key* checkpoint."""
        data = self.load(key)
        done = set(data.get("done", []))
        done.add(item_id)
        data["done"] = sorted(done)
        self.save(key, data)

    def is_done(self, key: str, item_id: str) -> bool:
        """Check whether *item_id* was already completed."""
        data = self.load(key)
        return item_id in set(data.get("done", []))

    def get_results(self, key: str) -> list:
        """Return all saved results from checkpoint, or empty list."""
        data = self.load(key)
        return data.get("results", [])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_path(relative: str) -> str:
    """Resolve a path relative to the repo root."""
    return os.path.join(_REPO_ROOT, relative)


def _read_urls_from_csv(csv_path: str, url_column: str = "github_url") -> list[str]:
    """Read unique GitHub URLs from a CSV file.

    Checks for both ``github_url`` and ``repo_url`` columns and uses
    whichever is present.

    Returns:
        List of unique, non-empty URL strings.
    """
    urls: list[str] = []
    seen: set[str] = set()
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            headers = reader.fieldnames or []
            # Determine which column to use
            col = None
            if "github_url" in headers:
                col = "github_url"
            elif "repo_url" in headers:
                col = "repo_url"
            else:
                col = url_column  # fallback

            for row in reader:
                url = (row.get(col) or "").strip()
                if url and url != "nan" and url not in seen:
                    seen.add(url)
                    urls.append(url)
    except FileNotFoundError:
        logger.error("CSV not found: %s", csv_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to read CSV %s: %s", csv_path, exc)
    return urls


def _load_contribution_edges_from_csv(csv_path: str) -> list[dict]:
    """Reconstruct contribution edge dicts from a saved contributor_stats.csv.

    Used to recover data on re-run when all A7 items are already checkpointed.
    """
    edges: list[dict] = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                repo_name = row.get("repo_full_name", "")
                repo_url = f"https://github.com/{repo_name}" if repo_name and "/" in repo_name else repo_name
                contributor = row.get("contributor_login", "")
                commits = int(row.get("commits_90d", 0) or 0)
                if contributor and repo_url:
                    edges.append({
                        "contributor": contributor,
                        "repo": repo_url,
                        "commits": commits,
                        "first_date": "",
                        "last_date": "",
                    })
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load contribution edges from %s: %s", csv_path, exc)
    return edges


def _load_dep_edges_from_csv(csv_path: str) -> list[dict]:
    """Reconstruct dependency edge dicts from a saved dependency_edges.csv.

    Used to recover data on re-run when all dep items are already checkpointed.
    """
    edges: list[dict] = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                edges.append({
                    "from_repo": row.get("from_repo", ""),
                    "to_package": row.get("to_package", ""),
                    "ecosystem": row.get("ecosystem", ""),
                    "is_direct": row.get("is_direct", "True") in ("True", "true", "1"),
                })
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load dep edges from %s: %s", csv_path, exc)
    return edges


def _atomic_csv_write(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    """Write rows to a CSV file atomically (write .tmp, rename)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# A7 — Git log parsing (contributor statistics)
# ---------------------------------------------------------------------------

def run_a7_ingestion(
    config: IngestionConfig,
    checkpoint: Checkpoint,
) -> tuple[list[dict], dict[str, dict]]:
    """Run A7 git log parsing for all repos in config.repos_csv.

    Calls ``parse_repo_contributions`` for each GitHub URL not already
    checkpointed.  Converts results to contribution edge dicts and
    activity data via the helpers in ``git_log_parser``.

    Args:
        config:     IngestionConfig with repos_csv, github_token, etc.
        checkpoint: Checkpoint instance for resume support.

    Returns:
        Tuple of (contribution_edges, activity_data).
    """
    from pg_atlas.ingestion.git_log_parser import (
        parse_repo_contributions,
        results_to_activity_data,
        results_to_contribution_edges,
    )

    repos_csv = _resolve_path(config.repos_csv)
    urls = _read_urls_from_csv(repos_csv)
    total = len(urls)
    logger.info("A7 ingestion: %d repos loaded from %s", total, repos_csv)

    if not config.github_token:
        logger.warning(
            "No GITHUB_TOKEN set — unauthenticated rate limit is 60 req/hr. "
            "Set GITHUB_TOKEN env var for full corpus ingestion."
        )

    # Load previously cached activity data from checkpoint for re-run recovery.
    _ckpt_data_a7 = checkpoint.load("a7")
    activity_cache: dict = _ckpt_data_a7.get("activity_cache", {})

    results = []
    errors: list[dict] = []

    for idx, url in enumerate(urls, start=1):
        if checkpoint.is_done("a7", url):
            logger.debug("A7: skipping already-processed repo %s", url)
            continue

        try:
            result = parse_repo_contributions(
                url,
                github_token=config.github_token,
                window_days=config.since_days,
            )
            results.append(result)
            checkpoint.mark_done("a7", url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("A7: error processing %s: %s", url, exc)
            errors.append({"source": "a7", "url": url, "error": str(exc)})

        if idx % 10 == 0 or idx == total:
            pct = 100.0 * idx / total if total > 0 else 100.0
            logger.info(
                "A7 progress: %d/%d repos processed (%.0f%%)", idx, total, pct
            )

    contribution_edges = results_to_contribution_edges(results)
    activity_data = results_to_activity_data(results)

    # Persist newly fetched activity data into checkpoint cache for future re-runs.
    if activity_data:
        _ckpt = checkpoint.load("a7")
        cached = _ckpt.get("activity_cache", {})
        cached.update(activity_data)
        _ckpt["activity_cache"] = cached
        checkpoint.save("a7", _ckpt)
        logger.info("A7: saved activity cache for %d repos.", len(activity_data))

    # If all items were already checkpointed, recover from saved cache and CSV.
    if not activity_data and activity_cache:
        activity_data = activity_cache
        logger.info("A7: recovered activity_data for %d repos from checkpoint cache.", len(activity_data))

    if not contribution_edges:
        contrib_csv = os.path.join(_resolve_path(config.output_dir), "contributor_stats.csv")
        if os.path.isfile(contrib_csv):
            contribution_edges = _load_contribution_edges_from_csv(contrib_csv)
            logger.info("A7: recovered %d contribution edges from contributor_stats.csv.", len(contribution_edges))

    logger.info(
        "A7 complete: %d contribution edges, %d repos with activity data, %d errors",
        len(contribution_edges),
        len(activity_data),
        len(errors),
    )
    return contribution_edges, activity_data


# ---------------------------------------------------------------------------
# Dependency ingestion (deps.dev + crates.io)
# ---------------------------------------------------------------------------

def run_deps_ingestion(
    config: IngestionConfig,
    checkpoint: Checkpoint,
) -> list[dict]:
    """Run dependency ingestion from deps.dev and crates.io.

    Three phases:
    1. GitHub project enrichment for all URLs in seed_csv (stars/forks).
    2. Stellar seed package bootstrap from deps.dev.
    3. Soroban core crate reverse dependencies from crates.io.

    Args:
        config:     IngestionConfig with seed_csv, deps_rate_limit, etc.
        checkpoint: Checkpoint instance for resume support.

    Returns:
        List of dependency edge dicts suitable for graph enrichment.
    """
    from pg_atlas.ingestion.deps_dev_client import (
        STELLAR_SEED_PACKAGES,
        DepsDotDevClient,
    )
    from pg_atlas.ingestion.crates_io_client import (
        SOROBAN_CORE_CRATES,
        CratesIoClient,
    )

    dep_edges: list[dict] = []
    errors: list[dict] = []

    # --- Phase 1: project enrichment for GitHub URLs from seed CSV ---
    seed_csv = _resolve_path(config.seed_csv)
    github_urls = _read_urls_from_csv(seed_csv)
    client = DepsDotDevClient(rate_limit_per_min=config.deps_rate_limit)

    logger.info("Deps ingestion phase 1: %d GitHub URLs from %s", len(github_urls), seed_csv)

    for url in github_urls:
        if checkpoint.is_done("deps_enrich", url):
            continue
        try:
            enrichment = client.get_project_enrichment(url)
            if enrichment is not None:
                # Store enrichment results for adoption signals reuse
                ckpt_data = checkpoint.load("deps_enrich")
                results = ckpt_data.get("results", [])
                results.append({
                    "source_repo_url": enrichment.source_repo_url,
                    "stars": enrichment.stars,
                    "forks": enrichment.forks,
                    "open_issues": enrichment.open_issues,
                })
                ckpt_data["results"] = results
                checkpoint.save("deps_enrich", ckpt_data)
            checkpoint.mark_done("deps_enrich", url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Deps enrichment error for %s: %s", url, exc)
            errors.append({"source": "deps_enrich", "url": url, "error": str(exc)})

    # --- Phase 2: Stellar seed package bootstrap from deps.dev ---
    if not checkpoint.is_done("deps_bootstrap", "stellar_seed"):
        logger.info("Deps ingestion phase 2: Stellar seed package bootstrap")
        try:
            metadata, edges = client.bootstrap_stellar_graph()
            for edge in edges:
                # Map dependency edges to the canonical format
                source_url = None
                # Find source repo URL from metadata
                for meta in metadata:
                    if meta.name == edge.from_purl.split("@")[0].split(":")[-1]:
                        source_url = meta.source_repo_url
                        break

                dep_edges.append({
                    "from_repo": source_url or edge.from_purl,
                    "to_package": edge.to_name,
                    "ecosystem": edge.ecosystem,
                    "is_direct": edge.relation == "DIRECT",
                })
            checkpoint.mark_done("deps_bootstrap", "stellar_seed")
            logger.info("Stellar bootstrap: %d metadata, %d edges", len(metadata), len(edges))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Stellar bootstrap failed: %s", exc)
            errors.append({"source": "deps_bootstrap", "item": "stellar_seed", "error": str(exc)})

    # --- Phase 3: Soroban crate reverse dependencies from crates.io ---
    crates_client = CratesIoClient()
    logger.info("Deps ingestion phase 3: Soroban crate reverse deps (%d crates)", len(SOROBAN_CORE_CRATES))

    for crate in SOROBAN_CORE_CRATES:
        if checkpoint.is_done("deps_crates", crate):
            continue
        try:
            reverse_deps = crates_client.get_reverse_dependencies(crate)
            for dep in reverse_deps:
                dep_edges.append({
                    "from_repo": dep.crate_name,
                    "to_package": crate,
                    "ecosystem": "CARGO",
                    "is_direct": True,
                })
            checkpoint.mark_done("deps_crates", crate)
            logger.info("crates.io: %s -> %d reverse deps", crate, len(reverse_deps))
        except Exception as exc:  # noqa: BLE001
            logger.warning("crates.io error for %s: %s", crate, exc)
            errors.append({"source": "deps_crates", "crate": crate, "error": str(exc)})

    # ── Translate CARGO crate names → GitHub URLs ─────────────────────────────
    # CARGO edges carry crate package names (e.g. "soroban-sdk") as node IDs.
    # The graph uses GitHub URLs as node IDs. Translate before CSV write so that
    # dep edges connect to the real ecosystem graph instead of an isolated subgraph.
    cargo_edges = [e for e in dep_edges if e.get("ecosystem") == "CARGO"]
    if cargo_edges:
        all_crates = {e["from_repo"] for e in cargo_edges} | {e["to_package"] for e in cargo_edges}
        crate_url_map: dict[str, str] = {}
        for crate in all_crates:
            url = crates_client.get_crate_github_url(crate)
            if url:
                crate_url_map[crate] = url
        logger.info(
            "Cargo URL resolution: %d/%d unique crate names resolved to GitHub URLs",
            len(crate_url_map), len(all_crates),
        )
        for edge in dep_edges:
            if edge.get("ecosystem") == "CARGO":
                edge["from_repo"]  = crate_url_map.get(edge["from_repo"],  edge["from_repo"])
                edge["to_package"] = crate_url_map.get(edge["to_package"], edge["to_package"])

    logger.info("Deps ingestion complete: %d dependency edges, %d errors", len(dep_edges), len(errors))
    return dep_edges


# ---------------------------------------------------------------------------
# Adoption signals (npm downloads, PyPI downloads, GitHub stars/forks)
# ---------------------------------------------------------------------------

def run_adoption_ingestion(
    config: IngestionConfig,
    checkpoint: Checkpoint,
) -> dict[str, dict]:
    """Run adoption signal ingestion from npm, PyPI, and deps.dev project data.

    Collects:
    - npm downloads for Stellar NPM packages
    - PyPI downloads for Stellar Python packages
    - GitHub stars/forks from previously-cached deps.dev project enrichment data

    Args:
        config:     IngestionConfig.
        checkpoint: Checkpoint instance (reuses deps_enrich data).

    Returns:
        Dict mapping repo_url or package_name to adoption signals dict.
    """
    from pg_atlas.ingestion.deps_dev_client import STELLAR_SEED_PACKAGES
    from pg_atlas.ingestion.npm_downloads_client import get_npm_downloads
    from pg_atlas.ingestion.pypi_downloads_client import get_pypi_downloads

    adoption: dict[str, dict] = {}
    errors: list[dict] = []

    # --- npm downloads ---
    npm_packages = [
        p["name"] for p in STELLAR_SEED_PACKAGES if p["ecosystem"] == "NPM"
    ]
    logger.info("Adoption ingestion: %d npm packages", len(npm_packages))

    for name in npm_packages:
        if checkpoint.is_done("adoption_npm", name):
            continue
        try:
            downloads = get_npm_downloads(name)
            adoption[name] = {
                "monthly_downloads": downloads or 0,
                "github_stars": 0,
                "github_forks": 0,
            }
            checkpoint.mark_done("adoption_npm", name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("npm downloads error for %s: %s", name, exc)
            errors.append({"source": "adoption_npm", "package": name, "error": str(exc)})

    # --- PyPI downloads ---
    pypi_packages = [
        p["name"] for p in STELLAR_SEED_PACKAGES if p["ecosystem"] == "PYPI"
    ]
    logger.info("Adoption ingestion: %d PyPI packages", len(pypi_packages))

    for name in pypi_packages:
        if checkpoint.is_done("adoption_pypi", name):
            continue
        try:
            downloads = get_pypi_downloads(name)
            adoption[name] = {
                "monthly_downloads": downloads or 0,
                "github_stars": 0,
                "github_forks": 0,
            }
            checkpoint.mark_done("adoption_pypi", name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("PyPI downloads error for %s: %s", name, exc)
            errors.append({"source": "adoption_pypi", "package": name, "error": str(exc)})

    # --- Reuse GitHub stars/forks from deps.dev enrichment ---
    enrichment_results = checkpoint.get_results("deps_enrich")
    for entry in enrichment_results:
        url = entry.get("source_repo_url", "")
        if url:
            existing = adoption.get(url, {})
            adoption[url] = {
                "monthly_downloads": existing.get("monthly_downloads", 0),
                "github_stars": entry.get("stars", 0),
                "github_forks": entry.get("forks", 0),
            }

    logger.info("Adoption ingestion complete: %d entries, %d errors", len(adoption), len(errors))
    return adoption


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_full_ingestion(config: IngestionConfig | None = None) -> IngestionResult:
    """Execute the full ingestion pipeline.

    Single public entry point that orchestrates A7 git log parsing,
    dependency resolution (deps.dev + crates.io), and adoption signal
    collection (npm + PyPI + GitHub stars/forks).

    Produces three canonical CSV files and an INGESTION_REPORT.md in
    ``config.output_dir``.

    Args:
        config: IngestionConfig, or None to create from environment defaults.

    Returns:
        IngestionResult with all collected data and error log.
    """
    if config is None:
        config = IngestionConfig(
            github_token=os.environ.get("GITHUB_TOKEN"),
        )

    checkpoint_dir = _resolve_path(config.checkpoint_dir)
    output_dir = _resolve_path(config.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    checkpoint = Checkpoint(checkpoint_dir)
    all_errors: list[dict] = []

    logger.info("=" * 60)
    logger.info("PG Atlas — Full Ingestion Run")
    logger.info("=" * 60)
    logger.info("Output dir    : %s", output_dir)
    logger.info("Checkpoint dir: %s", checkpoint_dir)
    logger.info("GitHub token  : %s", "provided" if config.github_token else "NOT SET")
    logger.info("=" * 60)

    # --- Phase 1: A7 — contributor statistics ---
    logger.info("Phase 1/3: A7 Git Log Parsing")
    try:
        contribution_edges, activity_data = run_a7_ingestion(config, checkpoint)
    except Exception as exc:  # noqa: BLE001
        logger.error("A7 ingestion failed: %s", exc)
        contribution_edges = []
        activity_data = {}
        all_errors.append({"source": "a7_ingestion", "error": str(exc)})

    # --- Phase 2: Dependency resolution ---
    logger.info("Phase 2/3: Dependency Resolution")
    try:
        dependency_edges = run_deps_ingestion(config, checkpoint)
    except Exception as exc:  # noqa: BLE001
        logger.error("Dependency ingestion failed: %s", exc)
        dependency_edges = []
        all_errors.append({"source": "deps_ingestion", "error": str(exc)})

    # Recover dependency edges from CSV if all items were already checkpointed.
    if not dependency_edges:
        dep_csv = os.path.join(output_dir, "dependency_edges.csv")
        if os.path.isfile(dep_csv):
            dependency_edges = _load_dep_edges_from_csv(dep_csv)
            logger.info("Deps: recovered %d edges from dependency_edges.csv.", len(dependency_edges))

    # --- Phase 3: Adoption signals ---
    logger.info("Phase 3/3: Adoption Signals")
    try:
        adoption_data = run_adoption_ingestion(config, checkpoint)
    except Exception as exc:  # noqa: BLE001
        logger.error("Adoption ingestion failed: %s", exc)
        adoption_data = {}
        all_errors.append({"source": "adoption_ingestion", "error": str(exc)})

    # --- Write canonical CSVs ---
    # contributor_stats.csv
    contrib_rows = []
    for edge in contribution_edges:
        repo_url = edge.get("repo", "")
        # Extract repo_full_name from URL
        repo_name = repo_url
        if "github.com/" in repo_url:
            repo_name = repo_url.split("github.com/")[-1].strip("/")
        contrib_rows.append({
            "repo_full_name": repo_name,
            "contributor_login": edge.get("contributor", ""),
            "commits_90d": edge.get("commits", 0),
            "commit_share_pct": 0.0,  # computed after grouping
        })

    # Compute commit share percentages per repo
    from collections import defaultdict
    repo_totals: dict[str, int] = defaultdict(int)
    for row in contrib_rows:
        repo_totals[row["repo_full_name"]] += row["commits_90d"]
    for row in contrib_rows:
        total = repo_totals.get(row["repo_full_name"], 1)
        if total > 0:
            row["commit_share_pct"] = round(100.0 * row["commits_90d"] / total, 2)

    # Guard: only write CSVs if we have new data — never overwrite non-empty CSVs
    # with empty results from a fully-checkpointed re-run.
    _contrib_csv_path = os.path.join(output_dir, "contributor_stats.csv")
    if contrib_rows:
        _atomic_csv_write(
            _contrib_csv_path,
            contrib_rows,
            ["repo_full_name", "contributor_login", "commits_90d", "commit_share_pct"],
        )
        logger.info("Wrote contributor_stats.csv (%d rows)", len(contrib_rows))
    else:
        logger.info("contributor_stats.csv: no new data — preserving existing file.")

    # dependency_edges.csv
    dep_rows = []
    for edge in dependency_edges:
        dep_rows.append({
            "from_repo": edge.get("from_repo", ""),
            "to_package": edge.get("to_package", ""),
            "ecosystem": edge.get("ecosystem", ""),
            "is_direct": edge.get("is_direct", True),
        })

    _dep_csv_path = os.path.join(output_dir, "dependency_edges.csv")
    if dep_rows:
        _atomic_csv_write(
            _dep_csv_path,
            dep_rows,
            ["from_repo", "to_package", "ecosystem", "is_direct"],
        )
        logger.info("Wrote dependency_edges.csv (%d rows)", len(dep_rows))
    else:
        logger.info("dependency_edges.csv: no new data — preserving existing file.")

    # adoption_signals.csv
    adopt_rows = []
    for key, signals in adoption_data.items():
        # Determine ecosystem from key
        ecosystem = ""
        if key.startswith("@") or key.startswith("soroban-client"):
            ecosystem = "NPM"
        elif key.startswith("https://github.com"):
            ecosystem = "GITHUB"
        else:
            ecosystem = "PYPI"

        repo_name = key
        if "github.com/" in key:
            repo_name = key.split("github.com/")[-1].strip("/")

        adopt_rows.append({
            "repo_full_name": repo_name,
            "ecosystem": ecosystem,
            "monthly_downloads": signals.get("monthly_downloads", 0),
            "github_stars": signals.get("github_stars", 0),
            "github_forks": signals.get("github_forks", 0),
        })

    _atomic_csv_write(
        os.path.join(output_dir, "adoption_signals.csv"),
        adopt_rows,
        ["repo_full_name", "ecosystem", "monthly_downloads", "github_stars", "github_forks"],
    )
    logger.info("Wrote adoption_signals.csv (%d rows)", len(adopt_rows))

    # --- Coverage report ---
    coverage = {
        "total_contribution_edges": len(contribution_edges),
        "total_repos_with_activity": len(activity_data),
        "total_dependency_edges": len(dependency_edges),
        "total_adoption_entries": len(adoption_data),
        "total_errors": len(all_errors),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }

    # --- Write INGESTION_REPORT.md ---
    report_path = os.path.join(output_dir, "INGESTION_REPORT.md")
    _write_ingestion_report(report_path, coverage, all_errors, config)

    logger.info("=" * 60)
    logger.info("Ingestion complete.")
    logger.info("  Contribution edges : %d", coverage["total_contribution_edges"])
    logger.info("  Activity data repos: %d", coverage["total_repos_with_activity"])
    logger.info("  Dependency edges   : %d", coverage["total_dependency_edges"])
    logger.info("  Adoption entries   : %d", coverage["total_adoption_entries"])
    logger.info("  Errors             : %d", coverage["total_errors"])
    logger.info("=" * 60)

    return IngestionResult(
        contribution_edges=contribution_edges,
        activity_data=activity_data,
        dependency_edges=dependency_edges,
        adoption_data=adoption_data,
        coverage_report=coverage,
        errors=all_errors,
    )


def _write_ingestion_report(
    path: str,
    coverage: dict,
    errors: list[dict],
    config: IngestionConfig,
) -> None:
    """Write the INGESTION_REPORT.md summary file atomically."""
    lines = [
        "# PG Atlas Ingestion Report",
        "",
        f"**Generated**: {coverage.get('timestamp', 'unknown')}",
        "",
        "## Coverage Summary",
        "",
        f"| Metric | Count |",
        f"|---|---|",
        f"| Contribution edges | {coverage.get('total_contribution_edges', 0)} |",
        f"| Repos with activity data | {coverage.get('total_repos_with_activity', 0)} |",
        f"| Dependency edges | {coverage.get('total_dependency_edges', 0)} |",
        f"| Adoption signal entries | {coverage.get('total_adoption_entries', 0)} |",
        f"| Errors | {coverage.get('total_errors', 0)} |",
        "",
        "## Configuration",
        "",
        f"- Rolling window: {config.since_days} days",
        f"- Git max workers: {config.git_max_workers}",
        f"- deps.dev rate limit: {config.deps_rate_limit} req/min",
        f"- GitHub token: {'provided' if config.github_token else 'NOT SET'}",
        "",
        "## Output Files",
        "",
        f"- `contributor_stats.csv` — contributor commit statistics",
        f"- `dependency_edges.csv` — package dependency edges",
        f"- `adoption_signals.csv` — download counts and GitHub metrics",
        "",
    ]

    if errors:
        lines.append("## Errors")
        lines.append("")
        for err in errors:
            source = err.get("source", "unknown")
            msg = err.get("error", "unknown error")
            lines.append(f"- **{source}**: {msg}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by pg_atlas.ingestion.orchestrator*")
    lines.append("")

    content = "\n".join(lines)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.replace(tmp, path)
    logger.info("Wrote INGESTION_REPORT.md to %s", path)
