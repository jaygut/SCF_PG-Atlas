"""
pg_atlas/viz/figures.py — Unified programmatic figure generation.

Generates all 8 PG Atlas publication-quality figures from a PipelineResult
object. No file I/O required — all data is extracted from the result.

Usage:
    from pg_atlas.viz.figures import generate_all_figures
    paths = generate_all_figures(result, output_dir="04_implementation/figures")
    # paths = {"fig1_concentration_histogram.png": "/abs/path/...", ...}

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

from __future__ import annotations

import logging
import math
import os
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

import matplotlib
try:
    matplotlib.use("Agg")
except Exception:
    pass  # backend already set

import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path
import networkx as nx
import numpy as np

if TYPE_CHECKING:
    from pg_atlas.pipeline import PipelineResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared colour palette — muted Stellar-adjacent blues/oranges
# ---------------------------------------------------------------------------
C_PASS = "#2196A6"      # teal — PASS
C_FAIL = "#E05E3A"      # orange-red — FAIL
C_BORDER = "#F2B134"    # amber — borderline
C_DARK = "#1A2B3C"      # near-black
C_LIGHT = "#E8EFF5"     # background tint

STYLE = {
    "figure.facecolor": "white",
    "axes.facecolor": C_LIGHT,
    "axes.edgecolor": C_DARK,
    "axes.labelcolor": C_DARK,
    "xtick.color": C_DARK,
    "ytick.color": C_DARK,
    "text.color": C_DARK,
    "grid.color": "white",
    "grid.linewidth": 1.0,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.family": "DejaVu Sans",
}

# Network colour constants
CORE_COLOR = {
    "soroban-sdk":    "#00C8D4",   # bright teal  (65 dependents)
    "stellar-xdr":    "#FF6B47",   # coral-orange (40 dependents)
    "stellar-strkey": "#FFD166",   # amber        (32 dependents)
    "soroban-env":    "#B39DDB",   # lavender     (env-host + env-common, 12 dependents)
}

CORE_ANCHORS = {
    "soroban-sdk":    np.array([ 0.0,  2.5]),   # top-centre — dominant hub
    "stellar-xdr":    np.array([ 2.8,  0.5]),   # right
    "stellar-strkey": np.array([-2.8,  0.5]),   # left
    "soroban-env":    np.array([ 0.0, -2.5]),   # bottom-centre (env-host + env-common monorepo)
}

# Maps GitHub repository URLs and legacy short crate names → CORE_COLOR display key.
# soroban-env-host and soroban-env-common share the rs-soroban-env monorepo; merged as "soroban-env".
URL_TO_DISPLAY_NAME: dict[str, str] = {
    # GitHub URL form (post URL-translation fix — current production format)
    "https://github.com/stellar/rs-soroban-sdk":    "soroban-sdk",
    "https://github.com/stellar/rs-stellar-xdr":    "stellar-xdr",
    "https://github.com/stellar/rs-stellar-strkey": "stellar-strkey",
    "https://github.com/stellar/rs-soroban-env":    "soroban-env",
    # Short crate name form (legacy pre-URL-translation — backward compatible)
    "soroban-sdk":        "soroban-sdk",
    "stellar-xdr":        "stellar-xdr",
    "stellar-strkey":     "stellar-strkey",
    "soroban-env-host":   "soroban-env",
    "soroban-env-common": "soroban-env",
}


def _short_name(url_or_name: str) -> str:
    """Return a short display label: last path segment for GitHub URLs, else raw string."""
    if "github.com/" in url_or_name:
        return url_or_name.rstrip("/").split("/")[-1]
    return url_or_name

SPREAD_RADIUS = 1.4

BOT_NAMES = {
    "github-actions[bot]", "dependabot[bot]", "zetifintech[bot]",
    "abroad-finance-bot", "cursor[bot]", "vercel[bot]",
    "codegen-sh[bot]", "abroad-bot",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_all_figures(result: "PipelineResult", output_dir: str) -> dict[str, str]:
    """
    Generate all 8 PG Atlas figures from a PipelineResult.

    Args:
        result:     Complete PipelineResult from run_full_pipeline().
        output_dir: Directory to save PNG files into (created if needed).

    Returns:
        Dict mapping filename -> absolute path for each generated figure.
    """
    os.makedirs(output_dir, exist_ok=True)
    paths: dict[str, str] = {}

    # Apply style for the standard (non-dark-bg) figures
    plt.rcParams.update(STYLE)

    # Extract common data from result
    repo_max, repo_top = _extract_contributor_concentration(result)
    gate_pass_repos = {r.project for r in result.gate_results if r.passed}

    # --- Standard figures ---
    if repo_max:
        p = _fig1_concentration_histogram(repo_max, output_dir)
        if p:
            paths[os.path.basename(p)] = p

    if result.gate_results:
        p = _fig2_gate_funnel(result, output_dir)
        if p:
            paths[os.path.basename(p)] = p

    if repo_max:
        p = _fig3_contributor_bar(repo_max, repo_top, output_dir)
        if p:
            paths[os.path.basename(p)] = p

    if result.dependency_edges:
        p = _fig4_dep_hubs(result.dependency_edges, output_dir)
        if p:
            paths[os.path.basename(p)] = p

    if result.adoption_df is not None and len(result.adoption_df) > 0:
        p = _fig5_adoption_scatter(result.adoption_df, gate_pass_repos, output_dir)
        if p:
            paths[os.path.basename(p)] = p

    if repo_max:
        p = _fig6_hhi_tiers(repo_max, result, output_dir)
        if p:
            paths[os.path.basename(p)] = p

    # --- Network figures ---
    if result.dependency_edges:
        p = _net1_dependency_hubs(result.dependency_edges, output_dir)
        if p:
            paths[os.path.basename(p)] = p

    if result.contribution_edges:
        p = _net2_contributor_bipartite(result.contribution_edges, gate_pass_repos, output_dir)
        if p:
            paths[os.path.basename(p)] = p

    logger.info("Generated %d figures in %s", len(paths), output_dir)
    return paths


# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------
def _extract_contributor_concentration(result: "PipelineResult") -> tuple[dict, dict]:
    """Extract repo_max (short_name -> share%) and repo_top (short_name -> login).

    Primary source: result.pony_results (from graph-based pony factor analysis).
    Fallback: compute directly from result.contribution_edges when pony_results
    is empty (e.g. CSV-only mode where the graph lacks contributor edges).
    """
    repo_max: dict[str, float] = {}
    repo_top: dict[str, str] = {}

    if result.pony_results:
        for repo_url, pr in result.pony_results.items():
            short = repo_url.split("/")[-1] if "/" in repo_url else repo_url
            share_pct = pr.top_contributor_share * 100  # convert 0-1 to percentage
            repo_max[short] = share_pct
            repo_top[short] = pr.top_contributor
    elif result.contribution_edges:
        # Fallback: compute from raw contribution edges
        repo_commits: dict[str, int] = defaultdict(int)
        repo_top_contrib: dict[str, tuple[int, str]] = {}  # repo -> (max_commits, login)
        for e in result.contribution_edges:
            repo_raw = e["repo"]
            short = repo_raw.split("/")[-1] if "/" in repo_raw else repo_raw
            commits = e["commits"]
            repo_commits[short] += commits
            cur = repo_top_contrib.get(short, (0, ""))
            if commits > cur[0]:
                repo_top_contrib[short] = (commits, e["contributor"])
        for short, total in repo_commits.items():
            if total > 0 and short in repo_top_contrib:
                top_commits, top_login = repo_top_contrib[short]
                repo_max[short] = (top_commits / total) * 100
                repo_top[short] = top_login

    return repo_max, repo_top


# ---------------------------------------------------------------------------
# Figure 1 — Contributor Concentration Distribution (histogram)
# ---------------------------------------------------------------------------
def _fig1_concentration_histogram(repo_max: dict, output_dir: str) -> str | None:
    shares = sorted(repo_max.values())
    fig, ax = plt.subplots(figsize=(8, 5))

    bins = np.linspace(0, 100, 21)
    counts, edges, patches = ax.hist(shares, bins=bins, color=C_PASS,
                                     edgecolor="white", linewidth=0.8, zorder=3)

    # Recolour bars above 50% threshold red
    for i, (left, right) in enumerate(zip(edges[:-1], edges[1:])):
        if left >= 50:
            patches[i].set_facecolor(C_FAIL)
        elif right > 50:
            patches[i].set_facecolor(C_BORDER)

    ax.axvline(50, color=C_DARK, linestyle="--", linewidth=1.5, zorder=4,
               label="Pony Factor threshold (50%)")

    n_flagged = sum(1 for v in shares if v >= 50)
    n_total = len(shares)
    pct = round(n_flagged / n_total * 100) if n_total > 0 else 0
    ax.set_xlabel("Top contributor share of commits (90-day window, %)", fontsize=12)
    ax.set_ylabel("Number of repositories", fontsize=12)
    ax.set_title(
        f"Contributor Concentration \u2014 {n_flagged}/{n_total} repos ({pct}%) above Pony Factor threshold",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax.set_xlim(0, 100)
    ax.set_ylim(bottom=0)
    ax.yaxis.grid(True, zorder=0)

    pass_patch = mpatches.Patch(color=C_PASS, label="\u226450% (distributed)")
    fail_patch = mpatches.Patch(color=C_FAIL, label="\u226550% (pony-flagged)")
    ax.legend(handles=[pass_patch, fail_patch,
                       plt.Line2D([0], [0], color=C_DARK, linestyle="--",
                                  linewidth=1.5, label="50% threshold")],
              fontsize=10, loc="upper left")

    fig.tight_layout()
    path = os.path.join(output_dir, "fig1_concentration_histogram.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(path)


# ---------------------------------------------------------------------------
# Figure 2 — Gate Funnel (donut + bar combo)
# ---------------------------------------------------------------------------
def _fig2_gate_funnel(result: "PipelineResult", output_dir: str) -> str | None:
    total = len(result.gate_results)
    if total == 0:
        return None
    passed = sum(1 for r in result.gate_results if r.passed)
    failed = total - passed
    border = result.snapshot.gate_borderline_count if result.snapshot else 0
    pass_pct = round(passed / total * 100) if total > 0 else 0

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))

    # Left -- donut chart
    ax = axes[0]
    sizes = [passed, failed]
    colors = [C_PASS, C_FAIL]
    wedges, texts, autotexts = ax.pie(
        sizes, labels=["PASS", "FAIL"], colors=colors,
        autopct="%1.0f%%", startangle=90,
        wedgeprops={"width": 0.55, "edgecolor": "white", "linewidth": 2},
        textprops={"fontsize": 13, "fontweight": "bold"},
        pctdistance=0.75,
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontsize(12)
    ax.set_title(f"Layer 1 Gate Pass Rate\n({pass_pct}% threshold)", fontsize=13,
                 fontweight="bold", pad=15)
    ax.text(0, 0, f"{passed}/{total}", ha="center", va="center",
            fontsize=20, fontweight="bold", color=C_DARK)

    # Right -- stacked horizontal signal breakdown
    ax2 = axes[1]
    # Count by signals_passed
    signal_2plus = passed
    signal_under = failed
    signal_labels = [f"{result.gate_results[0].signals_required}/3 signals\n(PASS)" if result.gate_results else "PASS",
                     f"<{result.gate_results[0].signals_required}/3 signals\n(FAIL)" if result.gate_results else "FAIL"]
    signal_vals = [signal_2plus, signal_under]
    signal_colors = [C_PASS, C_FAIL]
    bars = ax2.barh(signal_labels, signal_vals, color=signal_colors,
                    edgecolor="white", linewidth=1.2, height=0.45)
    for bar, val in zip(bars, signal_vals):
        ax2.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                 f"{val} repos", va="center", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Number of repositories", fontsize=12)
    ax2.set_title(f"Signal Distribution\n(out of {total} scored repos)", fontsize=13,
                  fontweight="bold", pad=15)
    ax2.set_xlim(0, max(total + 2, 10))
    ax2.xaxis.grid(True, zorder=0)

    # Borderline annotation
    if border > 0 and passed > 0:
        ann_text = (f"  {border} of {passed} PASSes\n  are borderline\n  (recommended\n  for expert review)"
                    if border < passed
                    else f"  All {passed} PASSes\n  are borderline\n  (recommended\n  for expert review)")
        ax2.annotate(
            ann_text,
            xy=(passed, 0), xytext=(passed + 8, 0),
            arrowprops={"arrowstyle": "->", "color": C_DARK},
            fontsize=10, color=C_DARK,
            va="center",
        )

    fig.suptitle("PG Atlas Layer 1 Metric Gate",
                 fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()
    path = os.path.join(output_dir, "fig2_gate_funnel.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(path)


# ---------------------------------------------------------------------------
# Figure 3 — Top Contributor Share Per Repo (horizontal bar, sorted)
# ---------------------------------------------------------------------------
def _fig3_contributor_bar(repo_max: dict, repo_top: dict, output_dir: str) -> str | None:
    sorted_repos = sorted(repo_max.items(), key=lambda x: x[1], reverse=True)
    labels = [repo for repo, _ in sorted_repos]
    values = [v for _, v in sorted_repos]
    colors = [C_FAIL if v >= 50 else C_PASS for v in values]

    fig, ax = plt.subplots(figsize=(10, max(6, len(labels) * 0.3)))
    y = np.arange(len(labels))
    bars = ax.barh(y, values, color=colors, edgecolor="white",
                   linewidth=0.6, height=0.75)
    ax.axvline(50, color=C_DARK, linestyle="--", linewidth=1.4, zorder=4,
               label="50% Pony Factor threshold")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Top contributor share of commits (%)", fontsize=11)
    ax.set_title(
        "Per-Repo Contributor Concentration\n(90-day window \u2014 sorted by concentration risk)",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax.set_xlim(0, 110)
    ax.xaxis.grid(True, zorder=0)

    # Add contributor login for repos at 100%
    for i, (repo, share) in enumerate(sorted_repos):
        if share >= 95:
            login = repo_top.get(repo, "")
            if login:
                ax.text(share + 1.5, i, f"@{login}", va="center",
                        fontsize=6.5, color=C_DARK, alpha=0.85)

    pass_patch = mpatches.Patch(color=C_PASS, label="Distributed (< 50%)")
    fail_patch = mpatches.Patch(color=C_FAIL, label="Pony-flagged (\u2265 50%)")
    ax.legend(handles=[fail_patch, pass_patch,
                       plt.Line2D([0], [0], color=C_DARK, linestyle="--",
                                  linewidth=1.4, label="50% threshold")],
              fontsize=9, loc="lower right")

    fig.tight_layout()
    path = os.path.join(output_dir, "fig3_contributor_concentration_bar.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(path)


# ---------------------------------------------------------------------------
# Figure 4 — Soroban Ecosystem Dependency Hubs (bar chart)
# ---------------------------------------------------------------------------
def _fig4_dep_hubs(dependency_edges: list[dict], output_dir: str) -> str | None:
    # Normalise to_package → short display name (handles both GitHub URLs and legacy crate names)
    dep_counts = Counter(
        URL_TO_DISPLAY_NAME.get(e["to_package"], _short_name(e["to_package"]))
        for e in dependency_edges
    )
    if not dep_counts:
        return None
    top_n = dep_counts.most_common(8)
    packages = [p for p, _ in top_n]
    counts = [c for _, c in top_n]
    colors = [C_PASS if i < 3 else "#4BA3C3" for i in range(len(packages))]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(range(len(packages)), counts, color=colors,
                  edgecolor="white", linewidth=1.0, width=0.65)

    for bar, val in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.8,
                str(val), ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax.set_xticks(range(len(packages)))
    ax.set_xticklabels(packages, rotation=25, ha="right", fontsize=10)
    ax.set_ylabel("Number of dependent crates", fontsize=11)

    total_edges = len(dependency_edges)
    n_sources = len(set(_short_name(e["from_repo"]) for e in dependency_edges))
    ax.set_title(
        f"Soroban Ecosystem \u2014 Reverse Dependency Count per Core Package\n"
        f"({total_edges} crates.io edges across {n_sources} active repos)",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax.set_ylim(0, max(counts) * 1.18)
    ax.yaxis.grid(True, zorder=0)

    # Annotation for top package
    if packages and counts:
        ax.annotate(
            f"{packages[0]}: universal\ndependency of the\nSoroban ecosystem",
            xy=(0, counts[0]), xytext=(1.5, counts[0] * 0.75),
            arrowprops={"arrowstyle": "->", "color": C_DARK},
            fontsize=9, color=C_DARK,
        )

    fig.tight_layout()
    path = os.path.join(output_dir, "fig4_soroban_dep_hubs.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(path)


# ---------------------------------------------------------------------------
# Figure 5 — GitHub Stars vs Forks (adoption scatter)
# ---------------------------------------------------------------------------
def _fig5_adoption_scatter(adoption_df, gate_pass_repos: set, output_dir: str) -> str | None:
    if adoption_df is None or len(adoption_df) == 0:
        return None

    # Try to get repo names, stars, forks from the DataFrame
    if "github_stars" not in adoption_df.columns or "github_forks" not in adoption_df.columns:
        return None

    df = adoption_df.copy()
    # Determine repo name column
    if "repo_full_name" in df.columns:
        repo_col = "repo_full_name"
    elif df.index.name and "repo" in df.index.name.lower():
        df = df.reset_index()
        repo_col = df.columns[0]
    else:
        # Use index as repo name
        df = df.reset_index()
        repo_col = df.columns[0]

    repos = [str(r).split("/")[-1] for r in df[repo_col]]
    stars = df["github_stars"].astype(int).tolist()
    forks = df["github_forks"].astype(int).tolist()

    is_pass = [str(r) in gate_pass_repos for r in df[repo_col]]
    colors = [C_PASS if p else C_FAIL for p in is_pass]

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(stars, forks, c=colors, s=120, edgecolors=C_DARK,
               linewidths=0.8, zorder=4, alpha=0.9)

    for s, f, name in zip(stars, forks, repos):
        if s > 20 or f > 20:
            ax.annotate(name, (s, f),
                        textcoords="offset points", xytext=(6, 4),
                        fontsize=8, color=C_DARK)

    ax.set_xlabel("GitHub Stars", fontsize=12)
    ax.set_ylabel("GitHub Forks", fontsize=12)
    ax.set_title(
        f"Adoption Signals \u2014 GitHub Stars vs Forks\n"
        f"({len(df)} repos with resolved GitHub metadata)",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax.xaxis.grid(True, zorder=0)
    ax.yaxis.grid(True, zorder=0)

    pass_patch = mpatches.Patch(color=C_PASS, label="Gate PASS")
    fail_patch = mpatches.Patch(color=C_FAIL, label="Gate FAIL")
    ax.legend(handles=[pass_patch, fail_patch], fontsize=10)

    fig.tight_layout()
    path = os.path.join(output_dir, "fig5_adoption_scatter.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(path)


# ---------------------------------------------------------------------------
# Figure 6 — HHI Tier Breakdown (stacked bar by tier)
# ---------------------------------------------------------------------------
def _fig6_hhi_tiers(repo_max: dict, result: "PipelineResult", output_dir: str) -> str | None:
    shares = list(repo_max.values())
    if not shares:
        return None
    healthy = sum(1 for s in shares if s < 30)
    moderate = sum(1 for s in shares if 30 <= s < 50)
    concentrated = sum(1 for s in shares if 50 <= s < 80)
    critical = sum(1 for s in shares if s >= 80)

    categories = ["Healthy\n(<30% top share)", "Moderate\n(30\u201350%)",
                  "Concentrated\n(50\u201380%)", "Critical\n(\u226580%)"]
    values = [healthy, moderate, concentrated, critical]
    colors = ["#2E9E6B", "#F2B134", C_FAIL, "#A01010"]

    # Compute summary stats
    n_repos = len(shares)
    if result.pony_results:
        hhi_values = [pr.hhi for pr in result.pony_results.values()]
        mean_hhi = round(sum(hhi_values) / len(hhi_values)) if hhi_values else 0
        n_pony = sum(1 for pr in result.pony_results.values() if pr.pony_factor == 1)
    else:
        # Approximate HHI from max share: HHI ~ share^2 * 10000 (single-contributor approx)
        hhi_approx = [(s / 100) ** 2 * 10000 for s in shares]
        mean_hhi = round(sum(hhi_approx) / len(hhi_approx)) if hhi_approx else 0
        n_pony = sum(1 for s in shares if s >= 50)
    pony_rate = round(n_pony / n_repos * 100) if n_repos > 0 else 0

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(categories, values, color=colors,
                  edgecolor="white", linewidth=1.2, width=0.6)

    for bar, val in zip(bars, values):
        pct = val / n_repos * 100 if n_repos > 0 else 0
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15,
                f"{val} repos\n({pct:.0f}%)",
                ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax.set_ylabel("Number of repositories", fontsize=12)
    ax.set_title(
        f"Maintenance Health Tiers \u2014 {n_repos} Scored Repos\n"
        f"Mean HHI: {mean_hhi:,} | Pony Factor Rate: {pony_rate}%",
        fontsize=13, fontweight="bold", pad=12,
    )
    ax.set_ylim(0, max(values) * 1.30 if values else 10)
    ax.yaxis.grid(True, zorder=0)

    # Danger zone annotation
    ax.axhline(0, color="white")
    ax.annotate("\u2190 Pony Factor\n   risk zone",
                xy=(1.5, max(concentrated, critical)),
                xytext=(1.5, max(concentrated, critical) + 1.5),
                fontsize=9, color=C_DARK, ha="center")

    fig.tight_layout()
    path = os.path.join(output_dir, "fig6_hhi_tiers.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(path)


# ---------------------------------------------------------------------------
# Layout helper for dependency network
# ---------------------------------------------------------------------------
def _dep_layout(G, source_nodes, seed=42):
    rng = np.random.default_rng(seed)
    pos = {}
    for pkg, anchor in CORE_ANCHORS.items():
        pos[pkg] = anchor.copy()

    for src in source_nodes:
        targets = [t for _, t in G.out_edges(src)]
        if not targets:
            angle = rng.uniform(0, 2 * math.pi)
            pos[src] = np.array([math.cos(angle) * 5, math.sin(angle) * 5])
            continue
        centroid = np.mean([CORE_ANCHORS[t] for t in targets if t in CORE_ANCHORS],
                          axis=0)
        direction = centroid / (np.linalg.norm(centroid) + 1e-9)
        angle_jitter = rng.uniform(-math.pi * 0.8, math.pi * 0.8)
        rot = np.array([[math.cos(angle_jitter), -math.sin(angle_jitter)],
                        [math.sin(angle_jitter),  math.cos(angle_jitter)]])
        direction = rot @ direction
        radius = SPREAD_RADIUS + rng.uniform(-0.35, 0.6)
        pos[src] = centroid + direction * radius

    return pos


# ---------------------------------------------------------------------------
# Network 1 — Soroban Dependency Hub (dark background)
# ---------------------------------------------------------------------------
def _net1_dependency_hubs(dependency_edges: list[dict], output_dir: str) -> str | None:
    # Normalise node IDs: GitHub URLs → display names; other URLs → last path segment.
    def _norm_tgt(pkg: str) -> str:
        return URL_TO_DISPLAY_NAME.get(pkg, pkg)

    def _norm_src(repo: str) -> str:
        # Core crate repos resolve to their display name; all others → short path segment.
        return URL_TO_DISPLAY_NAME.get(repo, _short_name(repo))

    dep_counts = Counter(_norm_tgt(e["to_package"]) for e in dependency_edges)
    src_counts = Counter(_norm_src(e["from_repo"]) for e in dependency_edges)

    G = nx.DiGraph()
    core_nodes = list(CORE_COLOR.keys())
    source_nodes = []

    for pkg in core_nodes:
        G.add_node(pkg, kind="core")
    for e in dependency_edges:
        src = _norm_src(e["from_repo"])
        tgt = _norm_tgt(e["to_package"])
        if tgt not in CORE_COLOR:
            continue
        if src == tgt:  # skip self-loops (e.g. soroban-sdk repo → soroban-sdk crate)
            continue
        if src not in G:
            G.add_node(src, kind="source")
            source_nodes.append(src)
        G.add_edge(src, tgt)

    source_nodes = list(set(source_nodes))
    pos = _dep_layout(G, source_nodes, seed=7)

    # -- Figure --
    BG = "#0D1B2A"
    fig, ax = plt.subplots(figsize=(14, 11), facecolor=BG)
    ax.set_facecolor(BG)
    ax.set_aspect("equal")
    ax.axis("off")

    # --- Draw edges (one colour pass per target package) ---
    for pkg in core_nodes:
        col = CORE_COLOR[pkg]
        edges_to_pkg = [(u, v) for u, v in G.edges() if v == pkg]
        if not edges_to_pkg:
            continue
        # draw glow (thick, low alpha)
        nx.draw_networkx_edges(
            G, pos, edgelist=edges_to_pkg, ax=ax,
            edge_color=col, alpha=0.07,
            width=3.5, arrows=False,
        )
        # draw crisp line (thin, medium alpha)
        nx.draw_networkx_edges(
            G, pos, edgelist=edges_to_pkg, ax=ax,
            edge_color=col, alpha=0.35,
            width=0.9, arrows=False,
        )

    # --- Source crate nodes ---
    multi_dep = {n for n in source_nodes if src_counts[n] >= 3}
    single_dep = [n for n in source_nodes if n not in multi_dep]
    multi_dep_list = list(multi_dep)

    # single-dep: tiny white dots
    nx.draw_networkx_nodes(
        G, pos, nodelist=single_dep, ax=ax,
        node_color="white", node_size=18,
        alpha=0.55, linewidths=0,
    )
    # multi-dep (3+): slightly larger, outlined
    if multi_dep_list:
        nx.draw_networkx_nodes(
            G, pos, nodelist=multi_dep_list, ax=ax,
            node_color="white", node_size=80,
            alpha=0.85, linewidths=0.8,
            edgecolors="#FFFFFF",
        )

    # --- Core package nodes -- with glow rings ---
    for pkg in core_nodes:
        col = CORE_COLOR[pkg]
        n_dep = dep_counts[pkg]
        sz = 700 + n_dep * 22
        p = np.array([pos[pkg]])
        # outer glow ring
        ax.scatter(*p.T, s=sz * 2.8, color=col, alpha=0.12, linewidths=0, zorder=4)
        ax.scatter(*p.T, s=sz * 1.5, color=col, alpha=0.20, linewidths=0, zorder=4)
        # core node
        ax.scatter(*p.T, s=sz, color=col, alpha=1.0, linewidths=1.5,
                   edgecolors="white", zorder=5)

    # --- Core package labels ---
    for pkg in core_nodes:
        x, y = pos[pkg]
        n_dep = dep_counts[pkg]
        label = f"{pkg}\n({n_dep} dependents)"
        offset = 0.55 if y >= 0 else -0.55
        txt = ax.text(x, y + offset, label, fontsize=10, fontweight="bold",
                      ha="center", va="center", color="white", zorder=7,
                      linespacing=1.4)
        txt.set_path_effects([
            pe.withStroke(linewidth=3, foreground=BG)
        ])

    # --- Multi-dep source labels (notable crates) ---
    # Names here must match the _norm_src() output (last path segment for GitHub URLs).
    notable = {"stellar-cli", "rs-soroban-sdk", "rs-soroban-env",
               "zephyr-sdk", "solang", "soroban-cli", "soroban-rpc"}
    for n in multi_dep_list:
        if n in notable:
            x, y = pos[n]
            txt = ax.text(x, y + 0.22, n, fontsize=7.5, ha="center", va="bottom",
                          color="#CCDDEE", zorder=7, style="italic")
            txt.set_path_effects([pe.withStroke(linewidth=2, foreground=BG)])

    # --- Legend ---
    handles = [
        mpatches.Patch(color=col, label=f"{pkg}  ({dep_counts[pkg]})")
        for pkg, col in CORE_COLOR.items()
    ]
    handles.append(mpatches.Patch(color="white", alpha=0.55, label="Dependent crate (1\u20132 deps)"))
    handles.append(mpatches.Patch(color="white", alpha=0.85, label="Dependent crate (3+ deps)"))
    leg = ax.legend(
        handles=handles, loc="lower right", fontsize=9,
        facecolor="#1B2E42", edgecolor="#3A5068", labelcolor="white",
        title="Core Packages (reverse-dep count)", title_fontsize=9,
        framealpha=0.85, borderpad=0.9,
    )
    leg.get_title().set_color("white")

    # --- Title & annotation ---
    total_edges = len(dependency_edges)
    n_sources = len(source_nodes)
    n_cores = len(core_nodes)
    ax.set_title(
        f"Soroban Ecosystem \u2014 Package Dependency Network\n"
        f"{total_edges} crates.io edges \u00b7 {n_sources} dependent crates \u00b7 {n_cores} core packages",
        fontsize=14, fontweight="bold", color="white", pad=16,
    )
    fig.text(0.02, 0.02,
             "PG Atlas \u00b7 A9 Criticality Signal",
             fontsize=8, color="#6A90B0")

    fig.tight_layout()
    path = os.path.join(output_dir, "net1_soroban_dependency_hub.png")
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return os.path.abspath(path)


# ---------------------------------------------------------------------------
# Network 2 — Contributor-Repo Bipartite (dark background, two-column layout)
# ---------------------------------------------------------------------------
def _net2_contributor_bipartite(
    contribution_edges: list[dict],
    gate_pass_repos: set,
    output_dir: str,
) -> str | None:
    BG = "#0D1B2A"

    # Compute commit_share_pct from raw contribution edges
    repo_total_commits: dict[str, int] = defaultdict(int)
    for e in contribution_edges:
        repo_total_commits[e["repo"]] += e["commits"]

    enriched = []
    for e in contribution_edges:
        total = repo_total_commits[e["repo"]]
        share = (e["commits"] / total) * 100 if total > 0 else 0
        enriched.append({
            "repo": e["repo"],
            "contributor": e["contributor"],
            "share": share,
            "commits": e["commits"],
        })

    # --- Build contributor -> repos map (no bots) ---
    contrib_repos_map: dict[str, set] = defaultdict(set)
    for r in enriched:
        if r["contributor"] not in BOT_NAMES:
            contrib_repos_map[r["contributor"]].add(r["repo"])
    cross_repo_contribs = {c for c, reps in contrib_repos_map.items() if len(reps) > 1}

    # --- Filter edges: >= 15% share OR cross-repo contributor ---
    kept_edges = []
    for r in enriched:
        login = r["contributor"]
        if login in BOT_NAMES:
            continue
        if r["share"] >= 15 or login in cross_repo_contribs:
            kept_edges.append(r)

    if not kept_edges:
        return None

    repo_contrib_count = Counter(e["repo"] for e in kept_edges)
    contrib_total_commits: dict[str, int] = defaultdict(int)
    for e in kept_edges:
        contrib_total_commits[e["contributor"]] += e["commits"]

    all_repos = sorted(set(e["repo"] for e in kept_edges))
    all_contribs = sorted(set(e["contributor"] for e in kept_edges))

    # Sort: pass repos first -> then by contributor count desc
    sorted_repos = sorted(
        all_repos,
        key=lambda r: (r not in gate_pass_repos, -repo_contrib_count[r]),
    )
    # Sort: cross-repo first -> then by total commits desc
    sorted_contribs = sorted(
        all_contribs,
        key=lambda c: (c not in cross_repo_contribs, -contrib_total_commits[c]),
    )

    n_r = len(sorted_repos)
    n_c = len(sorted_contribs)

    # --- Two-column positions ---
    X_REPO = 0.0
    X_CONTRIB = 1.0
    repo_pos = {r: (X_REPO, 0.98 - i * (0.96 / max(n_r - 1, 1))) for i, r in enumerate(sorted_repos)}
    contrib_pos = {c: (X_CONTRIB, 0.98 - i * (0.96 / max(n_c - 1, 1))) for i, c in enumerate(sorted_contribs)}

    # --- Figure ---
    fig, ax = plt.subplots(figsize=(17, 15), facecolor=BG)
    ax.set_facecolor(BG)
    ax.set_xlim(-0.46, 1.46)
    ax.set_ylim(-0.10, 1.10)
    ax.axis("off")

    # --- Bezier-curve edge helper ---
    def _bezier(ax, p0, p1, color, lw, alpha):
        mid_x = (p0[0] + p1[0]) / 2
        verts = [p0, (mid_x, p0[1]), (mid_x, p1[1]), p1]
        codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4]
        patch = PathPatch(Path(verts, codes), facecolor="none",
                          edgecolor=color, linewidth=lw, alpha=alpha,
                          capstyle="round", zorder=2)
        ax.add_patch(patch)

    # --- Edge colour by share intensity ---
    def _edge_style(share):
        if share >= 70:
            return "#FFD700", max(1.2, share / 22), 0.88   # gold -- dominant pony
        elif share >= 40:
            return "#FF8C42", max(0.9, share / 28), 0.78   # orange -- high
        elif share >= 20:
            return "#5BC8AF", max(0.7, share / 35), 0.65   # teal -- moderate
        else:
            return "#2A4A6A", 0.5, 0.40                    # dim -- minor

    for e in kept_edges:
        p0 = repo_pos.get(e["repo"])
        p1 = contrib_pos.get(e["contributor"])
        if p0 is None or p1 is None:
            continue
        col, lw, alpha = _edge_style(e["share"])
        _bezier(ax, p0, p1, col, lw, alpha)

    # --- Subtle column spine lines ---
    for x in (X_REPO, X_CONTRIB):
        ax.plot([x, x], [0.01, 0.99], color="#1E3A52", linewidth=0.8,
                alpha=0.5, zorder=0)

    # --- Repo nodes ---
    for r in sorted_repos:
        p = repo_pos[r]
        is_p = r in gate_pass_repos
        col = "#00C8D4" if is_p else "#FF6B47"
        sz = 90 + repo_contrib_count[r] * 38
        if is_p:
            ax.scatter(*p, s=sz * 2.6, color=col, alpha=0.14, linewidths=0, zorder=3)
            ax.scatter(*p, s=sz, color=col, alpha=1.0, linewidths=1.5,
                       edgecolors="white", zorder=5)
        else:
            ax.scatter(*p, s=sz, color=col, alpha=0.82, linewidths=0.6,
                       edgecolors="#FFFFFF33", zorder=5)

    # --- Contributor nodes ---
    for c in sorted_contribs:
        p = contrib_pos[c]
        is_key = c in cross_repo_contribs
        if is_key:
            ax.scatter(*p, s=220, color="#F2B134", alpha=1.0, linewidths=1.2,
                       edgecolors="white", zorder=6, marker="*")
        else:
            ax.scatter(*p, s=48, color="#6A8FAF", alpha=0.72, linewidths=0.3,
                       edgecolors="#6A8FAF", zorder=5, marker="D")

    # --- Repo labels (right-aligned, left of column) ---
    for r in sorted_repos:
        p = repo_pos[r]
        is_p = r in gate_pass_repos
        short = r.split("/")[-1] if "/" in r else r
        txt = ax.text(p[0] - 0.028, p[1], short,
                      fontsize=8.5 if is_p else 6.5,
                      fontweight="bold" if is_p else "normal",
                      ha="right", va="center",
                      color="#00C8D4" if is_p else "#7AABCC", zorder=7)
        txt.set_path_effects([pe.withStroke(linewidth=2.5, foreground=BG)])

    # --- Contributor labels: cross-repo keystones + notable contributors ---
    pass_repo_contributors = {
        e["contributor"]
        for e in kept_edges
        if e["repo"] in gate_pass_repos and e["share"] >= 20
    }
    label_set = cross_repo_contribs | pass_repo_contributors

    for c in sorted_contribs:
        if c in label_set:
            p = contrib_pos[c]
            is_key = c in cross_repo_contribs
            txt = ax.text(p[0] + 0.028, p[1], f"@{c}",
                          fontsize=7.0 if is_key else 6.2,
                          fontweight="bold" if is_key else "normal",
                          ha="left", va="center",
                          color="#F2B134" if is_key else "#A0C8E0", zorder=7)
            txt.set_path_effects([pe.withStroke(linewidth=2.0, foreground=BG)])

    # --- Column headers ---
    for x, label, ha in [
        (X_REPO - 0.04, "\u25c0  REPOSITORIES", "right"),
        (X_CONTRIB + 0.04, "CONTRIBUTORS  \u25b6", "left"),
    ]:
        ax.text(x, 1.06, label, fontsize=9.5, fontweight="bold",
                ha=ha, va="bottom", color="#6AAAC8", alpha=0.85)

    # --- Legend ---
    n_pass = len([r for r in sorted_repos if r in gate_pass_repos])
    n_fail = len([r for r in sorted_repos if r not in gate_pass_repos])
    legend_elements = [
        mpatches.Patch(color="#00C8D4", label=f"Gate PASS repo ({n_pass})"),
        mpatches.Patch(color="#FF6B47", label=f"Gate FAIL repo ({n_fail})"),
        plt.Line2D([0], [0], marker="*", color="w", markerfacecolor="#F2B134",
                   markersize=12, label=f"Cross-repo keystone contributor ({len(cross_repo_contribs)})"),
        plt.Line2D([0], [0], marker="D", color="w", markerfacecolor="#6A8FAF",
                   markersize=7, label="Single-repo contributor"),
        plt.Line2D([0], [0], color="#FFD700", linewidth=3.0, label="\u2265 70% commit share  (pony-dominant)"),
        plt.Line2D([0], [0], color="#FF8C42", linewidth=2.2, label="40 \u2013 70%  (high concentration)"),
        plt.Line2D([0], [0], color="#5BC8AF", linewidth=1.6, label="20 \u2013 40%  (moderate)"),
        plt.Line2D([0], [0], color="#2A4A6A", linewidth=1.0, label="< 20%  (minor)"),
    ]
    leg = ax.legend(
        handles=legend_elements, loc="lower center",
        bbox_to_anchor=(0.5, -0.085), ncol=4,
        fontsize=8.5, facecolor="#1B2E42", edgecolor="#3A5068",
        labelcolor="white", title="Node & Edge Legend",
        title_fontsize=9, framealpha=0.90, borderpad=0.9,
    )
    leg.get_title().set_color("white")

    # --- Title ---
    ax.set_title(
        f"Contributor \u2013 Repo Bipartite Network\n"
        f"{n_r} repos  \u00b7  {n_c} contributors  \u00b7  "
        f"{len(cross_repo_contribs)} cross-repo keystones  \u00b7  "
        "edge colour = commit concentration",
        fontsize=13, fontweight="bold", color="white", pad=16,
    )
    fig.text(0.02, 0.005, "PG Atlas \u00b7 A7 Git Log + A9 Pony Factor Signal",
             fontsize=8, color="#6A90B0")

    path = os.path.join(output_dir, "net2_contributor_repo_bipartite.png")
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return os.path.abspath(path)
