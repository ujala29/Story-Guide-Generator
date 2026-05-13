# main.py  —  Story Guide Generator: full pipeline orchestrator
#
# Execution order:
#   Stage 1  [sequential]  Extraction
#   Stage 2  [parallel]    Visual_wise  |  filter_section  |  Metric_dictionary
#   Stage 3  [sequential]  Page_wise
#   Stage 4  [parallel]    dashboard_overview  |  glossary_faq
#
# Usage:
#   python main.py                              # all dashboards, all stages
#   python main.py --dashboard risk-dash        # single dashboard
#   python main.py --from-stage 2              # resume from stage 2
#   python main.py --skip-verifier --skip-catalog  # skip optional metric steps
#   python main.py --no-test                   # Visual_wise full run (not test mode)
#   python main.py --dry-run                   # no LLM / Snowflake calls

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent
SRC  = ROOT / "src"
sys.path.insert(0, str(SRC))
from utils.env_check import assert_env
from utils.config import ALL_DASHBOARDS
from utils.paths import get_paths

# Runners for each module
RUNNERS = {
    "extraction"        : SRC / "Extraction"         / "runner.py",
    "visual_wise"       : SRC / "Visual_wise"        / "runner.py",
    "filter_section"    : SRC / "filter_section"     / "runner.py",
    "metric_dict"       : SRC / "Metric_dictionary"  / "runner.py",
    "page_wise"         : SRC / "Page_wise"          / "runner.py",
    "dashboard_overview": SRC / "dashboard_overview" / "runner.py",
    "glossary_faq"      : SRC / "glossary_faq"       / "runner.py",
}

# Dashboards that support "all" natively in their own runner
SUPPORTS_ALL = {"extraction", "visual_wise", "filter_section", "metric_dict", "dashboard_overview", "glossary_faq"}

# ALL_DASHBOARDS imported from utils.config — single source of truth


# ─────────────────────────────────────────────────────────────
# Run helpers
# ─────────────────────────────────────────────────────────────

def _run(label: str, script: Path, args: list[str]) -> int:
    """Run a script sequentially, stream output, return exit code."""
    cmd = [sys.executable, str(script)] + args
    print(f"\n  $ {' '.join(str(c) for c in cmd)}")
    try:
        result = subprocess.run(cmd, check=False, timeout=1800)
    except subprocess.TimeoutExpired:
        print(f"\n[main] TIMEOUT — {label} did not finish within 30 minutes")
        return 1
    if result.returncode != 0:
        print(f"\n[main] FAILED — {label} exited with code {result.returncode}")
    return result.returncode


def _stream(proc: subprocess.Popen, prefix: str, lock: threading.Lock) -> None:
    """Forward a subprocess stdout line-by-line with a labelled prefix."""
    try:
        for line in proc.stdout:
            with lock:
                print(f"[{prefix}] {line}", end="", flush=True)
    except Exception as e:
        with lock:
            print(f"[{prefix}] [stream error: {e}]", flush=True)
        # Drain the pipe so the subprocess is never blocked waiting to write
        try:
            proc.stdout.read()
        except Exception:
            pass


def _heartbeat(
    procs: list[tuple[str, subprocess.Popen]],
    lock: threading.Lock,
    stop: threading.Event,
    interval: int = 30,
) -> None:
    """Print a 'still running' line every `interval` seconds for active processes."""
    elapsed = 0
    while not stop.wait(timeout=interval):
        elapsed += interval
        still_running = [label for label, proc in procs if proc.poll() is None]
        if still_running:
            with lock:
                print(
                    f"[main] ... still running after {elapsed}s: {', '.join(still_running)}",
                    flush=True,
                )


def _run_parallel(steps: list[tuple[str, Path, list[str]]]) -> int:
    """
    Launch multiple scripts concurrently.
    steps = [(label, script_path, extra_args), ...]
    Returns 0 if all succeed, else the first non-zero exit code.
    """
    procs: list[tuple[str, subprocess.Popen]] = []
    lock  = threading.Lock()

    for label, script, extra_args in steps:
        cmd = [sys.executable, str(script)] + extra_args
        with lock:
            print(f"\n  $ {' '.join(str(c) for c in cmd)}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        procs.append((label, proc))

    threads = []
    for label, proc in procs:
        t = threading.Thread(target=_stream, args=(proc, label, lock), daemon=True)
        t.start()
        threads.append(t)

    stop_heartbeat = threading.Event()
    hb = threading.Thread(
        target=_heartbeat, args=(procs, lock, stop_heartbeat), daemon=True
    )
    hb.start()

    for t in threads:
        t.join(timeout=1800)
        if t.is_alive():
            print(f"[main] WARNING: a parallel stage thread is still running after 30min timeout")

    stop_heartbeat.set()

    first_fail = 0
    for label, proc in procs:
        proc.wait()
        if proc.returncode != 0 and first_fail == 0:
            first_fail = proc.returncode
            print(f"\n[main] FAILED — {label} exited with code {proc.returncode}")

    return first_fail


def _args_for(module: str, dashboard: str, opts: argparse.Namespace) -> list[str]:
    """Build the CLI args list to pass to each module runner."""
    extra: list[str] = []

    # dashboard flag
    if module in SUPPORTS_ALL:
        extra += ["--dashboard", dashboard]      # pass "all" or specific
    else:
        extra += ["--dashboard", dashboard]      # single only; caller loops if "all"

    # module-specific flags
    if module == "visual_wise" and not opts.test_mode:
        extra.append("--no-test")

    if module == "metric_dict":
        if opts.skip_verifier:
            extra.append("--skip-verifier")
        if opts.skip_catalog:
            extra.append("--skip-catalog")
        if opts.dry_run:
            extra.append("--dry-run")

    if module == "page_wise":
        extra += ["--workers", str(opts.workers)]
        if opts.force:
            extra.append("--force")

    return extra


# ─────────────────────────────────────────────────────────────
# Preflight checks — verify upstream outputs exist before each stage
# ─────────────────────────────────────────────────────────────

def _preflight_stage2(dashboard: str) -> bool:
    """Stage 2 requires Stage 1 schema_sections output."""
    p = get_paths(dashboard)
    required = ["measures_resolved.json", "visuals.json", "filters.json"]
    missing = [f for f in required if not (p.stage1_sections_dir / f).exists()]
    if missing:
        print(f"[preflight] Stage 2 blocked — missing Stage 1 outputs for '{dashboard}': {missing}")
        print(f"            Run Stage 1 first: python main.py --dashboard {dashboard} --from-stage 1")
        return False
    return True


def _preflight_stage3(dashboard: str) -> bool:
    """Stage 3 requires Stage 2 LLM measures output + at least one enriched page."""
    p = get_paths(dashboard)
    ok = True
    if not p.final_measures_with_llm.exists():
        print(f"[preflight] Stage 3 blocked — missing Stage 2 output for '{dashboard}': final_measures_with_llm.json")
        print(f"            Run Stage 2 first: python main.py --dashboard {dashboard} --from-stage 2")
        ok = False
    enriched = list(p.enriched_pages_dir.glob("*.json")) if p.enriched_pages_dir.exists() else []
    if not enriched:
        print(f"[preflight] Stage 3 blocked — no enriched pages found for '{dashboard}' in {p.enriched_pages_dir}")
        print(f"            Run Stage 2 (visual_wise) first: python main.py --dashboard {dashboard} --from-stage 2")
        ok = False
    return ok


def _preflight_stage4(dashboard: str) -> bool:
    """Stage 4 requires Stage 3 widget_content output."""
    p = get_paths(dashboard)
    widgets = list(p.widget_content_dir.glob("*.json")) if p.widget_content_dir.exists() else []
    if not widgets:
        print(f"[preflight] Stage 4 blocked — no widget_content files found for '{dashboard}' in {p.widget_content_dir}")
        print(f"            Run Stage 3 first: python main.py --dashboard {dashboard} --from-stage 3")
        return False
    return True


PREFLIGHTS = {
    2: _preflight_stage2,
    3: _preflight_stage3,
    4: _preflight_stage4,
}


# ─────────────────────────────────────────────────────────────
# Stage runners
# ─────────────────────────────────────────────────────────────

def stage1_extraction(dashboard: str, opts: argparse.Namespace) -> int:
    print(f"\n{'=' * 62}")
    print(f"  STAGE 1 — Extraction  [{dashboard}]")
    print(f"{'=' * 62}")
    return _run("extraction", RUNNERS["extraction"], _args_for("extraction", dashboard, opts))


def stage2_parallel(dashboard: str, opts: argparse.Namespace) -> int:
    print(f"\n{'=' * 62}")
    print(f"  STAGE 2 — Visual_wise | filter_section | Metric_dictionary  [{dashboard}]  (parallel)")
    print(f"{'=' * 62}")

    steps = [
        ("visual_wise",    RUNNERS["visual_wise"],    _args_for("visual_wise",    dashboard, opts)),
        ("filter_section", RUNNERS["filter_section"], _args_for("filter_section", dashboard, opts)),
        ("metric_dict",    RUNNERS["metric_dict"],    _args_for("metric_dict",    dashboard, opts)),
    ]
    return _run_parallel(steps)


def stage3_page_wise(dashboard: str, opts: argparse.Namespace) -> int:
    print(f"\n{'=' * 62}")
    print(f"  STAGE 3 — Page_wise  [{dashboard}]")
    print(f"{'=' * 62}")
    return _run("page_wise", RUNNERS["page_wise"], _args_for("page_wise", dashboard, opts))


def stage4_parallel(dashboard: str, opts: argparse.Namespace) -> int:
    print(f"\n{'=' * 62}")
    print(f"  STAGE 4 — dashboard_overview | glossary_faq  [{dashboard}]  (parallel)")
    print(f"{'=' * 62}")
    steps = [
        ("dashboard_overview", RUNNERS["dashboard_overview"], _args_for("dashboard_overview", dashboard, opts)),
        ("glossary_faq",       RUNNERS["glossary_faq"],       _args_for("glossary_faq",       dashboard, opts)),
    ]
    return _run_parallel(steps)


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

STAGES = [
    (1, "Extraction",                  stage1_extraction),
    (2, "Visual_wise | filter | metric_dict (parallel)", stage2_parallel),
    (3, "Page_wise",                   stage3_page_wise),
    (4, "dashboard_overview | glossary_faq (parallel)", stage4_parallel),
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Story Guide Generator — full pipeline runner"
    )
    parser.add_argument(
        "--dashboard", default="all",
        help="Dashboard: risk-dash | pac-dash | all  (default: all)"
    )
    parser.add_argument(
        "--from-stage", type=int, default=1, metavar="N",
        help="Skip stages before N and resume from N  (default: 1)"
    )

    # Visual_wise flags
    parser.add_argument(
        "--no-test", dest="test_mode", action="store_false", default=True,
        help="Visual_wise: disable test mode and process all visual types"
    )

    # Metric_dictionary flags
    parser.add_argument("--skip-verifier", action="store_true",
                        help="Metric_dict: skip Snowflake verifier (step 11)")
    parser.add_argument("--skip-catalog",  action="store_true",
                        help="Metric_dict: skip metric catalog (step 12)")
    parser.add_argument("--dry-run",       action="store_true",
                        help="Metric_dict: no LLM / Snowflake calls")

    # Page_wise flags
    parser.add_argument("--workers", type=int, default=3,
                        help="Page_wise: parallel LLM workers  (default: 3)")
    parser.add_argument("--force", action="store_true",
                        help="Page_wise: skip all caches and re-run")

    args = parser.parse_args()

    # Resolve dashboard list
    if args.dashboard == "all":
        dashboards = ALL_DASHBOARDS
    else:
        if args.dashboard not in ALL_DASHBOARDS:
            print(f"ERROR: Unknown dashboard '{args.dashboard}'. Available: {', '.join(ALL_DASHBOARDS)}")
            sys.exit(1)
        dashboards = [args.dashboard]

    if not args.dry_run:
        assert_env()

    print("=" * 62)
    print("  Story Guide Generator — full pipeline")
    print(f"  Dashboards  : {dashboards}")
    print(f"  From stage  : {args.from_stage}")
    print(f"  Test mode   : {args.test_mode}")
    print(f"  Dry run     : {args.dry_run}")
    print("=" * 62)

    t_start = time.time()

    for dash in dashboards:
        print(f"\n{'#' * 62}")
        print(f"#  Dashboard: {dash}")
        print(f"{'#' * 62}")

        for stage_num, stage_label, stage_fn in STAGES:
            if stage_num < args.from_stage:
                print(f"\n[stage {stage_num}] SKIP — {stage_label}")
                continue

            preflight = PREFLIGHTS.get(stage_num)
            if preflight and not preflight(dash):
                sys.exit(1)

            rc = stage_fn(dash, args)
            if rc != 0:
                print(f"\n[main] Pipeline stopped at stage {stage_num} ({stage_label}) for {dash}.")
                sys.exit(rc)

    elapsed = time.time() - t_start
    print(f"\n{'=' * 62}")
    print(f"  PIPELINE COMPLETE  ({elapsed:.1f}s)")
    print(f"  Dashboards: {dashboards}")
    print(f"  Output → output/dashboards/<dashboard>/")
    print(f"{'=' * 62}")


if __name__ == "__main__":
    main()
