"""
entity_scatter_processor.py
============================
Processor for ENTITY_SCATTER widget type.

An entity scatter widget contains:
1. A pivot table with rows by provider/practice/PCP/facility (entity-level)
2. A scatter plot showing the same entities on two axes (volume vs performance)

Template structure (from Risk story guide):
  group_intro       — what this section does (translates story to specific entity names)
  entity_table:
    name            — table title
    definition      — what this table shows and what analytical shift it represents
    column_table[]  — per column: {column, what_to_look_for}
    reading_patterns[] — patterns across entity rows
  scatter_plot:
    name            — scatter title
    definition      — what the axes represent and what quadrant position means
    position_table[] — quadrant/position interpretations
"""

import json
from openai import OpenAI


ENTITY_SCATTER_SYSTEM = """You are a technical documentation writer producing content for a BI dashboard story guide.
Your audience is a healthcare analyst reading this guide to understand the dashboard.

You are writing the entity-level accountability section. This widget contains:
1. A detail table with rows broken down by an entity (provider, practice, PCP, facility)
   showing performance metrics per entity
2. A scatter plot showing the same entities distributed across two axes

For the entity table:
- Write what this table does — it translates the aggregate story into specific accountable names
- Write a column interpretation table: for each column, what does it measure and
  what specific signal should the reader look for?
- Write reading patterns: what combinations of column values across rows signal
  specific operational states (e.g. high gap + low recapture = direct intervention target)

For the scatter plot:
- Write what the axes represent and what the four quadrant positions mean
- The upper-right quadrant (high on both axes) is always the highest-priority target

Output valid JSON only. No explanation, no markdown fences."""


def build_entity_scatter_prompt(
    widget: dict,
    visuals: list,
    funnel_context: dict,
) -> str:

    table_visual   = next((v for v in visuals if v.get("type") in ("pivotTable", "tableEx")), None)
    scatter_visual = next((v for v in visuals if v.get("type") == "scatterChart"), None)

    if not table_visual:
        table_visual = visuals[0] if visuals else {}
    if not scatter_visual and len(visuals) > 1:
        scatter_visual = visuals[-1]

    # table info
    table_measures = table_visual.get("measures", []) if table_visual else []
    table_measure_lines = "\n".join(
        f"  - {m['display_name_in_visual'] or m['name']}: {m.get('definition','')[:100]}"
        for m in table_measures
    )
    table_rows = ", ".join(table_visual.get("row_dimensions", [])) if table_visual else ""

    # scatter info
    scatter_measures = scatter_visual.get("measures", []) if scatter_visual else []
    scatter_measure_lines = "\n".join(
        f"  - {m['display_name_in_visual'] or m['name']}: {m.get('definition','')[:100]}"
        for m in scatter_measures
    ) if scatter_measures else "  (no measures — uses same entity dimension as table)"
    scatter_cols = ", ".join(scatter_visual.get("columns_used", [])) if scatter_visual else ""

    scatter_section = f"""SCATTER PLOT:
  visual_id: {scatter_visual.get('visual_id') if scatter_visual else 'none'}
  title: {scatter_visual.get('title') if scatter_visual else 'none'}
  columns: {scatter_cols}
  measures:
{scatter_measure_lines}""" if scatter_visual else "SCATTER PLOT: not present in this widget"

    schema = """{
  "widget_id": "<widget_id>",
  "widget_type": "ENTITY_SCATTER",
  "widget_name": "<widget_name>",
  "screenshot_label": "<screenshot_label>",
  "group_intro": "1-2 sentences: what this section does — translates aggregate performance into specific entity names",
  "entity_table": {
    "name": "table title",
    "visual_id": "<table_visual_id>",
    "definition": "what this table shows and what analytical purpose it serves at this layer",
    "column_table": [
      {
        "column": "column display name",
        "what_to_look_for": "what this column measures and what signal to watch for"
      }
    ],
    "reading_patterns": [
      {
        "pattern": "combination of column values across a row",
        "interpretation": "what this combination means and what action it suggests"
      }
    ]
  },
  "scatter_plot": {
    "name": "scatter plot title",
    "visual_id": "<scatter_visual_id>",
    "definition": "what the x and y axes represent and what the scatter plot reveals about the entity population",
    "position_table": [
      {
        "position": "quadrant or position description (e.g. upper-right, lower-left)",
        "interpretation": "what this position means and what priority it represents"
      }
    ]
  }
}"""

    return f"""Dashboard: {funnel_context.get('dashboard_name')}
Page: {widget.get('page')}
Widget: {widget.get('widget_name')}
Sub-question: {widget.get('sub_question')}

ENTITY TABLE:
  visual_id: {table_visual.get('visual_id') if table_visual else 'none'}
  title: {table_visual.get('title') if table_visual else 'none'}
  rows by: {table_rows}
  measures:
{table_measure_lines}

{scatter_section}

Return JSON matching this structure:
{schema}

Fill in:
  widget_id: "{widget.get('widget_id')}"
  widget_name: "{widget.get('widget_name')}"
  screenshot_label: "{widget.get('screenshot_label')}"
  table_visual_id: "{table_visual.get('visual_id') if table_visual else ''}"
  scatter_visual_id: "{scatter_visual.get('visual_id') if scatter_visual else ''}"

Rules:
- column_table: cover ALL measures listed for the entity table
- reading_patterns: 3-4 patterns covering high-priority / low-priority / declining entity scenarios
- position_table: cover all 4 quadrants of the scatter plot
- JSON only"""


def process_entity_scatter(
    widget: dict,
    visuals: list,
    funnel_context: dict,
    client: OpenAI,
    model: str,
    max_retries: int = 3,
) -> dict:

    prompt = build_entity_scatter_prompt(widget, visuals, funnel_context)

    for attempt in range(1, max_retries + 1):
        print(f"    attempt {attempt}/{max_retries}...")

        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            max_tokens=3000,
            messages=[
                {"role": "system", "content": ENTITY_SCATTER_SYSTEM},
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

        if "entity_table" not in result:
            print(f"    missing entity_table")
            continue

        col_count  = len(result["entity_table"].get("column_table", []))
        pat_count  = len(result["entity_table"].get("reading_patterns", []))
        has_scatter = "scatter_plot" in result
        print(f"    ok — columns={col_count}  patterns={pat_count}  scatter={has_scatter}")
        return result

    raise RuntimeError(
        f"ENTITY_SCATTER failed for widget {widget.get('widget_id')} "
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
