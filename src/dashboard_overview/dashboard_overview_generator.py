"""
dashboard_overview_generator.py
Input : stage3/funnel_map.json + stage3/widget_content/*.json + stage1/filters.json
Output: stage3/dashboard_overview.md

Richer than the previous version — uses Page_wise outputs instead of raw
visual type lists so the LLM receives structured domain context, funnel
questions, widget group intros, and metric names rather than bare lists.
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPT_DIR = _ROOT / "prompt" / "system_prompt"


# ============================================================
# STEP 1 — Gather rich context from Page_wise outputs
# ============================================================

def gather_dashboard_info(dashboard: str, root: Path, filters: list) -> dict:
    stage3 = root / "output" / "dashboards" / dashboard / "stage3"

    # ── funnel_map.json ─────────────────────────────────────────
    funnel_map_path = stage3 / "funnel_map.json"
    funnel_map: dict = {}
    if funnel_map_path.exists():
        with open(funnel_map_path, encoding="utf-8") as f:
            funnel_map = json.load(f)
    else:
        print(f"  [WARN] funnel_map.json not found at {funnel_map_path}")
        print("  Run Page_wise/runner.py (steps 0+1) first for best results.")

    # ── funnel_connector.json ────────────────────────────────────
    connector_path = stage3 / "funnel_connector.json"
    funnel_connector: dict = {}
    if connector_path.exists():
        with open(connector_path, encoding="utf-8") as f:
            funnel_connector = json.load(f)
    else:
        print(f"  [WARN] funnel_connector.json not found at {connector_path}")
        print("  Run Page_wise/runner.py (step 4) for richer overview.")

    # ── widget_content/<page>.json ───────────────────────────────
    widget_content_dir = stage3 / "widget_content"
    widget_content: dict[str, dict] = {}
    if widget_content_dir.exists():
        for wf in sorted(widget_content_dir.glob("*.json")):
            with open(wf, encoding="utf-8") as f:
                data = json.load(f)
            page = data.get("page", wf.stem)
            widget_content[page] = data
    else:
        print(f"  [WARN] widget_content/ not found at {widget_content_dir}")

    # ── global filters ────────────────────────────────────────────
    SKIP_TABLES = {"X Axis scatter plot", "Y Axis scatter plot"}
    filter_names = list({
        f["name"] for f in filters
        if f.get("name")
        and not f["name"].startswith("Slicer_")
        and f.get("table", "") not in SKIP_TABLES
    })

    # ── pages ────────────────────────────────────────────────────
    meta             = funnel_map.get("_meta", {})
    pages_processed  = meta.get("pages_processed", [])
    pages_mirrored   = meta.get("pages_mirrored", [])

    # ── widgets grouped by page ────────────────────────────────
    widgets_by_page: dict[str, list] = {}
    for w in funnel_map.get("widgets", []):
        page = w.get("page", "Unknown")
        widgets_by_page.setdefault(page, []).append({
            "name":           w.get("widget_name", ""),
            "question":       w.get("sub_question", ""),
            "funnel_position": w.get("funnel_position", ""),
            "reading_order":  w.get("reading_order", 0),
        })

    # ── per-page widget group intros + metric names ────────────
    page_widget_intros: dict[str, list] = {}
    all_metrics: list[str] = []
    for page, data in widget_content.items():
        intros = []
        for w in data.get("widgets", []):
            names = [m["name"] for m in w.get("metrics", [])]
            all_metrics.extend(names)
            intros.append({
                "widget_name": w.get("widget_name", ""),
                "group_intro": w.get("group_intro", ""),
                "metrics":     names,
            })
        page_widget_intros[page] = intros

    return {
        "domain_context":         funnel_map.get("domain_context", ""),
        "funnel_question_top":    funnel_map.get("funnel_question_top", ""),
        "funnel_question_middle": funnel_map.get("funnel_question_middle", ""),
        "funnel_question_bottom": funnel_map.get("funnel_question_bottom", ""),
        "funnel_question_action": funnel_map.get("funnel_question_action", ""),
        "pages_processed":        pages_processed,
        "pages_mirrored":         pages_mirrored,
        "widgets_by_page":        widgets_by_page,
        "page_widget_intros":     page_widget_intros,
        "key_metrics":            list(dict.fromkeys(all_metrics)),
        "filters":                filter_names,
        # from funnel_connector (narrative synthesis layer)
        "funnel_table":           funnel_connector.get("funnel_table", []),
        "cross_page_patterns":    funnel_connector.get("cross_page_patterns", []),
        "closing_paragraph":      funnel_connector.get("closing_paragraph", ""),
    }


# ============================================================
# STEP 2 — System prompt
# ============================================================

def load_overview_prompt() -> str:
    base     = (PROMPT_DIR / "base_context.txt").read_text(encoding="utf-8")
    template = (PROMPT_DIR / "dashboard_overview.txt").read_text(encoding="utf-8")
    return base + "\n\n" + template


# ============================================================
# STEP 3 — User prompt (much richer than before)
# ============================================================

def _format_widgets_by_page(widgets_by_page: dict) -> str:
    lines = []
    for page, widgets in widgets_by_page.items():
        lines.append(f"\nPage: {page}")
        for w in sorted(widgets, key=lambda x: x["reading_order"]):
            lines.append(
                f"  [{w['funnel_position']}] {w['name']}\n"
                f"    → {w['question']}"
            )
    return "\n".join(lines)


def _format_page_intros(page_widget_intros: dict) -> str:
    lines = []
    for page, widgets in page_widget_intros.items():
        lines.append(f"\nPage: {page}")
        for w in widgets:
            lines.append(f"  Widget: {w['widget_name']}")
            if w["group_intro"]:
                lines.append(f"  {w['group_intro']}")
            if w["metrics"]:
                lines.append(f"  Metrics: {', '.join(w['metrics'])}")
    return "\n".join(lines)


def _format_funnel_table(funnel_table: list) -> str:
    if not funnel_table:
        return "(not yet generated — run step 4)"
    lines = ["Layer | Section | Question it answers",
             "------|---------|--------------------"]
    for row in funnel_table:
        lines.append(
            f"{row.get('layer','')} | {row.get('section','')} | {row.get('question_it_answers','')}"
        )
    return "\n".join(lines)


def _format_cross_page_patterns(patterns: list) -> str:
    if not patterns:
        return "(not yet generated — run step 4)"
    return "\n".join(
        f"- {p.get('pattern','')}\n  → {p.get('interpretation','')}"
        for p in patterns
    )


def build_overview_prompt(info: dict, system_prompt: str) -> tuple[str, str]:
    pages_section = ""
    if info["pages_mirrored"]:
        pages_section = (
            f"Primary pages: {info['pages_processed']}\n"
            f"Mirrored pages (same content, different time window): {info['pages_mirrored']}"
        )
    else:
        pages_section = f"Pages: {info['pages_processed']}"

    user_prompt = f"""
Generate "Dashboard at a Glance" for the Risk Management Dashboard.

─── DOMAIN CONTEXT ──────────────────────────────────────────
{info['domain_context']}

─── KEY QUESTIONS THIS DASHBOARD ANSWERS ────────────────────
TOP (current state):
  {info['funnel_question_top']}

MIDDLE (why / trend):
  {info['funnel_question_middle']}

BOTTOM (who / what):
  {info['funnel_question_bottom']}

ACTION (what to do):
  {info['funnel_question_action']}

─── PAGES ───────────────────────────────────────────────────
{pages_section}

─── WIDGET STRUCTURE (reading order, funnel position, purpose) ──
{_format_widgets_by_page(info['widgets_by_page'])}

─── WIDGET CONTENT CONTEXT (group intros + metrics per page) ────
{_format_page_intros(info['page_widget_intros'])}

─── KEY METRICS IN THIS DASHBOARD ──────────────────────────
{info['key_metrics']}

─── HOW THE FUNNEL CONNECTS (Layer / Section / Question) ────
{_format_funnel_table(info['funnel_table'])}

─── CROSS-PAGE PATTERNS (for section 1.4 key questions) ─────
{_format_cross_page_patterns(info['cross_page_patterns'])}

─── NARRATIVE CLOSING ARC (for section 1.6 navigation) ──────
{info['closing_paragraph']}

─── GLOBAL FILTERS ──────────────────────────────────────────
{info['filters']}

─── USERS ───────────────────────────────────────────────────
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
# STEP 5 — Save
# ============================================================

def save_overview(content: str, dashboard: str, root: Path) -> Path:
    out_dir = root / "output" / "dashboards" / dashboard / "stage3"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "dashboard_overview.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"  [SAVED] {out_path}")
    return out_path


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate dashboard_overview.md from Page_wise outputs"
    )
    parser.add_argument("--dashboard", default="risk-dash",
                        help="Dashboard name (default: risk-dash)")
    args = parser.parse_args()

    root = _ROOT

    llm_client = OpenAI(
        api_key=os.environ["TF_API_KEY"],
        base_url=os.environ["TF_BASE_URL"],
    )

    filters_path = root / "output" / "dashboards" / args.dashboard / "stage1" / "schema_sections" / "filters.json"
    print(f"Loading filters from: {filters_path}")
    with open(filters_path, encoding="utf-8") as f:
        filters = json.load(f)

    info = gather_dashboard_info(args.dashboard, root, filters)

    print(f"  Dashboard    : {args.dashboard}")
    print(f"  Pages        : {info['pages_processed']}")
    print(f"  Mirrored     : {info['pages_mirrored']}")
    print(f"  Widgets      : {sum(len(v) for v in info['widgets_by_page'].values())}")
    print(f"  Key metrics  : {len(info['key_metrics'])}")
    print(f"  Filters      : {len(info['filters'])}")
    print(f"  Has domain context : {bool(info['domain_context'])}")

    print("\nGenerating dashboard overview...")
    result = generate_dashboard_overview(info, llm_client)

    save_overview(result, args.dashboard, root)
    print("\nDONE")


if __name__ == "__main__":
    main()
