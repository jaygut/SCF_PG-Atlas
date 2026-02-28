"""
pg_atlas/cli.py — Command-line interface for the PG Atlas pipeline.

Provides a single entry point that:
  1. Loads GITHUB_TOKEN from a .env file automatically
  2. Runs ingestion (A7 + deps.dev + crates.io + npm + PyPI)
  3. Runs metric computation (A6 → A9 → A10 → Gate → MDS → KCI → FER)
  4. Exports a governance report (Markdown + EcosystemSnapshot JSON)

Usage:
    python -m pg_atlas run             # full pipeline
    python -m pg_atlas ingest          # ingestion only
    python -m pg_atlas metrics         # metrics only (uses existing CSVs)
    python -m pg_atlas status          # show checkpoint/output state

All commands read GITHUB_TOKEN from .env in the repo root (or the path
specified by --env-file) before falling back to the environment variable.

Author: Jay Gutierrez, PhD | SCF #41 — Building the Backbone
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ── .env loader (stdlib only — no python-dotenv required) ────────────────────

def _load_dotenv(env_file: str | None = None) -> dict[str, str]:
    """Load key=value pairs from a .env file into the environment.

    Reads a dotenv-style file, strips comments and blank lines, and injects
    any KEY=VALUE pairs into os.environ (existing values are NOT overwritten).
    Returns the dict of values that were newly loaded.

    Args:
        env_file: Explicit path. If None, searches for .env starting from the
                  file's own directory up to the filesystem root.
    """
    if env_file is None:
        # Walk up from repo root (this file lives at pg_atlas/cli.py)
        start = Path(__file__).parent.parent
        for directory in [start, *start.parents]:
            candidate = directory / ".env"
            if candidate.is_file():
                env_file = str(candidate)
                break

    if not env_file or not Path(env_file).is_file():
        return {}

    loaded: dict[str, str] = {}
    with open(env_file, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes if present
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
                loaded[key] = value

    return loaded


# ── Logging setup ─────────────────────────────────────────────────────────────

def _setup_logging(level: str = "INFO") -> None:
    """Configure root logger with timestamps and coloured level names."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(level=numeric, format=fmt, datefmt=datefmt, stream=sys.stderr)
    # Silence noisy urllib3 / httplib debug output
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("urllib.request").setLevel(logging.WARNING)


logger = logging.getLogger("pg_atlas.cli")


# ── Subcommand: run (full pipeline) ──────────────────────────────────────────

def cmd_run(args: argparse.Namespace) -> int:
    """Full pipeline: ingestion → active subgraph → metrics → gate → report."""
    _load_dotenv(args.env_file)
    _setup_logging(args.log_level)

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.warning(
            "GITHUB_TOKEN not set. Unauthenticated GitHub rate limit is 60 req/hr. "
            "Set it in .env or pass --token."
        )

    from pg_atlas.ingestion.orchestrator import IngestionConfig
    from pg_atlas.pipeline import run_full_pipeline

    if args.fresh:
        _clear_checkpoints()

    ingest_cfg = IngestionConfig(
        github_token=token,
        since_days=args.since_days,
        git_max_workers=args.workers,
    )

    scf_round = args.scf_round or f"SCF {datetime.now(tz=timezone.utc).strftime('%b %Y')}"
    report_path = args.report_path or os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "04_implementation", "snapshots",
        f"report_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.md",
    )

    logger.info("=" * 60)
    logger.info("PG Atlas — Full Pipeline Run")
    logger.info("  SCF Round    : %s", scf_round)
    logger.info("  GitHub token : %s", "present" if token else "ABSENT")
    logger.info("  Since days   : %d", args.since_days)
    logger.info("  Workers      : %d", args.workers)
    logger.info("  Report path  : %s", report_path)
    logger.info("=" * 60)

    t0 = time.monotonic()
    result = run_full_pipeline(
        real_data=True,
        ingest_config=ingest_cfg,
        scf_round=scf_round,
        report_path=report_path,
    )
    elapsed = time.monotonic() - t0

    # ── Summary ───────────────────────────────────────────────────────────────
    snap = result.snapshot
    gate = result.gate_summary_stats

    print()
    print("=" * 60)
    print("  PG ATLAS — RUN COMPLETE")
    print("=" * 60)
    print(f"  Elapsed          : {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Active nodes     : {result.G_active.number_of_nodes()}")
    print(f"  Criticality nodes: {len(result.criticality_scores)}")
    print(f"  Pony factor repos: {len(result.pony_results)}")
    print(f"  Bridge edges     : {len(result.bridge_edges)}")
    print(f"  Gate passed      : {gate.get('passed', 0)}")
    print(f"  Gate failed      : {gate.get('failed', 0)}")
    print(f"  MDS entries      : {len(result.maintenance_debt_surface)}")
    print(f"  Keystone contribs: {len(result.keystone_contributors)}")
    print(f"  FER evaluations  : {len(result.funding_efficiency)}")
    print()
    print("  North Star Answer:")
    print(f"  {snap.north_star_answer}")
    print()
    print(f"  Report saved to  : {report_path}")
    print("=" * 60)

    return 0


# ── Subcommand: ingest ────────────────────────────────────────────────────────

def cmd_ingest(args: argparse.Namespace) -> int:
    """Run only the ingestion pipeline (A7 + deps + adoption)."""
    _load_dotenv(args.env_file)
    _setup_logging(args.log_level)

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.warning("GITHUB_TOKEN not set — unauthenticated (60 req/hr).")

    from pg_atlas.ingestion.orchestrator import IngestionConfig, run_full_ingestion

    if args.fresh:
        _clear_checkpoints()

    cfg = IngestionConfig(
        github_token=token,
        since_days=args.since_days,
        git_max_workers=args.workers,
    )

    t0 = time.monotonic()
    result = run_full_ingestion(cfg)
    elapsed = time.monotonic() - t0

    cov = result.coverage_report
    print()
    print("=" * 60)
    print("  INGESTION COMPLETE")
    print("=" * 60)
    print(f"  Elapsed              : {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Contribution edges   : {cov.get('total_contribution_edges', 0)}")
    print(f"  Activity data repos  : {cov.get('total_repos_with_activity', 0)}")
    print(f"  Dependency edges     : {cov.get('total_dependency_edges', 0)}")
    print(f"  Adoption entries     : {cov.get('total_adoption_entries', 0)}")
    print(f"  Errors               : {cov.get('total_errors', 0)}")
    print(f"  Output dir           : 01_data/real/")
    print("=" * 60)

    if result.errors:
        print("\n  Errors encountered:")
        for err in result.errors[:10]:
            print(f"    [{err.get('source', '?')}] {err.get('error', '?')}")
        if len(result.errors) > 10:
            print(f"    ... and {len(result.errors) - 10} more (see INGESTION_REPORT.md)")

    return 0


# ── Subcommand: metrics ───────────────────────────────────────────────────────

def cmd_metrics(args: argparse.Namespace) -> int:
    """Run metrics pipeline only — uses existing 01_data/real/ CSVs."""
    _load_dotenv(args.env_file)
    _setup_logging(args.log_level)

    from pg_atlas.pipeline import run_full_pipeline

    scf_round = args.scf_round or f"SCF {datetime.now(tz=timezone.utc).strftime('%b %Y')}"
    report_path = args.report_path or os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "04_implementation", "snapshots",
        f"report_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}.md",
    )

    logger.info("Running metrics pipeline (no ingestion)...")
    t0 = time.monotonic()
    result = run_full_pipeline(
        real_data=False,
        scf_round=scf_round,
        report_path=report_path,
    )
    elapsed = time.monotonic() - t0

    gate = result.gate_summary_stats
    snap = result.snapshot

    print()
    print("=" * 60)
    print("  METRICS PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Elapsed          : {elapsed:.1f}s")
    print(f"  Active nodes     : {result.G_active.number_of_nodes()}")
    print(f"  Gate passed      : {gate.get('passed', 0)}")
    print(f"  Gate failed      : {gate.get('failed', 0)}")
    print(f"  MDS entries      : {len(result.maintenance_debt_surface)}")
    print(f"  Keystone contribs: {len(result.keystone_contributors)}")
    print()
    print(f"  North Star: {snap.north_star_answer}")
    print(f"  Report    : {report_path}")
    print("=" * 60)
    return 0


# ── Subcommand: status ────────────────────────────────────────────────────────

def cmd_status(args: argparse.Namespace) -> int:
    """Show the current state of checkpoints and output files."""
    _load_dotenv(args.env_file)
    _setup_logging("WARNING")

    repo_root = Path(__file__).parent.parent
    real_dir = repo_root / "01_data" / "real"
    ckpt_dir = real_dir / "checkpoints"

    print("\nPG Atlas — Status Report")
    print("=" * 40)

    # Token
    token = args.token or os.environ.get("GITHUB_TOKEN")
    print(f"  GITHUB_TOKEN  : {'✓ present' if token else '✗ not set'}")

    # Output CSVs
    print("\n  Output files (01_data/real/):")
    for fname in ["contributor_stats.csv", "dependency_edges.csv",
                  "adoption_signals.csv", "INGESTION_REPORT.md"]:
        fpath = real_dir / fname
        if fpath.exists():
            size = fpath.stat().st_size
            mtime = datetime.fromtimestamp(fpath.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"    ✓ {fname:<30} {size:>8} bytes  ({mtime})")
        else:
            print(f"    ✗ {fname:<30} not found")

    # Checkpoints
    print("\n  Checkpoints (01_data/real/checkpoints/):")
    if ckpt_dir.exists():
        for f in sorted(ckpt_dir.glob("*.json")):
            import json
            try:
                with open(f) as fh:
                    data = json.load(fh)
                done_count = len(data.get("done", []))
                print(f"    ✓ {f.name:<35} {done_count:>4} items done")
            except Exception:
                print(f"    ? {f.name:<35} (unreadable)")
    else:
        print("    (no checkpoints yet)")

    # Snapshots
    snap_dir = repo_root / "04_implementation" / "snapshots"
    print("\n  Snapshots (04_implementation/snapshots/):")
    if snap_dir.exists():
        snaps = sorted(snap_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        for s in snaps[:3]:
            size = s.stat().st_size
            mtime = datetime.fromtimestamp(s.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"    ✓ {s.name:<40} {size:>7} bytes  ({mtime})")
        if len(snaps) > 3:
            print(f"    ... and {len(snaps) - 3} more")
    else:
        print("    (no snapshots yet)")

    print()
    return 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clear_checkpoints() -> None:
    """Remove all checkpoint files to force a fresh run."""
    import shutil
    ckpt_dir = Path(__file__).parent.parent / "01_data" / "real" / "checkpoints"
    if ckpt_dir.exists():
        shutil.rmtree(ckpt_dir)
        logger.info("Cleared checkpoints at %s", ckpt_dir)


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pg-atlas",
        description=(
            "PG Atlas — Graph intelligence backbone for SCF public goods funding.\n"
            "Reads GITHUB_TOKEN from .env automatically."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline (ingestion + metrics + report)
  python -m pg_atlas run

  # Full pipeline with explicit token and round label
  python -m pg_atlas run --token ghp_... --scf-round "SCF Q2 2026"

  # Ingestion only (skip metrics computation)
  python -m pg_atlas ingest

  # Metrics only (uses existing 01_data/real/ CSVs)
  python -m pg_atlas metrics --report-path 04_implementation/snapshots/report.md

  # Check current state without running anything
  python -m pg_atlas status

  # Clear checkpoints and start fresh
  python -m pg_atlas run --fresh
        """,
    )

    # Global flags
    parser.add_argument(
        "--env-file",
        default=None,
        metavar="PATH",
        help="Path to .env file (default: auto-detect .env in repo root)",
    )
    parser.add_argument(
        "--token",
        default=None,
        metavar="GITHUB_TOKEN",
        help="GitHub personal access token (overrides .env and environment)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # Shared flags for run/ingest/metrics
    def add_pipeline_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--since-days",
            type=int,
            default=90,
            metavar="N",
            help="Rolling window in days for git commit stats (default: 90)",
        )
        p.add_argument(
            "--workers",
            type=int,
            default=4,
            metavar="N",
            help="Concurrent GitHub API threads for A7 parsing (default: 4)",
        )
        p.add_argument(
            "--fresh",
            action="store_true",
            help="Clear checkpoints before running (forces full re-ingestion)",
        )
        p.add_argument(
            "--scf-round",
            default=None,
            metavar="NAME",
            help='SCF round label, e.g. "SCF Q2 2026" (default: current month)',
        )
        p.add_argument(
            "--report-path",
            default=None,
            metavar="PATH",
            help="Markdown report output path (default: auto-named in 04_implementation/snapshots/)",
        )

    # run
    p_run = subparsers.add_parser(
        "run",
        help="Full pipeline: ingestion → metrics → gate → report",
    )
    add_pipeline_flags(p_run)
    p_run.set_defaults(func=cmd_run)

    # ingest
    p_ingest = subparsers.add_parser(
        "ingest",
        help="Ingestion only: A7 git log + deps.dev + crates.io + npm + PyPI",
    )
    add_pipeline_flags(p_ingest)
    p_ingest.set_defaults(func=cmd_ingest)

    # metrics
    p_metrics = subparsers.add_parser(
        "metrics",
        help="Metrics only: reads existing CSVs, skips ingestion",
    )
    p_metrics.add_argument("--fresh", action="store_true", help=argparse.SUPPRESS)
    p_metrics.add_argument("--since-days", type=int, default=90, help=argparse.SUPPRESS)
    p_metrics.add_argument("--workers", type=int, default=4, help=argparse.SUPPRESS)
    p_metrics.add_argument(
        "--scf-round", default=None, metavar="NAME",
        help='SCF round label, e.g. "SCF Q2 2026"',
    )
    p_metrics.add_argument(
        "--report-path", default=None, metavar="PATH",
        help="Markdown report output path",
    )
    p_metrics.set_defaults(func=cmd_metrics)

    # status
    p_status = subparsers.add_parser(
        "status",
        help="Show checkpoint and output file status without running anything",
    )
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
