"""
trend_lines_processor.py
========================
Processor for TREND_LINES widget type.

Template structure (from Risk story guide):
  group_intro      — what the time dimension adds (1-2 sentences)
  charts[]         — per line chart:
    name           — chart title (e.g. "Members and Eligible Population trends")
    definition     — what this chart tracks and why it matters
    patterns[]     — only for charts with meaningful visual patterns (optional)
      pattern      — what visual shape/movement to look for
      interpretation — what it means operationally
    italic_callout — optional connecting insight (only on most important charts)

Charts are grouped by theme when multiple charts cover the same topic
(e.g. Members + Eligible Population -> one sub-section together).
"""

import json
import sys
from pathlib import Path
from openai import OpenAI

_SRC = str(Path(__file__).resolve().parent.parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.llm_client import llm_chat


TREND_SYSTEM = """You are a technical documentation writer producing content for a BI dashboard story guide.
Your audience is a healthcare analyst reading this guide to understand the dashboard.

You are writing the "Trends over time" section. This section covers ALL trend line charts
on the dashboard page — each chart compares current year vs previous year, month by month.

For each chart or chart group:
- Write a 1-2 sentence definition explaining what this chart tracks and what analytical
  context it provides. Be specific about what the two lines represent and why the comparison matters.
- For the most analytically important charts, include a pattern table showing what
  specific visual shapes or movements mean operationally (e.g. "Current line rising toward
  potential line" = gaps narrowing). Not every chart needs a pattern table — only include
  one when there are genuinely meaningful visual patterns to interpret.
- Include an italic_callout only for the single most important chart in the group
  (the one that has the most diagnostic value). This is a 1-sentence insight that
  connects this chart to another metric or tells the reader what to do when they
  see something alarming.

Charts that track the same theme should be grouped into one sub-section
(e.g. Members trend + Eligible Population trend -> "Members and Eligible Population trends").

Output valid JSON only. No explanation, no markdown fences."""


def build_trend_prompt(widget: dict, visuals: list, funnel_context: dict) -> str:
    """Build user prompt for TREND_LINES widget."""

    # build chart descriptions
    chart_lines = []
    for v in visuals:
        # get the primary measure (non-PY version if possible)
        measures = v.get("measures", [])
        primary = next(
            (m for m in measures if "PY" not in m["name"] and "previous" not in m.get("display_name_in_visual","").lower()),
            measures[0] if measures else {}
        )
        all_measure_names = [m["display_name_in_visual"] or m["name"] for m in measures]

        chart_lines.append(
            f"  chart: {v['title']}\n"
            f"  visual_id: {v['visual_id']}\n"
            f"  lines plotted: {', '.join(all_measure_names)}\n"
            f"  primary measure: {primary.get('name','')}\n"
            f"  definition: {primary.get('definition','')[:120]}"
        )

    charts_text = "\n\n".join(chart_lines)

    schema = """{
  "widget_id": "<widget_id>",
  "widget_type": "TREND_LINES",
  "widget_name": "<widget_name>",
  "screenshot_label": "<screenshot_label>",
  "group_intro": "1-2 sentences: what the time dimension adds and how to read these charts as a system",
  "charts": [
    {
      "name": "chart group name (e.g. 'Members and Eligible Population trends')",
      "visual_ids": ["id1", "id2"],
      "definition": "what these charts track and why the current vs previous year comparison matters",
      "patterns": [
        {
          "pattern": "what visual shape or movement to look for",
          "interpretation": "what it means operationally"
        }
      ],
      "italic_callout": "optional 1-sentence connecting insight — null if not the most important chart"
    }
  ]
}"""

    return f"""Dashboard: {funnel_context.get('dashboard_name')}
Page: {widget.get('page')}
Widget: {widget.get('widget_name')}
Sub-question: {widget.get('sub_question')}

These are all the trend line charts in this widget group:

{charts_text}

Produce the story guide content for this trend lines section.
Group related charts together into named sub-sections where they cover the same theme.

Return JSON matching this structure:
{schema}

Fill in:
  widget_id: "{widget.get('widget_id')}"
  widget_name: "{widget.get('widget_name')}"
  screenshot_label: "{widget.get('screenshot_label')}"

Rules:
- All visual_ids must appear in the charts array (distributed across chart groups)
- Pattern tables only for charts with genuinely meaningful visual patterns to interpret
- italic_callout only on the single most analytically important chart group
- Group charts by theme — do not list each chart separately if they cover the same topic
- JSON only"""


def process_trend_lines(
    widget: dict,
    visuals: list,
    funnel_context: dict,
    client: OpenAI,
    model: str,
    max_retries: int = 3,
) -> dict:
    """Call LLM to fill TREND_LINES slots. Returns filled content dict."""

    prompt = build_trend_prompt(widget, visuals, funnel_context)

    for attempt in range(1, max_retries + 1):
        print(f"    attempt {attempt}/{max_retries}...")

        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            max_tokens=3000,
            messages=[
                {"role": "system", "content": TREND_SYSTEM},
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

        if "charts" not in result or not result["charts"]:
            print(f"    missing charts array")
            continue

        # validate all visual_ids accounted for
        input_ids  = {v["visual_id"] for v in visuals}
        output_ids = {vid for c in result["charts"] for vid in c.get("visual_ids", [])}
        missing    = input_ids - output_ids
        if missing:
            print(f"    missing visual_ids: {missing} — retrying")
            continue

        chart_count = len(result["charts"])
        print(f"    ok — {chart_count} chart groups")
        return result

    raise RuntimeError(
        f"TREND_LINES failed for widget {widget.get('widget_id')} "
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
