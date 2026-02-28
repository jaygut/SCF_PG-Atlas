"""
PG Atlas — Network Visualization Generator
Produces 2 network figures from real pipeline data.

  net1_dependency_hubs()    — Soroban crate dependency graph (dark bg)
  net2_contributor_bipartite()  — Contributor-repo bipartite (light bg)

Output: 04_implementation/figures/
"""

import csv
import os
import math
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.path import Path
from matplotlib.patches import PathPatch
import numpy as np
import networkx as nx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "01_data", "real")
OUT_DIR  = os.path.join(ROOT, "04_implementation", "figures")
os.makedirs(OUT_DIR, exist_ok=True)

CONTRIB_CSV = os.path.join(DATA_DIR, "contributor_stats.csv")
DEP_CSV     = os.path.join(DATA_DIR, "dependency_edges.csv")

# ---------------------------------------------------------------------------
# Shared palette
# ---------------------------------------------------------------------------
CORE_COLOR = {
    "soroban-sdk":       "#00C8D4",   # bright teal  (65 dependents)
    "stellar-xdr":       "#FF6B47",   # coral-orange (40 dependents)
    "stellar-strkey":    "#FFD166",   # amber        (32 dependents)
    "soroban-env-host":  "#B39DDB",   # lavender     ( 8 dependents)
    "soroban-env-common":"#69DB7C",   # mint green   ( 4 dependents)
}

GATE_PASS_REPOS = {
    "GaloisInc/saw-script",
    "calimero-network/core",
    "Inferara/soroban-security-catalogue",
    "tupui/soroban-versioning",
}

BOT_NAMES = {
    "github-actions[bot]", "dependabot[bot]", "zetifintech[bot]",
    "abroad-finance-bot", "cursor[bot]", "vercel[bot]",
    "codegen-sh[bot]", "abroad-bot",
}

# ---------------------------------------------------------------------------
# Helper: compute a custom layout for the dependency graph
# Core packages placed at fixed anchors; source crates positioned at the
# weighted centroid of their targets plus a random radial offset so they
# fan out around whichever hub(s) they depend on.
# ---------------------------------------------------------------------------
CORE_ANCHORS = {
    "soroban-sdk":       np.array([ 0.0,  2.5]),   # top-centre — dominant hub
    "stellar-xdr":       np.array([ 2.8,  0.5]),   # right
    "stellar-strkey":    np.array([-2.8,  0.5]),   # left
    "soroban-env-host":  np.array([ 1.5, -2.5]),   # bottom-right
    "soroban-env-common":np.array([-1.5, -2.5]),   # bottom-left
}
SPREAD_RADIUS = 1.4   # how far source crates orbit their hub centroid


def _dep_layout(G, source_nodes, seed=42):
    rng = np.random.default_rng(seed)
    pos = {}
    for pkg, anchor in CORE_ANCHORS.items():
        pos[pkg] = anchor.copy()

    for src in source_nodes:
        targets = [t for _, t in G.out_edges(src)]
        if not targets:
            # orphan — scatter far from centre
            angle = rng.uniform(0, 2 * math.pi)
            pos[src] = np.array([math.cos(angle) * 5, math.sin(angle) * 5])
            continue
        # centroid of target anchors
        centroid = np.mean([CORE_ANCHORS[t] for t in targets if t in CORE_ANCHORS],
                           axis=0)
        # push outward from centroid with random angle spread
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
def net1_dependency_hubs():
    rows       = list(csv.DictReader(open(DEP_CSV)))
    dep_counts = Counter(r["to_package"] for r in rows)
    src_counts = Counter(r["from_repo"] for r in rows)   # edges per source crate

    G = nx.DiGraph()
    core_nodes   = list(CORE_COLOR.keys())
    source_nodes = []

    for pkg in core_nodes:
        G.add_node(pkg, kind="core")
    for r in rows:
        src, tgt = r["from_repo"], r["to_package"]
        if tgt not in CORE_COLOR:
            continue
        if src not in G:
            G.add_node(src, kind="source")
            source_nodes.append(src)
        G.add_edge(src, tgt)

    source_nodes = list(set(source_nodes))
    pos = _dep_layout(G, source_nodes, seed=7)

    # ── Figure ──────────────────────────────────────────────────────────────
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
    multi_dep  = list(multi_dep)

    # single-dep: tiny white dots
    nx.draw_networkx_nodes(
        G, pos, nodelist=single_dep, ax=ax,
        node_color="white", node_size=18,
        alpha=0.55, linewidths=0,
    )
    # multi-dep (3+): slightly larger, outlined
    if multi_dep:
        nx.draw_networkx_nodes(
            G, pos, nodelist=multi_dep, ax=ax,
            node_color="white", node_size=80,
            alpha=0.85, linewidths=0.8,
            edgecolors="#FFFFFF",
        )

    # --- Core package nodes — with glow rings ---
    for pkg in core_nodes:
        col   = CORE_COLOR[pkg]
        n_dep = dep_counts[pkg]
        sz    = 700 + n_dep * 22   # scale by importance
        p     = np.array([pos[pkg]])
        # outer glow ring
        ax.scatter(*p.T, s=sz * 2.8, color=col, alpha=0.12, linewidths=0, zorder=4)
        ax.scatter(*p.T, s=sz * 1.5, color=col, alpha=0.20, linewidths=0, zorder=4)
        # core node
        ax.scatter(*p.T, s=sz, color=col, alpha=1.0, linewidths=1.5,
                   edgecolors="white", zorder=5)

    # --- Core package labels ---
    label_kw = dict(fontsize=11, fontweight="bold", ha="center", va="center",
                    color="white", zorder=6)
    for pkg in core_nodes:
        x, y = pos[pkg]
        n_dep = dep_counts[pkg]
        label = f"{pkg}\n({n_dep} dependents)"
        # nudge label above/below node to avoid overlap
        offset = 0.55 if y >= 0 else -0.55
        txt = ax.text(x, y + offset, label, fontsize=10, fontweight="bold",
                      ha="center", va="center", color="white", zorder=7,
                      linespacing=1.4)
        txt.set_path_effects([
            pe.withStroke(linewidth=3, foreground=BG)
        ])

    # --- Multi-dep source labels (notable crates) ---
    notable = {"soroban-cli", "soroban-rpc", "zephyr-sdk",
               "soroban-sdk", "soroban-env-host"}
    for n in multi_dep:
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
    handles.append(mpatches.Patch(color="white", alpha=0.55, label="Dependent crate (1–2 deps)"))
    handles.append(mpatches.Patch(color="white", alpha=0.85, label="Dependent crate (3+ deps)"))
    leg = ax.legend(
        handles=handles, loc="lower right", fontsize=9,
        facecolor="#1B2E42", edgecolor="#3A5068", labelcolor="white",
        title="Core Packages (reverse-dep count)", title_fontsize=9,
        framealpha=0.85, borderpad=0.9,
    )
    leg.get_title().set_color("white")

    # --- Title & annotation ---
    ax.set_title(
        "Soroban Ecosystem — Package Dependency Network\n"
        "149 crates.io edges · 109 dependent crates · 5 core packages",
        fontsize=14, fontweight="bold", color="white", pad=16,
    )
    fig.text(0.02, 0.02,
             "PG Atlas · SCF Q2 2026 · A9 Criticality Signal",
             fontsize=8, color="#6A90B0")

    fig.tight_layout()
    path = os.path.join(OUT_DIR, "net1_soroban_dependency_hub.png")
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  [✓] {path}")


# ---------------------------------------------------------------------------
# Network 2 — Contributor-Repo Bipartite (dark background, two-column layout)
#
# Redesign rationale:
#   - True bipartite two-column layout: repos left, contributors right.
#     Repos sorted pass-first then by contributor count; contributors
#     sorted cross-repo-first then by total commits.
#   - Bezier curve edges (S-curves between columns) coloured by commit
#     share intensity so the pony-risk signal is immediately visible:
#       gold ≥70% (dominant pony), orange 40-70%, teal 20-40%, dim <20%
#   - Dark navy background consistent with net1.
#   - Repo node size scales with number of linked contributors.
#   - Cross-repo keystone contributors shown as gold stars.
# ---------------------------------------------------------------------------
def net2_contributor_bipartite():
    rows = list(csv.DictReader(open(CONTRIB_CSV)))

    BG = "#0D1B2A"   # same dark navy as net1

    # --- Build contributor → repos map (no bots) ---
    contrib_repos_map = defaultdict(set)
    for r in rows:
        if r["contributor_login"] not in BOT_NAMES:
            contrib_repos_map[r["contributor_login"]].add(r["repo_full_name"])
    cross_repo_contribs = {c for c, reps in contrib_repos_map.items() if len(reps) > 1}

    # --- Filter edges: ≥15% share OR cross-repo contributor ---
    kept_edges = []
    for r in rows:
        login = r["contributor_login"]
        if login in BOT_NAMES:
            continue
        share = float(r["commit_share_pct"])
        if share >= 15 or login in cross_repo_contribs:
            kept_edges.append({
                "repo":        r["repo_full_name"],
                "contributor": login,
                "share":       share,
                "commits":     int(r["commits_90d"]),
            })

    repo_contrib_count   = Counter(e["repo"] for e in kept_edges)
    contrib_total_commits = defaultdict(int)
    for e in kept_edges:
        contrib_total_commits[e["contributor"]] += e["commits"]

    all_repos    = sorted(set(e["repo"]        for e in kept_edges))
    all_contribs = sorted(set(e["contributor"] for e in kept_edges))

    # Sort: pass repos first → then by contributor count desc
    sorted_repos = sorted(
        all_repos,
        key=lambda r: (r not in GATE_PASS_REPOS, -repo_contrib_count[r]),
    )
    # Sort: cross-repo first → then by total commits desc
    sorted_contribs = sorted(
        all_contribs,
        key=lambda c: (c not in cross_repo_contribs, -contrib_total_commits[c]),
    )

    n_r = len(sorted_repos)
    n_c = len(sorted_contribs)

    # --- Two-column positions ---
    X_REPO    = 0.0
    X_CONTRIB = 1.0
    repo_pos    = {r: (X_REPO,    0.98 - i * (0.96 / max(n_r - 1, 1))) for i, r in enumerate(sorted_repos)}
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
            return "#FFD700", max(1.2, share / 22), 0.88   # gold — dominant pony
        elif share >= 40:
            return "#FF8C42", max(0.9, share / 28), 0.78   # orange — high
        elif share >= 20:
            return "#5BC8AF", max(0.7, share / 35), 0.65   # teal — moderate
        else:
            return "#2A4A6A", 0.5, 0.40                    # dim — minor

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
        p     = repo_pos[r]
        is_p  = r in GATE_PASS_REPOS
        col   = "#00C8D4" if is_p else "#FF6B47"
        sz    = 90 + repo_contrib_count[r] * 38
        if is_p:
            ax.scatter(*p, s=sz * 2.6, color=col, alpha=0.14, linewidths=0, zorder=3)
            ax.scatter(*p, s=sz, color=col, alpha=1.0, linewidths=1.5,
                       edgecolors="white", zorder=5)
        else:
            ax.scatter(*p, s=sz, color=col, alpha=0.82, linewidths=0.6,
                       edgecolors="#FFFFFF33", zorder=5)

    # --- Contributor nodes ---
    for c in sorted_contribs:
        p      = contrib_pos[c]
        is_key = c in cross_repo_contribs
        if is_key:
            ax.scatter(*p, s=220, color="#F2B134", alpha=1.0, linewidths=1.2,
                       edgecolors="white", zorder=6, marker="*")
        else:
            ax.scatter(*p, s=48, color="#6A8FAF", alpha=0.72, linewidths=0.3,
                       edgecolors="#6A8FAF", zorder=5, marker="D")

    # --- Repo labels (right-aligned, left of column) ---
    for r in sorted_repos:
        p     = repo_pos[r]
        is_p  = r in GATE_PASS_REPOS
        short = r.split("/")[-1]
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
        if e["repo"] in GATE_PASS_REPOS and e["share"] >= 20
    }
    label_set = cross_repo_contribs | pass_repo_contributors

    for c in sorted_contribs:
        if c in label_set:
            p      = contrib_pos[c]
            is_key = c in cross_repo_contribs
            txt = ax.text(p[0] + 0.028, p[1], f"@{c}",
                          fontsize=7.0 if is_key else 6.2,
                          fontweight="bold" if is_key else "normal",
                          ha="left", va="center",
                          color="#F2B134" if is_key else "#A0C8E0", zorder=7)
            txt.set_path_effects([pe.withStroke(linewidth=2.0, foreground=BG)])

    # --- Column headers ---
    for x, label, ha in [
        (X_REPO - 0.04, "◀  REPOSITORIES", "right"),
        (X_CONTRIB + 0.04, "CONTRIBUTORS  ▶", "left"),
    ]:
        ax.text(x, 1.06, label, fontsize=9.5, fontweight="bold",
                ha=ha, va="bottom", color="#6AAAC8", alpha=0.85)

    # --- Legend ---
    legend_elements = [
        mpatches.Patch(color="#00C8D4", label=f"Gate PASS repo ({len([r for r in sorted_repos if r in GATE_PASS_REPOS])})"),
        mpatches.Patch(color="#FF6B47", label=f"Gate FAIL repo ({len([r for r in sorted_repos if r not in GATE_PASS_REPOS])})"),
        plt.Line2D([0], [0], marker="*", color="w", markerfacecolor="#F2B134",
                   markersize=12, label=f"Cross-repo keystone contributor ({len(cross_repo_contribs)})"),
        plt.Line2D([0], [0], marker="D", color="w", markerfacecolor="#6A8FAF",
                   markersize=7, label="Single-repo contributor"),
        plt.Line2D([0], [0], color="#FFD700", linewidth=3.0, label="≥ 70% commit share  (pony-dominant)"),
        plt.Line2D([0], [0], color="#FF8C42", linewidth=2.2, label="40 – 70%  (high concentration)"),
        plt.Line2D([0], [0], color="#5BC8AF", linewidth=1.6, label="20 – 40%  (moderate)"),
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
        "Contributor – Repo Bipartite Network  ·  SCF Q2 2026\n"
        f"{n_r} repos  ·  {n_c} contributors  ·  "
        f"{len(cross_repo_contribs)} cross-repo keystones  ·  "
        "edge colour = commit concentration",
        fontsize=13, fontweight="bold", color="white", pad=16,
    )
    fig.text(0.02, 0.005, "PG Atlas · A7 Git Log + A9 Pony Factor Signal",
             fontsize=8, color="#6A90B0")

    path = os.path.join(OUT_DIR, "net2_contributor_repo_bipartite.png")
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"  [✓] {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("PG Atlas Network Visualization Generator")
    print(f"Output: {OUT_DIR}/")
    print()
    print("Building networks...")
    net1_dependency_hubs()
    net2_contributor_bipartite()
    print()
    print("Done — 2 network figures saved.")
