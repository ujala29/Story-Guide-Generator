"""
Page_wise pipeline runner
Executes all 5 steps in order for a given dashboard.

Step 0  funnel_input_builder_step0.py  -> stage3/funnel_llm_input.json
Step 1  funnel_mapper_step1.py         -> stage3/funnel_map.json
Step 3  widget_group_writer_step3.py   -> stage3/widget_content/
Step 4  funnel_connector_step4.py      -> stage3/funnel_connector.json
Step 5  document_assembler_step5.py    -> stage3/final_story_guide.md

Usage:
  python runner.py                          # risk-dash, all steps
  python runner.py --dashboard pac-dash
  python runner.py --force                  # skip all caches
  python runner.py --from-step 3           # resume from step 3 onwards
  python runner.py --workers 5             # more parallel LLM calls in step 3
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

STEPS = [
    (0, "Build funnel input",  "funnel_input_builder_step0.py"),
    (1, "Map funnel",          "funnel_mapper_step1.py"),
    (3, "Write widget groups", "widget_group_writer_step3.py"),
    (4, "Connect funnel",      "funnel_connector_step4.py"),
    (5, "Assemble document",   "document_assembler_step5.py"),
]

# steps that accept --force
SUPPORTS_FORCE = {"funnel_mapper_step1.py", "widget_group_writer_step3.py",
                  "funnel_connector_step4.py"}


def run_step(script_name: str, cmd_args: list[str]) -> None:
    cmd = [sys.executable, str(HERE / script_name)] + cmd_args
    print(f"  $ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=False, timeout=1800)
    except subprocess.TimeoutExpired:
        print(f"\n[runner] TIMEOUT — {script_name} did not finish within 30 minutes")
        sys.exit(1)
    if result.returncode != 0:
        print(f"\n[runner] FAILED — {script_name} exited with code {result.returncode}")
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full Page_wise pipeline (steps 0->1->3->4->5)"
    )
    parser.add_argument("--dashboard", default="risk-dash",
                        help="Dashboard name (default: risk-dash)")
    parser.add_argument("--force", action="store_true",
                        help="Re-run all cached steps instead of skipping them")
    parser.add_argument("--from-step", type=int, default=0, metavar="N",
                        help="Skip steps before N and start from N (e.g. --from-step 3)")
    parser.add_argument("--workers", type=int, default=3,
                        help="Parallel LLM calls in step 3 (default: 3)")
    args = parser.parse_args()
    assert_env()

    dash = args.dashboard
    root = HERE.parent.parent  # Story Guide Generator_ root
    out  = root / "output" / "dashboards" / dash / "page_wise" / "final_story_guide.md"

    print("=" * 62)
    print(f"  Page_wise runner — dashboard: {dash}")
    print(f"  from-step : {args.from_step}    force: {args.force}")
    print("=" * 62)

    for step_num, label, script in STEPS:
        if step_num < args.from_step:
            print(f"\n[step {step_num}] SKIP — {label}")
            continue

        print(f"\n[step {step_num}] {label}")
        print("-" * 62)

        cmd_args = ["--dashboard", dash]

        if script == "widget_group_writer_step3.py":
            cmd_args += ["--all", "--workers", str(args.workers)]

        if args.force and script in SUPPORTS_FORCE:
            cmd_args.append("--force")

        run_step(script, cmd_args)

    print("\n" + "=" * 62)
    print("  ALL STEPS COMPLETE")
    print(f"  Output -> {out}")
    print("=" * 62)


if __name__ == "__main__":
    main()
