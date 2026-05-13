# src/dashboard_overview/runner.py
#
# Entry point for dashboard overview generation.
# Calls dashboard_overview_generator.py for one or all dashboards.
#
# Usage:
#   python runner.py                      # all dashboards
#   python runner.py --dashboard risk-dash

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import sys
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_SRC = str(_HERE.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.env_check import assert_env, assert_prompts
from utils.config import ALL_DASHBOARDS

from dashboard_overview_generator import (
    gather_dashboard_info,
    generate_dashboard_overview,
    save_overview,
)

load_dotenv()
assert_env()
assert_prompts(_HERE.parent.parent / "prompt" / "system_prompt")

_ROOT = _HERE.parent.parent


def run_dashboard(dashboard: str, llm_client) -> None:
    filters_path = (
        _ROOT / "output" / "dashboards" / dashboard
        / "extraction" / "schema_sections" / "filters.json"
    )

    print(f"\n{'=' * 55}")
    print(f"  Dashboard Overview — {dashboard}")
    print(f"{'=' * 55}")

    if not filters_path.exists():
        print(f"  [ERROR] filters.json not found: {filters_path}")
        print("  Run Stage 1 extraction first.")
        return

    with open(filters_path, encoding="utf-8") as f:
        filters = json.load(f)

    info = gather_dashboard_info(dashboard, _ROOT, filters)

    print(f"  Pages        : {info['pages_processed']}")
    print(f"  Mirrored     : {info['pages_mirrored']}")
    print(f"  Widgets      : {sum(len(v) for v in info['widgets_by_page'].values())}")
    print(f"  Key metrics  : {len(info['key_metrics'])}")
    print(f"  Filters      : {len(info['filters'])}")

    print("\n  Generating dashboard overview...")
    result = generate_dashboard_overview(info, llm_client)
    save_overview(result, dashboard, _ROOT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard Overview Generator")
    parser.add_argument(
        "--dashboard", type=str, default="all",
        help="Dashboard to run: risk-dash | pac-dash | all  (default: all)"
    )
    args = parser.parse_args()

    dashboards = ALL_DASHBOARDS if args.dashboard == "all" else [args.dashboard]

    if args.dashboard != "all" and args.dashboard not in ALL_DASHBOARDS:
        print(f"ERROR: Unknown dashboard '{args.dashboard}'. Available: {', '.join(ALL_DASHBOARDS)}")
        sys.exit(1)

    llm_client = OpenAI(
        api_key=os.environ["TF_API_KEY"],
        base_url=os.environ["TF_BASE_URL"],
    )

    for dash in dashboards:
        run_dashboard(dash, llm_client)

    print("\nDone.")


if __name__ == "__main__":
    main()
