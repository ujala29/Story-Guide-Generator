"""
multi_chart_processor.py
========================
Processor for MULTI_CHART widget type.

Multiple donut/bar/pie charts that each segment the same metric by a
different operational dimension (visit type, network status, provider type,
channel, geography).

Template structure (from Risk story guide â€” gap closure patterns):
  group_intro       â€” what these charts collectively reveal (operational intelligence)
  charts[]          â€” per chart:
    name            â€” chart title
    visual_id       â€” visual ID
    definition      â€” what dimension this chart segments by (1 sentence)
    segment_table[] â€” per segment: {segment, interpretation}
"""

import json
import sys
from pathlib import Path
from openai import OpenAI

_SRC = str(Path(__file__).resolve().parent.parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.llm_client import llm_chat


MULTI_CHART_SYSTEM = """You are a technical documentation writer producing content for a BI dashboard story guide.
Your audience is a healthcare analyst reading this guide to understand the dashboard.

You are writing a multi-chart operational breakdown section. This widget contains
multiple donut or bar charts, each segmenting the same underlying metric by a
different operational dimension.

These charts are NOT diagnostic trend charts â€” they are operational intelligence.
They answer: "Through what channel / in what setting / by what type is this happening?"

For the group_intro:
- Explain what these charts collectively reveal â€” the operational picture of how
  the metric is distributed across channels, settings, or types
- Note that these charts are descriptive, not prescriptive â€” they show the current
  pattern, not what the target should be

For each chart:
- Write a 1-sentence definition of what dimension it segments by
- Write a segment interpretation table: for each possible dominant segment pattern,
  what does it mean operationally? What should the reader investigate or act on?
- Segments should be patterns (e.g. "Outpatient dominant", "Significant out-of-network")
  not just literal segment names â€” describe the meaningful pattern, not just enumerate values

Output valid JSON only. No explanation, no markdown fences."""


def build_multi_chart_prompt(
    widget: dict,
    visuals: list,
    funnel_context: dict,
) -> str:

    chart_lines = []
    for v in visuals:
        measures    = v.get("measures", [])
        cols        = v.get("columns_used", [])
        primary_def = measures[0].get("definition", "")[:100] if measures else ""

        chart_lines.append(
            f"  visual_id: {v['visual_id']}\n"
            f"  title: {v['title']}\n"
            f"  type: {v.get('type','')}\n"
            f"  segments by: {', '.join(cols)}\n"
            f"  measure definition: {primary_def}"
        )

    charts_text = "\n\n".join(chart_lines)

    schema = """{
  "widget_id": "<widget_id>",
  "widget_type": "MULTI_CHART",
  "widget_name": "<widget_name>",
  "screenshot_label": "<screenshot_label>",
  "group_intro": "1-2 sentences: what these charts collectively reveal as operational intelligence",
  "charts": [
    {
      "name": "chart title",
      "visual_id": "<visual_id>",
      "definition": "1 sentence: what dimension this chart segments the metric by",
      "segment_table": [
        {
          "segment": "dominant pattern name (e.g. 'Outpatient dominant', 'Mostly in-network')",
          "interpretation": "what this pattern means operationally and what to investigate or act on"
        }
      ]
    }
  ]
}"""

    return f"""Dashboard: {funnel_context.get('dashboard_name')}
Page: {widget.get('page')}
Widget: {widget.get('widget_name')}
Sub-question: {widget.get('sub_question')}

These charts all segment the same metric by different operational dimensions:

{charts_text}

Return JSON matching this structure:
{schema}

Fill in:
  widget_id: "{widget.get('widget_id')}"
  widget_name: "{widget.get('widget_name')}"
  screenshot_label: "{widget.get('screenshot_label')}"

Rules:
- All {len(visuals)} visual_ids must appear in the charts array
- segment_table: 2-3 dominant pattern interpretations per chart (not every possible value)
- Patterns should describe meaningful operational states, not just enumerate segment names
- JSON only"""


def process_multi_chart(
    widget: dict,
    visuals: list,
    funnel_context: dict,
    client: OpenAI,
    model: str,
    max_retries: int = 3,
) -> dict:

    prompt = build_multi_chart_prompt(widget, visuals, funnel_context)

    for attempt in range(1, max_retries + 1):
        print(f"    attempt {attempt}/{max_retries}...")

        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            max_completion_tokens=6000,
            messages=[
                {"role": "system", "content": MULTI_CHART_SYSTEM},
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

        # validate all visual_ids present
        input_ids  = {v["visual_id"] for v in visuals}
        output_ids = {c.get("visual_id") for c in result["charts"]}
        missing    = input_ids - output_ids
        if missing:
            print(f"    missing visual_ids: {missing}")
            continue

        chart_count = len(result["charts"])
        print(f"    ok â€” {chart_count} charts")
        return result

    raise RuntimeError(
        f"MULTI_CHART failed for widget {widget.get('widget_id')} "
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
