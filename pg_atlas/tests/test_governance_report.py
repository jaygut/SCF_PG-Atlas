"""
Tests for pg_atlas/reports/governance_report.py

Validates EcosystemSnapshot generation, active-project counting,
criticality formatting, and top-10-critical-package filtering.

All tests are offline — no API calls, no real CSVs. Uses tmp_path for output.
"""

import networkx as nx
import pytest

from pg_atlas.reports.governance_report import (
    export_report_markdown,
    generate_governance_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_g_active(project_nodes=0, repo_nodes=0):
    """Build a bare DiGraph with Project and Repo nodes (no ``active`` attr on Projects)."""
    G = nx.DiGraph()
    for i in range(project_nodes):
        G.add_node(f"project_{i}", node_type="Project")
    for i in range(repo_nodes):
        G.add_node(f"repo_{i}", node_type="Repo")
    return G


def _call_report(g_active, criticality_scores=None, gate_results=None, tmp_path=None, **kwargs):
    """Wrap ``generate_governance_report()`` with sensible defaults for all params not under test."""
    return generate_governance_report(
        G_active=g_active,
        gate_results=gate_results or [],
        mds_entries=[],
        kci_results=[],
        fer_results=[],
        pony_results={},
        criticality_scores=criticality_scores or {},
        core_numbers={},
        bridges=[],
        scf_round="Test Round",
        output_dir=str(tmp_path) if tmp_path else "/tmp/pg_atlas_test",
        **kwargs,
    )


def _write_markdown(snapshot, tmp_path, gate_results=None):
    """Call ``export_report_markdown()`` and return (markdown_text, output_path)."""
    output_path = str(tmp_path / "report.md")
    md = export_report_markdown(
        snapshot=snapshot,
        gate_results=gate_results or [],
        mds_entries=[],
        kci_results=[],
        fer_results=[],
        output_path=output_path,
    )
    return md, output_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestActiveProjectCounting:

    def test_active_projects_counts_all_project_nodes(self, tmp_path):
        """3 Project nodes (no ``active`` attr), 0 Repo nodes -> total_active_projects == 3."""
        G = _minimal_g_active(project_nodes=3, repo_nodes=0)
        snapshot = _call_report(G, tmp_path=tmp_path)
        assert snapshot.total_active_projects == 3

    def test_active_projects_excludes_non_project_nodes(self, tmp_path):
        """1 Project node + 2 Repo nodes -> total_active_projects == 1."""
        G = _minimal_g_active(project_nodes=1, repo_nodes=2)
        snapshot = _call_report(G, tmp_path=tmp_path)
        assert snapshot.total_active_projects == 1


class TestMeanCriticalityFormatting:

    def test_mean_criticality_displays_two_decimal_places(self, tmp_path):
        """mean_criticality=0.03 must render as '0.03', not '0.0'."""
        G = _minimal_g_active(project_nodes=3)
        crit = {f"project_{i}": 0.03 for i in range(3)}
        snapshot = _call_report(G, criticality_scores=crit, tmp_path=tmp_path)

        md, _ = _write_markdown(snapshot, tmp_path)
        assert "| Mean Criticality | 0.03 |" in md
        assert "| Mean Criticality | 0.0 |" not in md

    def test_mean_criticality_zero_displays_correctly(self, tmp_path):
        """Empty criticality -> mean_criticality=0.0 must render as '0.00'."""
        G = _minimal_g_active(project_nodes=1)
        snapshot = _call_report(G, criticality_scores={}, tmp_path=tmp_path)

        md, _ = _write_markdown(snapshot, tmp_path)
        assert "| Mean Criticality | 0.00 |" in md


class TestTop10CriticalPackages:

    def test_top_10_critical_excludes_zero_criticality_nodes(self, tmp_path):
        """Only nodes with score > 0 should appear in top_10_critical_packages."""
        G = _minimal_g_active(project_nodes=4)
        crit = {
            "project_0": 5,
            "project_1": 3,
            "project_2": 0,
            "project_3": 0,
        }
        snapshot = _call_report(G, criticality_scores=crit, tmp_path=tmp_path)

        assert len(snapshot.top_10_critical_packages) == 2
        names = [p["name"] for p in snapshot.top_10_critical_packages]
        assert "project_2" not in names
        assert "project_3" not in names

    def test_top_10_critical_respects_ten_cap(self, tmp_path):
        """15 non-zero nodes -> list capped at 10, sorted descending."""
        G = _minimal_g_active(project_nodes=15)
        crit = {f"project_{i}": i + 1 for i in range(15)}
        snapshot = _call_report(G, criticality_scores=crit, tmp_path=tmp_path)

        top = snapshot.top_10_critical_packages
        assert len(top) == 10
        scores = [p["criticality"] for p in top]
        assert scores == sorted(scores, reverse=True)
