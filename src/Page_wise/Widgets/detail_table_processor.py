"""
detail_table_processor.py
=========================
Processor for DETAIL_TABLE widget type.

Used for segmentation/classification tables broken down by:
  - Payer / plan
  - Risk model / sub-model
  - Attribution status (Continued, Discontinued, Newly Enrolled)
  - Any other classification dimension

Template structure (from Risk story guide):

  FOR STANDARD COLUMN TABLE (payer/plan, risk model):
    group_intro      — what dimension this table introduces and why it matters (1-2 sentences)
    column_table[]   — per column: {column, what_to_look_for}
    patterns[]       — critical patterns across rows
    italic_callout   — most important watch-out

  FOR SEGMENT TABLE (attribution status — rows have meaningful behavioral expectations):
    group_intro      — what segmentation this table reveals
    segment_table[]  — per row segment: {segment, expected_behavior, red_flag}
    italic_callout   — most time-sensitive signal
"""

import json
from openai import OpenAI


DETAIL_TABLE_SYSTEM = """You are a technical documentation writer producing content for a BI dashboard story guide.
Your audience is a healthcare analyst reading this guide to understand the dashboard.

You are writing a detail table section. This is a pivot/matrix table that segments
the population by a specific dimension and shows performance metrics for each segment.

There are two formats depending on the table type:

FORMAT A — Column-focused table (payer/plan, risk model, geographic region):
  The table has many columns of metrics. The reader needs to know what each column
  measures and what to watch for in it. Write a column interpretation table.
  Also write critical cross-row patterns — what combinations of values across rows
  signal important states.

FORMAT B — Segment-focused table (attribution status, enrollment cohort, member category):
  The rows themselves have meaningful behavioral expectations. Write a segment
  interpretation table showing: for each row segment, what is the expected behavior
  and what is the red flag to watch for.

Choose the correct format based on what the table segments by.

For all tables:
- group_intro: 1-2 sentences explaining what dimension this table introduces and why it
  matters for the dashboard story. Connect it to the funnel question this table answers.
- italic_callout: the single most important insight or watch-out for this table.
  Something a reader might miss that is analytically critical.

Output valid JSON only. No explanation, no markdown fences."""


def build_detail_table_prompt(
    widget: dict,
    visuals: list,
    funnel_context: dict,
) -> str:
    """Build user prompt for DETAIL_TABLE widget."""

    v = visuals[0] if visuals else {}

    measures = v.get("measures", [])
    row_dims  = v.get("row_dimensions", [])
    cols_used = v.get("columns_used", [])

    measure_lines = "\n".join(
        f"  - {m['display_name_in_visual'] or m['name']}: {m.get('definition','')[:100]}"
        for m in measures
    )

    # detect table type from row dimensions
    row_dim_str  = ", ".join(row_dims) if row_dims else "unknown"
    cols_str     = ", ".join(cols_used) if cols_used else "unknown"

    # hint for the LLM about which format to use
    segment_keywords = ["attribution", "status", "enrollment", "cohort", "category"]
    is_segment = any(
        kw in row_dim_str.lower() or kw in cols_str.lower()
        for kw in segment_keywords
    )

    # known segment values for common table types — helps LLM use correct names
    known_segments_hint = ""
    if "attribution" in row_dim_str.lower() or "attribution" in cols_str.lower():
        known_segments_hint = (
            "\nKNOWN SEGMENTS for this table: "
            "Continued (members in both prior and current period), "
            "Discontinued (members who have left), "
            "Newly Enrolled (new entrants). "
            "Use exactly these three segment names."
        )

    format_hint = (
        "Use FORMAT B (segment-focused) — this table segments by a status/cohort "
        "dimension where each row has meaningful behavioral expectations."
        + known_segments_hint
        if is_segment else
        "Use FORMAT A (column-focused) — this table segments by a classification "
        "dimension where the columns carry the interpretation."
    )

    schema_a = """{
  "widget_id": "<widget_id>",
  "widget_type": "DETAIL_TABLE",
  "table_format": "COLUMN_FOCUSED",
  "widget_name": "<widget_name>",
  "screenshot_label": "<screenshot_label>",
  "group_intro": "1-2 sentences: what dimension this table introduces and why it matters",
  "column_table": [
    {
      "column": "column display name",
      "what_to_look_for": "what this column measures and what signal to watch for in it"
    }
  ],
  "patterns": [
    {
      "pattern": "cross-row pattern description",
      "interpretation": "what it means operationally"
    }
  ],
  "italic_callout": "most important insight or watch-out — null if none"
}"""

    schema_b = """{
  "widget_id": "<widget_id>",
  "widget_type": "DETAIL_TABLE",
  "table_format": "SEGMENT_FOCUSED",
  "widget_name": "<widget_name>",
  "screenshot_label": "<screenshot_label>",
  "group_intro": "1-2 sentences: what segmentation this table reveals and why it matters",
  "segment_table": [
    {
      "segment": "row segment name",
      "expected_behavior": "what normal/healthy behavior looks like for this segment",
      "red_flag": "what would be alarming and what it would signal operationally"
    }
  ],
  "italic_callout": "most time-sensitive signal — null if none"
}"""

    schema = schema_b if is_segment else schema_a

    return f"""Dashboard: {funnel_context.get('dashboard_name')}
Page: {widget.get('page')}
Widget: {widget.get('widget_name')}
Sub-question: {widget.get('sub_question')}
Funnel position: {widget.get('funnel_position')}

TABLE DETAILS:
  Row dimension(s): {row_dim_str}
  Column dimension(s): {cols_str}
  Visual type: {v.get('type','')}

COLUMNS IN THIS TABLE (measures shown per row):
{measure_lines}

{format_hint}

Return JSON matching this structure:
{schema}

Fill in:
  widget_id: "{widget.get('widget_id')}"
  widget_name: "{widget.get('widget_name')}"
  screenshot_label: "{widget.get('screenshot_label')}"

Rules:
- column_table must cover ALL columns listed above (for FORMAT A)
- segment_table must cover all known segments for this dimension (for FORMAT B)
- italic_callout: one sentence, the single most important analytical insight
- JSON only"""


def process_detail_table(
    widget: dict,
    visuals: list,
    funnel_context: dict,
    client: OpenAI,
    model: str,
    max_retries: int = 3,
) -> dict:
    """Call LLM to fill DETAIL_TABLE slots. Returns filled content dict."""

    prompt = build_detail_table_prompt(widget, visuals, funnel_context)

    for attempt in range(1, max_retries + 1):
        print(f"    attempt {attempt}/{max_retries}...")

        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            max_tokens=3000,
            messages=[
                {"role": "system", "content": DETAIL_TABLE_SYSTEM},
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

        # validate required fields
        fmt = result.get("table_format", "")
        if fmt == "COLUMN_FOCUSED" and not result.get("column_table"):
            print(f"    missing column_table")
            continue
        if fmt == "SEGMENT_FOCUSED" and not result.get("segment_table"):
            print(f"    missing segment_table")
            continue
        if "group_intro" not in result:
            print(f"    missing group_intro")
            continue

        print(f"    ok — format={fmt}")
        return result

    raise RuntimeError(
        f"DETAIL_TABLE failed for widget {widget.get('widget_id')} "
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
