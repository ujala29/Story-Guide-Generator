"""
Metric Dictionary pipeline runner
==================================
Runs all Metric_dictionary steps for one or all dashboards.

Dependency graph
----------------
  pipeline_step9        [sequential]  DAX -> SQL compiler (calls steps 1-8 internally)
       ↓
  llm_fallback_step10   [sequential]  LLM validate / fix / build / define
       ↓
  ┌────────────────────────────────┐
  │  snowflake_verifier_step11     │  [parallel]  optional — needs Snowflake creds
  │  metric_catalog_step12         │  [parallel]  optional — tech + business catalog
  └────────────────────────────────┘

Library modules (steps 0-8) are imported internally by pipeline_step9 —
they are NOT called directly here.

Usage
-----
  python runner.py                          # risk-dash, all steps
  python runner.py --dashboard pac-dash
  python runner.py --dashboard all          # every dashboard in pipeline config
  python runner.py --skip-verifier          # skip Snowflake verification
  python runner.py --skip-catalog           # skip metric catalog generation
  python runner.py --dry-run                # pass --dry-run to each step
  python runner.py --from-step 10          # resume from llm_fallback onwards
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import argparse
import subprocess
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

HERE = Path(__file__).parent
_SRC = str(HERE.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.env_check import assert_env


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run(label: str, script: str, extra_args: list[str]) -> int:
    """Run a script sequentially, stream its output, return exit code."""
    cmd = [sys.executable, str(HERE / script)] + extra_args
    print(f"\n  $ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=False, cwd=str(HERE), timeout=1800)
    except subprocess.TimeoutExpired:
        print(f"\n[runner] TIMEOUT — {script} did not finish within 30 minutes")
        return 1
    if result.returncode != 0:
        print(f"\n[runner] FAILED — {script} exited with code {result.returncode}")
    return result.returncode




# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full Metric Dictionary pipeline (steps 9 -> 10 -> 11 ∥ 12)"
    )
    parser.add_argument(
        "--dashboard", default="risk-dash",
        help="Dashboard name, or 'all' to run every dashboard (default: risk-dash)"
    )
    parser.add_argument(
        "--from-step", type=int, default=9, metavar="N",
        help="Skip steps before N and start from N — values: 9, 10, 11/12 (default: 9)"
    )
    parser.add_argument(
        "--skip-verifier", action="store_true", default=True,
        help="Skip snowflake_verifier_step11 (default: True — enable with --no-skip-verifier)"
    )
    parser.add_argument(
        "--skip-catalog", action="store_true",
        help="Skip metric_catalog_step12 (catalog is optional)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Pass --dry-run to every step (no LLM calls, no Snowflake queries)"
    )
    args = parser.parse_args()
    if not args.dry_run:
        assert_env()

    dash     = args.dashboard
    dry_flag = ["--dry-run"] if args.dry_run else []

    print("=" * 62)
    print(f"  Metric Dictionary runner — dashboard: {dash}")
    print(f"  from-step     : {args.from_step}")
    print(f"  skip-verifier : {args.skip_verifier}")
    print(f"  skip-catalog  : {args.skip_catalog}")
    print(f"  dry-run       : {args.dry_run}")
    print("=" * 62)

    # ── Step 9 — DAX -> SQL compiler (sequential) ─────────────────
    if args.from_step <= 9:
        print("\n[step 9] pipeline — DAX -> SQL compiler")
        print("-" * 62)
        rc = _run(
            "pipeline",
            "pipeline_step9.py",
            ["--dashboard", dash] + dry_flag,
        )
        if rc != 0:
            sys.exit(rc)

    # ── Step 10 — LLM fallback (sequential) ──────────────────────
    if args.from_step <= 10:
        print("\n[step 10] llm_fallback — validate / fix / build / define")
        print("-" * 62)
        rc = _run(
            "llm_fallback",
            "llm_fallback_step10.py",
            ["--dashboard", dash] + dry_flag,
        )
        if rc != 0:
            sys.exit(rc)

    # ── Step 12 — metric catalog (sequential, after step 10) ─────
    if args.from_step <= 12 and not args.skip_catalog:
        print("\n[step 12] metric_catalog — tech + business definitions")
        print("-" * 62)
        rc = _run(
            "catalog",
            "metric_catalog_step12.py",
            ["--dashboard", dash] + dry_flag,
        )
        if rc != 0:
            sys.exit(rc)

    # ── Step 11 — Snowflake verifier (optional, skipped by default) ──
    if args.from_step <= 11 and not args.skip_verifier:
        print("\n[step 11] snowflake_verifier")
        print("-" * 62)
        rc = _run(
            "verifier",
            "snowflake_verifier_step11.py",
            ["--dry-run"] if args.dry_run else [],
        )
        if rc != 0:
            sys.exit(rc)

    print("\n" + "=" * 62)
    print("  ALL STEPS COMPLETE")
    print(f"  Output -> output/dashboards/{dash}/metric_dictionary/")
    print("=" * 62)


if __name__ == "__main__":
    main()
