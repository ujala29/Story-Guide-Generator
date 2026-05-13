"""
widget_group_writer.py
======================
Stage 3B — Widget Content Generator

For a given page, processes all widget groups from funnel_map.json
and generates the story guide content for each one.

One LLM call per widget. All widget content for the page written to
one JSON file.

CURRENTLY IMPLEMENTED:
  KPI_CARD_ROW    — KPI cards with direction tables and cross-reading patterns
  TREND_LINES     — Trend line charts grouped by theme
  DETAIL_TABLE    — Segmentation/classification tables (payer, model, attribution)
  CLINICAL_PAIR   — Disease bar chart + risk factor detail table
  ENTITY_SCATTER  — Entity table (provider/practice) + scatter plot
  MULTI_CHART     — Operational breakdown charts (gap closure donuts, etc.)

Run:
  python widget_group_writer.py --page "Overview LY"
  python widget_group_writer.py --page "Risk capture potential"
  python widget_group_writer.py --all
  python widget_group_writer.py --page "Overview LY" --workers 9
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import json
import os
import sys
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

from Widgets.trend_lines_processor import process_trend_lines
from Widgets.detail_table_processor import process_detail_table
from Widgets.clinical_pair_processor import process_clinical_pair
from Widgets.entity_scatter_processor import process_entity_scatter
from Widgets.multi_chart_processor import process_multi_chart
from Widgets.action_table_processor import process_action_table
from Widgets.segmentation_processor import process_segmentation

load_dotenv()

TF_MODEL = os.getenv("TF_MODEL", "internal-bedrock/sonnet-46")

_SRC = str(Path(__file__).resolve().parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.llm_client import llm_chat, get_client


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_project_root() -> Path:
    """
    Walk up from this file until we find the project root.
    Project root contains both 'output/' and 'config/' folders.
    Handles running from src/stage3/ or app/story/ or project root.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "output").exists() and (parent / "config").exists():
            return parent
    # fallback: walk up looking for run.py
    for parent in Path(__file__).resolve().parents:
        if (parent / "run.py").exists():
            return parent
    return Path(__file__).resolve().parent.parent.parent


def load_json(path: Path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def page_to_slug(page_name: str) -> str:
    """'Overview LY' -> 'overview_ly'"""
    return page_name.lower().replace(" ", "_").replace("/", "_")


def call_llm(system: str, user: str, max_tokens: int = 4000) -> str:
    return llm_chat(
        [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.1,
        max_completion_tokens=max_tokens,
    )


def parse_json_response(raw: str) -> dict | list:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        while lines and lines[-1].strip() in ("```", ""):
            lines.pop()
        text = "\n".join(lines).strip()
    return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# Widget type detection
# ─────────────────────────────────────────────────────────────────────────────

CARD_TYPES = {"card", "cardVisual", "multiRowCard"}

def detect_widget_type(widget: dict, visuals: list) -> str:
    """
    Detect widget type from its visual composition.
    Returns a type string used to select the right prompt and output schema.
    """
    vtypes  = {v.get("type", "") for v in visuals}
    pos     = widget.get("funnel_position", "")
    has_table   = any(v.get("type") in ("pivotTable", "tableEx") for v in visuals)
    has_bar     = any(v.get("type") in ("barChart", "clusteredBarChart", "columnChart") for v in visuals)
    has_line    = any(v.get("type") == "lineChart" for v in visuals)
    has_scatter = any(v.get("type") == "scatterChart" for v in visuals)
    has_donut   = any(v.get("type") == "donutChart" for v in visuals)

    # KPI cards — all card/multiRowCard
    if vtypes <= CARD_TYPES:
        return "KPI_CARD_ROW"
    if vtypes - {"multiRowCard"} <= {"card", "cardVisual"}:
        return "KPI_CARD_ROW"

    # Trend lines — all line charts
    if vtypes <= {"lineChart"}:
        return "TREND_LINES"

    # Action page
    if pos == "ACTION":
        if has_table:
            return "ACTION_TABLE"
        return "SEGMENTATION"

    # Entity table + scatter
    if has_table and has_scatter:
        return "ENTITY_SCATTER"

    # Clinical pair — bar + table on disease/risk factor dimension
    if has_table and has_bar:
        cols = [c for v in visuals for c in v.get("columns_used", [])]
        if any("disease" in c or "risk_factor" in c or "risk_group" in c for c in cols):
            return "CLINICAL_PAIR"
        return "BREAKDOWN_WIDGET"

    # Single segmentation/detail table
    if has_table:
        return "DETAIL_TABLE"

    # Multiple bar/donut charts (gap closure donuts)
    if has_bar or has_donut:
        return "MULTI_CHART"

    return "DETAIL_TABLE"


# ─────────────────────────────────────────────────────────────────────────────
# Data builder — pull enriched visual data for visuals in a widget
# ─────────────────────────────────────────────────────────────────────────────

def get_widget_visuals(widget: dict, visual_lookup: dict) -> list:
    """Return list of enriched visual dicts for all visual_ids in this widget."""
    return [
        visual_lookup[vid]
        for vid in widget.get("visual_ids", [])
        if vid in visual_lookup
    ]


def get_unique_measures(visuals: list) -> list:
    """
    Return deduplicated list of measures across all visuals in the widget.
    Exclude multiRowCard display measures — they are YoY/MoM card indicators,
    not base metrics. The base metrics come from card/cardVisual visuals.
    Also strips 'Formatted ' prefix from measure names — these are display
    wrappers whose underlying metric is the same as the unprefixed version.
    """
    seen = set()
    result = []
    for v in visuals:
        if v.get("type") == "multiRowCard":
            continue
        for m in v.get("measures", []):
            name = m.get("name", "")
            # strip "Formatted " prefix for display — same underlying metric
            display_name = name.removeprefix("Formatted ").strip()
            if display_name and display_name not in seen:
                seen.add(display_name)
                result.append({
                    **m,
                    "name": display_name,
                })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# KPI_CARD_ROW — prompt + output schema
# ─────────────────────────────────────────────────────────────────────────────

KPI_SYSTEM = """You are a technical documentation writer producing content for a BI dashboard story guide.
Your audience is a healthcare analyst or quality leader reading this guide to understand the dashboard.

You are writing the KPI cards section. The output must match this exact structure and interpretation style:

For each metric:
- Write a 1-2 sentence definition in plain business language. What does this metric measure
  and what does it represent? Be specific — include what it is calculated from if relevant.
- Write the direction table: what does it mean when this metric is Increasing vs Decreasing?
  Be analytical, not generic. "Increasing = good" is not acceptable.
  Instead: what does an increase operationally signal? What should the reader check or do?
- Optionally include a 1-sentence italic callout connecting this metric to another related metric
  (e.g. "Documented Risk should always be read alongside Potential Risk")

For the cross-reading patterns (reading all cards together):
- Write 4-6 patterns — specific combinations of metrics moving in particular directions
- Each pattern must describe what that combination signals about the organization's actual state
- Patterns should be non-obvious — not just "everything up = good"

Output valid JSON only. No explanation, no markdown."""


def build_kpi_prompt(
    widget: dict,
    visuals: list,
    funnel_context: dict,
) -> str:
    """Build the user prompt for a KPI_CARD_ROW widget."""

    measures = get_unique_measures(visuals)

    # format measures for the prompt
    measure_lines = []
    for m in measures:
        measure_lines.append(
            f"  metric: {m['name']}\n"
            f"  definition: {m.get('definition', '')}\n"
            f"  dax: {m.get('dax', '')[:100]}"
        )
    measures_text = "\n\n".join(measure_lines)

    schema = """{
  "widget_id": "<widget_id>",
  "widget_type": "KPI_CARD_ROW",
  "widget_name": "<widget_name>",
  "screenshot_label": "<screenshot_label>",
  "group_intro": "1-2 sentences: what this KPI row represents and how it should be read as a system",
  "metrics": [
    {
      "name": "metric name",
      "definition": "1-2 sentence plain-language definition",
      "direction_table": [
        {"direction": "Increasing", "interpretation": "what an increase signals operationally"},
        {"direction": "Decreasing", "interpretation": "what a decrease signals operationally"}
      ],
      "italic_callout": "optional 1-sentence connecting insight — null if not needed"
    }
  ],
  "reading_together": {
    "heading": "Reading the cards together",
    "patterns": [
      {"pattern": "Metric A ↑, Metric B ↓", "interpretation": "what this combination means"},
      {"pattern": "...", "interpretation": "..."}
    ]
  }
}"""

    return f"""Dashboard: {funnel_context.get('dashboard_name')}
Page: {widget.get('page')}
Widget: {widget.get('widget_name')}
Sub-question this widget answers: {widget.get('sub_question')}

These are the KPI cards in this widget group:

{measures_text}

Produce the story guide content for this KPI card group.
Use the metric definitions above as the foundation — enrich them with analytical interpretation.

Return JSON matching this exact structure:
{schema}

Fill in:
  widget_id: "{widget.get('widget_id')}"
  widget_name: "{widget.get('widget_name')}"
  screenshot_label: "{widget.get('screenshot_label')}"

Rules:
- Every metric listed above must appear in the metrics array
- Direction table MUST use exactly the key "interpretation" — not "operationally signals" or any other key
- Direction interpretations must be specific and analytical, not generic
- Cross-reading patterns must be combinations of 2+ metrics — not single metric observations
- italic_callout: only include when there is a genuinely important relationship between this metric and another
- JSON only"""


def process_kpi_card_row(
    widget: dict,
    visuals: list,
    funnel_context: dict,
    max_retries: int = 3,
) -> dict:
    """Call LLM to fill KPI card row slots. Returns filled content dict."""

    prompt = build_kpi_prompt(widget, visuals, funnel_context)

    for attempt in range(1, max_retries + 1):
        print(f"    attempt {attempt}/{max_retries}...")
        raw = call_llm(KPI_SYSTEM, prompt, max_tokens=3000)

        if not raw:
            print(f"    empty response")
            continue

        try:
            result = parse_json_response(raw)
        except Exception as e:
            print(f"    parse failed: {e}")
            print(f"    last 200 chars: ...{raw[-200:]}")
            continue

        # basic validation
        if "metrics" not in result or not result["metrics"]:
            print(f"    missing metrics array")
            continue
        if "reading_together" not in result:
            print(f"    missing reading_together")
            continue

        print(f"    ok — {len(result['metrics'])} metrics, "
              f"{len(result['reading_together'].get('patterns', []))} patterns")
        return result

    raise RuntimeError(
        f"KPI card row failed for widget {widget.get('widget_id')} "
        f"after {max_retries} attempts"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch — route each widget to the right processor
# ─────────────────────────────────────────────────────────────────────────────

def process_widget(
    widget: dict,
    visual_lookup: dict,
    funnel_context: dict,
) -> dict:
    """
    Detect widget type and call the right processor.
    Returns filled content dict, or a placeholder for unimplemented types.
    """
    visuals     = get_widget_visuals(widget, visual_lookup)
    widget_type = detect_widget_type(widget, visuals)

    print(f"  [{widget['widget_id']}] {widget['widget_name']} "
          f"-> {widget_type} ({len(visuals)} visuals)")

    client = get_client()

    if widget_type == "KPI_CARD_ROW":
        return process_kpi_card_row(widget, visuals, funnel_context)

    if widget_type == "TREND_LINES":
        return process_trend_lines(widget, visuals, funnel_context, client, TF_MODEL)

    if widget_type == "DETAIL_TABLE":
        return process_detail_table(widget, visuals, funnel_context, client, TF_MODEL)

    if widget_type == "CLINICAL_PAIR":
        return process_clinical_pair(widget, visuals, funnel_context, client, TF_MODEL)

    if widget_type == "ENTITY_SCATTER":
        return process_entity_scatter(widget, visuals, funnel_context, client, TF_MODEL)

    if widget_type == "MULTI_CHART":
        return process_multi_chart(widget, visuals, funnel_context, client, TF_MODEL)

    if widget_type == "ACTION_TABLE":
        return process_action_table(widget, visuals, funnel_context, client, TF_MODEL)

    if widget_type == "SEGMENTATION":
        return process_segmentation(widget, visuals, funnel_context, client, TF_MODEL)

    # placeholder for unimplemented types
    return {
        "widget_id":   widget["widget_id"],
        "widget_type": widget_type,
        "widget_name": widget["widget_name"],
        "status":      "NOT_IMPLEMENTED",
        "note":        f"Widget type {widget_type} not yet implemented",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page processor
# ─────────────────────────────────────────────────────────────────────────────

def process_page(
    page_name: str,
    funnel_map: dict,
    visual_lookup: dict,
    out_dir: Path,
    force: bool = False,
    max_workers: int = 3,
) -> None:
    """Process all widgets on a page and write output JSON."""

    slug     = page_to_slug(page_name)
    out_path = out_dir / f"{slug}.json"

    # get widgets for this page
    widgets = [
        w for w in funnel_map.get("widgets", [])
        if w.get("page") == page_name
    ]

    if not widgets:
        print(f"[widget_writer] no widgets found for page '{page_name}'")
        return

    # cache check
    if not force and out_path.exists():
        existing = load_json(out_path)
        if existing and existing.get("content_hash") == funnel_map.get("_meta", {}).get("content_hash"):
            print(f"[widget_writer] cache hit for '{page_name}' — use --force to re-run")
            return

    print(f"\n[widget_writer] page: '{page_name}' ({len(widgets)} widgets) "
          f"— {max_workers} parallel workers")

    funnel_context = {
        "dashboard_name":         funnel_map.get("dashboard_name"),
        "domain_context":         funnel_map.get("domain_context"),
        "funnel_question_top":    funnel_map.get("funnel_question_top"),
        "funnel_question_middle": funnel_map.get("funnel_question_middle"),
        "funnel_question_bottom": funnel_map.get("funnel_question_bottom"),
        "funnel_question_action": funnel_map.get("funnel_question_action"),
    }

    # run all widgets concurrently — each is an independent LLM call
    # results dict keyed by widget_id to preserve reading_order on merge
    results: dict[str, dict] = {}
    errors:  dict[str, str]  = {}
    print_lock = threading.Lock()

    def run_widget(widget: dict) -> tuple[str, dict]:
        wid = widget["widget_id"]
        try:
            content = process_widget(widget, visual_lookup, funnel_context)
            with print_lock:
                print(f"  ✓ [{wid}] {widget['widget_name']}")
            return wid, content
        except Exception as e:
            with print_lock:
                print(f"  ✗ [{wid}] {widget['widget_name']} — ERROR: {e}")
            return wid, {
                "widget_id":   wid,
                "widget_type": "ERROR",
                "widget_name": widget["widget_name"],
                "status":      "ERROR",
                "note":        str(e),
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_widget, w): w for w in widgets}
        for future in as_completed(futures):
            wid, content = future.result()
            results[wid] = content

    # restore reading_order from funnel_map
    widget_contents = [
        results[w["widget_id"]]
        for w in widgets
        if w["widget_id"] in results
    ]

    result = {
        "page":         page_name,
        "page_slug":    slug,
        "content_hash": funnel_map.get("_meta", {}).get("content_hash"),
        "widgets":      widget_contents,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    implemented   = sum(1 for w in widget_contents if w.get("status") != "NOT_IMPLEMENTED")
    unimplemented = len(widget_contents) - implemented
    print(f"[widget_writer] written: {out_path}")
    print(f"[widget_writer] done: {implemented} implemented, {unimplemented} pending")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate widget content for one or all pages"
    )
    parser.add_argument("--dashboard", default="risk-dash")
    parser.add_argument("--page", default=None,
                        help="Page display name e.g. 'Overview LY'")
    parser.add_argument("--all", dest="all_pages", action="store_true",
                        help="Process all pages (default behaviour — kept for compatibility)")
    parser.add_argument("--workers", type=int, default=3,
                        help="Parallel LLM calls per page (default: 3). "
                             "Increase if your endpoint has high rate limits, "
                             "decrease if you see 429 errors.")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if output exists")
    args = parser.parse_args()

    root     = get_project_root()
    stage3   = root / "output" / "dashboards" / args.dashboard / "page_wise"
    out_dir  = stage3 / "widget_content"

    # load inputs
    funnel_map  = load_json(stage3 / "funnel_map.json")
    llm_input   = load_json(stage3 / "funnel_llm_input.json")

    if not funnel_map:
        raise FileNotFoundError(f"funnel_map.json not found at {stage3}")
    if not llm_input:
        raise FileNotFoundError(f"funnel_llm_input.json not found at {stage3}")

    # build visual lookup: visual_id -> visual dict
    visual_lookup = {v["visual_id"]: v for v in llm_input.get("visuals", [])}
    print(f"[widget_writer] dashboard   : {args.dashboard}")
    print(f"[widget_writer] visuals     : {len(visual_lookup)}")

    # determine which pages to process
    # preserve insertion order from widgets list (set would scramble it)
    seen: set[str] = set()
    all_page_names: list[str] = []
    for w in funnel_map.get("widgets", []):
        p = w.get("page", "")
        if p and p not in seen:
            seen.add(p)
            all_page_names.append(p)

    # thumb rule: Overview pages always run first, then the rest in order
    overview_pages = [p for p in all_page_names if "overview" in p.lower()]
    other_pages    = [p for p in all_page_names if "overview" not in p.lower()]
    ordered_pages  = overview_pages + other_pages

    if args.page:
        pages_to_process = [args.page]
    else:
        # default (and --all): run every page, overview first.
        # The cache check inside process_page auto-skips pages whose output
        # already matches the current content_hash — no --force needed for
        # pages that simply haven't been generated yet.
        pages_to_process = ordered_pages

    print(f"[widget_writer] pages       : {pages_to_process}")

    for page_name in pages_to_process:
        process_page(
            page_name     = page_name,
            funnel_map    = funnel_map,
            visual_lookup = visual_lookup,
            out_dir       = out_dir,
            force         = args.force,
            max_workers   = args.workers,
        )


if __name__ == "__main__":
    main()
