"""
pg_atlas/pipeline.py — Single-call pipeline orchestrator.

Provides run_full_pipeline() which executes the entire PG Atlas metric
computation sequence in the correct dependency order and returns a complete
EcosystemSnapshot with all intermediate results.

Usage:
    from pg_atlas.pipeline import run_full_pipeline
    result = run_full_pipeline()
    print(result.snapshot.north_star_answer)

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import networkx as nx
import pandas as pd

from pg_atlas.config import DEFAULT_CONFIG, PGAtlasConfig
from pg_atlas.graph.active_subgraph import active_subgraph_projection
from pg_atlas.graph.builder import build_graph_from_csv
from pg_atlas.metrics.adoption import compute_adoption_scores
from pg_atlas.metrics.bridges import find_bridge_edges
from pg_atlas.metrics.criticality import (
    compute_criticality_scores,
    compute_decay_criticality,
    compute_percentile_ranks,
)
from pg_atlas.metrics.funding_efficiency import compute_funding_efficiency
from pg_atlas.metrics.gate import evaluate_all_projects, gate_summary
from pg_atlas.metrics.kcore import kcore_analysis
from pg_atlas.metrics.keystone_contributor import compute_keystone_contributors
from pg_atlas.metrics.maintenance_debt import compute_maintenance_debt_surface
from pg_atlas.metrics.pony_factor import compute_pony_factors
from pg_atlas.reports.governance_report import (
    EcosystemSnapshot,
    export_report_markdown,
    generate_governance_report,
)

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """
    Complete output of a single PG Atlas pipeline run.

    Contains every intermediate result for inspection, plus the final
    EcosystemSnapshot for persistence and reporting.
    """

    # Input graph state
    G_full: nx.DiGraph
    G_active: nx.DiGraph
    dormant_nodes: set

    # Core metrics
    criticality_scores: dict[str, int]
    criticality_percentiles: dict[str, float]
    decay_criticality: dict[str, float]
    pony_results: dict
    adoption_df: pd.DataFrame
    adoption_scores: dict[str, float]
    kcore_numbers: dict[str, int]
    bridge_edges: list[tuple[str, str]]

    # Gate
    gate_results: list
    gate_summary_stats: dict

    # Strategic surfaces
    maintenance_debt_surface: list
    keystone_contributors: list
    funding_efficiency: list

    # Ingestion edge data (for visualization)
    contribution_edges: list = field(default_factory=list)
    dependency_edges: list = field(default_factory=list)

    # Final output
    snapshot: EcosystemSnapshot = field(default=None)

    # Generated figure paths (populated by viz module)
    figure_paths: dict = field(default_factory=dict)


def run_full_pipeline(
    seed_list_path: str | None = None,
    orgs_path: str | None = None,
    repos_path: str | None = None,
    config: PGAtlasConfig = DEFAULT_CONFIG,
    scf_round: str | None = None,
    output_dir: str = "04_implementation/snapshots",
    report_path: str | None = None,
    real_data: bool = False,
    ingest_config: "IngestionConfig | None" = None,
    generate_figures: bool = True,
    figures_dir: str | None = None,
) -> PipelineResult:
    """
    Execute the complete PG Atlas pipeline in one call.

    Dependency order:
        0. (Optional) Real data ingestion
        1. Build graph from CSV
        1b. (Optional) Enrich graph with ingestion results
        2. Active subgraph projection (A6)
        3. Criticality scores (A9)
        4. Pony factor + HHI + Shannon (A9)
        5. Adoption signals (A10)
        6. K-core decomposition
        7. Bridge edge detection
        8. Temporal decay criticality
        9. Metric Gate evaluation
        10. Maintenance Debt Surface
        11. Keystone Contributor Index
        12. Funding Efficiency Ratio
        13. Governance Report (EcosystemSnapshot)
        14. Markdown export (optional)

    Args:
        seed_list_path: Path to A5 CSV (defaults to 01_data/processed/).
        orgs_path:      Path to A6 CSV (defaults to 01_data/processed/).
        repos_path:     Path to A7 CSV (defaults to 01_data/processed/).
        config:         PGAtlasConfig with all thresholds.
        scf_round:      SCF round label (e.g. "SCF Q2 2026").
        output_dir:     Directory for JSON snapshot output.
        report_path:    If provided, exports Markdown report to this path.
        real_data:      If True, run real API ingestion before pipeline.
        ingest_config:  IngestionConfig for real_data mode (created from
                        environment defaults if not provided).

    Returns:
        PipelineResult with every intermediate and final result.
    """
    logger.info("PG Atlas pipeline starting.")

    # ── 0. Real data ingestion (optional) ─────────────────────────────────────
    ingestion_result = None
    if real_data:
        from pg_atlas.ingestion.orchestrator import run_full_ingestion, IngestionConfig
        if ingest_config is None:
            ingest_config = IngestionConfig()
        logger.info("Phase 0/14: Running real data ingestion...")
        ingestion_result = run_full_ingestion(ingest_config)
        logger.info(
            "Phase 0/14: Ingestion complete — %d contrib edges, %d dep edges, %d adoption entries.",
            len(ingestion_result.contribution_edges),
            len(ingestion_result.dependency_edges),
            len(ingestion_result.adoption_data),
        )

    # ── 0b. Populate contribution/dependency edge lists ──────────────────────
    # Also load adoption_data and activity_data for cached-CSV enrichment path.
    _adoption_data_csv: dict = {}
    _activity_data_csv: dict = {}

    if real_data and ingestion_result is not None:
        contrib_edges_raw = ingestion_result.contribution_edges
        dep_edges_raw = ingestion_result.dependency_edges
    else:
        import csv as _csv
        import json as _json
        import os as _os

        from pg_atlas.ingestion.orchestrator import (
            _load_contribution_edges_from_csv,
            _load_dep_edges_from_csv,
        )

        _repo_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        _contrib_csv = _os.path.join(_repo_root, "01_data", "real", "contributor_stats.csv")
        _dep_csv = _os.path.join(_repo_root, "01_data", "real", "dependency_edges.csv")
        _adopt_csv = _os.path.join(_repo_root, "01_data", "real", "adoption_signals.csv")
        _a7_ckpt = _os.path.join(_repo_root, "01_data", "real", "checkpoints", "a7_progress.json")

        contrib_edges_raw = _load_contribution_edges_from_csv(_contrib_csv) if _os.path.isfile(_contrib_csv) else []
        dep_edges_raw = _load_dep_edges_from_csv(_dep_csv) if _os.path.isfile(_dep_csv) else []

        # adoption_signals.csv → dict[repo_url, dict]
        if _os.path.isfile(_adopt_csv):
            with open(_adopt_csv, newline="") as _f:
                for _row in _csv.DictReader(_f):
                    _name = _row.get("repo_full_name", "")
                    if _name:
                        _url = (
                            _name if _name.startswith("http")
                            else f"https://github.com/{_name}"
                        )
                        _adoption_data_csv[_url] = {
                            "monthly_downloads": int(_row.get("monthly_downloads") or 0),
                            "github_stars": int(_row.get("github_stars") or 0),
                            "github_forks": int(_row.get("github_forks") or 0),
                        }

        # a7_progress.json → activity_cache dict[repo_url, dict]
        if _os.path.isfile(_a7_ckpt):
            try:
                with open(_a7_ckpt) as _f:
                    _activity_data_csv = _json.load(_f).get("activity_cache", {})
            except Exception:
                _activity_data_csv = {}

    # ── 1. Build graph ─────────────────────────────────────────────────────────
    G = build_graph_from_csv(seed_list_path, orgs_path, repos_path, config)
    logger.info("Phase 1/14: Graph built — %d nodes, %d edges.", G.number_of_nodes(), G.number_of_edges())

    # ── 1b. Enrich graph ───────────────────────────────────────────────────────
    # Two paths: (a) live ingestion result, (b) cached CSVs from a prior run.
    # Either way the graph gets contributor commit shares, dependency edges,
    # adoption signals, and activity metadata — enabling full metric computation
    # without re-calling any external APIs.
    if real_data and ingestion_result is not None:
        from pg_atlas.graph.builder import enrich_graph_with_ingestion
        G = enrich_graph_with_ingestion(
            G,
            dep_edges=ingestion_result.dependency_edges,
            contrib_edges=ingestion_result.contribution_edges,
            adoption_data=ingestion_result.adoption_data,
            activity_data=ingestion_result.activity_data,
        )
        logger.info(
            "Phase 1b/14: Graph enriched (live ingestion) — now %d nodes, %d edges.",
            G.number_of_nodes(),
            G.number_of_edges(),
        )
    elif contrib_edges_raw or dep_edges_raw:
        from pg_atlas.graph.builder import enrich_graph_with_ingestion
        G = enrich_graph_with_ingestion(
            G,
            dep_edges=dep_edges_raw,
            contrib_edges=contrib_edges_raw,
            adoption_data=_adoption_data_csv,
            activity_data=_activity_data_csv,
        )
        logger.info(
            "Phase 1b/14: Graph enriched (cached CSVs) — now %d nodes, %d edges. "
            "adoption=%d, activity=%d",
            G.number_of_nodes(),
            G.number_of_edges(),
            len(_adoption_data_csv),
            len(_activity_data_csv),
        )

    # ── 2. Active subgraph projection ──────────────────────────────────────────
    G_active, dormant = active_subgraph_projection(G, config)
    logger.info("Phase 2/14: Active subgraph — %d nodes, %d dormant.", G_active.number_of_nodes(), len(dormant))

    # ── 3. Criticality scores ──────────────────────────────────────────────────
    crit = compute_criticality_scores(G_active)
    crit_pcts = compute_percentile_ranks(crit)
    logger.info("Phase 3/14: Criticality — scored %d nodes.", len(crit))

    # ── 4. Pony factor ─────────────────────────────────────────────────────────
    pony = compute_pony_factors(G_active, config)
    logger.info("Phase 4/14: Pony factor — %d repos, %d flagged.", len(pony), sum(1 for r in pony.values() if r.pony_factor == 1))

    # ── 5. Adoption ────────────────────────────────────────────────────────────
    df_adopt, adopt_scores = compute_adoption_scores(G_active)
    logger.info("Phase 5/14: Adoption — scored %d nodes.", len(adopt_scores))

    # ── 6. K-core ──────────────────────────────────────────────────────────────
    G_und, kcores = kcore_analysis(G_active)
    logger.info("Phase 6/14: K-core — max core = %d.", max(kcores.values(), default=0))

    # ── 7. Bridge edges ────────────────────────────────────────────────────────
    bridges = find_bridge_edges(G_active)
    logger.info("Phase 7/14: Bridges — %d bridge edges found.", len(bridges))

    # ── 8. Decay criticality ──────────────────────────────────────────────────
    decay = compute_decay_criticality(G_active, crit, config)
    logger.info("Phase 8/14: Decay criticality computed for %d nodes.", len(decay))

    # ── 9. Metric Gate ─────────────────────────────────────────────────────────
    gate_rows = []
    for node in set(crit.keys()) & set(pony.keys()):
        gate_rows.append({
            "project": node,
            "criticality_raw": crit[node],
            "criticality_pct": crit_pcts.get(node, 0.0),
            "hhi": pony[node].hhi,
            "top_contributor": pony[node].top_contributor,
            "top_contributor_share": pony[node].top_contributor_share,
            "adoption_score": adopt_scores.get(node, 0.0),
        })
    df_gate = pd.DataFrame(gate_rows) if gate_rows else pd.DataFrame()
    gate_results = evaluate_all_projects(df_gate, config) if len(df_gate) > 0 else []
    gate_stats = gate_summary(gate_results)
    logger.info("Phase 9/14: Gate — %d passed, %d failed.", gate_stats.get("passed", 0), gate_stats.get("failed", 0))

    # ── 10. Maintenance Debt Surface ──────────────────────────────────────────
    mds = compute_maintenance_debt_surface(G_active, crit, pony, config)
    logger.info("Phase 10/14: MDS — %d repos on debt surface.", len(mds))

    # ── 11. Keystone Contributors ─────────────────────────────────────────────
    kci = compute_keystone_contributors(G_active, crit, pony)
    logger.info("Phase 11/14: KCI — %d keystone contributors found.", len(kci))

    # ── 12. Funding Efficiency ────────────────────────────────────────────────
    # Build a projects DataFrame from the graph's Project nodes
    project_data = []
    for node, data in G_active.nodes(data=True):
        if data.get("node_type") == "Project":
            project_data.append({
                "title": node,
                "total_awarded_usd": data.get("total_awarded_usd", data.get("funding", 0)),
            })
    df_projects = pd.DataFrame(project_data) if project_data else pd.DataFrame(columns=["title", "total_awarded_usd"])
    fer = compute_funding_efficiency(G_active, crit, pony, df_projects, config)
    logger.info("Phase 12/14: FER — %d projects evaluated.", len(fer))

    # ── 13. Governance Report ─────────────────────────────────────────────────
    snapshot = generate_governance_report(
        G_active=G_active,
        gate_results=gate_results,
        mds_entries=mds,
        kci_results=kci,
        fer_results=fer,
        pony_results=pony,
        criticality_scores=crit,
        core_numbers=kcores,
        bridges=bridges,
        config=config,
        scf_round=scf_round,
        output_dir=output_dir,
    )
    logger.info("Phase 13/14: EcosystemSnapshot generated.")

    # ── 14. Markdown export (optional) ────────────────────────────────────────
    if report_path:
        export_report_markdown(
            snapshot=snapshot,
            gate_results=gate_results,
            mds_entries=mds,
            kci_results=kci,
            fer_results=fer,
            output_path=report_path,
        )
        logger.info("Phase 14/15: Markdown report exported to %s.", report_path)
    else:
        logger.info("Phase 14/15: Markdown export skipped (no report_path).")

    # ── 15. Figure generation ─────────────────────────────────────────────────
    # Build a temporary PipelineResult so generate_all_figures can read it
    result_temp = PipelineResult(
        G_full=G,
        G_active=G_active,
        dormant_nodes=dormant,
        criticality_scores=crit,
        criticality_percentiles=crit_pcts,
        decay_criticality=decay,
        pony_results=pony,
        adoption_df=df_adopt,
        adoption_scores=adopt_scores,
        kcore_numbers=kcores,
        bridge_edges=bridges,
        gate_results=gate_results,
        gate_summary_stats=gate_stats,
        maintenance_debt_surface=mds,
        keystone_contributors=kci,
        funding_efficiency=fer,
        contribution_edges=contrib_edges_raw,
        dependency_edges=dep_edges_raw,
        snapshot=snapshot,
    )

    figure_paths_out: dict = {}
    if generate_figures:
        try:
            from pg_atlas.viz.figures import generate_all_figures
            # Auto-name figure dir as sibling to snapshot dir
            _snap_date = snapshot.snapshot_date if snapshot else datetime.now().strftime("%Y-%m-%d")
            _slug = (scf_round or "").replace(" ", "_").replace("/", "-").lower()
            _auto_fig_dir = os.path.join(
                os.path.dirname(os.path.abspath(output_dir)),
                "figures",
                f"{_snap_date}_{_slug}" if _slug else _snap_date,
            )
            _fig_dir = figures_dir or _auto_fig_dir
            figure_paths_out = generate_all_figures(result_temp, _fig_dir)
            logger.info("Phase 15/15: Generated %d figures to %s", len(figure_paths_out), _fig_dir)
        except Exception as _e:
            logger.warning("Phase 15/15: Figure generation failed: %s", _e)
            figure_paths_out = {}
    else:
        logger.info("Phase 15/15: Figure generation skipped (generate_figures=False).")

    # ── Re-export report with figure references if figures were generated ─────
    if report_path and figure_paths_out:
        export_report_markdown(
            snapshot=snapshot,
            gate_results=gate_results,
            mds_entries=mds,
            kci_results=kci,
            fer_results=fer,
            output_path=report_path,
            figure_paths=figure_paths_out,
        )
        logger.info("Phase 15/15: Report re-exported with figure references.")

    logger.info("PG Atlas pipeline complete.")

    result_temp.figure_paths = figure_paths_out
    return result_temp
