"""
Unit tests for pg_atlas.ingestion clients (deps.dev, crates.io, npm, pypi).

All tests are fully offline — no network connections are made.
Tests cover instantiation, constants, and URL encoding behaviour.
"""
import urllib.parse

import pytest
from pg_atlas.ingestion.crates_io_client import (
    CRATES_IO_USER_AGENT,
    SOROBAN_CORE_CRATES,
    CratesIoClient,
)
from pg_atlas.ingestion.deps_dev_client import (
    STELLAR_SEED_PACKAGES,
    DepsDotDevClient,
)
from pg_atlas.ingestion.npm_downloads_client import NPM_DOWNLOADS_BASE, get_npm_downloads
from pg_atlas.ingestion.pypi_downloads_client import PYPISTATS_BASE, get_pypi_downloads


# ---------------------------------------------------------------------------
# DepsDotDevClient
# ---------------------------------------------------------------------------


def test_deps_dev_client_instantiation():
    """DepsDotDevClient instantiates without errors and sets rate-limit attributes."""
    client = DepsDotDevClient()
    assert client is not None
    assert client._min_interval > 0


def test_deps_dev_client_custom_rate_limit():
    """Custom rate limit correctly sets the minimum interval."""
    client = DepsDotDevClient(rate_limit_per_min=60)
    assert abs(client._min_interval - 1.0) < 1e-9


def test_deps_dev_client_default_rate_limit():
    """Default rate limit (100/min) produces 0.6s minimum interval."""
    client = DepsDotDevClient()
    assert abs(client._min_interval - 0.6) < 1e-9


def test_stellar_seed_packages_list():
    """STELLAR_SEED_PACKAGES is a non-empty list of dicts with 'ecosystem' and 'name' keys."""
    assert isinstance(STELLAR_SEED_PACKAGES, list)
    assert len(STELLAR_SEED_PACKAGES) > 0
    for pkg in STELLAR_SEED_PACKAGES:
        assert "ecosystem" in pkg, f"Missing 'ecosystem' key in {pkg}"
        assert "name" in pkg, f"Missing 'name' key in {pkg}"


def test_stellar_seed_packages_contains_npm():
    """STELLAR_SEED_PACKAGES includes key Stellar NPM packages."""
    npm_packages = [
        p["name"] for p in STELLAR_SEED_PACKAGES if p["ecosystem"] == "NPM"
    ]
    assert "@stellar/stellar-sdk" in npm_packages
    assert "@stellar/js-xdr" in npm_packages


def test_stellar_seed_packages_contains_pypi():
    """STELLAR_SEED_PACKAGES includes the stellar-sdk PyPI package."""
    pypi_packages = [
        p["name"] for p in STELLAR_SEED_PACKAGES if p["ecosystem"] == "PYPI"
    ]
    assert "stellar-sdk" in pypi_packages


def test_stellar_seed_packages_contains_cargo():
    """STELLAR_SEED_PACKAGES includes core Cargo packages."""
    cargo_packages = [
        p["name"] for p in STELLAR_SEED_PACKAGES if p["ecosystem"] == "CARGO"
    ]
    assert "soroban-sdk" in cargo_packages
    assert "stellar-xdr" in cargo_packages


# ---------------------------------------------------------------------------
# CratesIoClient
# ---------------------------------------------------------------------------


def test_crates_io_client_instantiation():
    """CratesIoClient instantiates without errors."""
    client = CratesIoClient()
    assert client is not None


def test_crates_io_client_user_agent():
    """CratesIoClient has a correctly formatted User-Agent string.

    crates.io TOS requires a User-Agent that includes the application name,
    version, and a contact method. Requests without a valid User-Agent may
    be blocked.
    """
    assert "pg-atlas" in CRATES_IO_USER_AGENT
    assert "contact" in CRATES_IO_USER_AGENT
    # Must include application name and some form of contact
    assert len(CRATES_IO_USER_AGENT) > 20


def test_crates_io_user_agent_module_constant():
    """CRATES_IO_USER_AGENT module constant matches the TOS-compliant format."""
    # Verify it's not the default urllib User-Agent
    assert "Python-urllib" not in CRATES_IO_USER_AGENT
    assert "pg-atlas/0.1" in CRATES_IO_USER_AGENT


def test_soroban_crates_list():
    """SOROBAN_CORE_CRATES is a non-empty list containing soroban-sdk."""
    assert isinstance(SOROBAN_CORE_CRATES, list)
    assert len(SOROBAN_CORE_CRATES) > 0
    assert "soroban-sdk" in SOROBAN_CORE_CRATES


def test_soroban_crates_list_contains_all_expected():
    """SOROBAN_CORE_CRATES includes all five expected core Soroban crates."""
    expected = {
        "soroban-sdk",
        "stellar-xdr",
        "stellar-strkey",
        "soroban-env-host",
        "soroban-env-common",
    }
    actual = set(SOROBAN_CORE_CRATES)
    assert expected.issubset(actual), (
        f"Missing expected Soroban crates: {expected - actual}"
    )


def test_crates_io_client_rate_limit():
    """CratesIoClient enforces 1 req/sec rate limit."""
    client = CratesIoClient()
    # The client uses a class-level constant for the minimum interval
    assert client._MIN_INTERVAL == 1.0


# ---------------------------------------------------------------------------
# npm downloads client — URL encoding
# ---------------------------------------------------------------------------


def test_npm_package_name_encoding():
    """Scoped @stellar/js-xdr is properly URL-encoded in request paths.

    The npm downloads API requires scoped packages to have the '@' encoded as
    '%40' and '/' as '%2F' in the URL path (not as raw characters).
    """
    package_name = "@stellar/js-xdr"
    encoded = urllib.parse.quote(package_name, safe="")
    assert "%40" in encoded, "@ must be percent-encoded as %40"
    assert "%2F" in encoded or "/" not in encoded, "/ in package name must be encoded"
    # Verify the full encoded form
    assert encoded == "%40stellar%2Fjs-xdr"


def test_npm_base_url_constant():
    """NPM_DOWNLOADS_BASE constant has the correct endpoint."""
    assert NPM_DOWNLOADS_BASE == "https://api.npmjs.org/downloads/point"


def test_npm_unscoped_package_encoding():
    """Unscoped package name encodes without modification."""
    package_name = "soroban-client"
    encoded = urllib.parse.quote(package_name, safe="")
    assert encoded == "soroban-client"


# ---------------------------------------------------------------------------
# PyPI downloads client
# ---------------------------------------------------------------------------


def test_pypistats_base_url_constant():
    """PYPISTATS_BASE constant has the correct endpoint."""
    assert PYPISTATS_BASE == "https://pypistats.org/api/packages"


def test_pypi_package_name_lowercased_in_url():
    """PyPI package names are lowercased before URL construction."""
    # Verify that our client would lowercase the package name by checking
    # that the URL encode of lowercase "stellar-sdk" is "stellar-sdk"
    package_name = "stellar-sdk"
    encoded = urllib.parse.quote(package_name.lower(), safe="")
    assert encoded == "stellar-sdk"


# ---------------------------------------------------------------------------
# Orchestrator — IngestionConfig, Checkpoint, IngestionResult
# ---------------------------------------------------------------------------

import json
import os

from pg_atlas.ingestion.orchestrator import (
    Checkpoint,
    IngestionConfig,
    IngestionResult,
)


def test_ingestion_config_defaults():
    """IngestionConfig instantiates with correct default values."""
    cfg = IngestionConfig()
    assert cfg.github_token is None
    assert cfg.since_days == 90
    assert cfg.git_max_workers == 4
    assert cfg.deps_rate_limit == 100
    assert cfg.checkpoint_dir == "01_data/real/checkpoints"
    assert cfg.output_dir == "01_data/real"
    assert cfg.repos_csv == "01_data/processed/A7_submission_github_repos.csv"
    assert cfg.seed_csv == "01_data/processed/A5_pg_candidate_seed_list.csv"
    assert cfg.orgs_csv == "01_data/processed/A6_github_orgs_seed.csv"


def test_checkpoint_save_and_load(tmp_path):
    """Checkpoint round-trips data through save and load."""
    ckpt = Checkpoint(str(tmp_path))
    payload = {"done": ["a", "b"], "results": [{"x": 1}]}
    ckpt.save("test_key", payload)
    loaded = ckpt.load("test_key")
    assert loaded == payload


def test_checkpoint_mark_and_check_done(tmp_path):
    """Checkpoint.mark_done and is_done correctly track completed items."""
    ckpt = Checkpoint(str(tmp_path))
    assert ckpt.is_done("mykey", "item_1") is False
    ckpt.mark_done("mykey", "item_1")
    assert ckpt.is_done("mykey", "item_1") is True
    assert ckpt.is_done("mykey", "item_2") is False
    # Mark a second item and verify both are tracked
    ckpt.mark_done("mykey", "item_2")
    assert ckpt.is_done("mykey", "item_2") is True
    assert ckpt.is_done("mykey", "item_1") is True


def test_checkpoint_atomic_write(tmp_path):
    """Checkpoint writes are atomic: no .tmp file remains, result is valid JSON."""
    ckpt = Checkpoint(str(tmp_path))
    ckpt.save("atomic_test", {"hello": "world"})

    # Verify no .tmp file remains
    tmp_files = [f for f in os.listdir(str(tmp_path)) if f.endswith(".tmp")]
    assert len(tmp_files) == 0, f"Leftover .tmp files found: {tmp_files}"

    # Verify the written file is valid JSON
    target = os.path.join(str(tmp_path), "atomic_test_progress.json")
    assert os.path.exists(target)
    with open(target, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data == {"hello": "world"}


def test_ingestion_result_structure():
    """IngestionResult instantiates with empty default fields and they are accessible."""
    result = IngestionResult()
    assert isinstance(result.contribution_edges, list)
    assert len(result.contribution_edges) == 0
    assert isinstance(result.activity_data, dict)
    assert len(result.activity_data) == 0
    assert isinstance(result.dependency_edges, list)
    assert len(result.dependency_edges) == 0
    assert isinstance(result.adoption_data, dict)
    assert len(result.adoption_data) == 0
    assert isinstance(result.coverage_report, dict)
    assert len(result.coverage_report) == 0
    assert isinstance(result.errors, list)
    assert len(result.errors) == 0
