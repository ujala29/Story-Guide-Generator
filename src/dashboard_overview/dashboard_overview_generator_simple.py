"""
dashboard_overview_generator_simple.py  — BASELINE VERSION (for comparison)

Input : stage3/enriched_pages/*.json + stage1/filters.json
Output: stage3/dashboard_overview_simple.md

Uses the original approach: reads raw enriched_page files and sends flat
visual-type lists (cards, tables, charts) to the LLM — no funnel_map,
no funnel_connector, no widget_content context.

Run alongside dashboard_overview_generator.py to compare output quality:
  python dashboard_overview_generator_simple.py --dashboard risk-dash
  python dashboard_overview_generator.py         --dashboard risk-dash
Then compare:
  stage3/dashboard_overview_simple.md  ← this file
  stage3/dashboard_overview.md         ← enhanced version
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_ROOT      = Path(__file__).resolve().parent.parent.parent
PROMPT_DIR = _ROOT / "prompt" / "system_prompt"

CARD_TYPES    = {"cardVisual", "card", "multiRowCard"}
TABLE_TYPES   = {"pivotTable", "tableEx"}
LINE_TYPES    = {"lineChart"}
BAR_TYPES     = {"clusteredBarChart", "barChart", "columnChart"}
DONUT_TYPES   = {"donutChart"}
SCATTER_TYPES = {"scatterChart"}
SKIP_TYPES    = {"slicer"}

SKIP_PAGES = {"additional dimensions", "additional_dimensions",
              "scatter plot tooltip", "scatter_plot_tooltip"}


# ============================================================
# STEP 1 — Gather raw info from enriched_pages
# ============================================================

def gather_dashboard_info(dashboard: str, root: Path, filters: list) -> dict:
    enriched_dir = root / "output" / "dashboards" / dashboard / "stage3" / "enriched_pages"

    if not enriched_dir.exists():
        raise FileNotFoundError(
            f"enriched_pages not found at {enriched_dir}\n"
            "Run stage 3-PRE (visual_enricher_pages_wise.py) first."
        )

    page_files = sorted(
        f for f in enriched_dir.glob("*.json")
        if f.stem.lower().replace(" ", "_") not in SKIP_PAGES
    )

    pages       = []
    kpi_cards   = []
    tables      = []
    line_charts = []
    bar_charts  = []
    donuts      = []
    scatter     = []
    key_metrics = []

    for fpath in page_files:
        with open(fpath, encoding="utf-8") as f:
            page_data = json.load(f)

        page_name = page_data.get("page", fpath.stem)
        if page_name.lower().replace(" ", "_") in SKIP_PAGES:
            continue

        pages.append(page_name)

        for visual in page_data.get("visuals", []):
            vtype = visual.get("type", "")
            title = visual.get("title", "").strip()

            if not title or title.startswith("(unnamed"):
                continue
            if vtype in SKIP_TYPES:
                continue

            measures     = visual.get("measures_used", [])
            bare_measures = [m.split(".")[-1] for m in measures]

            if vtype in CARD_TYPES:
                kpi_cards.append(title)
                key_metrics.extend(bare_measures)
            elif vtype in TABLE_TYPES:
                tables.append(title)
            elif vtype in LINE_TYPES:
                line_charts.append(title)
            elif vtype in BAR_TYPES:
                bar_charts.append(title)
            elif vtype in DONUT_TYPES:
                donuts.append(title)
            elif vtype in SCATTER_TYPES:
                scatter.append(title)

    SKIP_FILTER_TABLES = {"X Axis scatter plot", "Y Axis scatter plot"}
    filter_names = list({
        f["name"] for f in filters
        if f.get("name")
        and not f["name"].startswith("Slicer_")
        and f.get("table", "") not in SKIP_FILTER_TABLES
    })

    return {
        "pages"      : pages,
        "kpi_cards"  : kpi_cards,
        "tables"     : tables,
        "line_charts": line_charts,
        "bar_charts" : bar_charts,
        "donuts"     : donuts,
        "scatter"    : scatter,
        "key_metrics": list(set(key_metrics)),
        "filters"    : filter_names,
    }


# ============================================================
# STEP 2 — System prompt
# ============================================================

def load_overview_prompt() -> str:
    base     = (PROMPT_DIR / "base_context.txt").read_text(encoding="utf-8")
    template = (PROMPT_DIR / "dashboard_overview.txt").read_text(encoding="utf-8")
    return base + "\n\n" + template


# ============================================================
# STEP 3 — User prompt (simple flat lists — baseline approach)
# ============================================================

def build_overview_prompt(info: dict, system_prompt: str) -> tuple[str, str]:
    user_prompt = f"""
Generate "Dashboard at a Glance" for Risk Management Dashboard.

Pages: {info['pages']}

KPI Cards: {info['kpi_cards']}

Tables: {info['tables']}

Trend charts: {info['line_charts']}

Bar charts: {info['bar_charts']}

Donut charts: {info['donuts']}

Scatter plots: {info['scatter']}

Key metrics: {info['key_metrics']}

Global filters: {info['filters']}

Domain: Healthcare risk adjustment — HCC coding, RAF scores, value-based care.

Users:
- Medical Director
- Care Manager
- Payer Analyst
- Practice Manager
"""
    return system_prompt, user_prompt


# ============================================================
# STEP 4 — LLM call
# ============================================================

def generate_dashboard_overview(info: dict, llm_client) -> str:
    system_prompt = load_overview_prompt()
    system_prompt, user_prompt = build_overview_prompt(info, system_prompt)

    response = llm_client.chat.completions.create(
        model=os.environ.get("TF_MODEL", "internal-bedrock/sonnet-46"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content


# ============================================================
# STEP 5 — Save  (different filename so both versions can coexist)
# ============================================================

def save_overview(content: str, dashboard: str, root: Path) -> Path:
    out_dir = root / "output" / "dashboards" / dashboard / "stage3"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "dashboard_overview_simple.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"  [SAVED] {out_path}")
    return out_path


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate dashboard_overview_simple.md (baseline — raw visual lists)"
    )
    parser.add_argument("--dashboard", default="risk-dash",
                        help="Dashboard name (default: risk-dash)")
    args = parser.parse_args()

    root = _ROOT

    llm_client = OpenAI(
        api_key=os.environ["TF_API_KEY"],
        base_url=os.environ["TF_BASE_URL"],
    )

    filters_path = (root / "output" / "dashboards" / args.dashboard
                    / "stage1" / "schema_sections" / "filters.json")
    print(f"Loading filters from: {filters_path}")
    with open(filters_path, encoding="utf-8") as f:
        filters = json.load(f)

    info = gather_dashboard_info(args.dashboard, root, filters)

    print(f"  Dashboard    : {args.dashboard}")
    print(f"  Pages        : {len(info['pages'])}")
    print(f"  KPI cards    : {len(info['kpi_cards'])}")
    print(f"  Tables       : {len(info['tables'])}")
    print(f"  Key metrics  : {len(info['key_metrics'])}")
    print(f"  Filters      : {len(info['filters'])}")

    print("\nGenerating dashboard overview (simple / baseline)...")
    result = generate_dashboard_overview(info, llm_client)

    save_overview(result, args.dashboard, root)
    print("\nDONE")
    print("\nCompare with enhanced version:")
    print(f"  Simple  : output/dashboards/{args.dashboard}/stage3/dashboard_overview_simple.md")
    print(f"  Enhanced: output/dashboards/{args.dashboard}/stage3/dashboard_overview.md")


if __name__ == "__main__":
    main()
