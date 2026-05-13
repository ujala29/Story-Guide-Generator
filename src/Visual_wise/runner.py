# src/Visual_wise/runner.py
#
# Entry point for the Visual_wise pipeline (L0->L1->L2->L3 per page).
# Sets STORY_DASHBOARD env var and delegates to visaul_pipeline_runner.py.
#
# Usage:
#   python runner.py                          # all dashboards
#   python runner.py --dashboard risk-dash    # single dashboard
#   python runner.py --dashboard risk-dash --no-test   # full run (not test mode)

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import argparse
import os
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
from utils.config import ALL_DASHBOARDS

PIPELINE_SCRIPT = HERE / "visaul_pipeline_runner.py"


def run_dashboard(dashboard: str, test_mode: bool) -> None:
    print(f"\n{'=' * 62}")
    print(f"  Visual_wise pipeline — {dashboard}")
    print(f"  test_mode: {test_mode}")
    print(f"{'=' * 62}")

    env = os.environ.copy()
    env["STORY_DASHBOARD"] = dashboard

    # TEST_MODE is read inside the script as a hardcoded flag.
    # Pass it as an env var so the runner can override it if needed.
    env["STORY_TEST_MODE"] = "1" if test_mode else "0"

    cmd = [sys.executable, str(PIPELINE_SCRIPT)]
    print(f"  $ STORY_DASHBOARD={dashboard} python visaul_pipeline_runner.py")

    try:
        result = subprocess.run(cmd, env=env, check=False, timeout=1800)
    except subprocess.TimeoutExpired:
        print(f"\n[runner] TIMEOUT — visaul_pipeline_runner.py did not finish within 30 minutes")
        sys.exit(1)
    if result.returncode != 0:
        print(f"\n[runner] FAILED — visaul_pipeline_runner.py exited with code {result.returncode}")
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visual_wise pipeline runner (L0->L1->L2->L3)"
    )
    parser.add_argument(
        "--dashboard", type=str, default="all",
        help="Dashboard to run: risk-dash | pac-dash | all  (default: all)"
    )
    parser.add_argument(
        "--no-test", dest="test_mode", action="store_false", default=True,
        help="Disable test mode and process all visual types (default: test mode ON)"
    )
    args = parser.parse_args()

    if args.dashboard != "all" and args.dashboard not in ALL_DASHBOARDS:
        print(f"ERROR: Unknown dashboard '{args.dashboard}'. Available: {', '.join(ALL_DASHBOARDS)}")
        sys.exit(1)

    assert_env()
    dashboards = ALL_DASHBOARDS if args.dashboard == "all" else [args.dashboard]

    for dash in dashboards:
        run_dashboard(dash, args.test_mode)

    print("\nDone.")


if __name__ == "__main__":
    main()
