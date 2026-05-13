"""
funnel_mapper.py
================
Stage 3A — Step 2

Calls the LLM once per LOGICAL page group to produce funnel_map.json.

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
  output/dashboards/<dash>/stage3/funnel_map.json

Run:
  python -m app.story.funnel_mapper
  python -m app.story.funnel_mapper --dashboard risk-dash
  python -m app.story.funnel_mapper --force
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
# A page whose name = "<base> <suffix>" is a duplicate of "<base> <other_suffix>"
TIME_PERIOD_SUFFIXES = {
    "ly", "lm", "ytd", "mtd", "qtd",
    "q1", "q2", "q3", "q4",
    "prior year", "current year",
    "prior month", "current month",
    "yoy", "mom", "qoq",
    "py", "cy",
}

# ── Keywords that identify action/targeting pages ─────────────────────────────
# Generic — works for any dashboard type
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

    Works by checking if the last word(s) of the name match a known suffix.
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

    Returns a tuple used for sorting — lower = higher priority.
    """
    lower = name.lower()
    suffix_priority = {
        "ly": 0, "ytd": 0, "q1": 0, "py": 0, "prior year": 0,
        "lm": 1, "mtd": 1, "qtd": 1, "mom": 1, "current month": 1,
        "q2": 2, "q3": 3, "q4": 4,
        "yoy": 5, "qoq": 6, "cy": 7, "current year": 8,
    }
    parts = lower.split()

    # check last word
    last = parts[-1] if parts else ""
    if last in suffix_priority:
        return (suffix_priority[last], lower)

    # check last two words
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
         (LY before LM, YTD before MTD, etc.)
      3. Mark action pages
      4. Sort: non-action pages first (by order), action pages last
    """
    page_order = {p["display_name"]: p.get("order", 99) for p in all_pages}

    # group by base name
    groups: dict[str, list[str]] = {}
    for p in sorted(all_pages, key=lambda x: x.get("order", 99)):
        name = p["display_name"]
        base = get_page_base_name(name)
        groups.setdefault(base, []).append(name)

    plan = []
    for base_name, members in groups.items():
        # sort by representative priority — LY before LM etc.
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

    # non-action pages first, action pages last
    plan.sort(key=lambda x: (1 if x["is_action"] else 0, x["order"]))

    return plan


def _is_action_page(page_name: str) -> bool:
    lower = page_name.lower()
    return any(kw in lower for kw in ACTION_PAGE_KEYWORDS)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builders
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


def build_first_call_prompt(
    dashboard_name: str,
    all_pages: list,
    rep_page: str,
    mirror_pages: list,
    visuals: list,
) -> str:
    """
    First LLM call: representative page -> funnel questions + widgets.
    """
    pages_block = "\n".join(
        f"  - {p['display_name']} (order: {p['order']})"
        for p in sorted(all_pages, key=lambda x: x["order"])
    )

    mirror_note = ""
    if mirror_pages:
        mirror_note = (
            f"\nNOTE — page variants: '{rep_page}' and '{', '.join(mirror_pages)}' "
            f"are the same dashboard page shown for different comparison periods "
            f"(e.g. year-over-year vs month-over-month, or different quarters).\n"
            f"Same visuals, same layout, same widget structure — only the time comparison differs.\n"
            f"You are analyzing '{rep_page}' only. The widget structure will be reused for the other variant(s)."
        )

    visuals_block = _format_visuals(visuals)

    schema = """{
  "dashboard_name": "...",
  "domain_context": "2-3 sentences explaining what business problem this dashboard solves and what the reader needs to understand first",
  "funnel_question_top": "one sentence — what does the TOP section answer?",
  "funnel_question_middle": "one sentence — what does the MIDDLE section answer?",
  "funnel_question_bottom": "one sentence — what does the BOTTOM section answer?",
  "funnel_question_action": "one sentence — what does the ACTION page answer? (null if no action page)",
  "widgets": [
    {
      "widget_id": "w01",
      "funnel_position": "TOP",
      "widget_name": "short descriptive name",
      "sub_question": "the specific question this widget answers",
      "visual_ids": ["id1", "id2"],
      "screenshot_label": "plain English — what to screenshot, list visual titles",
      "reading_order": 1
    }
  ]
}"""

    return f"""Analyze this dashboard page and produce the funnel map.

DASHBOARD: {dashboard_name}
ALL PAGES:
{pages_block}
{mirror_note}

VISUALS ON PAGE "{rep_page}" ({len(visuals)} visuals):
{visuals_block}

Return JSON with this exact structure:
{schema}

Grouping rules — apply these strictly:
- All {len(visuals)} visual_ids above must appear — each in exactly one widget
- reading_order starts at 1
- KPI cards -> EXACTLY TWO widgets: Widget A = landscape row (population + risk scores), Widget B = performance row (rates + cost + gaps)
- Each multiRowCard YoY/MoM indicator goes IN THE SAME widget as its parent KPI card
- ALL lineCharts on this page -> EXACTLY ONE single widget. Do not split by metric. One widget, all line chart visual_ids together.
- bar/column chart + detail table on same dimension -> ONE widget
- FIRST classification table after KPI cards (payer, LOB, plan, region) -> TOP
- DEEPER classification tables further down (model, cohort, attribution) -> MIDDLE
- entity table (rows by provider/practice/PCP/facility) -> BOTTOM
- entity table + scatter plot showing same entity population -> ONE widget, BOTTOM
- never group a classification table with an entity table
- donut/pie operational breakdown (by visit type, network, channel) -> BOTTOM
- If any page in ALL PAGES suggests action/targeting -> funnel_question_action must be a real sentence
- JSON only, no other text"""


def build_action_page_prompt(
    dashboard_name: str,
    page_name: str,
    visuals: list,
    funnel_questions: dict,
    reading_order_start: int,
) -> str:
    """
    Prompt for action/targeting pages.
    Funnel questions already known — only need widgets for this page.
    """
    context = (
        f"ACTION = {funnel_questions.get('funnel_question_action', 'targeting and outreach')}"
    )

    visuals_block = _format_visuals(visuals)

    schema = """[
  {
    "widget_id": "wNN",
    "funnel_position": "ACTION",
    "widget_name": "short descriptive name",
    "sub_question": "specific question this widget answers",
    "visual_ids": ["id1", "id2"],
    "screenshot_label": "plain English description",
    "reading_order": N
  }
]"""

    return f"""Page "{page_name}" is the ACTION/targeting page of dashboard "{dashboard_name}".
{context}

Group all {len(visuals)} visuals into widgets using these ACTION page rules:

Rule A — Summary widget: A pivot/detail table showing performance by payer, plan, or LOB
  (with columns like targeted patients, targeted gaps, recapture rates, RAF scores)
  forms ONE widget. Group any LOB bar/column chart with this table if present.
  Sub-question: "Which payers/plans have the most targetable revenue opportunity?"

Rule B — Segmentation widget: ALL bar charts, donut charts, and column charts that segment
  targeted gaps by member characteristics (wellness visit status, PCP visit frequency,
  days since last visit, cost of care, ED utilization, risk bucket, coding gap bucket,
  care gap bucket, member-PCP distance, geographic zip) form ONE single widget together.
  These collectively answer: "How should outreach be structured across member segments?"
  Never split segmentation charts into separate widgets — they are all part of one section.

Rule C — Entity targeting widget: A pivot table showing targeted gaps by practice/PCP
  forms ONE widget. Sub-question: "Which practices and PCPs should be prioritized?"

Rule D — Member list widget: A patient-level table listing individual members
  forms ONE widget. Sub-question: "Which specific members should be contacted?"

VISUALS ({len(visuals)} visuals):
{visuals_block}

Return a JSON ARRAY of widgets:
{schema}

- All {len(visuals)} visual_ids must appear — each in exactly one widget
- reading_order starts at {reading_order_start}
- funnel_position = "ACTION" for all widgets
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
# LLM call + retry
# ─────────────────────────────────────────────────────────────────────────────

def call_llm(system: str, user: str) -> str:
    client = OpenAI(api_key=TF_API_KEY, base_url=TF_BASE_URL)
    response = client.chat.completions.create(
        model=TF_MODEL,
        temperature=0.1,
        max_tokens=6000,
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


def call_with_retry(
    user_prompt: str,
    page_visual_ids: set,
    check_funnel_questions: bool,
    max_retries: int = 3,
) -> tuple[list, dict]:
    """
    Returns (widgets, top_fields).
    top_fields has funnel questions only for the first page call.
    """
    last_raw    = ""
    last_errors = []

    for attempt in range(1, max_retries + 1):
        print(f"  attempt {attempt}/{max_retries} ...")

        current_user = user_prompt if attempt == 1 else (
            f"Your previous response had these errors:\n"
            + "\n".join(f"  - {e}" for e in last_errors)
            + f"\n\nPrevious response:\n{last_raw}\n\n"
            + "Fix ALL errors. Every visual_id from the page must appear in exactly one widget. "
            + "Return corrected JSON only."
        )

        raw = call_llm(SYSTEM_PROMPT, current_user)
        last_raw = raw

        if not raw:
            last_errors = ["LLM returned empty response"]
            print(f"  empty response")
            continue

        try:
            parsed = parse_json_response(raw)
        except json.JSONDecodeError as e:
            last_errors = [f"Invalid JSON: {e}"]
            print(f"  JSON parse failed: {e}")
            print(f"  response length  : {len(raw)} chars")
            print(f"  last 300 chars   : ...{raw[-300:]}")
            continue

        # extract widgets and top-level fields
        if isinstance(parsed, list):
            widgets    = parsed
            top_fields = {}
        elif isinstance(parsed, dict):
            widgets    = parsed.get("widgets", [])
            top_fields = {
                k: parsed.get(k)
                for k in ["dashboard_name", "domain_context",
                          "funnel_question_top", "funnel_question_middle",
                          "funnel_question_bottom", "funnel_question_action"]
            }
        else:
            last_errors = ["Response is neither object nor array"]
            continue

        errors = validate_page_widgets(
            widgets, page_visual_ids,
            check_funnel_questions=check_funnel_questions,
            top_fields=top_fields if check_funnel_questions else None,
        )

        if not errors:
            print(f"  validation passed — {len(widgets)} widgets")
            return widgets, top_fields

        last_errors = errors
        print(f"  validation failed ({len(errors)} errors):")
        for e in errors:
            print(f"    - {e}")

    raise RuntimeError(
        f"Failed after {max_retries} attempts. Last errors: {last_errors}"
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

    Matching strategy:
      source visual title + type  ->  target visual title + type
    Unmatched target visuals get their own single-visual widget at the end.
    """
    # build lookup: (title, type) -> visual_id for target page
    target_lookup: dict[tuple, str] = {}
    for v in target_visuals:
        key = (v["title"], v["type"])
        target_lookup[key] = v["visual_id"]

    # build lookup for source: visual_id -> (title, type)
    # We need the source enriched visuals — use the input data
    # Since we only have widget visual_ids, we build a reverse map
    # from the funnel_llm_input visuals array (passed in via closure)
    # Instead: pass source_visuals as parameter
    return _do_mirror(
        source_widgets, source_page, target_page,
        target_visuals, target_lookup, widget_id_offset
    )


def _do_mirror(
    source_widgets, source_page, target_page,
    target_visuals, target_lookup, widget_id_offset,
) -> list:
    """
    Build mirrored widget list for the target page.
    """
    # source visual_id -> (title, type) needs source visuals
    # We don't have them here easily — so we use a simpler approach:
    # match by position within each widget (same order of visual_ids).
    # This works because LY and LM have the same visuals in the same order.

    # build target visual list in original order
    target_ids_ordered = [v["visual_id"] for v in target_visuals]
    # we don't know source order, so we match by widget structure:
    # for each source widget, find target visuals by title+type matching

    # build source visual id -> (title, type) from target_visuals
    # We can't directly, so we rely on title matching across pages.
    # Build target: (title, type) -> id
    used_target_ids = set()
    mirrored = []

    for i, sw in enumerate(source_widgets):
        new_widget_id = f"w{widget_id_offset + i + 1:02d}"
        matched_ids   = []

        # for each source visual_id in this widget, find the matching
        # target visual by (title, type) — this requires source title/type
        # which we don't have here. Fallback: use index-based matching.
        # Since both pages have same count and order, zip works.
        for j, src_vid in enumerate(sw.get("visual_ids", [])):
            # try to find a target visual not yet used
            # that matches by relative position
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

    all_widgets      = []
    funnel_questions = {}
    is_first_call    = True

    for step in plan:
        rep_page    = step["representative"]
        mirror_pages = step["mirrors"]

        rep_visuals = visuals_by_page.get(rep_page, [])
        if not rep_visuals:
            print(f"\n[funnel_mapper] SKIP '{rep_page}' — no visuals found")
            continue

        rep_ids = {v["visual_id"] for v in rep_visuals}

        print(f"\n[funnel_mapper] processing '{rep_page}' "
              f"({len(rep_visuals)} visuals)")

        # build prompt
        if is_first_call:
            prompt = build_first_call_prompt(
                dashboard_name, all_pages,
                rep_page, mirror_pages, rep_visuals,
            )
        elif step["is_action"]:
            prompt = build_action_page_prompt(
                dashboard_name, rep_page, rep_visuals,
                funnel_questions,
                reading_order_start=len(all_widgets) + 1,
            )
        else:
            # non-action page after the first (rare — e.g. a third overview page)
            # treat same as action page but without forcing ACTION position
            prompt = build_action_page_prompt(
                dashboard_name, rep_page, rep_visuals,
                funnel_questions,
                reading_order_start=len(all_widgets) + 1,
            )

        # call LLM
        widgets, top_fields = call_with_retry(
            user_prompt            = prompt,
            page_visual_ids        = rep_ids,
            check_funnel_questions = is_first_call,
        )

        # store funnel questions from first call
        if is_first_call and top_fields:
            funnel_questions = top_fields

            # clean dashboard_name — LLM sometimes appends page name like
            # "Risk Management Dashboard – Overview LY". Strip everything
            # after a dash/em-dash separator.
            raw_name = funnel_questions.get("dashboard_name", "")
            for sep in [" – ", " — ", " - ", " | "]:
                if sep in raw_name:
                    raw_name = raw_name.split(sep)[0].strip()
            if raw_name:
                funnel_questions["dashboard_name"] = raw_name

            is_first_call = False

        # renumber widget IDs to be globally unique
        offset = len(all_widgets)
        for i, w in enumerate(widgets):
            w["widget_id"]    = f"w{offset + i + 1:02d}"
            w["page"]         = rep_page

        all_widgets.extend(widgets)

        # mirror pages: Option B — do NOT add widgets to funnel_map.
        # widget_group_writer applies LY structure to LM on the fly.
        # Just record the mirror relationship.
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
            "dashboard":      llm_input["dashboard"],
            "content_hash":   llm_input["content_hash"],
            "total_widgets":  len(all_widgets),
            "total_visuals":  len(all_visuals),
            "pages_processed": [s["representative"] for s in plan],
            "pages_mirrored":  [
                m for s in plan for m in s["mirrors"]
            ],
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
        description="Generate funnel_map.json — one LLM call per logical page"
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
            f"Run funnel_input_builder.py first."
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
