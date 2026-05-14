"""
funnel_mapper.py
================
Stage 3A — Step 2

Calls the LLM in THREE focused calls per page instead of one giant combined call.
This prevents visual ID loss on pages with 25+ visuals.

Call 1 — Funnel questions (tiny call, no visual IDs)
Call 2 — Classify visuals (flat dict: visual_id -> position)
Call 3 — Group per bucket (one focused call per TOP/MIDDLE/BOTTOM/ACTION bucket)

GENERIC PAGE DEDUPLICATION:
  Pages that share the same base name but differ only by a time-period
  suffix (LY, LM, YTD, MTD, Q1-Q4, Prior, Current, etc.) are treated
  as structural duplicates. Only the representative (first alphabetically
  or by order) is sent to the LLM. Others are recorded in mirror_map.

  Examples:
    "Overview LY" + "Overview LM"     -> representative: "Overview LY"
    "Summary YTD" + "Summary MTD"     -> representative: "Summary YTD"
    "Detail Q1"  + "Detail Q2" + ...  -> representative: "Detail Q1"

  This works for ANY dashboard without hardcoding page names.

OUTPUT:
  output/dashboards/<dash>/page_wise/funnel_map.json

Run:
  python src/Page_wise/funnel_mapper_step1.py --dashboard risk-dash
  python src/Page_wise/funnel_mapper_step1.py --dashboard risk-dash --force
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import json
import os
import re
import argparse
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

TF_API_KEY  = os.getenv("TF_API_KEY")
TF_BASE_URL = os.getenv("TF_BASE_URL")
TF_MODEL    = os.getenv("TF_MODEL", "internal-bedrock/sonnet-46")

VALID_POSITIONS = {"TOP", "MIDDLE", "BOTTOM", "ACTION"}

# ── Time-period suffixes that make pages structural duplicates ────────────────
TIME_PERIOD_SUFFIXES = {
    "ly", "lm", "ytd", "mtd", "qtd",
    "q1", "q2", "q3", "q4",
    "prior year", "current year",
    "prior month", "current month",
    "yoy", "mom", "qoq",
    "py", "cy",
}

# ── Keywords that identify action/targeting pages ─────────────────────────────
ACTION_PAGE_KEYWORDS = {
    "capture potential", "action", "targeting", "outreach",
    "intervention", "chase list", "worklist", "prioritization",
}


# ─────────────────────────────────────────────────────────────────────────────
# Generic page grouping logic
# ─────────────────────────────────────────────────────────────────────────────

def get_page_base_name(page_name: str) -> str:
    """
    Extract the base name of a page by stripping time-period suffixes.

    "Overview LY"      -> "Overview"
    "Summary YTD"      -> "Summary"
    "Detail Q1"        -> "Detail"
    "Performance MTD"  -> "Performance"
    "Risk capture potential" -> "Risk capture potential"  (no suffix)
    """
    name = page_name.strip()
    parts = name.split()

    # check last word
    if parts and parts[-1].lower() in TIME_PERIOD_SUFFIXES:
        base = " ".join(parts[:-1]).strip()
        return base if base else name

    # check last two words (e.g. "Prior Year", "Current Month")
    if len(parts) >= 2:
        last_two = " ".join(parts[-2:]).lower()
        if last_two in TIME_PERIOD_SUFFIXES:
            base = " ".join(parts[:-2]).strip()
            return base if base else name

    return name


def _is_action_page(page_name: str) -> bool:
    lower = page_name.lower()
    return any(kw in lower for kw in ACTION_PAGE_KEYWORDS)


def _rank_representative(name: str) -> tuple:
    """
    When multiple pages share the same base name, rank them to pick
    the best representative.

    Priority:
      1. LY before LM  (year-over-year is more analytically complete)
      2. YTD before MTD, QTD
      3. Q1 before Q2, Q3, Q4
      4. Lower order number
      5. Alphabetical fallback
    """
    lower = name.lower()
    suffix_priority = {
        "ly": 0, "ytd": 0, "q1": 0, "py": 0, "prior year": 0,
        "lm": 1, "mtd": 1, "qtd": 1, "mom": 1, "current month": 1,
        "q2": 2, "q3": 3, "q4": 4,
        "yoy": 5, "qoq": 6, "cy": 7, "current year": 8,
    }
    parts = lower.split()

    last = parts[-1] if parts else ""
    if last in suffix_priority:
        return (suffix_priority[last], lower)

    if len(parts) >= 2:
        last_two = " ".join(parts[-2:])
        if last_two in suffix_priority:
            return (suffix_priority[last_two], lower)

    return (99, lower)  # no suffix — treat as standalone


def build_page_plan(all_pages: list) -> list[dict]:
    """
    Build a processing plan from any dashboard's page list.

    Steps:
      1. Group pages by their base name (strip time-period suffixes)
      2. Within each group, pick the best representative using _rank_representative
      3. Mark action pages
      4. Sort: non-action pages first (by order), action pages last
    """
    page_order = {p["display_name"]: p.get("order", 99) for p in all_pages}

    groups: dict[str, list[str]] = {}
    for p in sorted(all_pages, key=lambda x: x.get("order", 99)):
        name = p["display_name"]
        base = get_page_base_name(name)
        groups.setdefault(base, []).append(name)

    plan = []
    for base_name, members in groups.items():
        members_sorted = sorted(members, key=_rank_representative)
        rep     = members_sorted[0]
        mirrors = members_sorted[1:]

        plan.append({
            "representative": rep,
            "mirrors":        mirrors,
            "is_action":      _is_action_page(rep),
            "order":          page_order.get(rep, 99),
            "base_name":      base_name,
        })

    plan.sort(key=lambda x: (1 if x["is_action"] else 0, x["order"]))

    return plan


# ─────────────────────────────────────────────────────────────────────────────
# System prompt (shared across all three calls)
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a dashboard analyst who understands the analytical story BI dashboards tell.

Every dashboard tells a story through a funnel of four questions:
  TOP    -> What is the current state? (KPI cards + first segment breakdown by LOB/region/payer)
  MIDDLE -> Why is it this way? (trends over time, deeper segmentation by model/cohort/attribution)
  BOTTOM -> Who and what specifically is driving it? (entity tables by provider/practice/facility, clinical breakdowns, operational gap patterns)
  ACTION -> What do I do about it? (targeting lists, outreach segments, prioritization — always on a separate page)

GROUPING RULES — these apply to every dashboard:

Rule 1 — KPI cards: ALL card and multiRowCard visuals on a page form EXACTLY TWO widgets,
  split by the purpose of each row:
  Widget A = the "landscape" row: population size metrics + risk/outcome score metrics
             (e.g. member count, eligible population, documented risk, potential risk, gap)
  Widget B = the "performance" row: rate and cost metrics
             (e.g. recapture rates, PMPM cost, % members with gaps)
  Each multiRowCard YoY/MoM indicator goes inside the SAME widget as its parent KPI card.
  Never merge all cards into one widget. Never create one widget per card.

Rule 2 — Trend charts: ALL lineChart visuals on a page MUST form EXACTLY ONE widget.
  Never split trend charts into separate widgets — not by metric, not by theme, not for any reason.
  If a page has 6 line charts, they form 1 widget with 6 visual_ids.
  If a page has 3 line charts, they form 1 widget with 3 visual_ids.
  They all answer the same question together: "How are these metrics trending over time?"

Rule 3 — Bar chart + detail table on same dimension: When a bar/column chart ranks items by
  a category dimension AND a detail table shows the same items with more columns, they form
  ONE widget. The chart gives ranking, the table gives the detail. Same sub-question.
  If the dimension is clinical/disease/condition/HCC -> BOTTOM position (identifies what is driving gaps).
  If the dimension is LOB/payer/region -> TOP position (first segment breakdown).

Rule 4 — Entity table + scatter plot: When a pivot table has rows broken down by an entity
  (provider, practice, PCP, facility, physician) AND a scatter plot shows the same entity
  population on two axes, they form ONE widget. The scatter is always the companion to the
  entity table.

Rule 5 — Table position depends on TWO factors: row dimension type AND reading order on page:

  FIRST classification breakdown after KPI cards -> TOP:
    The first table/chart that breaks the headline KPIs down by an external segment
    (payer, plan, LOB, line of business, region, geography) = TOP position.
    It is the immediate "first decomposition" of the headline numbers.
    Group it with any bar/column chart that segments the same dimension.

  DEEPER classification breakdowns further down the page -> MIDDLE:
    Tables breaking down by model type, risk model, cohort, attribution status,
    enrollment status = MIDDLE position. These explain WHY the headline looks the way it does.

  ACCOUNTABLE ENTITY tables -> always BOTTOM:
    Tables whose rows are providers, practices, PCPs, physicians, facilities, hospitals
    = BOTTOM position regardless of where they appear on the page.
    Never put a classification table and an entity table in the same widget.

Rule 6 — Operational breakdown charts (donut, pie) showing distribution by visit type,
  network status, channel, or provider type -> BOTTOM position. Not MIDDLE.

Rule 7 — If any page in ALL PAGES has a name suggesting action/targeting/outreach,
  funnel_question_action must be a real sentence. Never return null when such a page exists.

Output must be valid JSON only. No explanation text, no markdown fences."""


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builders — one per call
# ─────────────────────────────────────────────────────────────────────────────

def build_funnel_questions_prompt(
    dashboard_name: str,
    all_pages: list,
    sample_measures: list,
    action_page_names: list,
) -> str:
    """
    Call 1: tiny call — funnel questions only, no visual IDs.
    action_page_names is pre-detected in code so the LLM doesn't have to guess.
    """
    pages_block = "\n".join(
        f"  - {p['display_name']} (order: {p.get('order', 99)})"
        for p in sorted(all_pages, key=lambda x: x.get("order", 99))
    )
    measures_text = "\n".join(f"  - {m}" for m in sample_measures[:15])

    if action_page_names:
        action_instruction = (
            f"\nACTION PAGES (already detected): {', '.join(action_page_names)}\n"
            f"funnel_question_action MUST be a real sentence describing what these pages help the user do."
        )
        action_schema_hint = "one sentence — what do the action/targeting pages help the user do?"
    else:
        action_instruction = "\nNo action/targeting pages exist in this dashboard."
        action_schema_hint = "null"

    schema = f"""{{
  "dashboard_name": "...",
  "domain_context": "2-3 sentences explaining what business problem this dashboard solves and what the reader needs to understand first",
  "funnel_question_top": "one sentence — what does the TOP section answer?",
  "funnel_question_middle": "one sentence — what does the MIDDLE section answer?",
  "funnel_question_bottom": "one sentence — what does the BOTTOM section answer?",
  "funnel_question_action": "{action_schema_hint}"
}}"""

    return f"""Analyze this dashboard and describe the analytical story it tells through its funnel structure.

DASHBOARD: {dashboard_name}
ALL PAGES:
{pages_block}
{action_instruction}

SAMPLE MEASURES from the main page:
{measures_text}

Return JSON only:
{schema}

- JSON only, no markdown fences"""


def build_classify_prompt(visuals: list) -> str:
    """
    Call 2: classify all visuals on the page into funnel positions.
    Returns a flat dict: {visual_id: "TOP"|"MIDDLE"|"BOTTOM"|"ACTION"}
    """
    visuals_block = _format_visuals(visuals)

    return f"""Classify each visual into exactly one funnel position: TOP, MIDDLE, BOTTOM, or ACTION.

Classification rules (apply in order):
- card / cardVisual / multiRowCard → TOP
- lineChart → MIDDLE
- pivotTable / tableEx with row_dimensions containing provider / practice / PCP / physician / facility → BOTTOM
- pivotTable / tableEx with row_dimensions containing payer / LOB / region / plan → TOP
- pivotTable / tableEx with row_dimensions containing model / cohort / attribution → MIDDLE
- scatterChart → BOTTOM
- barChart / columnChart on clinical / disease / HCC dimension → BOTTOM
- barChart / columnChart on LOB / payer / region → TOP
- donutChart → BOTTOM
- When uncertain, default to TOP

VISUALS ({len(visuals)} total):
{visuals_block}

Return a JSON object mapping every visual_id to its position:
{{"visual_id_1": "TOP", "visual_id_2": "MIDDLE", "visual_id_3": "BOTTOM"}}

ALL {len(visuals)} visual_ids must be present as keys. JSON object only, no other text."""


def build_group_bucket_prompt(
    bucket_visuals: list,
    position: str,
    funnel_questions: dict,
    reading_order_start: int,
) -> str:
    """
    Call 3: group the visuals in one bucket into widgets.
    Each bucket call is small and focused on one position only.
    """
    context = f"""DASHBOARD FUNNEL CONTEXT:
- TOP answers   : {funnel_questions.get('funnel_question_top', '')}
- MIDDLE answers: {funnel_questions.get('funnel_question_middle', '')}
- BOTTOM answers: {funnel_questions.get('funnel_question_bottom', '')}
- ACTION answers: {funnel_questions.get('funnel_question_action', 'n/a')}"""

    position_rules = {
        "TOP": """Rules for TOP bucket:
- KPI cards (card/cardVisual/multiRowCard): EXACTLY TWO widgets
    Widget A = landscape row: population + risk score metrics (member count, eligible, documented risk, potential risk, gap)
    Widget B = performance row: rate + cost + gap metrics (recapture rates, PMPM, % with gaps)
    Each multiRowCard YoY/MoM indicator goes IN THE SAME widget as its parent KPI card
- First classification table (by payer/LOB/plan/region): ONE widget, group any matching bar/column chart with it
- Never merge all cards into one widget. Never create one widget per card.""",

        "MIDDLE": """Rules for MIDDLE bucket:
- ALL lineChart visuals on this page → EXACTLY ONE widget together (never split trend lines)
- bar/column chart + detail table on the same model/cohort/attribution dimension → ONE widget
- Deeper segmentation tables (by model, cohort, attribution, enrollment) → group by shared dimension""",

        "BOTTOM": """Rules for BOTTOM bucket:
- entity table (rows by provider/practice/PCP/facility) + scatter plot showing the same entity population → ONE widget
- bar/column chart on clinical/disease/HCC dimension + detail table on same dimension → ONE widget
- donut/pie operational breakdown (by visit type, network, channel) → its own widget
- Never put a classification table and an entity table in the same widget""",

        "ACTION": """Rules for ACTION bucket:
- Rule A — Summary widget: pivot/detail table showing performance by payer/plan/LOB
    (targeted patients, targeted gaps, recapture rates, RAF scores) → ONE widget.
    Group any LOB bar/column chart with this table if present.
- Rule B — Segmentation widget: ALL bar charts, donut charts, column charts that segment
    targeted gaps by member characteristics (wellness visit status, PCP visit frequency,
    days since last visit, cost, ED utilization, risk bucket, gap bucket, distance, zip)
    → ONE single widget together. Never split these.
- Rule C — Entity targeting widget: pivot table by practice/PCP showing targeted gaps → ONE widget
- Rule D — Member list widget: patient-level table listing individual members → ONE widget""",
    }

    visuals_block = _format_visuals(bucket_visuals)

    schema = """[
  {
    "widget_id": "wNN",
    "funnel_position": "POSITION",
    "widget_name": "short descriptive name",
    "sub_question": "the specific question this widget answers",
    "visual_ids": ["id1", "id2"],
    "screenshot_label": "plain English — what to screenshot, list visual titles",
    "reading_order": N
  }
]"""

    return f"""Group these {position} visuals into widgets.

{context}

{position_rules.get(position, '')}

VISUALS ({len(bucket_visuals)} visuals in {position} bucket):
{visuals_block}

Return a JSON ARRAY of widgets:
{schema}

- funnel_position = "{position}" for every widget in this array
- reading_order starts at {reading_order_start}
- ALL {len(bucket_visuals)} visual_ids must appear — each in exactly one widget
- JSON array only, no other text"""


def _format_visuals(visuals: list) -> str:
    """
    Compact format: ID, title, type + measure labels + definition snippets.
    No full DAX — keeps token count low.
    """
    lines = []
    for v in visuals:
        measure_parts = []
        for m in v["measures"]:
            label = m["display_name_in_visual"]
            defn  = m["definition"][:70] if m["definition"] else ""
            measure_parts.append(f"{label}: {defn}" if defn else label)

        measures_text = " | ".join(measure_parts) or "(no measures)"

        row_text = ""
        if v.get("row_dimensions"):
            row_text = f" | rows_by: {', '.join(v['row_dimensions'])}"

        lines.append(
            f"[{v['visual_id']}] \"{v['title']}\" ({v['type']})\n"
            f"    {measures_text}{row_text}"
        )

    return "\n\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_page_widgets(
    widgets: list,
    page_visual_ids: set,
    check_funnel_questions: bool = False,
    top_fields: dict = None,
) -> list[str]:
    errors = []

    if check_funnel_questions and top_fields:
        for key in ["domain_context", "funnel_question_top",
                    "funnel_question_middle", "funnel_question_bottom"]:
            if not top_fields.get(key):
                errors.append(f"Missing required field: '{key}'")

    if not widgets:
        errors.append("widgets array is empty")
        return errors

    output_ids: dict[str, str] = {}
    for w in widgets:
        wid = w.get("widget_id", "?")
        for vid in w.get("visual_ids", []):
            if vid in output_ids:
                errors.append(
                    f"'{vid}' appears in multiple widgets: "
                    f"'{output_ids[vid]}' and '{wid}'"
                )
            output_ids[vid] = wid

    missing = page_visual_ids - set(output_ids.keys())
    if missing:
        errors.append(
            f"{len(missing)} visual_id(s) missing: "
            f"{sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}"
        )

    invented = set(output_ids.keys()) - page_visual_ids
    if invented:
        errors.append(
            f"{len(invented)} invented visual_id(s): {sorted(invented)[:5]}"
        )

    for w in widgets:
        pos = w.get("funnel_position", "")
        if pos not in VALID_POSITIONS:
            errors.append(
                f"Widget '{w.get('widget_id')}' invalid position: '{pos}'"
            )

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# LLM helpers
# ─────────────────────────────────────────────────────────────────────────────

def call_llm(system: str, user: str) -> str:
    client = OpenAI(api_key=TF_API_KEY, base_url=TF_BASE_URL)
    response = client.chat.completions.create(
        model=TF_MODEL,
        temperature=0.1,
        max_completion_tokens=16000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return response.choices[0].message.content.strip()


def parse_json_response(raw: str) -> dict | list:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        while lines and lines[-1].strip() in ("```", ""):
            lines.pop()
        text = "\n".join(lines).strip()
    return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# Three focused LLM execution functions
# ─────────────────────────────────────────────────────────────────────────────

def get_funnel_questions(
    dashboard_name: str,
    all_pages: list,
    sample_measures: list,
    action_page_names: list,
    max_retries: int = 3,
) -> dict:
    """
    Call 1: extract funnel questions only. No visual IDs involved.
    """
    prompt = build_funnel_questions_prompt(
        dashboard_name, all_pages, sample_measures, action_page_names
    )
    required = ["domain_context", "funnel_question_top",
                "funnel_question_middle", "funnel_question_bottom"]

    for attempt in range(1, max_retries + 1):
        print(f"  [Call 1 — funnel questions] attempt {attempt}/{max_retries} ...")
        try:
            raw = call_llm(SYSTEM_PROMPT, prompt)
        except Exception as e:
            print(f"  LLM call failed ({type(e).__name__}): {e}")
            continue
        try:
            parsed = parse_json_response(raw)
        except json.JSONDecodeError as e:
            print(f"  JSON parse failed: {e}")
            print(f"  response_length={len(raw)} chars")
            print(f"  last 400 chars: ...{raw[-400:]}")
            continue
        if not isinstance(parsed, dict):
            print(f"  unexpected response type: {type(parsed)}")
            continue
        missing = [k for k in required if not parsed.get(k)]
        if not missing:
            print(f"  funnel questions extracted successfully")
            return parsed
        print(f"  missing required fields: {missing}, retrying ...")

    raise RuntimeError(
        f"get_funnel_questions failed after {max_retries} attempts"
    )


def classify_visuals(
    visuals: list,
    page_visual_ids: set,
    max_retries: int = 3,
) -> dict:
    """
    Call 2: classify all visuals into funnel positions.
    Returns {visual_id: "TOP"|"MIDDLE"|"BOTTOM"|"ACTION"}.
    """
    prompt = build_classify_prompt(visuals)

    for attempt in range(1, max_retries + 1):
        print(f"  [Call 2 — classify] attempt {attempt}/{max_retries} ...")
        try:
            raw = call_llm(SYSTEM_PROMPT, prompt)
        except Exception as e:
            print(f"  LLM call failed ({type(e).__name__}): {e}")
            continue
        try:
            parsed = parse_json_response(raw)
        except json.JSONDecodeError as e:
            print(f"  JSON parse failed: {e}")
            print(f"  response_length={len(raw)} chars")
            print(f"  last 400 chars: ...{raw[-400:]}")
            continue
        if not isinstance(parsed, dict):
            print(f"  unexpected response type: {type(parsed)}")
            continue

        # strip invented IDs and invalid positions silently
        result = {
            k: v for k, v in parsed.items()
            if k in page_visual_ids and v in VALID_POSITIONS
        }

        missing = page_visual_ids - set(result.keys())
        if not missing:
            print(f"  classified {len(result)} visuals successfully")
            return result

        print(f"  {len(missing)} visual_id(s) missing from classification, retrying ...")

    # last resort: default all unclassified to TOP
    print(f"  WARNING: classify_visuals exhausted retries — defaulting missing IDs to TOP")
    for vid in page_visual_ids:
        result.setdefault(vid, "TOP")
    return result


def group_bucket(
    bucket_visuals: list,
    position: str,
    funnel_questions: dict,
    reading_order_start: int,
    max_retries: int = 3,
) -> list:
    """
    Call 3: group visuals in one bucket into widgets.
    Each call is small (one position's visuals only).
    """
    if not bucket_visuals:
        return []

    bucket_ids = {v["visual_id"] for v in bucket_visuals}
    prompt = build_group_bucket_prompt(
        bucket_visuals, position, funnel_questions, reading_order_start
    )

    last_raw    = ""
    last_errors = []

    for attempt in range(1, max_retries + 1):
        print(f"  [Call 3 — group {position} ({len(bucket_visuals)} visuals)] "
              f"attempt {attempt}/{max_retries} ...")

        current_prompt = prompt if attempt == 1 else (
            "Your previous response had these errors:\n"
            + "\n".join(f"  - {e}" for e in last_errors)
            + f"\n\nPrevious response:\n{last_raw}\n\n"
            + "Fix ALL errors. Every visual_id must appear in exactly one widget. "
            + "Return corrected JSON array only."
        )

        try:
            raw = call_llm(SYSTEM_PROMPT, current_prompt)
        except Exception as e:
            last_errors = [f"LLM call failed: {type(e).__name__}: {e}"]
            print(f"  LLM call failed ({type(e).__name__}): {e}")
            continue

        last_raw = raw

        if not raw:
            last_errors = ["LLM returned empty response"]
            print(f"  empty response — finish_reason=length likely; token budget too small")
            continue

        try:
            parsed = parse_json_response(raw)
        except json.JSONDecodeError as e:
            last_errors = [f"Invalid JSON: {e}"]
            print(f"  JSON parse failed: {e}")
            print(f"  response_length={len(raw)} chars")
            print(f"  last 400 chars: ...{raw[-400:]}")
            continue

        widgets = parsed if isinstance(parsed, list) else parsed.get("widgets", [])

        errors = validate_page_widgets(widgets, bucket_ids)
        if not errors:
            print(f"  validation passed — {len(widgets)} widgets in {position} bucket")
            return widgets

        last_errors = errors
        print(f"  validation failed ({len(errors)} errors):")
        for e in errors:
            print(f"    - {e}")

    raise RuntimeError(
        f"group_bucket({position}) failed after {max_retries} attempts. "
        f"Last errors: {last_errors}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mirror widget IDs for duplicate pages
# ─────────────────────────────────────────────────────────────────────────────

def mirror_widgets_for_page(
    source_widgets: list,
    source_page: str,
    target_page: str,
    target_visuals: list,
    widget_id_offset: int,
) -> list:
    """
    Overview LM has the same structure as Overview LY but different visual IDs.
    We map source visual IDs to target visual IDs by matching title + type.
    """
    target_lookup: dict[tuple, str] = {}
    for v in target_visuals:
        key = (v["title"], v["type"])
        target_lookup[key] = v["visual_id"]

    return _do_mirror(
        source_widgets, source_page, target_page,
        target_visuals, target_lookup, widget_id_offset
    )


def _do_mirror(
    source_widgets, source_page, target_page,
    target_visuals, target_lookup, widget_id_offset,
) -> list:
    target_ids_ordered = [v["visual_id"] for v in target_visuals]
    used_target_ids = set()
    mirrored = []

    for i, sw in enumerate(source_widgets):
        new_widget_id = f"w{widget_id_offset + i + 1:02d}"
        matched_ids   = []

        for j, src_vid in enumerate(sw.get("visual_ids", [])):
            for tv in target_visuals:
                tid = tv["visual_id"]
                if tid not in used_target_ids:
                    matched_ids.append(tid)
                    used_target_ids.add(tid)
                    break

        mirrored.append({
            "widget_id":       new_widget_id,
            "funnel_position": sw["funnel_position"],
            "widget_name":     sw["widget_name"],
            "sub_question":    sw["sub_question"],
            "visual_ids":      matched_ids,
            "screenshot_label": sw["screenshot_label"].replace(
                source_page, target_page
            ),
            "reading_order":   sw["reading_order"],
            "mirrored_from":   source_page,
        })

    # any unmatched target visuals get a catch-all widget
    unmatched = [
        v["visual_id"] for v in target_visuals
        if v["visual_id"] not in used_target_ids
    ]
    if unmatched:
        mirrored.append({
            "widget_id":       f"w{widget_id_offset + len(source_widgets) + 1:02d}",
            "funnel_position": "TOP",
            "widget_name":     f"Additional visuals — {target_page}",
            "sub_question":    "Additional metrics for this period",
            "visual_ids":      unmatched,
            "screenshot_label": f"Remaining visuals on {target_page}",
            "reading_order":   source_widgets[-1]["reading_order"] if source_widgets else 1,
            "mirrored_from":   source_page,
        })

    return mirrored


# ─────────────────────────────────────────────────────────────────────────────
# Main orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def run_funnel_mapper(llm_input: dict) -> dict:
    dashboard_name = llm_input["dashboard_name"]
    all_pages      = llm_input["pages"]
    all_visuals    = llm_input["visuals"]

    # group visuals by page name
    visuals_by_page: dict[str, list] = {}
    for v in all_visuals:
        visuals_by_page.setdefault(v["page"], []).append(v)

    # build processing plan
    plan = build_page_plan(all_pages)
    print(f"[funnel_mapper] processing plan:")
    for step in plan:
        mirror_str = (
            f" (mirrors: {step['mirrors']})" if step["mirrors"] else ""
        )
        print(f"  -> '{step['representative']}'{mirror_str}")

    all_widgets             = []
    funnel_questions        = {}
    funnel_questions_fetched = False

    for step in plan:
        rep_page     = step["representative"]
        mirror_pages = step["mirrors"]

        rep_visuals = visuals_by_page.get(rep_page, [])
        if not rep_visuals:
            print(f"\n[funnel_mapper] SKIP '{rep_page}' — no visuals found")
            continue

        rep_ids = {v["visual_id"] for v in rep_visuals}

        print(f"\n[funnel_mapper] processing '{rep_page}' "
              f"({len(rep_visuals)} visuals)")

        # ── Call 1: funnel questions — once, from first page ──────────────
        if not funnel_questions_fetched:
            sample_measures = []
            for v in rep_visuals:
                for m in v.get("measures", []):
                    dn = m.get("display_name_in_visual", "")
                    if dn and dn not in sample_measures:
                        sample_measures.append(dn)
                    if len(sample_measures) >= 15:
                        break
                if len(sample_measures) >= 15:
                    break

            action_page_names = [
                s["representative"] for s in plan if s["is_action"]
            ]
            funnel_questions = get_funnel_questions(
                dashboard_name, all_pages, sample_measures, action_page_names
            )

            # clean dashboard_name — LLM sometimes appends page name
            raw_name = funnel_questions.get("dashboard_name", "")
            for sep in [" – ", " — ", " - ", " | "]:
                if sep in raw_name:
                    raw_name = raw_name.split(sep)[0].strip()
            if raw_name:
                funnel_questions["dashboard_name"] = raw_name

            funnel_questions_fetched = True

        # ── Call 2 + 3: classify then group per bucket ────────────────────
        if step["is_action"]:
            # action pages: all visuals go directly to ACTION bucket
            print(f"  action page — skipping classification, grouping as ACTION")
            page_widgets = group_bucket(
                rep_visuals, "ACTION", funnel_questions,
                reading_order_start=len(all_widgets) + 1,
            )
        else:
            # Call 2: classify all visuals into positions
            classification = classify_visuals(rep_visuals, rep_ids)

            # split into buckets
            buckets: dict[str, list] = {
                "TOP": [], "MIDDLE": [], "BOTTOM": [], "ACTION": []
            }
            for v in rep_visuals:
                pos = classification.get(v["visual_id"], "TOP")
                buckets[pos].append(v)

            for pos, vlist in buckets.items():
                if vlist:
                    print(f"  {pos}: {len(vlist)} visuals")

            # Call 3: group each non-empty bucket separately
            page_widgets   = []
            reading_order  = len(all_widgets) + 1
            for pos in ["TOP", "MIDDLE", "BOTTOM", "ACTION"]:
                if not buckets[pos]:
                    continue
                bucket_widgets = group_bucket(
                    buckets[pos], pos, funnel_questions,
                    reading_order_start=reading_order,
                )
                page_widgets.extend(bucket_widgets)
                reading_order += len(bucket_widgets)

        # renumber widget IDs to be globally unique across all pages
        offset = len(all_widgets)
        for i, w in enumerate(page_widgets):
            w["widget_id"] = f"w{offset + i + 1:02d}"
            w["page"]      = rep_page

        all_widgets.extend(page_widgets)

        # mirror pages: record only — widget_group_writer applies LY structure to LM on the fly
        for mirror_page in mirror_pages:
            mirror_visuals = visuals_by_page.get(mirror_page, [])
            print(f"  mirror '{mirror_page}' "
                  f"({len(mirror_visuals)} visuals) — recorded only, not processed")

    # fix reading_order to be globally sequential
    for i, w in enumerate(all_widgets):
        w["reading_order"] = i + 1

    return {
        "dashboard":              llm_input["dashboard"],
        "dashboard_name":         funnel_questions.get("dashboard_name")
                                  or dashboard_name,
        "domain_context":         funnel_questions.get("domain_context", ""),
        "funnel_question_top":    funnel_questions.get("funnel_question_top", ""),
        "funnel_question_middle": funnel_questions.get("funnel_question_middle", ""),
        "funnel_question_bottom": funnel_questions.get("funnel_question_bottom", ""),
        "funnel_question_action": funnel_questions.get("funnel_question_action"),
        "widgets":                all_widgets,
        "_meta": {
            "dashboard":       llm_input["dashboard"],
            "content_hash":    llm_input["content_hash"],
            "total_widgets":   len(all_widgets),
            "total_visuals":   len(all_visuals),
            "pages_processed": [s["representative"] for s in plan],
            "pages_mirrored":  [m for s in plan for m in s["mirrors"]],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "output").exists() and (parent / "config").exists():
            return parent
    for parent in Path(__file__).resolve().parents:
        if (parent / "run.py").exists():
            return parent
    return Path(__file__).resolve().parent.parent.parent


def load_json(path: Path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate funnel_map.json — three focused LLM calls per page"
    )
    parser.add_argument("--dashboard", default="risk-dash")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if cache is fresh")
    args = parser.parse_args()

    root     = get_project_root()
    stage3   = root / "output" / "dashboards" / args.dashboard / "page_wise"
    in_path  = stage3 / "funnel_llm_input.json"
    out_path = stage3 / "funnel_map.json"

    print(f"[funnel_mapper] dashboard  : {args.dashboard}")
    print(f"[funnel_mapper] input      : {in_path}")

    llm_input = load_json(in_path)
    if not llm_input:
        raise FileNotFoundError(
            f"funnel_llm_input.json not found at {in_path}\n"
            f"Run funnel_input_builder_step0.py first."
        )

    # cache check
    if not args.force and out_path.exists():
        existing = load_json(out_path)
        if (existing
                and existing.get("_meta", {}).get("content_hash")
                == llm_input.get("content_hash")):
            print(
                f"[funnel_mapper] cache hit — up to date "
                f"(hash: {llm_input['content_hash']}). Use --force to re-run."
            )
            return

    print(f"[funnel_mapper] total visuals : {llm_input['total_visuals']}")
    print(f"[funnel_mapper] content_hash  : {llm_input['content_hash']}")

    funnel_map = run_funnel_mapper(llm_input)

    stage3.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(funnel_map, f, indent=2, ensure_ascii=False)

    m = funnel_map["_meta"]
    print(f"\n[funnel_mapper] widgets created : {m['total_widgets']}")
    print(f"[funnel_mapper] written to      : {out_path}")

    # summary
    print("\n── Funnel Map ──────────────────────────────────────────────")
    print(f"TOP    : {funnel_map.get('funnel_question_top')}")
    print(f"MIDDLE : {funnel_map.get('funnel_question_middle')}")
    print(f"BOTTOM : {funnel_map.get('funnel_question_bottom')}")
    print(f"ACTION : {funnel_map.get('funnel_question_action')}")
    print()
    for w in funnel_map.get("widgets", []):
        mirror = " [mirrored]" if w.get("mirrored_from") else ""
        print(
            f"  [{w['reading_order']:02d}] {w['funnel_position']:<7} "
            f"pg={w.get('page',''):<25} "
            f"{w['widget_name']:<40} "
            f"({len(w['visual_ids'])} visuals){mirror}"
        )
    print("────────────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
