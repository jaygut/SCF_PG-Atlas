"""
OpenGrants / DAOIP-5 Client — SCF project data from DAO star OpenGrants.

Attempts to fetch SCF project data from the OpenGrants DAOIP-5 API. This is a
best-effort client — the system is designed to function fully without it. If the
API is unavailable or returns an error, an empty list is returned and a WARNING
is logged rather than raising an exception.

Uses only Python stdlib (urllib.request).
"""
import json
import logging
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

OPENGRANTS_BASE = "https://opengrants.daostar.org/system/scf"


def _get(url: str) -> Optional[dict | list]:
    """Perform a GET request to the OpenGrants API with error handling.

    Args:
        url: Full URL to fetch.

    Returns:
        Parsed JSON response (dict or list), or None on any error.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        logger.warning(
            "OpenGrants API HTTP %d error fetching %s: %s", exc.code, url, exc.reason
        )
        return None
    except urllib.error.URLError as exc:
        logger.warning(
            "OpenGrants API network error fetching %s: %s", url, exc.reason
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenGrants API unexpected error fetching %s: %s", url, exc)
        return None


def fetch_scf_projects() -> list[dict]:
    """Attempt to fetch SCF project data from the OpenGrants DAOIP-5 API.

    Calls the OPENGRANTS_BASE endpoint and returns all project records found.
    This client is intentionally best-effort — the PG Atlas system is designed
    to operate without this data source.

    Returns:
        List of project dicts from the API response, or an empty list if the
        API is unavailable, returns an unexpected format, or errors occur.
        A WARNING is logged in all failure cases.
    """
    url = OPENGRANTS_BASE
    logger.info("Fetching SCF projects from OpenGrants DAOIP-5 API: %s", url)

    data = _get(url)
    if data is None:
        logger.warning(
            "OpenGrants API unavailable — continuing without DAOIP-5 data. "
            "The system operates normally without this source."
        )
        return []

    # The DAOIP-5 standard wraps projects in a "grants" or "applications" key;
    # handle both formats and a bare list gracefully.
    if isinstance(data, list):
        logger.info("OpenGrants: fetched %d project records", len(data))
        return data

    if isinstance(data, dict):
        for key in ("grants", "applications", "projects", "data"):
            projects = data.get(key)
            if isinstance(projects, list):
                logger.info(
                    "OpenGrants: fetched %d project records from key '%s'",
                    len(projects),
                    key,
                )
                return projects

    logger.warning(
        "OpenGrants: unexpected response format (type=%s) — returning empty list",
        type(data).__name__,
    )
    return []
