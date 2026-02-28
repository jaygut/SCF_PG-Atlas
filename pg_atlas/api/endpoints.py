"""
pg_atlas/api/endpoints.py — FastAPI analytics API for PG Atlas metrics.

Provides RESTful endpoints for the Layer 1 Metric Gate and all PG Atlas scores.

Note: This is a stub designed for integration with Alex Olieman's D5 PostgreSQL
schema. The graph_builder dependency will be replaced with a db-backed builder
once A2 schema is locked.

Endpoint summary:
    GET  /api/v1/health                  — Liveness probe.
    GET  /api/v1/gate/{project_id}       — Metric gate result for one project.
    GET  /api/v1/scores/criticality      — All criticality scores sorted desc.
    GET  /api/v1/maintenance-debt        — MDS watch list + summary.
    GET  /api/v1/keystone-contributors   — KCI results + summary.
    GET  /api/v1/funding-efficiency      — FER results + underfunded count.
    GET  /api/v1/snapshots/latest        — Most recent EcosystemSnapshot.
    POST /api/v1/snapshots               — Generate and return a new snapshot.

Author: Jay Gutierrez, PhD | SCF #41
"""

import logging
from dataclasses import asdict
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── Optional FastAPI / Pydantic dependency ─────────────────────────────────────
try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    HAS_FASTAPI = True
except ImportError:
    FastAPI = None
    HTTPException = None
    BaseModel = object
    HAS_FASTAPI = False


# ── Request / Response models (Pydantic if available, plain class otherwise) ───

if HAS_FASTAPI:
    class SnapshotRequest(BaseModel):
        """Request body for POST /snapshots."""
        round_id: Optional[str] = None
        output_dir: Optional[str] = "04_implementation/snapshots"

    class HealthResponse(BaseModel):
        """Health check response."""
        status: str
        version: str

else:
    class SnapshotRequest:  # type: ignore[no-redef]
        """Placeholder when FastAPI is not installed."""
        def __init__(self, round_id=None, output_dir=None):
            self.round_id = round_id
            self.output_dir = output_dir

    class HealthResponse:  # type: ignore[no-redef]
        """Placeholder when FastAPI is not installed."""
        pass


def create_app(graph_builder_fn: Optional[Callable] = None) -> "FastAPI":
    """
    Create and return the PG Atlas FastAPI application.

    The graph_builder_fn is called with no arguments and must return a
    NetworkX DiGraph ready for active_subgraph_projection. This design
    allows injection of either synthetic data (tests) or real PostgreSQL
    data (production) without changing the endpoint logic.

    Args:
        graph_builder_fn: Callable that returns a NetworkX DiGraph.
                          If None, a synthetic graph is built on each request.

    Returns:
        Configured FastAPI application instance.

    Raises:
        ImportError: If fastapi or pydantic are not installed.
    """
    if not HAS_FASTAPI:
        raise ImportError(
            "fastapi and pydantic are required: pip install fastapi pydantic"
        )

    app = FastAPI(
        title="PG Atlas API",
        version="0.1.0",
        description=(
            "Layer 1 Metric Gate and analytics endpoints for the Stellar Community Fund "
            "Public Goods Atlas. Built on a NetworkX graph derived from dependency graphs, "
            "contributor history, and funding data."
        ),
    )

    # ── Helper: build graph and run pipeline ──────────────────────────────────
    def _build_pipeline_results():
        """
        Run the full PG Atlas pipeline and return all metric results.

        Returns a dict with keys: G_active, criticality_scores, pony_results,
        adoption_scores, mds_entries, kci_results, gate_results, fer_results.
        """
        import networkx as nx

        from pg_atlas.config import DEFAULT_CONFIG
        from pg_atlas.graph.active_subgraph import active_subgraph_projection
        from pg_atlas.metrics.criticality import compute_criticality_scores
        from pg_atlas.metrics.adoption import compute_adoption_scores
        from pg_atlas.metrics.pony_factor import compute_pony_factors
        from pg_atlas.metrics.maintenance_debt import compute_maintenance_debt_surface
        from pg_atlas.metrics.keystone_contributor import compute_keystone_contributors
        from pg_atlas.metrics.gate import evaluate_all_projects, gate_summary
        from pg_atlas.metrics.funding_efficiency import compute_funding_efficiency, fer_summary

        import pandas as pd

        # Build graph
        if graph_builder_fn is not None:
            G = graph_builder_fn()
        else:
            # Import the synthetic graph builder from tests/conftest as fallback
            try:
                from pg_atlas.graph.builder import build_graph_from_csv
                import os
                base = "01_data/processed"
                G = build_graph_from_csv(
                    seed_list_path=os.path.join(base, "A5_pg_candidate_seed_list.csv"),
                    orgs_path=os.path.join(base, "A6_github_orgs_seed.csv"),
                    repos_path=os.path.join(base, "A7_submission_github_repos.csv"),
                )
            except Exception:
                G = nx.DiGraph()

        G_active, _ = active_subgraph_projection(G, DEFAULT_CONFIG)
        criticality_scores = compute_criticality_scores(G_active)
        pony_results = compute_pony_factors(G_active, DEFAULT_CONFIG)
        _, adoption_scores = compute_adoption_scores(G_active)
        mds_entries = compute_maintenance_debt_surface(
            G_active, criticality_scores, pony_results, DEFAULT_CONFIG
        )
        kci_results = compute_keystone_contributors(
            G_active, criticality_scores, pony_results
        )

        # Build df_scores for gate evaluation
        from pg_atlas.metrics.criticality import compute_percentile_ranks
        crit_pcts = compute_percentile_ranks(criticality_scores)
        rows = []
        for node, data in G_active.nodes(data=True):
            if data.get("node_type") != "Repo":
                continue
            pony = pony_results.get(node)
            rows.append({
                "project": node,
                "criticality_raw": criticality_scores.get(node, 0),
                "criticality_pct": crit_pcts.get(node, 0.0),
                "hhi": pony.hhi if pony else 0.0,
                "top_contributor": pony.top_contributor if pony else "unknown",
                "top_contributor_share": pony.top_contributor_share if pony else 0.0,
                "adoption_score": adoption_scores.get(node, 0.0),
            })

        df_scores = pd.DataFrame(rows) if rows else pd.DataFrame()
        gate_results = evaluate_all_projects(df_scores, DEFAULT_CONFIG) if not df_scores.empty else []

        # FER: requires project-level data from graph attributes
        fer_results = []
        project_crit: dict[str, float] = {}
        for node, data in G_active.nodes(data=True):
            if data.get("node_type") != "Repo":
                continue
            proj = data.get("project")
            if proj:
                project_crit[proj] = project_crit.get(proj, 0.0) + criticality_scores.get(node, 0)

        return {
            "G_active": G_active,
            "criticality_scores": criticality_scores,
            "crit_pcts": crit_pcts,
            "pony_results": pony_results,
            "adoption_scores": adoption_scores,
            "mds_entries": mds_entries,
            "kci_results": kci_results,
            "gate_results": gate_results,
            "fer_results": fer_results,
        }

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
    async def health() -> dict:
        """Liveness probe — returns service status and version."""
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/v1/gate/{project_id}", tags=["gate"])
    async def get_gate_result(project_id: str) -> dict:
        """
        Return the Metric Gate evaluation for a single project.

        Args:
            project_id: Project name or repo node ID.

        Returns:
            MetricGateResult as JSON dict.

        Raises:
            404: If project_id not found in the active subgraph.
        """
        pipeline = _build_pipeline_results()
        gate_results = pipeline["gate_results"]

        matching = [r for r in gate_results if r.project == project_id]
        if not matching:
            raise HTTPException(
                status_code=404,
                detail=f"Project '{project_id}' not found in the active subgraph.",
            )

        result = matching[0]
        return {
            "project": result.project,
            "passed": result.passed,
            "signals_passed": result.signals_passed,
            "signals_required": result.signals_required,
            "borderline": result.borderline,
            "gate_explanation": result.gate_explanation,
            "criticality": {
                "passed": result.criticality.passed,
                "raw_value": result.criticality.raw_value,
                "percentile": result.criticality.percentile,
                "threshold_used": result.criticality.threshold_used,
                "narrative": result.criticality.narrative,
            },
            "pony_factor": {
                "passed": result.pony_factor.passed,
                "raw_value": result.pony_factor.raw_value,
                "threshold_used": result.pony_factor.threshold_used,
                "narrative": result.pony_factor.narrative,
            },
            "adoption": {
                "passed": result.adoption.passed,
                "raw_value": result.adoption.raw_value,
                "percentile": result.adoption.percentile,
                "threshold_used": result.adoption.threshold_used,
                "narrative": result.adoption.narrative,
            },
            "thresholds_snapshot": result.thresholds_snapshot,
        }

    @app.get("/api/v1/scores/criticality", tags=["metrics"])
    async def get_criticality_scores() -> dict:
        """
        Return all criticality scores for active repos, sorted by score desc.

        Returns:
            {"results": [{node, score, percentile}...], "total": N}
        """
        pipeline = _build_pipeline_results()
        criticality_scores = pipeline["criticality_scores"]
        crit_pcts = pipeline["crit_pcts"]

        sorted_scores = sorted(
            criticality_scores.items(), key=lambda x: x[1], reverse=True
        )
        results = [
            {
                "node": node,
                "score": score,
                "percentile": round(crit_pcts.get(node, 0.0), 1),
            }
            for node, score in sorted_scores
        ]
        return {"results": results, "total": len(results)}

    @app.get("/api/v1/maintenance-debt", tags=["metrics"])
    async def get_maintenance_debt() -> dict:
        """
        Return the Maintenance Debt Surface watch list.

        Returns:
            {"surface": [MaintenanceDebtEntry as dict...], "summary": {...}}
        """
        from pg_atlas.metrics.maintenance_debt import mds_summary

        pipeline = _build_pipeline_results()
        mds_entries = pipeline["mds_entries"]

        surface = [
            {
                "project": e.project,
                "criticality_percentile": e.criticality_percentile,
                "hhi": e.hhi,
                "hhi_tier": e.hhi_tier,
                "commit_trend": e.commit_trend,
                "days_since_last_commit": e.days_since_last_commit,
                "transitive_dependents": e.transitive_dependents,
                "top_contributor": e.top_contributor,
                "top_contributor_share": e.top_contributor_share,
                "risk_score": e.risk_score,
                "urgency_narrative": e.urgency_narrative,
            }
            for e in mds_entries
        ]
        summary = mds_summary(mds_entries)
        return {"surface": surface, "summary": summary}

    @app.get("/api/v1/keystone-contributors", tags=["metrics"])
    async def get_keystone_contributors() -> dict:
        """
        Return Keystone Contributor Index results.

        Returns:
            {"contributors": [...], "summary": {...}}
        """
        from pg_atlas.metrics.keystone_contributor import kci_summary

        pipeline = _build_pipeline_results()
        kci_results = pipeline["kci_results"]

        contributors = [
            {
                "contributor": r.contributor,
                "kci_score": r.kci_score,
                "kci_percentile": r.kci_percentile,
                "dominant_repos": r.dominant_repos,
                "total_dominant_repos": r.total_dominant_repos,
                "at_risk_downstream": r.at_risk_downstream,
                "risk_narrative": r.risk_narrative,
            }
            for r in kci_results
        ]
        summary = kci_summary(kci_results)
        return {"contributors": contributors, "summary": summary}

    @app.get("/api/v1/funding-efficiency", tags=["metrics"])
    async def get_funding_efficiency() -> dict:
        """
        Return Funding Efficiency Ratio results.

        Returns:
            {"results": [...], "underfunded_count": N}
        """
        pipeline = _build_pipeline_results()
        fer_results = pipeline["fer_results"]

        underfunded_count = sum(
            1 for r in fer_results
            if getattr(r, "fer_tier", "") in ("critically_underfunded", "underfunded")
        )

        results_out = [
            {
                "project": r.project,
                "fer": getattr(r, "fer", None),
                "fer_tier": getattr(r, "fer_tier", "unknown"),
                "criticality_pct": getattr(r, "criticality_pct", 0.0),
                "funding_pct": getattr(r, "funding_pct", 0.0),
                "narrative": getattr(r, "narrative", ""),
            }
            for r in fer_results
        ]
        return {"results": results_out, "underfunded_count": underfunded_count}

    @app.get("/api/v1/snapshots/latest", tags=["snapshots"])
    async def get_latest_snapshot() -> dict:
        """
        Return the most recent EcosystemSnapshot as JSON.

        Generates a fresh snapshot on each call (production would cache/persist).

        Returns:
            EcosystemSnapshot as JSON dict.
        """
        from pg_atlas.reports.governance_report import generate_governance_report
        from pg_atlas.metrics.kcore import kcore_analysis
        from pg_atlas.metrics.bridges import find_bridge_edges
        from pg_atlas.config import DEFAULT_CONFIG
        from dataclasses import asdict

        pipeline = _build_pipeline_results()

        try:
            core_numbers = kcore_analysis(pipeline["G_active"])
        except Exception:
            core_numbers = {}

        try:
            bridges = find_bridge_edges(pipeline["G_active"])
        except Exception:
            bridges = []

        snapshot = generate_governance_report(
            G_active=pipeline["G_active"],
            gate_results=pipeline["gate_results"],
            mds_entries=pipeline["mds_entries"],
            kci_results=pipeline["kci_results"],
            fer_results=pipeline["fer_results"],
            pony_results=pipeline["pony_results"],
            criticality_scores=pipeline["criticality_scores"],
            core_numbers=core_numbers,
            bridges=bridges,
            config=DEFAULT_CONFIG,
            output_dir="/tmp/pg_atlas_snapshots",
        )
        return asdict(snapshot)

    @app.post("/api/v1/snapshots", tags=["snapshots"])
    async def create_snapshot(request: SnapshotRequest) -> dict:
        """
        Generate a new EcosystemSnapshot and return it as JSON.

        Args:
            request: SnapshotRequest with optional round_id and output_dir.

        Returns:
            EcosystemSnapshot as JSON dict.
        """
        from pg_atlas.reports.governance_report import generate_governance_report
        from pg_atlas.metrics.kcore import kcore_analysis
        from pg_atlas.metrics.bridges import find_bridge_edges
        from pg_atlas.config import DEFAULT_CONFIG
        from dataclasses import asdict

        pipeline = _build_pipeline_results()

        try:
            core_numbers = kcore_analysis(pipeline["G_active"])
        except Exception:
            core_numbers = {}

        try:
            bridges = find_bridge_edges(pipeline["G_active"])
        except Exception:
            bridges = []

        output_dir = getattr(request, "output_dir", None) or "04_implementation/snapshots"
        round_id = getattr(request, "round_id", None)

        snapshot = generate_governance_report(
            G_active=pipeline["G_active"],
            gate_results=pipeline["gate_results"],
            mds_entries=pipeline["mds_entries"],
            kci_results=pipeline["kci_results"],
            fer_results=pipeline["fer_results"],
            pony_results=pipeline["pony_results"],
            criticality_scores=pipeline["criticality_scores"],
            core_numbers=core_numbers,
            bridges=bridges,
            config=DEFAULT_CONFIG,
            scf_round=round_id,
            output_dir=output_dir,
        )
        return asdict(snapshot)

    logger.info("PG Atlas FastAPI application created with 8 endpoints.")
    return app
