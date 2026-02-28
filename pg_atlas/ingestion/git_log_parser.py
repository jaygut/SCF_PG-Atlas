"""
A7 — Git Log Parser & Contributor Statistics
Primary owner: Jay Gutierrez | Due: March 22, 2026 | Budget: $10K

Parses contributor statistics for all Stellar public goods repos using the
GitHub REST API. Produces structured output compatible with the NetworkX
graph enrichment layer.

Acceptance Criteria (A7):
1. Runs against all repos in 01_data/processed/A7_submission_github_repos.csv
2. Populates Contributor data + contributed_to edge data with commit counts,
   first/last dates
3. Determines Repo.latest_commit_date and Repo.days_since_commit
4. Handles inaccessible repos gracefully (logged at WARNING, not fatal)
"""
import logging
import time
import re
import os
import json
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_WINDOW_DAYS = 90

# Relative path anchor for default CSV location
_THIS_FILE = os.path.abspath(__file__)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_FILE)))
_DEFAULT_REPOS_CSV = os.path.join(
    _REPO_ROOT, "01_data", "processed", "A7_submission_github_repos.csv"
)


@dataclass
class ContributorStats:
    """Aggregated contribution statistics for a single contributor."""

    display_name: str
    email: str
    email_aliases: list[str] = field(default_factory=list)
    commits_in_window: int = 0
    first_commit_date: str = ""      # ISO 8601
    last_commit_date: str = ""       # ISO 8601
    repos_contributed_to: list[str] = field(default_factory=list)


@dataclass
class RepoContributionResult:
    """Full contribution result for a single repository."""

    repo_url: str
    github_path: str                  # e.g. "stellar/js-stellar-sdk"
    latest_commit_date: str           # ISO 8601 or ""
    days_since_latest_commit: int     # 9999 if unknown
    total_commits_in_window: int
    contributors: list[ContributorStats]
    accessible: bool
    error: Optional[str] = None


def _parse_github_path(url: str) -> Optional[str]:
    """Extract 'owner/repo' from a GitHub URL.

    Handles http/https, trailing slashes, and .git suffixes.
    Returns None if the URL is not a parseable GitHub repo URL.

    Examples:
        >>> _parse_github_path("https://github.com/stellar/js-stellar-sdk")
        'stellar/js-stellar-sdk'
        >>> _parse_github_path("https://github.com/stellar/js-stellar-sdk/")
        'stellar/js-stellar-sdk'
        >>> _parse_github_path("https://notgithub.com/foo/bar")
        None
    """
    if not url:
        return None
    url = url.strip().rstrip("/")
    # Remove .git suffix if present
    if url.endswith(".git"):
        url = url[:-4]
    pattern = r"^https?://github\.com/([^/]+/[^/]+)$"
    match = re.match(pattern, url, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _github_request(
    path: str,
    token: Optional[str] = None,
    retries: int = 3,
) -> Optional[dict | list]:
    """Make a GitHub API GET request with rate-limit handling.

    Handles:
    - 401/403: logs WARNING "Rate limited or unauthorized", returns None
    - 404: logs WARNING "Repo not found: {path}", returns None
    - 429: exponential backoff, retries up to `retries` times
    - Network errors: logs WARNING, returns None

    Args:
        path: API path starting with '/', e.g. '/repos/owner/repo/commits'
        token: GitHub personal access token for authentication
        retries: Maximum number of retry attempts for transient errors

    Returns:
        Parsed JSON response as dict or list, or None on failure.
    """
    url = f"{GITHUB_API_BASE}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    attempt = 0
    backoff = 1.0

    while attempt <= retries:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                logger.warning("Rate limited or unauthorized (HTTP %d): %s", exc.code, path)
                return None
            elif exc.code == 404:
                logger.warning("Repo not found: %s", path)
                return None
            elif exc.code == 429:
                if attempt < retries:
                    wait = backoff * (2 ** attempt)
                    logger.warning(
                        "Rate limited (429) on %s — sleeping %.1fs before retry %d/%d",
                        path, wait, attempt + 1, retries,
                    )
                    time.sleep(wait)
                    attempt += 1
                    continue
                else:
                    logger.warning("Rate limited (429) on %s — max retries reached", path)
                    return None
            else:
                logger.warning("HTTP %d error on %s: %s", exc.code, path, exc.reason)
                return None
        except urllib.error.URLError as exc:
            logger.warning("Network error on %s: %s", path, exc.reason)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unexpected error on %s: %s", path, exc)
            return None
        break  # successful response exits the loop

    return None


def parse_repo_contributions(
    github_url: str,
    github_token: Optional[str] = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> RepoContributionResult:
    """Fetch commit history for a single repo using the GitHub commits API.

    Uses GET /repos/{owner}/{repo}/commits with a `since` parameter set to
    (now - window_days) to limit results. Paginates through up to 10 pages
    (100 commits per page = max 1000 commits). Groups commits by email to
    produce per-contributor statistics.

    Args:
        github_url: Full GitHub repository URL.
        github_token: Optional GitHub PAT for higher rate limits.
        window_days: Number of days to look back for commit history.

    Returns:
        RepoContributionResult with accessible=False and error set if the
        repo is unreachable or the URL is not a valid GitHub URL.
    """
    github_path = _parse_github_path(github_url)
    if github_path is None:
        logger.warning("Cannot parse GitHub path from URL: %s", github_url)
        return RepoContributionResult(
            repo_url=github_url,
            github_path="",
            latest_commit_date="",
            days_since_latest_commit=9999,
            total_commits_in_window=0,
            contributors=[],
            accessible=False,
            error=f"Not a valid GitHub URL: {github_url}",
        )

    since_dt = datetime.now(tz=timezone.utc) - timedelta(days=window_days)
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Collect raw commits from all pages
    raw_commits: list[dict] = []
    max_pages = 10
    per_page = 100

    for page in range(1, max_pages + 1):
        api_path = (
            f"/repos/{github_path}/commits"
            f"?since={since_iso}&per_page={per_page}&page={page}"
        )
        data = _github_request(api_path, token=github_token)
        if data is None:
            # None from _github_request means the repo is inaccessible
            return RepoContributionResult(
                repo_url=github_url,
                github_path=github_path,
                latest_commit_date="",
                days_since_latest_commit=9999,
                total_commits_in_window=0,
                contributors=[],
                accessible=False,
                error=f"API request failed for {github_path}",
            )
        if not isinstance(data, list):
            logger.warning("Unexpected response type for %s commits: %s", github_path, type(data))
            return RepoContributionResult(
                repo_url=github_url,
                github_path=github_path,
                latest_commit_date="",
                days_since_latest_commit=9999,
                total_commits_in_window=0,
                contributors=[],
                accessible=False,
                error=f"Unexpected API response for {github_path}",
            )
        raw_commits.extend(data)
        if len(data) < per_page:
            # Last page — no more commits
            break

    # Determine latest commit date (GitHub returns newest-first)
    latest_commit_date = ""
    days_since_latest_commit = 9999
    if raw_commits:
        first_commit = raw_commits[0]
        commit_data = first_commit.get("commit", {})
        author_data = commit_data.get("author", {})
        date_str = author_data.get("date", "")
        if date_str:
            latest_commit_date = date_str
            try:
                commit_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                now_utc = datetime.now(tz=timezone.utc)
                days_since_latest_commit = (now_utc - commit_dt).days
            except ValueError:
                logger.warning("Could not parse commit date '%s' for %s", date_str, github_path)

    # Group commits by author email → ContributorStats
    email_map: dict[str, ContributorStats] = {}
    commit_dates_by_email: dict[str, list[str]] = {}

    for commit_entry in raw_commits:
        commit_data = commit_entry.get("commit", {})
        author_data = commit_data.get("author", {})
        gh_author = commit_entry.get("author") or {}

        email = author_data.get("email", "").strip().lower()
        name = author_data.get("name", "") or gh_author.get("login", "unknown")
        login = gh_author.get("login", "")
        date_str = author_data.get("date", "")

        if not email:
            email = f"unknown_{name}@unknown"

        if email not in email_map:
            email_map[email] = ContributorStats(
                display_name=login if login else name,
                email=email,
                email_aliases=[],
                commits_in_window=0,
                first_commit_date="",
                last_commit_date="",
                repos_contributed_to=[github_url],
            )
            commit_dates_by_email[email] = []

        email_map[email].commits_in_window += 1
        if date_str:
            commit_dates_by_email[email].append(date_str)

        # Track name aliases
        if name and name not in email_map[email].email_aliases and name != email_map[email].display_name:
            email_map[email].email_aliases.append(name)

    # Compute first/last commit dates per contributor
    for email, stats in email_map.items():
        dates = sorted(commit_dates_by_email.get(email, []))
        if dates:
            stats.first_commit_date = dates[0]
            stats.last_commit_date = dates[-1]

    contributors = list(email_map.values())

    return RepoContributionResult(
        repo_url=github_url,
        github_path=github_path,
        latest_commit_date=latest_commit_date,
        days_since_latest_commit=days_since_latest_commit,
        total_commits_in_window=len(raw_commits),
        contributors=contributors,
        accessible=True,
        error=None,
    )


def parse_all_repos(
    repos_csv_path: str,
    github_token: Optional[str] = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    max_workers: int = 4,
) -> list[RepoContributionResult]:
    """Parse all repos from A7_submission_github_repos.csv in parallel.

    Reads the CSV, extracts all unique GitHub URLs, and processes each repo
    using a ThreadPoolExecutor with up to max_workers concurrent threads.
    Logs progress at INFO level and warnings for inaccessible repos.

    Args:
        repos_csv_path: Absolute path to the submission repos CSV file.
        github_token: Optional GitHub PAT for higher rate limits.
        window_days: Number of days to look back for commit history.
        max_workers: Maximum number of concurrent threads.

    Returns:
        List of RepoContributionResult objects (accessible + inaccessible).
    """
    urls: list[str] = []
    try:
        with open(repos_csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                url = row.get("github_url", "").strip()
                if url:
                    urls.append(url)
    except FileNotFoundError:
        logger.error("Repos CSV not found: %s", repos_csv_path)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to read repos CSV %s: %s", repos_csv_path, exc)
        return []

    total = len(urls)
    logger.info("Loaded %d repo URLs from %s", total, repos_csv_path)

    results: list[RepoContributionResult] = []
    futures_to_url: dict = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for url in urls:
            future = executor.submit(
                parse_repo_contributions, url, github_token, window_days
            )
            futures_to_url[future] = url

        completed = 0
        for future in as_completed(futures_to_url):
            completed += 1
            url = futures_to_url[future]
            logger.info("Processing %d/%d: %s", completed, total, url)
            try:
                result = future.result()
                if not result.accessible:
                    logger.warning(
                        "Inaccessible repo (%s): %s",
                        result.error or "unknown error",
                        url,
                    )
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Unhandled error processing %s: %s", url, exc)
                results.append(
                    RepoContributionResult(
                        repo_url=url,
                        github_path=_parse_github_path(url) or "",
                        latest_commit_date="",
                        days_since_latest_commit=9999,
                        total_commits_in_window=0,
                        contributors=[],
                        accessible=False,
                        error=str(exc),
                    )
                )

    return results


def results_to_contribution_edges(
    results: list[RepoContributionResult],
) -> list[dict]:
    """Convert results to edge dicts for graph enrichment.

    Produces one edge dict per (contributor, repo) pair where the repo was
    accessible. These dicts are consumed by graph.builder.enrich_graph_with_ingestion().

    Args:
        results: List of RepoContributionResult objects from parse_all_repos().

    Returns:
        List of dicts with keys: contributor, repo, commits, first_date, last_date.
    """
    edges: list[dict] = []
    for result in results:
        if not result.accessible:
            continue
        for contrib in result.contributors:
            edges.append(
                {
                    "contributor": contrib.display_name or contrib.email,
                    "repo": result.repo_url,
                    "commits": contrib.commits_in_window,
                    "first_date": contrib.first_commit_date,
                    "last_date": contrib.last_commit_date,
                }
            )
    return edges


def results_to_activity_data(
    results: list[RepoContributionResult],
) -> dict[str, dict]:
    """Convert results to activity data keyed by repo URL.

    Provides per-repo activity metadata for use in active subgraph projection
    (A6) and repo node enrichment.

    Args:
        results: List of RepoContributionResult objects from parse_all_repos().

    Returns:
        Dict mapping repo_url to a dict with keys: days_since_commit,
        latest_commit_date, accessible.
    """
    activity: dict[str, dict] = {}
    for result in results:
        activity[result.repo_url] = {
            "days_since_commit": result.days_since_latest_commit,
            "latest_commit_date": result.latest_commit_date,
            "accessible": result.accessible,
        }
    return activity


def run_a7(
    repos_csv: str = None,
    github_token: Optional[str] = None,
    output_json: Optional[str] = None,
) -> list[RepoContributionResult]:
    """Main entry point for the A7 deliverable.

    Reads the submission repos CSV, parses all GitHub repos in parallel,
    optionally saves results as JSON, and prints a summary to stdout.

    Args:
        repos_csv: Path to the A7 submission repos CSV. Defaults to
            01_data/processed/A7_submission_github_repos.csv relative to the
            repository root.
        github_token: Optional GitHub PAT. Can also be set via the
            GITHUB_TOKEN environment variable.
        output_json: Optional path to write results as JSON.

    Returns:
        List of RepoContributionResult objects.
    """
    if repos_csv is None:
        repos_csv = _DEFAULT_REPOS_CSV

    if github_token is None:
        github_token = os.environ.get("GITHUB_TOKEN")

    if github_token:
        logger.info("GitHub token provided — higher rate limits active")
    else:
        logger.warning(
            "No GitHub token — unauthenticated rate limit is 60 req/hr. "
            "Set GITHUB_TOKEN env var or pass github_token= for full corpus."
        )

    results = parse_all_repos(
        repos_csv_path=repos_csv,
        github_token=github_token,
        window_days=DEFAULT_WINDOW_DAYS,
        max_workers=4,
    )

    accessible = [r for r in results if r.accessible]
    inaccessible = [r for r in results if not r.accessible]
    all_contributors: set[str] = set()
    for r in accessible:
        for c in r.contributors:
            all_contributors.add(c.email)

    print("=" * 60)
    print("A7 — Git Log Parser Results")
    print("=" * 60)
    print(f"Total repos processed : {len(results)}")
    print(f"Accessible            : {len(accessible)}")
    print(f"Inaccessible          : {len(inaccessible)}")
    print(f"Unique contributors   : {len(all_contributors)}")
    print("=" * 60)

    if output_json:
        def _serialise(obj):
            """JSON serialiser for dataclasses."""
            if hasattr(obj, "__dataclass_fields__"):
                return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
            raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")

        try:
            with open(output_json, "w", encoding="utf-8") as fh:
                json.dump(results, fh, default=_serialise, indent=2)
            logger.info("Results saved to %s", output_json)
            print(f"Results saved to: {output_json}")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to save results to %s: %s", output_json, exc)

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    run_a7()
