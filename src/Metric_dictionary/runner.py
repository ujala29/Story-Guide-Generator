"""
Metric Dictionary pipeline runner
==================================
Runs all Metric_dictionary steps for one or all dashboards.

Dependency graph
----------------
  pipeline_step9        [sequential]  DAX → SQL compiler (calls steps 1-8 internally)
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

import argparse
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).parent


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run(label: str, script: str, extra_args: list[str]) -> int:
    """Run a script sequentially, stream its output, return exit code."""
    cmd = [sys.executable, str(HERE / script)] + extra_args
    print(f"\n  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False, cwd=str(HERE))
    if result.returncode != 0:
        print(f"\n[runner] FAILED — {script} exited with code {result.returncode}")
    return result.returncode


def _stream(proc: subprocess.Popen, prefix: str) -> None:
    """Forward a process's stdout line-by-line with a prefix tag."""
    for line in proc.stdout:
        print(f"[{prefix}] {line}", end="")


def _run_parallel(steps: list[tuple[str, str, list[str]]]) -> int:
    """
    Run multiple scripts at the same time.
    steps = [(label, script_name, extra_args), ...]
    Returns 0 if all succeed, else the first non-zero exit code.
    """
    procs: list[tuple[str, subprocess.Popen]] = []

    for label, script, extra_args in steps:
        cmd = [sys.executable, str(HERE / script)] + extra_args
        print(f"\n  $ {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(HERE),
        )
        procs.append((label, proc))

    # stream each process's output on its own thread so lines don't interleave silently
    threads = []
    for label, proc in procs:
        t = threading.Thread(target=_stream, args=(proc, label), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    first_fail = 0
    for label, proc in procs:
        proc.wait()
        if proc.returncode != 0 and first_fail == 0:
            first_fail = proc.returncode
            print(f"\n[runner] FAILED — {label} exited with code {proc.returncode}")

    return first_fail


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full Metric Dictionary pipeline (steps 9 → 10 → 11 ∥ 12)"
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
        "--skip-verifier", action="store_true",
        help="Skip snowflake_verifier_step11 (use when Snowflake creds are unavailable)"
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

    dash     = args.dashboard
    dry_flag = ["--dry-run"] if args.dry_run else []

    print("=" * 62)
    print(f"  Metric Dictionary runner — dashboard: {dash}")
    print(f"  from-step     : {args.from_step}")
    print(f"  skip-verifier : {args.skip_verifier}")
    print(f"  skip-catalog  : {args.skip_catalog}")
    print(f"  dry-run       : {args.dry_run}")
    print("=" * 62)

    # ── Step 9 — DAX → SQL compiler (sequential) ─────────────────
    if args.from_step <= 9:
        print("\n[step 9] pipeline — DAX → SQL compiler")
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

    # ── Steps 11 + 12 — parallel ─────────────────────────────────
    parallel_steps: list[tuple[str, str, list[str]]] = []

    if args.from_step <= 11 and not args.skip_verifier:
        parallel_steps.append((
            "verifier",
            "snowflake_verifier_step11.py",
            ["--dry-run"] if args.dry_run else [],
        ))

    if args.from_step <= 12 and not args.skip_catalog:
        parallel_steps.append((
            "catalog",
            "metric_catalog_step12.py",
            ["--dashboard", dash] + dry_flag,
        ))

    if parallel_steps:
        if len(parallel_steps) == 1:
            label, script, extra = parallel_steps[0]
            step_num = 11 if "verifier" in script else 12
            print(f"\n[step {step_num}] {label}")
            print("-" * 62)
            rc = _run(label, script, extra)
        else:
            print("\n[steps 11 + 12] verifier ∥ catalog  (running in parallel)")
            print("-" * 62)
            rc = _run_parallel(parallel_steps)

        if rc != 0:
            sys.exit(rc)
    else:
        print("\n[runner] steps 11 and 12 both skipped.")

    print("\n" + "=" * 62)
    print("  ALL STEPS COMPLETE")
    print(f"  Output → output/dashboards/{dash}/stage2/")
    print("=" * 62)


if __name__ == "__main__":
    main()
