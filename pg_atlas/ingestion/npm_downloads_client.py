"""
npm Downloads Client — Registry download statistics for NPM packages.

Fetches download counts from the npm registry downloads API. Used by the
A10 Adoption Signals Aggregation deliverable to compute percentile-ranked
adoption scores for Stellar ecosystem packages.

Rate limit: 1 request/second (self-imposed, API is generous).
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

NPM_DOWNLOADS_BASE = "https://api.npmjs.org/downloads/point"

# Default period for download counts
_DEFAULT_PERIOD = "last-month"

# Minimum interval between requests (self-imposed courtesy rate limit)
_MIN_INTERVAL: float = 1.0
_last_call: float = 0.0


def _rate_limited_get(url: str) -> Optional[dict]:
    """Perform a rate-limited GET request to the npm downloads API.

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
            logger.debug("npm: package not found — %s", url)
        else:
            logger.warning("npm HTTP %d error: %s", exc.code, url)
        return None
    except urllib.error.URLError as exc:
        logger.warning("npm network error: %s — %s", exc.reason, url)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("npm unexpected error for %s: %s", url, exc)
        return None


def get_npm_downloads(
    package_name: str,
    period: str = _DEFAULT_PERIOD,
) -> Optional[int]:
    """Fetch download count for a single npm package.

    Calls GET https://api.npmjs.org/downloads/point/{period}/{package}.
    Handles scoped packages (e.g. @stellar/js-xdr) by URL-encoding the
    package name — the leading '@' must be preserved as '%40'.

    Args:
        package_name: npm package name, including scope if applicable,
            e.g. "@stellar/js-xdr" or "soroban-client".
        period: Download period, e.g. "last-day", "last-week", "last-month".
            Defaults to "last-month".

    Returns:
        Integer download count, or None if the package is not found or the
        API is unavailable.
    """
    # URL-encode the package name. For scoped packages like @stellar/js-xdr,
    # urllib.parse.quote encodes '@' as '%40' and '/' as '%2F', which is
    # correct for the npm downloads API path.
    encoded_name = urllib.parse.quote(package_name, safe="")
    url = f"{NPM_DOWNLOADS_BASE}/{period}/{encoded_name}"

    data = _rate_limited_get(url)
    if data is None:
        return None

    downloads = data.get("downloads")
    if downloads is None:
        logger.warning("npm: 'downloads' key missing in response for %s", package_name)
        return None

    return int(downloads)


def get_npm_downloads_batch(
    packages: list[str],
    period: str = _DEFAULT_PERIOD,
) -> dict[str, Optional[int]]:
    """Fetch download counts for multiple npm packages.

    Processes packages sequentially with a 1 req/sec rate limit.

    Args:
        packages: List of npm package names (scoped or unscoped).
        period: Download period passed to each individual request.

    Returns:
        Dict mapping package name to download count (or None on failure).
    """
    results: dict[str, Optional[int]] = {}
    for package_name in packages:
        logger.info("Fetching npm downloads for: %s", package_name)
        results[package_name] = get_npm_downloads(package_name, period=period)
    return results
