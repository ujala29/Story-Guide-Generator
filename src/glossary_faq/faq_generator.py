"""
FAQ Generator
=============
Input:
  - stage3/widget_content/*.json     → italic_callouts (watch-outs → FAQ answers)
  - stage3/funnel_connector.json     → cross_page_patterns (navigation FAQs)
  - stage1/schema_sections/filters.json → filter metadata (filter FAQs)
  - stage3/funnel_map.json           → sub_questions + domain_context

Output:
  - stage3/faq.md

The LLM receives structured signals from all sources and produces a FAQ section
that answers real user questions: filter confusion, number mismatches, data lag,
cross-page navigation, and "why does X look different" interpretation questions.
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_ROOT      = Path(__file__).resolve().parent.parent.parent
PROMPT_DIR = _ROOT / "prompt" / "system_prompt"

SKIP_PAGES   = {"additional dimensions", "additional_dimensions",
                "scatter plot tooltip", "scatter_plot_tooltip"}
SKIP_TABLES  = {"X Axis scatter plot", "Y Axis scatter plot"}
PERIOD_MAP   = {
    "Last Year" : "YTD (year-to-date: Jan 1 of current year to selected month)",
    "Last Month": "Rolling (last year's date to current date)",
}


# ============================================================
# STEP 1 — Collect FAQ signals from all sources
# ============================================================

def collect_faq_signals(dashboard: str, root: Path) -> dict:
    stage1 = root / "output" / "dashboards" / dashboard / "stage1" / "schema_sections"
    stage3 = root / "output" / "dashboards" / dashboard / "stage3"

    # ── Source A: italic_callouts from widget_content ─────────
    callouts: list[dict] = []    # [{page, widget, metric, callout}]

    widget_dir = stage3 / "widget_content"
    if widget_dir.exists():
        for wf in sorted(widget_dir.glob("*.json")):
            with open(wf, encoding="utf-8") as f:
                data = json.load(f)
            page = data.get("page", "")
            if page.lower().replace(" ", "_") in SKIP_PAGES:
                continue
            for widget in data.get("widgets", []):
                widget_name = widget.get("widget_name", "")
                for metric in widget.get("metrics", []):
                    callout = metric.get("italic_callout")
                    if callout:
                        callouts.append({
                            "page"   : page,
                            "widget" : widget_name,
                            "metric" : metric.get("name", ""),
                            "callout": callout,
                        })
    else:
        print(f"  [WARN] widget_content/ not found at {widget_dir}")

    # ── Source B: cross_page_patterns from funnel_connector ───
    cross_page_patterns: list[dict] = []
    connector_path = stage3 / "funnel_connector.json"
    if connector_path.exists():
        with open(connector_path, encoding="utf-8") as f:
            connector = json.load(f)
        cross_page_patterns = connector.get("cross_page_patterns", [])
    else:
        print(f"  [WARN] funnel_connector.json not found at {connector_path}")

    # ── Source C: filter metadata ─────────────────────────────
    filters_raw: list[dict] = []
    filters_path = stage1 / "filters.json"
    if filters_path.exists():
        with open(filters_path, encoding="utf-8") as f:
            filters_raw = json.load(f)
    else:
        print(f"  [WARN] filters.json not found at {filters_path}")

    # Build a deduplicated list of filter summaries
    seen_cols: set[str] = set()
    filter_summaries: list[dict] = []
    for flt in filters_raw:
        col  = flt.get("column", "")
        name = flt.get("name", "")
        tbl  = flt.get("table", "")
        if not name or tbl in SKIP_TABLES or name.startswith("Slicer_"):
            continue
        if col in seen_cols:
            continue
        seen_cols.add(col)

        raw_default = flt.get("default_value") or "All"
        translated  = PERIOD_MAP.get(raw_default, raw_default)

        filter_summaries.append({
            "name"         : name,
            "column"       : col,
            "slicer_mode"  : flt.get("slicer_mode", ""),
            "single_select": flt.get("single_select", "false"),
            "default"      : translated,
        })

    # ── Source D: sub_questions from funnel_map ───────────────
    sub_questions: list[dict] = []   # [{page, widget, question}]
    funnel_path = stage3 / "funnel_map.json"
    domain_context = ""
    if funnel_path.exists():
        with open(funnel_path, encoding="utf-8") as f:
            funnel_map = json.load(f)
        domain_context = funnel_map.get("domain_context", "")
        for w in funnel_map.get("widgets", []):
            q = w.get("sub_question", "").strip()
            if q:
                sub_questions.append({
                    "page"   : w.get("page", ""),
                    "widget" : w.get("widget_name", ""),
                    "question": q,
                })
    else:
        print(f"  [WARN] funnel_map.json not found at {funnel_path}")

    return {
        "callouts"            : callouts,
        "cross_page_patterns" : cross_page_patterns,
        "filter_summaries"    : filter_summaries,
        "sub_questions"       : sub_questions,
        "domain_context"      : domain_context,
    }


# ============================================================
# STEP 2 — System prompt
# ============================================================

FAQ_SYSTEM_INLINE = """\
You are a documentation writer for a healthcare risk adjustment dashboard.

Your task: produce a "Frequently Asked Questions" section for a Story Guide.
This section answers real questions business users ask when reading the dashboard.

## QUESTION CATEGORIES — cover all that apply

1. Filter questions: wrong numbers, filter order, what does X filter do
2. Number mismatch questions: why my number differs from a colleague's
3. Interpretation questions: why is X low/high/zero, what does a movement mean
4. Data freshness questions: why hasn't data updated, claims lag, refresh timing
5. Navigation questions: which page answers which question, cross-page patterns
6. Definition questions: what does a term or acronym mean (2–3 sentence answers)

## OUTPUT FORMAT — produce exactly this structure

## 8.1 Frequently Asked Questions

**[Question in bold?]**
Answer in 1–3 sentences. Prescriptive. Plain English.

[repeat for each Q&A — aim for 10–15 questions total]

## TONE RULES
- Business English, no jargon, no SQL
- Prescriptive where possible ("Always set Year before Month")
- Answer the anxiety, not just the technical fact
- Keep answers to 1–3 sentences — this is a reference section, not a tutorial
- For Period mode: ALWAYS say "YTD" or "Rolling", never "Last Year" or "Last Month"
"""


def load_faq_prompt() -> str:
    path = PROMPT_DIR / "faq.txt"
    if path.exists():
        base_path = PROMPT_DIR / "base_context.txt"
        base = base_path.read_text(encoding="utf-8") if base_path.exists() else ""
        return (base + "\n\n" + path.read_text(encoding="utf-8")).strip()
    return FAQ_SYSTEM_INLINE


# ============================================================
# STEP 3 — Build user prompt
# ============================================================

def _format_callouts(callouts: list[dict]) -> str:
    if not callouts:
        return "  (none)"
    lines = []
    for c in callouts:
        lines.append(f"  [{c['page']} → {c['widget']} → {c['metric']}]")
        lines.append(f"  Watch-out: {c['callout']}")
        lines.append("")
    return "\n".join(lines)


def _format_cross_page(patterns: list[dict]) -> str:
    if not patterns:
        return "  (none)"
    return "\n".join(
        f"  Pattern: {p.get('pattern','')}\n  Interpretation: {p.get('interpretation','')}\n"
        for p in patterns
    )


def _format_filters(filters: list[dict]) -> str:
    if not filters:
        return "  (none)"
    lines = []
    for f in filters:
        single = "single-select" if str(f["single_select"]).lower() == "true" else "multi-select"
        lines.append(
            f"  - {f['name']} | column: {f['column']} | {single} | default: {f['default']}"
        )
    return "\n".join(lines)


def _format_sub_questions(questions: list[dict]) -> str:
    if not questions:
        return "  (none)"
    lines = []
    seen: set[str] = set()
    for q in questions:
        text = q["question"]
        if text not in seen:
            seen.add(text)
            lines.append(f"  [{q['page']}] {text}")
    return "\n".join(lines)


def build_faq_prompt(data: dict, system_prompt: str) -> tuple[str, str]:
    user_prompt = f"""Generate a FAQ section for the Risk Management Dashboard.

─── DOMAIN CONTEXT ──────────────────────────────────────────
{data['domain_context'] or '(Healthcare risk adjustment — HCC coding, RAF scores, value-based care)'}

─── WATCH-OUTS FROM WIDGET CONTENT (each is a seed for a FAQ answer) ──────
{_format_callouts(data['callouts'])}

─── CROSS-PAGE NAVIGATION PATTERNS ─────────────────────────
{_format_cross_page(data['cross_page_patterns'])}

─── FILTER METADATA (for filter-related FAQs) ───────────────
{_format_filters(data['filter_summaries'])}

─── ANALYTICAL QUESTIONS THIS DASHBOARD ANSWERS (sub-questions) ──────────
{_format_sub_questions(data['sub_questions'])}

─── USERS ───────────────────────────────────────────────────
Medical Director, Care Manager, Payer Analyst, Practice Manager

Use the above signals to generate 10–15 FAQ entries.
Every watch-out should become at least one FAQ question.
Every cross-page pattern should inform at least one navigation FAQ.
Every filter should have a "what does X do" or "how do I use X" FAQ entry.
"""
    return system_prompt, user_prompt


# ============================================================
# STEP 4 — LLM call
# ============================================================

def generate_faq(data: dict, llm_client) -> str:
    system_prompt = load_faq_prompt()
    system_prompt, user_prompt = build_faq_prompt(data, system_prompt)

    response = llm_client.chat.completions.create(
        model=os.environ.get("TF_MODEL", "internal-bedrock/sonnet-46"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content


# ============================================================
# STEP 5 — Save
# ============================================================

def save_faq(content: str, dashboard: str, root: Path) -> Path:
    out_dir  = root / "output" / "dashboards" / dashboard / "stage3"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "faq.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"  [SAVED] {out_path}")
    return out_path


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate faq.md from widget_content + funnel_connector + filters"
    )
    parser.add_argument("--dashboard", default="risk-dash",
                        help="Dashboard name (default: risk-dash)")
    args = parser.parse_args()

    llm_client = OpenAI(
        api_key=os.environ["TF_API_KEY"],
        base_url=os.environ["TF_BASE_URL"],
    )

    data = collect_faq_signals(args.dashboard, _ROOT)

    print(f"  Dashboard          : {args.dashboard}")
    print(f"  Watch-out callouts : {len(data['callouts'])}")
    print(f"  Cross-page patterns: {len(data['cross_page_patterns'])}")
    print(f"  Filters            : {len(data['filter_summaries'])}")
    print(f"  Sub-questions      : {len(data['sub_questions'])}")

    print("\nGenerating FAQ...")
    result = generate_faq(data, llm_client)

    save_faq(result, args.dashboard, _ROOT)
    print("\nDONE")


if __name__ == "__main__":
    main()
