"""
pg_atlas/tests/conftest.py — Shared pytest fixtures for PG Atlas test suite.

The synthetic graph fixture reproduces the prototype's graph construction
exactly (SEED=41) so that all metric tests have a deterministic baseline.

Fixtures:
    synthetic_graph  — Full multi-layer graph (SEED=41), session-scoped.
    active_subgraph  — Active projection of synthetic_graph.
    real_csv_graph   — Graph built from actual seed CSVs (session-scoped).
    github_token     — GitHub PAT from GITHUB_TOKEN env var (or None).

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import os
import random

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from pg_atlas.config import DEFAULT_CONFIG


# ── Pytest configuration hooks ────────────────────────────────────────────────

def pytest_configure(config):
    """Register custom markers and add --run-integration CLI option support."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests that call real external APIs (deselected by default, "
        "pass --run-integration or -m integration to enable)",
    )


def pytest_addoption(parser):
    """Add --run-integration CLI flag to enable integration tests."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that call real external APIs.",
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --run-integration is passed or -m integration is used.

    If the user explicitly selects integration tests via '-m integration',
    do not skip them. Otherwise, skip any test marked with @pytest.mark.integration
    unless --run-integration was passed on the command line.
    """
    # If the user passed -m with an expression that includes 'integration',
    # do not auto-skip — they explicitly asked for integration tests.
    markexpr = config.getoption("-m", default="")
    if "integration" in markexpr:
        return

    if config.getoption("--run-integration"):
        return

    skip_integration = pytest.mark.skip(
        reason="Integration test -- pass --run-integration or -m integration to run"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)

SEED = 41

# ── Synthetic data constants (mirroring build_notebook.py) ───────────────────

HUB_PACKAGES_NPM = [
    "@stellar/js-xdr",
    "@stellar/stellar-base",
    "@stellar/stellar-sdk",
    "@stellar/freighter-api",
    "soroban-client",
    "axios",
    "eventsource",
]

HUB_PACKAGES_CARGO = [
    "soroban-sdk",
    "stellar-xdr",
    "stellar-strkey",
    "soroban-env-host",
    "sha2",
    "serde",
    "tokio",
]

HUB_PACKAGES_PYPI = [
    "stellar-sdk",
    "requests",
    "pynacl",
    "stellar-base",
]

REAL_CONTRIBUTORS = [
    "christian-rogobete",
    "ignacio-garcia",
    "enzo-soyer",
    "esteban-iglesias",
    "orbitLens",
    "christos-salaforis",
    "alejandro-mujica",
    "dmitri-volkov",
    "wei-zhang",
    "sofia-ramirez",
    "alex-olieman",
    "pamphile-roy",
]

SYNTHETIC_CONTRIBUTORS = [f"dev-{i:03d}" for i in range(1, 99)]
ALL_CONTRIBUTORS = REAL_CONTRIBUTORS + SYNTHETIC_CONTRIBUTORS


def _build_synthetic_graph() -> nx.DiGraph:
    """
    Construct the deterministic synthetic graph matching the prototype (SEED=41).

    This is a direct port of the graph construction code from:
    06_demos/01_active_subgraph_prototype/build_notebook.py (Sections 2–5).

    The graph mirrors the Stellar ecosystem structure:
    - 86 SCF-funded PG projects (real names from A5 CSV)
    - ~190 repository nodes (npm/cargo/pypi split)
    - ~140 external dependency packages (real hub packages)
    - ~110 contributor nodes
    - Power-law degree distribution (hub-biased preferential attachment)
    """
    random.seed(SEED)
    np.random.seed(SEED)

    # ── Load real project data ────────────────────────────────────────────────
    base = "/Users/jaygut/Desktop/SCF_PG-Atlas/01_data/processed"
    seed_path = os.path.join(base, "A5_pg_candidate_seed_list.csv")

    df_projects = pd.read_csv(seed_path)
    df_projects["total_awarded_usd"] = pd.to_numeric(
        df_projects["total_awarded_usd"], errors="coerce"
    ).fillna(0)

    PROJECT_NAMES = df_projects["title"].tolist()
    PROJECT_FUNDING = dict(zip(df_projects["title"], df_projects["total_awarded_usd"]))
    PROJECT_STATUS = dict(zip(df_projects["title"], df_projects["integration_status"]))
    PROJECT_CATEGORY = dict(zip(df_projects["title"], df_projects["category"]))

    G = nx.DiGraph()

    # ── Project nodes ─────────────────────────────────────────────────────────
    for name in PROJECT_NAMES:
        status = PROJECT_STATUS.get(name, "Development")
        activity_prob = {"Mainnet": 0.90, "Development": 0.65, "Testnet": 0.45}.get(
            status, 0.50
        )
        if random.random() < activity_prob:
            days_since_commit = max(0, int(np.random.exponential(15)))
        else:
            days_since_commit = int(np.random.uniform(91, 365))

        G.add_node(
            name,
            node_type="Project",
            category=PROJECT_CATEGORY.get(name, "Unknown"),
            funding=PROJECT_FUNDING.get(name, 0),
            status=status,
            active=(days_since_commit <= 90),
            days_since_commit=days_since_commit,
        )

    # ── Repo nodes ────────────────────────────────────────────────────────────
    ECOSYSTEMS = ["npm", "cargo", "cargo", "pypi"]
    repo_nodes = []

    for proj_name in PROJECT_NAMES:
        category = PROJECT_CATEGORY.get(proj_name, "")
        n_repos = np.random.choice([1, 2, 3], p=[0.3, 0.5, 0.2])

        for i in range(n_repos):
            if "Infrastructure" in category:
                eco = random.choice(["cargo", "cargo", "npm"])
            else:
                eco = random.choice(["npm", "npm", "cargo", "pypi"])

            repo_id = f"repo:{proj_name.lower().replace(' ', '-').replace('.', '')}-{eco}-{i}"

            proj_days = G.nodes[proj_name]["days_since_commit"]
            days_since = max(0, int(proj_days + np.random.normal(0, 10)))

            is_top = PROJECT_FUNDING.get(proj_name, 0) > 100000
            stars_val = int(np.random.lognormal(mean=5.0 if is_top else 2.5, sigma=1.2))
            forks_val = int(stars_val * random.uniform(0.1, 0.4))
            downloads_val = int(np.random.lognormal(mean=8.0 if is_top else 4.0, sigma=2.0))

            G.add_node(
                repo_id,
                node_type="Repo",
                ecosystem=eco,
                project=proj_name,
                active=(days_since <= 90),
                days_since_commit=days_since,
                latest_commit_date=f"2026-{max(1, min(12, 2 - days_since // 30)):02d}-15",
                stars=stars_val,
                forks=forks_val,
                downloads=downloads_val,
            )
            repo_nodes.append(repo_id)
            G.add_edge(repo_id, proj_name, edge_type="belongs_to")

    # ── External dependency nodes ─────────────────────────────────────────────
    ext_nodes = []

    for pkg in HUB_PACKAGES_NPM:
        G.add_node(
            pkg, node_type="ExternalRepo", ecosystem="npm",
            active=True, days_since_commit=random.randint(1, 30), is_hub=True,
            downloads=int(np.random.lognormal(13.0, 1.5)),
        )
        ext_nodes.append(pkg)

    for pkg in HUB_PACKAGES_CARGO:
        G.add_node(
            pkg, node_type="ExternalRepo", ecosystem="cargo",
            active=True, days_since_commit=random.randint(1, 30), is_hub=True,
            downloads=int(np.random.lognormal(11.0, 1.5)),
        )
        ext_nodes.append(pkg)

    for pkg in HUB_PACKAGES_PYPI:
        G.add_node(
            pkg, node_type="ExternalRepo", ecosystem="pypi",
            active=True, days_since_commit=random.randint(1, 30), is_hub=True,
            downloads=int(np.random.lognormal(12.0, 1.5)),
        )
        ext_nodes.append(pkg)

    for i in range(60):
        eco = random.choice(["npm", "npm", "cargo", "pypi"])
        name = f"ext-{eco}-pkg-{i:03d}"
        active = random.random() < 0.75
        G.add_node(
            name, node_type="ExternalRepo", ecosystem=eco,
            active=active,
            days_since_commit=random.randint(1, 200) if not active else random.randint(1, 60),
            is_hub=False,
            downloads=int(np.random.lognormal(6.0, 2.0)),
        )
        ext_nodes.append(name)

    # ── Dependency edges (power-law, hub-biased) ──────────────────────────────
    npm_repos = [r for r in repo_nodes if G.nodes[r]["ecosystem"] == "npm"]
    cargo_repos = [r for r in repo_nodes if G.nodes[r]["ecosystem"] == "cargo"]
    pypi_repos = [r for r in repo_nodes if G.nodes[r]["ecosystem"] == "pypi"]

    npm_ext = [p for p in HUB_PACKAGES_NPM] + [
        n for n in ext_nodes if G.nodes[n]["ecosystem"] == "npm"
    ]
    cargo_ext = [p for p in HUB_PACKAGES_CARGO] + [
        n for n in ext_nodes if G.nodes[n]["ecosystem"] == "cargo"
    ]
    pypi_ext = [p for p in HUB_PACKAGES_PYPI] + [
        n for n in ext_nodes if G.nodes[n]["ecosystem"] == "pypi"
    ]

    def add_deps(from_nodes, to_pool, n_direct_range=(1, 5), hub_bias=3.0):
        weights = np.array(
            [hub_bias if G.nodes[t].get("is_hub", False) else 1.0 for t in to_pool],
            dtype=float,
        )
        weights /= weights.sum()
        for src in from_nodes:
            n_deps = random.randint(*n_direct_range)
            targets = np.random.choice(
                to_pool, size=min(n_deps, len(to_pool)), replace=False, p=weights
            )
            for tgt in targets:
                if src != tgt and not G.has_edge(src, tgt):
                    G.add_edge(src, tgt, edge_type="depends_on", confidence="inferred_shadow")

    add_deps(npm_repos, npm_ext, n_direct_range=(2, 6), hub_bias=4.0)
    add_deps(cargo_repos, cargo_ext, n_direct_range=(2, 5), hub_bias=5.0)
    add_deps(pypi_repos, pypi_ext, n_direct_range=(1, 4), hub_bias=3.0)

    for repo in random.sample(npm_repos, k=len(npm_repos) // 4):
        wasm_target = random.choice(cargo_ext[:3])
        if not G.has_edge(repo, wasm_target):
            G.add_edge(repo, wasm_target, edge_type="depends_on", confidence="inferred_shadow")

    # ── Contributor nodes and contributed_to edges ────────────────────────────
    for contrib in ALL_CONTRIBUTORS:
        is_prolific = contrib in REAL_CONTRIBUTORS
        G.add_node(
            contrib,
            node_type="Contributor",
            is_prolific=is_prolific,
            active=True if is_prolific else random.random() < 0.7,
        )

    from collections import defaultdict

    repo_contributors = defaultdict(list)

    for repo in repo_nodes:
        proj = G.nodes[repo]["project"]
        is_top_project = PROJECT_FUNDING.get(proj, 0) > 150000

        if is_top_project and REAL_CONTRIBUTORS:
            primary = random.choice(REAL_CONTRIBUTORS[:6])
        else:
            primary = random.choice(ALL_CONTRIBUTORS)

        pony_risk = random.random() < 0.35

        if pony_risk:
            primary_share = random.uniform(0.55, 0.92)
        else:
            primary_share = random.uniform(0.20, 0.49)

        total_commits = random.randint(30, 500)
        primary_commits = int(total_commits * primary_share)

        repo_contributors[repo].append((primary, primary_commits))
        G.add_edge(
            primary, repo,
            edge_type="contributed_to",
            commits=primary_commits,
            last_commit_days=G.nodes[repo]["days_since_commit"],
        )

        n_secondary = random.randint(0, 4) if not pony_risk else random.randint(0, 2)
        remaining_commits = total_commits - primary_commits

        available = [c for c in ALL_CONTRIBUTORS if c != primary]
        secondary_pool = random.sample(available, k=min(n_secondary, len(available)))

        for sc in secondary_pool:
            sc_commits = max(
                1,
                int(remaining_commits / max(1, n_secondary) * random.uniform(0.5, 1.5)),
            )
            repo_contributors[repo].append((sc, sc_commits))
            G.add_edge(
                sc, repo,
                edge_type="contributed_to",
                commits=sc_commits,
                last_commit_days=G.nodes[repo]["days_since_commit"] + random.randint(0, 20),
            )

    return G


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def synthetic_graph() -> nx.DiGraph:
    """
    Deterministic synthetic graph matching prototype (SEED=41).

    Session-scoped: built once and reused across all test functions.
    """
    return _build_synthetic_graph()


@pytest.fixture(scope="session")
def active_subgraph(synthetic_graph: nx.DiGraph) -> nx.DiGraph:
    """
    Active subgraph projection of the synthetic graph (session-scoped).
    """
    from pg_atlas.graph.active_subgraph import active_subgraph_projection

    G_active, _ = active_subgraph_projection(synthetic_graph, DEFAULT_CONFIG)
    return G_active


@pytest.fixture(scope="session")
def real_csv_graph() -> nx.DiGraph:
    """
    Graph built from actual seed CSVs (session-scoped).

    Reads from the real A5, A6, A7 processed CSVs. No network access required.
    """
    from pg_atlas.graph.builder import build_graph_from_csv

    base = "/Users/jaygut/Desktop/SCF_PG-Atlas/01_data/processed"
    return build_graph_from_csv(
        seed_list_path=os.path.join(base, "A5_pg_candidate_seed_list.csv"),
        orgs_path=os.path.join(base, "A6_github_orgs_seed.csv"),
        repos_path=os.path.join(base, "A7_submission_github_repos.csv"),
    )


@pytest.fixture(scope="session")
def github_token() -> str | None:
    """
    GitHub personal access token from the GITHUB_TOKEN environment variable.

    Returns None if the variable is not set. Tests that require GitHub API
    access should skip when this fixture returns None.
    """
    return os.environ.get("GITHUB_TOKEN")
