# src/filter_section/runner.py
#
# Entry point for filter guide generation.
# Calls filter_story_guidemaker.py for one or all dashboards.
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

from filter_story_guidemaker import (
    extract_filters_by_page,
    get_global_filters,
    print_filter_summary,
    generate_filter_guide,
    save_filter_guide,
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
    print(f"  Filter Guide — {dashboard}")
    print(f"{'=' * 55}")

    if not filters_path.exists():
        print(f"  [ERROR] filters.json not found: {filters_path}")
        print("  Run Stage 1 extraction first.")
        return

    try:
        with open(filters_path, encoding="utf-8") as f:
            filters = json.load(f)
    except json.JSONDecodeError as e:
        print(f"  [ERROR] filters.json is malformed ({e}). Re-run Extraction.")
        return

    print(f"  Total slicers found: {len(filters)}")

    page_filters   = extract_filters_by_page(filters)
    global_filters = get_global_filters(page_filters)

    print_filter_summary(page_filters, global_filters)

    print("  Generating filter guide...")
    result = generate_filter_guide(global_filters, page_filters, llm_client)
    save_filter_guide(result, dashboard)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter Guide Generator")
    parser.add_argument(
        "--dashboard", type=str, default="all",
        help="Dashboard to run: risk-dash | pac-dash | all  (default: all)"
    )
    args = parser.parse_args()

    if args.dashboard != "all" and args.dashboard not in ALL_DASHBOARDS:
        print(f"ERROR: Unknown dashboard '{args.dashboard}'. Available: {', '.join(ALL_DASHBOARDS)}")
        sys.exit(1)

    dashboards = ALL_DASHBOARDS if args.dashboard == "all" else [args.dashboard]

    llm_client = OpenAI(
        api_key=os.environ["TF_API_KEY"],
        base_url=os.environ["TF_BASE_URL"],
    )

    for dash in dashboards:
        run_dashboard(dash, llm_client)

    print("\nDone.")


if __name__ == "__main__":
    main()
