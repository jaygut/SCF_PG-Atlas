"""
PyPI Downloads Client — Registry download statistics for Python packages.

Fetches recent download counts from the pypistats.org API. Used by the
A10 Adoption Signals Aggregation deliverable to compute percentile-ranked
adoption scores for Stellar ecosystem Python packages (e.g. stellar-sdk).

Rate limit: 1 request/second (self-imposed courtesy rate limit).
Uses only Python stdlib (urllib.request).
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

PYPISTATS_BASE = "https://pypistats.org/api/packages"

# Minimum interval between requests (self-imposed courtesy rate limit)
_MIN_INTERVAL: float = 1.0
_last_call: float = 0.0


def _rate_limited_get(url: str) -> Optional[dict]:
    """Perform a rate-limited GET request to the pypistats API.

    Enforces 1 request/second and handles HTTP/network errors gracefully.

    Args:
        url: Full URL to fetch.

    Returns:
        Parsed JSON dict, or None on any error.
    """
    global _last_call
    now = time.monotonic()
    elapsed = now - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call = time.monotonic()

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
            logger.debug("pypistats: package not found — %s", url)
        else:
            logger.warning("pypistats HTTP %d error: %s", exc.code, url)
        return None
    except urllib.error.URLError as exc:
        logger.warning("pypistats network error: %s — %s", exc.reason, url)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("pypistats unexpected error for %s: %s", url, exc)
        return None


def get_pypi_downloads(package_name: str) -> Optional[int]:
    """Fetch recent download count for a single PyPI package.

    Calls GET https://pypistats.org/api/packages/{package}/recent and
    returns the total recent downloads (last 30 days) from the "last_month"
    category in the response.

    Args:
        package_name: PyPI package name, e.g. "stellar-sdk".

    Returns:
        Integer recent download count (last 30 days), or None if the package
        is not found or the API is unavailable.
    """
    encoded_name = urllib.parse.quote(package_name.lower(), safe="")
    url = f"{PYPISTATS_BASE}/{encoded_name}/recent"

    data = _rate_limited_get(url)
    if data is None:
        return None

    # pypistats returns {"data": {"last_month": N, "last_week": M, "last_day": K}, ...}
    downloads_data = data.get("data", {})
    if isinstance(downloads_data, list):
        # Some endpoints return a list; sum all entries
        total = sum(entry.get("downloads", 0) for entry in downloads_data)
        return total if total > 0 else None

    last_month = downloads_data.get("last_month")
    if last_month is None:
        logger.warning(
            "pypistats: 'last_month' key missing in response for %s", package_name
        )
        return None

    return int(last_month)


def get_pypi_downloads_batch(packages: list[str]) -> dict[str, Optional[int]]:
    """Fetch recent download counts for multiple PyPI packages.

    Processes packages sequentially with a 1 req/sec rate limit.

    Args:
        packages: List of PyPI package names.

    Returns:
        Dict mapping package name to recent download count (or None on failure).
    """
    results: dict[str, Optional[int]] = {}
    for package_name in packages:
        logger.info("Fetching PyPI downloads for: %s", package_name)
        results[package_name] = get_pypi_downloads(package_name)
    return results
