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
from dataclasses import dataclass
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

    # Final output
    snapshot: EcosystemSnapshot


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

    # ── 1. Build graph ─────────────────────────────────────────────────────────
    G = build_graph_from_csv(seed_list_path, orgs_path, repos_path, config)
    logger.info("Phase 1/14: Graph built — %d nodes, %d edges.", G.number_of_nodes(), G.number_of_edges())

    # ── 1b. Enrich graph with ingestion results (if real_data) ────────────────
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
            "Phase 1b/14: Graph enriched — now %d nodes, %d edges.",
            G.number_of_nodes(),
            G.number_of_edges(),
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
        logger.info("Phase 14/14: Markdown report exported to %s.", report_path)
    else:
        logger.info("Phase 14/14: Markdown export skipped (no report_path).")

    logger.info("PG Atlas pipeline complete.")

    return PipelineResult(
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
        snapshot=snapshot,
    )
