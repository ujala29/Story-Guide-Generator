"""
clinical_pair_processor.py
==========================
Processor for CLINICAL_PAIR widget type.

A clinical pair is a bar/horizontal chart ranking items by a clinical dimension
(disease, condition, HCC category) paired with a detail table showing the same
items with full metric columns.

Template structure (from Risk story guide):
  group_intro       — what shift these visuals represent ("from which practice -> to which HCC")
  bar_chart:
    name            — chart title
    definition      — what it ranks and what position means
    patterns[]      — what high/low/chronic conditions signal
  detail_table:
    name            — table title
    column_table[]  — per column: {column, what_to_look_for}
  italic_callout    — most important combined insight
"""

import json
import sys
from pathlib import Path
from openai import OpenAI

_SRC = str(Path(__file__).resolve().parent.parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.llm_client import llm_chat


CLINICAL_PAIR_SYSTEM = """You are a technical documentation writer producing content for a BI dashboard story guide.
Your audience is a healthcare analyst reading this guide to understand the dashboard.

You are writing a clinical/categorical breakdown section. This widget contains:
1. A bar chart that ranks clinical items (diseases, conditions, HCC categories) by a metric
2. A detail table showing the same items with full performance columns

This section moves the reader from "who is responsible" (practice/PCP level) to
"what specifically is the clinical problem" (condition/disease level).

For the bar chart:
- Write what it ranks and what the position of an item means
- Write a pattern table: what does it mean when a condition is at the far left (low value)?
  What does a very high value mean? Are chronic conditions particularly important?

For the detail table:
- Write a column interpretation table: for each column, what does it measure
  and what signal should the reader look for in it?

For the italic_callout:
- Write the single most important combined insight — what should a reader
  prioritize when they look at these two visuals together?

Output valid JSON only. No explanation, no markdown fences."""


def build_clinical_pair_prompt(
    widget: dict,
    visuals: list,
    funnel_context: dict,
) -> str:

    bar_visual   = next((v for v in visuals if "bar" in v.get("type","").lower() or "Bar" in v.get("type","")), None)
    table_visual = next((v for v in visuals if v.get("type") in ("pivotTable", "tableEx")), None)

    if not bar_visual:
        bar_visual = visuals[0] if visuals else {}
    if not table_visual:
        table_visual = visuals[-1] if len(visuals) > 1 else visuals[0] if visuals else {}

    # bar chart info
    bar_measures = bar_visual.get("measures", [])
    bar_measure_lines = "\n".join(
        f"  - {m['display_name_in_visual'] or m['name']}: {m.get('definition','')[:100]}"
        for m in bar_measures
    )
    bar_col = ", ".join(bar_visual.get("columns_used", []))

    # table info
    table_measures = table_visual.get("measures", [])
    table_measure_lines = "\n".join(
        f"  - {m['display_name_in_visual'] or m['name']}: {m.get('definition','')[:100]}"
        for m in table_measures
    )
    table_cols = ", ".join(table_visual.get("columns_used", []))
    table_rows = ", ".join(table_visual.get("row_dimensions", []))

    schema = """{
  "widget_id": "<widget_id>",
  "widget_type": "CLINICAL_PAIR",
  "widget_name": "<widget_name>",
  "screenshot_label": "<screenshot_label>",
  "group_intro": "1-2 sentences: what analytical shift this section represents — moving from entity-level to condition-level detail",
  "bar_chart": {
    "name": "chart title",
    "visual_id": "<bar_visual_id>",
    "definition": "what this chart ranks and what the position of an item on the axis means",
    "patterns": [
      {
        "pattern": "what to look for (e.g. a condition with very low recapture rate)",
        "interpretation": "what it means operationally and what action it suggests"
      }
    ]
  },
  "detail_table": {
    "name": "table title",
    "visual_id": "<table_visual_id>",
    "column_table": [
      {
        "column": "column display name",
        "what_to_look_for": "what this column measures and what signal to watch for"
      }
    ]
  },
  "italic_callout": "the single most important combined insight from reading both visuals together"
}"""

    return f"""Dashboard: {funnel_context.get('dashboard_name')}
Page: {widget.get('page')}
Widget: {widget.get('widget_name')}
Sub-question: {widget.get('sub_question')}

BAR CHART:
  visual_id: {bar_visual.get('visual_id')}
  title: {bar_visual.get('title')}
  type: {bar_visual.get('type')}
  dimension: {bar_col}
  measures:
{bar_measure_lines}

DETAIL TABLE:
  visual_id: {table_visual.get('visual_id')}
  title: {table_visual.get('title')}
  type: {table_visual.get('type')}
  rows by: {table_rows}
  columns: {table_cols}
  measures:
{table_measure_lines}

Return JSON matching this structure:
{schema}

Fill in:
  widget_id: "{widget.get('widget_id')}"
  widget_name: "{widget.get('widget_name')}"
  screenshot_label: "{widget.get('screenshot_label')}"
  bar_visual_id: "{bar_visual.get('visual_id')}"
  table_visual_id: "{table_visual.get('visual_id')}"

Rules:
- bar chart patterns: 3-4 patterns covering low/high/chronic condition scenarios
- column_table: cover ALL measures listed for the detail table
- italic_callout: one sentence, the combined prioritization insight
- JSON only"""


def process_clinical_pair(
    widget: dict,
    visuals: list,
    funnel_context: dict,
    client: OpenAI,
    model: str,
    max_retries: int = 3,
) -> dict:

    prompt = build_clinical_pair_prompt(widget, visuals, funnel_context)

    for attempt in range(1, max_retries + 1):
        print(f"    attempt {attempt}/{max_retries}...")

        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            max_tokens=3000,
            messages=[
                {"role": "system", "content": CLINICAL_PAIR_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()

        if not raw:
            print(f"    empty response")
            continue

        try:
            result = _parse_json(raw)
        except Exception as e:
            print(f"    parse failed: {e}")
            print(f"    last 200 chars: ...{raw[-200:]}")
            continue

        if "bar_chart" not in result or "detail_table" not in result:
            print(f"    missing bar_chart or detail_table")
            continue

        bar_pats = len(result["bar_chart"].get("patterns", []))
        col_cols = len(result["detail_table"].get("column_table", []))
        print(f"    ok — bar_patterns={bar_pats}  table_columns={col_cols}")
        return result

    raise RuntimeError(
        f"CLINICAL_PAIR failed for widget {widget.get('widget_id')} "
        f"after {max_retries} attempts"
    )


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        while lines and lines[-1].strip() in ("```", ""):
            lines.pop()
        text = "\n".join(lines).strip()
    return json.loads(text)
