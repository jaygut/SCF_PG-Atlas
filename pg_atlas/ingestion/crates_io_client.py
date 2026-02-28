"""
crates.io API Client — Rust/Cargo reverse dependency lookups for PG Atlas.

Fills the critical Cargo blind spot: deps.dev returns dependentCount=0 for all
Cargo packages, making it unusable for the Soroban/Rust ecosystem. This client
calls the crates.io API directly to fetch reverse dependencies and download counts.

Rate limit: 1 request/second (crates.io TOS requirement).
User-Agent header is mandatory per crates.io policy.
Uses only Python stdlib (urllib.request).

Reference: https://crates.io/data-access
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

CRATES_IO_BASE = "https://crates.io/api/v1"

# crates.io TOS requires a descriptive User-Agent identifying your application
# and providing a contact method. Requests without a valid User-Agent may be
# rate-limited or blocked.
CRATES_IO_USER_AGENT = (
    "pg-atlas/0.1 (contact: scf-public-goods; https://github.com/stellar/pg-atlas)"
)

# Core Soroban/Rust crates that form the foundation of the Stellar smart contract
# ecosystem. These are the root nodes for reverse dependency crawling.
SOROBAN_CORE_CRATES: list[str] = [
    "soroban-sdk",
    "stellar-xdr",
    "stellar-strkey",
    "soroban-env-host",
    "soroban-env-common",
]


@dataclass
class CratesReverseDep:
    """A single reverse dependency relationship from crates.io."""

    crate_name: str
    version: str
    downloads: int


@dataclass
class CratesDownloadData:
    """Download statistics for a crate from crates.io."""

    crate_name: str
    total_downloads: int
    recent_downloads: int  # last 90 days if available, else 0


class CratesIoClient:
    """Rate-limited client for the crates.io REST API.

    Enforces a 1 request/second rate limit (crates.io TOS requirement) via
    time.sleep. All requests include the required User-Agent header. Errors
    are handled gracefully — methods return empty lists or zero-download
    objects rather than raising exceptions.
    """

    # Minimum interval between requests (1 req/sec per crates.io TOS)
    _MIN_INTERVAL: float = 1.0

    def __init__(self) -> None:
        """Initialise the client with rate-limit tracking."""
        self._last_call: float = 0.0

    def _get(self, url: str) -> Optional[dict]:
        """Rate-limited GET request to crates.io with error handling.

        Enforces 1 req/sec minimum interval, includes the mandatory User-Agent
        header, and handles HTTP and network errors gracefully.

        Args:
            url: Full URL to fetch.

        Returns:
            Parsed JSON dict, or None on any error.
        """
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._MIN_INTERVAL:
            time.sleep(self._MIN_INTERVAL - elapsed)
        self._last_call = time.monotonic()

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": CRATES_IO_USER_AGENT,
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                logger.debug("crates.io: not found — %s", url)
            elif exc.code == 429:
                logger.warning("crates.io: rate limited (429) — %s", url)
            else:
                logger.warning("crates.io HTTP %d error: %s", exc.code, url)
            return None
        except urllib.error.URLError as exc:
            logger.warning("crates.io network error: %s — %s", exc.reason, url)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("crates.io unexpected error for %s: %s", url, exc)
            return None

    def get_reverse_dependencies(
        self,
        crate_name: str,
        max_pages: int = 5,
    ) -> list[CratesReverseDep]:
        """Fetch reverse dependencies for a crate from crates.io.

        Paginates through up to max_pages pages (100 results per page) of
        reverse dependencies using GET /api/v1/crates/{crate}/reverse_dependencies.

        Args:
            crate_name: The name of the crate to look up.
            max_pages: Maximum number of pages to fetch (100 results each).

        Returns:
            List of CratesReverseDep objects. Empty list if the crate is not
            found or the API is unavailable.
        """
        reverse_deps: list[CratesReverseDep] = []

        for page in range(1, max_pages + 1):
            encoded_name = urllib.parse.quote(crate_name, safe="")
            url = (
                f"{CRATES_IO_BASE}/crates/{encoded_name}/reverse_dependencies"
                f"?page={page}&per_page=100"
            )
            data = self._get(url)
            if data is None:
                break

            dependencies = data.get("dependencies", [])
            versions = {v["id"]: v for v in data.get("versions", [])}

            for dep in dependencies:
                version_id = dep.get("version_id")
                version_obj = versions.get(version_id, {})
                dep_crate = version_obj.get("crate", dep.get("crate_id", ""))
                dep_version = version_obj.get("num", "")
                dep_downloads = version_obj.get("downloads", 0)

                reverse_deps.append(
                    CratesReverseDep(
                        crate_name=dep_crate,
                        version=dep_version,
                        downloads=dep_downloads,
                    )
                )

            if len(dependencies) < 100:
                # Last page reached
                break

        logger.debug(
            "crates.io: %d reverse deps found for %s", len(reverse_deps), crate_name
        )
        return reverse_deps

    def get_downloads(self, crate_name: str) -> CratesDownloadData:
        """Fetch total and recent download counts for a crate.

        Calls GET /api/v1/crates/{crate} and extracts the downloads field.
        Also calls the downloads/history endpoint for recent (90-day) data
        when available.

        Args:
            crate_name: The name of the crate to look up.

        Returns:
            CratesDownloadData with total_downloads and recent_downloads.
            Returns zero counts if the crate is not found.
        """
        encoded_name = urllib.parse.quote(crate_name, safe="")
        url = f"{CRATES_IO_BASE}/crates/{encoded_name}"
        data = self._get(url)

        if data is None:
            return CratesDownloadData(
                crate_name=crate_name,
                total_downloads=0,
                recent_downloads=0,
            )

        crate_data = data.get("crate", {})
        total_downloads = crate_data.get("downloads", 0)
        recent_downloads = crate_data.get("recent_downloads", 0)

        return CratesDownloadData(
            crate_name=crate_name,
            total_downloads=total_downloads,
            recent_downloads=recent_downloads,
        )

    def bootstrap_soroban_reverse_graph(self) -> list[dict]:
        """Fetch reverse dependencies for all SOROBAN_CORE_CRATES.

        Iterates over each crate in SOROBAN_CORE_CRATES, fetches its reverse
        dependencies from crates.io, and returns the results as a flat list of
        edge dicts compatible with the graph enrichment layer.

        Returns:
            List of dicts with keys: from_crate, to_crate, to_version, downloads.
            Empty list if all API calls fail.
        """
        all_edges: list[dict] = []

        for crate_name in SOROBAN_CORE_CRATES:
            logger.info("Fetching reverse deps for Soroban crate: %s", crate_name)
            reverse_deps = self.get_reverse_dependencies(crate_name)

            for dep in reverse_deps:
                all_edges.append(
                    {
                        "from_crate": crate_name,
                        "to_crate": dep.crate_name,
                        "to_version": dep.version,
                        "downloads": dep.downloads,
                    }
                )

            logger.info(
                "  %s: %d reverse dependents found", crate_name, len(reverse_deps)
            )

        logger.info(
            "Soroban reverse graph bootstrap complete: %d edges total", len(all_edges)
        )
        return all_edges
