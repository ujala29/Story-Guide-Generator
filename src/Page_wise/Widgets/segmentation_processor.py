"""
segmentation_processor.py
==========================
Processor for SEGMENTATION widget type.

Multiple bar/donut/column charts each segmenting targeted gaps by a
member characteristic dimension for outreach prioritization.

Template structure (from Risk story guide pages 15-17):
  group_intro       — what these charts collectively enable for outreach strategy
  charts[]          — per chart:
    name            — chart title
    visual_id       — visual ID
    definition      — what dimension this chart segments by and why it matters for outreach
    segment_table[] — per segment: {segment, interpretation, outreach_action}

Each segment has:
  - interpretation: what this segment tells you about the member's clinical/access situation
  - outreach_action: what specific outreach action is indicated for this segment
"""

import json
import sys
from pathlib import Path
from openai import OpenAI

_SRC = str(Path(__file__).resolve().parent.parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.llm_client import llm_chat


SEGMENTATION_SYSTEM = """You are a technical documentation writer producing content for a BI dashboard story guide.
Your audience is a care manager or outreach coordinator using this guide to structure targeted interventions.

You are writing the outreach segmentation section. These charts distribute targeted
care gap patients across member characteristic dimensions — PCP visit frequency,
days since last visit, wellness visit status, risk bucket, cost of care, etc.

The purpose of each chart is to help the care team decide HOW to reach different
member subgroups — what outreach channel, what message, what urgency level.

For each chart:
- Write a 1-sentence definition of what dimension this chart segments by
  and why that dimension matters for outreach strategy
- Write a segment interpretation table with 2-4 meaningful segments:
  Each segment needs:
    interpretation: what this segment tells you about the member's situation
    outreach_action: the specific recommended outreach action for this segment
      (e.g. "schedule AWV", "mail/phone outreach", "chart review", "telehealth")

The outreach_action field is what makes this section different from a diagnostic table —
it must give the reader a concrete next step, not just an observation.

Output valid JSON only. No explanation, no markdown fences."""


def build_segmentation_prompt(
    widget: dict,
    visuals: list,
    funnel_context: dict,
) -> str:

    chart_lines = []
    for v in visuals:
        measures  = v.get("measures", [])
        cols      = v.get("columns_used", [])
        defn      = measures[0].get("definition", "")[:80] if measures else ""

        chart_lines.append(
            f"  visual_id: {v['visual_id']}\n"
            f"  title: {v['title']}\n"
            f"  type: {v.get('type','')}\n"
            f"  segments by: {', '.join(cols)}\n"
            f"  measure: {measures[0].get('name','') if measures else ''}\n"
            f"  measure def: {defn}"
        )

    charts_text = "\n\n".join(chart_lines)

    schema = """{
  "widget_id": "<widget_id>",
  "widget_type": "SEGMENTATION",
  "widget_name": "<widget_name>",
  "screenshot_label": "<screenshot_label>",
  "group_intro": "1-2 sentences: what these charts collectively enable — how they help structure outreach strategy across member subgroups",
  "charts": [
    {
      "name": "chart title",
      "visual_id": "<visual_id>",
      "definition": "1 sentence: what dimension this chart segments by and why it matters for outreach prioritization",
      "segment_table": [
        {
          "segment": "segment name or range (e.g. '0 PCP visits', '31-60 days', 'Due for AWV')",
          "interpretation": "what this segment tells you about the member's clinical or access situation",
          "outreach_action": "specific recommended action for this segment (e.g. 'schedule AWV', 'phone outreach', 'chart review')"
        }
      ]
    }
  ]
}"""

    return f"""Dashboard: {funnel_context.get('dashboard_name')}
Page: {widget.get('page')} (ACTION/targeting page)
Widget: {widget.get('widget_name')}
Sub-question: {widget.get('sub_question')}

These charts segment targeted care gap patients by member characteristics
to guide outreach strategy:

{charts_text}

Return JSON matching this structure:
{schema}

Fill in:
  widget_id: "{widget.get('widget_id')}"
  widget_name: "{widget.get('widget_name')}"
  screenshot_label: "{widget.get('screenshot_label')}"

Rules:
- All {len(visuals)} visual_ids must appear in the charts array
- segment_table: 2-4 segments per chart — meaningful ranges or categories, not all possible values
- outreach_action must be a specific action (not "investigate further" or "monitor")
- interpretation explains the member's situation; outreach_action tells what to DO
- JSON only"""


def process_segmentation(
    widget: dict,
    visuals: list,
    funnel_context: dict,
    client: OpenAI,
    model: str,
    max_retries: int = 3,
) -> dict:

    prompt = build_segmentation_prompt(widget, visuals, funnel_context)

    for attempt in range(1, max_retries + 1):
        print(f"    attempt {attempt}/{max_retries}...")

        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": SEGMENTATION_SYSTEM},
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
            print(f"    missing visual_ids: {missing} — retrying")
            continue

        chart_count = len(result["charts"])
        print(f"    ok — {chart_count} charts")
        return result

    raise RuntimeError(
        f"SEGMENTATION failed for widget {widget.get('widget_id')} "
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
