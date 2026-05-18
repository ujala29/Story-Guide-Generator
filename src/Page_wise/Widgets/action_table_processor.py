"""
action_table_processor.py
=========================
Processor for ACTION_TABLE widget type.

Used for tables on action/targeting pages:
  - Payer/plan opportunity summary (with LOB bar chart)
  - Practice/PCP targeting list
  - Member-level targeting list

Template structure (from Risk story guide page 14, 17):
  page_intro        â€” what shift this page represents (only for first widget on page)
  group_intro       â€” what this specific table does
  column_table[]    â€” per column: {column, what_to_look_for}
  italic_callout    â€” the single most important prioritization insight
"""

import json
import sys
from pathlib import Path
from openai import OpenAI

_SRC = str(Path(__file__).resolve().parent.parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.llm_client import llm_chat
from utils.json_utils import parse_llm_json


ACTION_TABLE_SYSTEM = """You are a technical documentation writer producing content for a BI dashboard story guide.
Your audience is a healthcare analyst or care manager reading this guide to take action.

You are writing an action page table section. This page shifts from "what is the gap"
to "who do we target." Tables on this page are operational prioritization tools.

For each table:
- group_intro: 1-2 sentences explaining what this table enables operationally.
  Be action-oriented â€” what decision does the reader make using this table?
- column_table: for each column, explain what it measures AND what signal makes
  a row a high-priority target. Frame as "look for rows where X..."
- italic_callout: the single most important prioritization rule for this table.
  The one thing a reader must not miss when using it for outreach decisions.

Output valid JSON only. No explanation, no markdown fences."""


def build_action_table_prompt(
    widget: dict,
    visuals: list,
    funnel_context: dict,
) -> str:

    # separate table visual from any companion chart (e.g. LOB bar chart)
    table_visual  = next(
        (v for v in visuals if v.get("type") in ("pivotTable", "tableEx")), None
    )
    chart_visuals = [
        v for v in visuals
        if v.get("type") not in ("pivotTable", "tableEx")
    ]

    if not table_visual:
        table_visual = visuals[0] if visuals else {}

    measures    = table_visual.get("measures", []) if table_visual else []
    row_dims    = table_visual.get("row_dimensions", []) if table_visual else []
    cols_used   = table_visual.get("columns_used", []) if table_visual else []

    measure_lines = "\n".join(
        f"  - {m.get('display_name_in_visual') or m['name']}: {m.get('definition','')[:100]}"
        for m in measures
    )

    row_dim_str = ", ".join(row_dims) if row_dims else "unknown"

    schema = """{
  "widget_id": "<widget_id>",
  "widget_type": "ACTION_TABLE",
  "widget_name": "<widget_name>",
  "screenshot_label": "<screenshot_label>",
  "group_intro": "1-2 sentences: what this widget enables operationally and what decision the reader makes with it",
  "bar_chart": {
    "name": "chart title",
    "visual_id": "<visual_id>",
    "definition": "1 sentence: what this chart shows and what the reader looks for in it"
  },
  "column_table": [
    {
      "column": "column display name",
      "what_to_look_for": "what this column measures AND what value makes a row a high-priority target"
    }
  ],
  "italic_callout": "the single most important prioritization rule"
}"""

    # only include bar_chart slot if companion chart exists
    if not chart_visuals:
        schema = """{
  "widget_id": "<widget_id>",
  "widget_type": "ACTION_TABLE",
  "widget_name": "<widget_name>",
  "screenshot_label": "<screenshot_label>",
  "group_intro": "1-2 sentences: what this table enables operationally",
  "column_table": [
    {
      "column": "column display name",
      "what_to_look_for": "what this column measures AND what makes a row high-priority"
    }
  ],
  "italic_callout": "the single most important prioritization rule"
}"""

    # companion chart instruction
    bar_chart_instruction = ""
    if chart_visuals:
        chart_titles = ", ".join(v.get("title","") for v in chart_visuals)
        chart_ids    = ", ".join(v.get("visual_id","") for v in chart_visuals)
        bar_chart_instruction = (
            f"\nCOMPANION CHART: '{chart_titles}' (visual_id: {chart_ids})\n"
            f"Fill the bar_chart slot with: name, visual_id, and a 1-sentence definition "
            f"of what this chart shows and what the reader looks for."
        )

    return f"""Dashboard: {funnel_context.get('dashboard_name')}
Page: {widget.get('page')} (ACTION page)
Widget: {widget.get('widget_name')}
Sub-question: {widget.get('sub_question')}

TABLE:
  visual_id: {table_visual.get('visual_id') if table_visual else ''}
  title: {table_visual.get('title') if table_visual else ''}
  rows by: {row_dim_str}
  columns: {', '.join(cols_used)}
{bar_chart_instruction}

COLUMNS IN THIS TABLE:
{measure_lines}

Return JSON matching this structure:
{schema}

Fill in:
  widget_id: "{widget.get('widget_id')}"
  widget_name: "{widget.get('widget_name')}"
  screenshot_label: "{widget.get('screenshot_label')}"

Rules:
- column_table: cover ALL columns listed above
- Frame everything action-oriented â€” what does the reader DO with this?
- italic_callout: one sentence, the most important prioritization rule
- If bar_chart slot is in the schema, fill it with the companion chart details
- JSON only"""


def process_action_table(
    widget: dict,
    visuals: list,
    funnel_context: dict,
    client: OpenAI,
    model: str,
    max_retries: int = 3,
) -> dict:

    prompt = build_action_table_prompt(widget, visuals, funnel_context)

    for attempt in range(1, max_retries + 1):
        print(f"    attempt {attempt}/{max_retries}...")

        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.1,
                max_completion_tokens=6000,
                messages=[
                    {"role": "system", "content": ACTION_TABLE_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
            )
        except Exception as e:
            print(f"    LLM call failed ({type(e).__name__}): {e}")
            continue

        raw           = (response.choices[0].message.content or "").strip()
        finish_reason = response.choices[0].finish_reason

        if not raw:
            print(f"    empty response — finish_reason={finish_reason}")
            continue

        try:
            result = _parse_json(raw)
        except Exception as e:
            print(f"    parse failed ({type(e).__name__}): {e}")
            print(f"    finish_reason={finish_reason}  response_length={len(raw)} chars")
            print(f"    last 400 chars: ...{raw[-400:]}")
            continue

        if "column_table" not in result or not result.get("group_intro"):
            print(f"    missing column_table or group_intro")
            continue

        col_count = len(result["column_table"])
        print(f"    ok â€” {col_count} columns")
        return result

    raise RuntimeError(
        f"ACTION_TABLE failed for widget {widget.get('widget_id')} "
        f"after {max_retries} attempts"
    )


def _parse_json(raw: str) -> dict:
    return parse_llm_json(raw, label="action_table_processor")
