"""
deps.dev API Client — Package dependency enrichment for PG Atlas.

Fetches package metadata, dependency edges, and project enrichment data
(stars, forks, OpenSSF scores) from the deps.dev REST API.

Rate limit: 100 requests/minute enforced via token-bucket logic.
Uses only Python stdlib (urllib.request) — no third-party HTTP libraries.
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

DEPS_DEV_BASE = "https://api.deps.dev/v3alpha"

# Seed packages covering the Stellar/Soroban ecosystem across NPM, PyPI, and Cargo.
# Note: Cargo packages return dependentCount=0 from deps.dev — use crates_io_client
# for Rust reverse dependency lookups (see CLAUDE.md: Cargo/Rust blind spot).
STELLAR_SEED_PACKAGES: list[dict] = [
    {"ecosystem": "NPM",   "name": "@stellar/js-xdr"},
    {"ecosystem": "NPM",   "name": "@stellar/stellar-base"},
    {"ecosystem": "NPM",   "name": "@stellar/stellar-sdk"},
    {"ecosystem": "NPM",   "name": "@stellar/freighter-api"},
    {"ecosystem": "NPM",   "name": "soroban-client"},
    {"ecosystem": "PYPI",  "name": "stellar-sdk"},
    {"ecosystem": "CARGO", "name": "soroban-sdk"},
    {"ecosystem": "CARGO", "name": "stellar-xdr"},
    {"ecosystem": "CARGO", "name": "stellar-strkey"},
]


@dataclass
class DepsVersion:
    """Metadata for a single package version from deps.dev."""

    purl: str
    name: str
    version: str
    ecosystem: str
    source_repo_url: Optional[str]
    published_at: str
    license: str
    is_default: bool


@dataclass
class DepsDependencyEdge:
    """A directed dependency edge between two packages."""

    from_purl: str
    to_name: str
    to_version: str
    ecosystem: str
    relation: str           # "DIRECT" or "INDIRECT"
    version_requirement: str
    confidence: str = "inferred_shadow"


@dataclass
class DepsProjectEnrichment:
    """GitHub project metadata returned by the deps.dev projects endpoint."""

    source_repo_url: str
    stars: int
    forks: int
    open_issues: int
    openssf_maintained_score: Optional[float]
    openssf_maintained_detail: Optional[str]


class DepsDotDevClient:
    """Rate-limited client for the deps.dev REST API.

    Enforces a minimum interval between requests to stay within the 100
    requests/minute API limit. All errors are handled gracefully — methods
    return None or empty lists rather than raising exceptions.

    Args:
        rate_limit_per_min: Maximum requests per minute (default: 100).
    """

    def __init__(self, rate_limit_per_min: int = 100) -> None:
        """Initialise the client with a configurable rate limit."""
        self._min_interval = 60.0 / rate_limit_per_min
        self._last_call: float = 0.0

    def _get(self, url: str) -> Optional[dict]:
        """Rate-limited GET request to deps.dev with error handling.

        Enforces the configured rate limit via time.sleep, then performs the
        request. Handles HTTP errors and network failures gracefully.

        Args:
            url: Full URL to fetch.

        Returns:
            Parsed JSON dict, or None on any error.
        """
        # Token-bucket rate limiting
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()

        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                logger.debug("deps.dev: not found — %s", url)
            else:
                logger.warning("deps.dev HTTP %d error: %s", exc.code, url)
            return None
        except urllib.error.URLError as exc:
            logger.warning("deps.dev network error: %s — %s", exc.reason, url)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("deps.dev unexpected error for %s: %s", url, exc)
            return None

    def get_version(
        self,
        ecosystem: str,
        name: str,
        version: str = "",
    ) -> Optional[DepsVersion]:
        """Fetch metadata for a package version from deps.dev.

        Calls GET /v3alpha/systems/{ecosystem}/packages/{name}/versions/{version}.
        If version is empty or "latest", the API returns the default version.

        Args:
            ecosystem: Package ecosystem, e.g. "NPM", "PYPI", "CARGO".
            name: Package name, e.g. "@stellar/stellar-sdk".
            version: Specific version string, or "" for the default version.

        Returns:
            DepsVersion dataclass, or None if the package is not found.
        """
        encoded_name = urllib.parse.quote(name, safe="")
        encoded_version = urllib.parse.quote(version or "latest", safe="")
        url = (
            f"{DEPS_DEV_BASE}/systems/{ecosystem}/packages/"
            f"{encoded_name}/versions/{encoded_version}"
        )
        data = self._get(url)
        if data is None:
            return None

        version_key = data.get("versionKey", {})
        links = data.get("links", [])
        source_repo_url: Optional[str] = None
        for link in links:
            if link.get("label") in ("SOURCE_REPO", "HOME_PAGE"):
                source_repo_url = link.get("url")
                break

        licenses = data.get("licenses", [])
        license_str = ", ".join(licenses) if licenses else ""

        return DepsVersion(
            purl=f"pkg:{ecosystem.lower()}/{name}@{version_key.get('version', version)}",
            name=version_key.get("name", name),
            version=version_key.get("version", version),
            ecosystem=version_key.get("system", ecosystem),
            source_repo_url=source_repo_url,
            published_at=data.get("publishedAt", ""),
            license=license_str,
            is_default=data.get("isDefault", False),
        )

    def get_dependencies(
        self,
        ecosystem: str,
        name: str,
        version: str,
    ) -> list[DepsDependencyEdge]:
        """Fetch direct dependency edges for a package version.

        Calls GET /v3alpha/systems/{ecosystem}/packages/{name}/versions/{version}:dependencies
        and returns only DIRECT edges.

        Args:
            ecosystem: Package ecosystem.
            name: Package name.
            version: Package version string.

        Returns:
            List of DepsDependencyEdge objects (DIRECT relation only).
        """
        encoded_name = urllib.parse.quote(name, safe="")
        encoded_version = urllib.parse.quote(version, safe="")
        url = (
            f"{DEPS_DEV_BASE}/systems/{ecosystem}/packages/"
            f"{encoded_name}/versions/{encoded_version}:dependencies"
        )
        data = self._get(url)
        if data is None:
            return []

        from_purl = f"pkg:{ecosystem.lower()}/{name}@{version}"
        edges: list[DepsDependencyEdge] = []
        nodes = data.get("nodes", [])

        # Build a map of node index → versionKey for resolving edges
        node_map: dict[int, dict] = {}
        for i, node in enumerate(nodes):
            node_map[i] = node.get("versionKey", {})

        for edge in data.get("edges", []):
            relation = edge.get("requirement", "")
            # deps.dev uses numeric indices for "from" and "to"
            to_idx = edge.get("toNode")
            if to_idx is None:
                continue
            to_key = node_map.get(to_idx, {})
            to_name = to_key.get("name", "")
            to_version = to_key.get("version", "")
            to_ecosystem = to_key.get("system", ecosystem)

            edges.append(
                DepsDependencyEdge(
                    from_purl=from_purl,
                    to_name=to_name,
                    to_version=to_version,
                    ecosystem=to_ecosystem,
                    relation="DIRECT",
                    version_requirement=relation,
                )
            )

        return edges

    def get_project_enrichment(
        self,
        github_url: str,
    ) -> Optional[DepsProjectEnrichment]:
        """Fetch project-level enrichment data (stars, forks, OpenSSF scores).

        Calls GET /v3alpha/projects/{project} where project is the GitHub path
        in the form "github.com/owner/repo".

        Args:
            github_url: Full GitHub URL, e.g. "https://github.com/stellar/js-stellar-sdk".

        Returns:
            DepsProjectEnrichment dataclass, or None if the project is not found.
        """
        # Normalise the URL to the format deps.dev expects: "github.com/owner/repo"
        url_clean = github_url.strip().rstrip("/")
        if url_clean.startswith("https://"):
            project_key = url_clean[len("https://"):]
        elif url_clean.startswith("http://"):
            project_key = url_clean[len("http://"):]
        else:
            project_key = url_clean

        encoded_key = urllib.parse.quote(project_key, safe="")
        url = f"{DEPS_DEV_BASE}/projects/{encoded_key}"
        data = self._get(url)
        if data is None:
            return None

        scorecard = data.get("scorecard") or {}
        checks = scorecard.get("checks", [])
        maintained_score: Optional[float] = None
        maintained_detail: Optional[str] = None
        for check in checks:
            if check.get("name") == "Maintained":
                maintained_score = check.get("score")
                maintained_detail = check.get("reason")
                break

        return DepsProjectEnrichment(
            source_repo_url=github_url,
            stars=data.get("starsCount", 0),
            forks=data.get("forksCount", 0),
            open_issues=data.get("openIssuesCount", 0),
            openssf_maintained_score=maintained_score,
            openssf_maintained_detail=maintained_detail,
        )

    def bootstrap_stellar_graph(
        self,
    ) -> tuple[list[DepsVersion], list[DepsDependencyEdge]]:
        """Run full bootstrap ingestion for STELLAR_SEED_PACKAGES.

        Fetches the default version metadata and direct dependency edges for
        every package in STELLAR_SEED_PACKAGES. Skips packages that return
        None from deps.dev gracefully.

        Returns:
            Tuple of (metadata_list, edge_list) where metadata_list contains
            DepsVersion objects and edge_list contains DepsDependencyEdge objects.
        """
        metadata: list[DepsVersion] = []
        edges: list[DepsDependencyEdge] = []

        for pkg in STELLAR_SEED_PACKAGES:
            ecosystem = pkg["ecosystem"]
            name = pkg["name"]

            logger.info("Bootstrapping %s/%s from deps.dev", ecosystem, name)
            version_info = self.get_version(ecosystem, name)
            if version_info is None:
                logger.warning("deps.dev: no version found for %s/%s", ecosystem, name)
                continue

            metadata.append(version_info)
            pkg_edges = self.get_dependencies(ecosystem, name, version_info.version)
            edges.extend(pkg_edges)
            logger.info(
                "  %s/%s@%s — %d dependency edges",
                ecosystem,
                name,
                version_info.version,
                len(pkg_edges),
            )

        logger.info(
            "Bootstrap complete: %d packages, %d edges", len(metadata), len(edges)
        )
        return metadata, edges
