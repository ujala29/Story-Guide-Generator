# src/Extraction/runner.py
#
# Stage 1 entry point.
# Runs extractor.py (which internally calls measure_resolver_) for one or all dashboards.
#
# Usage:
#   python runner.py                    # all dashboards
#   python runner.py --dashboard risk-dash
#   python runner.py --dashboard pac-dash

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import json
import argparse
from pathlib import Path

# Ensure Extraction/ is on the path so extractor.py imports work
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from extractor import run_extraction
from tmdl_sf_mapper import generate_mapping
from prompt_generator import generate_dashboard_prompts

_SRC = str(_HERE.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.config import DASHBOARDS, ALL_DASHBOARDS, ROOT
from utils.paths import get_paths


def main():
    parser = argparse.ArgumentParser(description="Stage 1 — Extraction + Measure Resolution")
    parser.add_argument(
        "--dashboard", type=str, default="all",
        help="Dashboard to run: risk-dash | pac-dash | all  (default: all)"
    )
    args = parser.parse_args()

    dashboards = ALL_DASHBOARDS if args.dashboard == "all" else [args.dashboard]

    for dash in dashboards:
        cfg = DASHBOARDS.get(dash)
        if not cfg:
            print(f"ERROR: Unknown dashboard '{dash}'. Available: {', '.join(ALL_DASHBOARDS)}")
            sys.exit(1)

        p = get_paths(dash)
        print("=" * 55)
        print(f"  Stage 1 — {dash}")
        print("=" * 55)

        # run_extraction already calls resolve_all internally and writes measures_resolved.json
        run_extraction(
            semantic_model_path=str(cfg["semantic_model"]),
            report_path=str(cfg["report"]),
            output_path=str(p.stage1_schema),
        )

        print(f"\n  Generating BI→SF naming map...")
        mapping = generate_mapping(cfg["semantic_model"])
        out = p.bi_sf_naming_matching
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Written → {out}")

        print(f"\n  Generating dashboard prompt files...")
        prompts_root = ROOT / "prompt"
        generate_dashboard_prompts(dash, mapping, prompts_root)

    print("\nDone.")


if __name__ == "__main__":
    main()
