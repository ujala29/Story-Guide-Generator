"""
Filter Guide Generator
Input : filter.json (slicer metadata)
Output: output/filter_guide/*.md
"""

import argparse
import json
import os
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

_SRC = str(Path(__file__).resolve().parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.llm_client import llm_chat

load_dotenv()

_ROOT      = Path(__file__).resolve().parent.parent.parent
PROMPT_DIR = _ROOT / "prompt" / "system_prompt"

# ============================================================
# STEP 1 — Filter JSON process karo
# ============================================================

def extract_filters_by_page(filters: list) -> dict:
    """Page wise filters group karo"""

    page_filters = {}

    # utility/tooltip pages that are not real dashboard pages
    SKIP_PAGES = {"additional dimensions", "additional_dimensions",
                  "scatter plot tooltip", "scatter_plot_tooltip"}

    for f in filters:
        page = f.get("page", "Unknown")
        if page.lower().replace(" ", "_") in {
            p.replace(" ", "_") for p in SKIP_PAGES
        }:
            continue
        if page not in page_filters:
            page_filters[page] = []

        page_filters[page].append({
            "name":        f.get("name", ""),
            "table":       f.get("table", ""),
            "column":      f.get("column", ""),
            "slicer_mode": f.get("slicer_mode", ""),
            "single_select":     f.get("single_select", "false"),
            "select_all_enabled": f.get("select_all_enabled", "true"),
            "default_value":     f.get("default_value", None),
            "conditions":  f.get("visual_filter_conditions", [])
        })

    return page_filters


def get_global_filters(page_filters: dict) -> list:
    """
    Global filters = jo sare pages pe common hain
    """
    if not page_filters:
        return []

    pages     = list(page_filters.values())
    first     = {f["column"] for f in pages[0]}

    # sare pages mein common columns
    common = first.copy()
    for page in pages[1:]:
        page_cols = {f["column"] for f in page}
        common   &= page_cols

    # global filters nikalo — pehle page se
    global_filters = [
        f for f in pages[0]
        if f["column"] in common
    ]

    return global_filters


def print_filter_summary(page_filters: dict, global_filters: list):
    print("\n" + "=" * 55)
    print("  FILTER SUMMARY")
    print("=" * 55)
    print(f"  Total pages    : {len(page_filters)}")
    print(f"  Global filters : {len(global_filters)}")

    for page, filters in page_filters.items():
        print(f"\n  Page: {page}")
        for f in filters:
            g = "GLOBAL" if f["column"] in {
                gf["column"] for gf in global_filters
            } else "page-only"
            print(f"    • {f['name']:<20} [{f['column']}] ({g})")

    print("=" * 55 + "\n")

# ============================================================
# STEP 2 — System Prompt
# ============================================================

def load_filter_prompt() -> str:
    try:
        base     = (PROMPT_DIR / "base_context.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        base = ""
    try:
        template = (PROMPT_DIR / "prompt_for_filter.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR: Prompt file not found: {PROMPT_DIR / 'prompt_for_filter.txt'}")
        sys.exit(1)
    return (base + "\n\n" + template).strip()

# ============================================================
# STEP 3 — User Prompt
# ============================================================
def build_filter_prompt(
    global_filters: list,
    page_filters: dict,
    system_prompt: str
):
    PERIOD_MODE_MAP = {
        "Last Year":  "YTD (year-to-date: Jan 1 of current year to selected month)",
        "Last Month": "Rolling (last year's date to current date)",
    }

    def _translate_default(f: dict) -> str:
        raw = f["default_value"] or "All"
        if f["column"].lower() in ("period", "period_mode", "periodmode"):
            return PERIOD_MODE_MAP.get(raw, raw)
        return raw

    global_list = "\n".join([
        f"- {f['name']} | column: {f['column']} | default: {_translate_default(f)}"
        for f in global_filters
    ])

    global_cols = {f["column"] for f in global_filters}
    page_specific = {
        page: [f for f in filters if f["column"] not in global_cols]
        for page, filters in page_filters.items()
    }
    page_specific = {p: fs for p, fs in page_specific.items() if fs}

    page_specific_list = ""
    for page, filters in page_specific.items():
        page_specific_list += f"\nPage: {page}\n"
        for f in filters:
            page_specific_list += f"  - {f['name']} | column: {f['column']} | default: {_translate_default(f)}\n"

    user_prompt = f"""
Generate a filters reference for this dashboard.

Global filters:
{global_list}

Page-specific filters:
{page_specific_list if page_specific_list else 'None'}

Output ONLY this, nothing else — no intros, no bullets, no extra sections:

## Global Filters

| Filter Name | What it does | Default |
|---|---|---|
[one row per global filter]

{"## Page-specific Filters" + chr(10) + chr(10) + "[one table per page that has page-specific filters, same 3 columns]" if page_specific else ""}

Domain: Healthcare risk adjustment dashboard.
Users: Executive, Provider, Practice Manager.
    """

    return system_prompt, user_prompt
# ============================================================
# STEP 4 — LLM Call
# ============================================================

def generate_filter_guide(
    global_filters: list,
    page_filters: dict,
    llm_client
) -> str:

    system_prompt = load_filter_prompt()
    system_prompt, user_prompt = build_filter_prompt(
        global_filters, page_filters, system_prompt
    )

    return llm_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.3,
        client=llm_client,
    )

# ============================================================
# STEP 5 — Save Output
# ============================================================

def save_filter_guide(content: str, dashboard: str) -> Path:
    out_dir = _ROOT / "output" / "dashboards" / dashboard / "filter_section"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "global_filters.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"  [SAVED] {out_path}")
    return out_path

# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate global_filters.md from slicer metadata"
    )
    parser.add_argument("--dashboard", default="risk-dash",
                        help="Dashboard name (default: risk-dash)")
    args = parser.parse_args()

    llm_client = OpenAI(
        api_key=os.environ["TF_API_KEY"],
        base_url=os.environ["TF_BASE_URL"],
    )

    filters_path = (_ROOT / "output" / "dashboards" / args.dashboard
                    / "extraction" / "schema_sections" / "filters.json")
    print(f"Loading filters from: {filters_path}")
    with open(filters_path, encoding="utf-8") as f:
        filters = json.load(f)

    print(f"Total slicers found: {len(filters)}")

    page_filters   = extract_filters_by_page(filters)
    global_filters = get_global_filters(page_filters)

    print_filter_summary(page_filters, global_filters)

    print("Generating filter guide...")
    result = generate_filter_guide(global_filters, page_filters, llm_client)

    save_filter_guide(result, args.dashboard)
    print("\nDONE")


if __name__ == "__main__":
    main()