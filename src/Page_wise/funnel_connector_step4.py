"""
funnel_connector.py
===================
Stage 3C

Reads funnel_map.json and generates funnel_connector.json containing:

1. funnel_table  — "How the funnel connects" table (Layer | Section | Question)
   One row per widget. Matches template page 18 of Risk story guide.

2. closing_paragraph — 2-3 sentences connecting all pages into one narrative arc

Single LLM call. No widget content files needed — sub_question per widget
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from funnel_map is sufficient input.

INPUT:
  output/dashboards/<dash>/stage3/funnel_map.json

OUTPUT:
  output/dashboards/<dash>/stage3/funnel_connector.json

Run:
  python funnel_connector.py
  python funnel_connector.py --dashboard risk-dash
  python funnel_connector.py --force
"""

import json
import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_SRC = str(Path(__file__).resolve().parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.llm_client import llm_chat


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "output").exists() and (parent / "config").exists():
            return parent
    return Path(__file__).resolve().parent.parent.parent


def load_json(path: Path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def call_llm(system: str, user: str) -> str:
    return llm_chat(
        [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.1,
        max_tokens=2000,
    )


def parse_json_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        while lines and lines[-1].strip() in ("```", ""):
            lines.pop()
        text = "\n".join(lines).strip()
    return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# Layer label mapping
# ─────────────────────────────────────────────────────────────────────────────

POSITION_TO_LAYER = {
    "TOP":    "Top",
    "MIDDLE": "Mid",
    "BOTTOM": "Bottom",
    "ACTION": "Action",
}


# ─────────────────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM = """You are a technical documentation writer producing the final summary section
of a BI dashboard story guide.

You are writing two things:
1. A "How the funnel connects" table — one row per widget section, three columns:
   Layer | Section | Question it answers
   This table shows the reader at a glance how each section of the dashboard
   connects to the analytical story, from headline metrics down to actions.

2. A closing paragraph — 2-3 sentences that describe how the layers connect
   into one continuous analytical narrative. This paragraph should explain
   how each layer answers the question the previous one raises.
   Write it in plain business language, not technical language.

Output valid JSON only. No explanation, no markdown fences."""


def build_prompt(funnel_map: dict) -> str:
    dashboard_name = funnel_map.get("dashboard_name", "")
    domain_context = funnel_map.get("domain_context", "")

    # build widget summary — only non-mirrored widgets
    widgets = [
        w for w in funnel_map.get("widgets", [])
        if not w.get("mirrored_from")
    ]

    widget_lines = []
    for w in widgets:
        layer = POSITION_TO_LAYER.get(w.get("funnel_position", ""), "")
        widget_lines.append(
            f"  [{layer}] {w['widget_name']}\n"
            f"    sub_question: {w.get('sub_question', '')}"
        )

    widgets_text = "\n\n".join(widget_lines)

    funnel_questions = (
        f"TOP    = {funnel_map.get('funnel_question_top','')}\n"
        f"MIDDLE = {funnel_map.get('funnel_question_middle','')}\n"
        f"BOTTOM = {funnel_map.get('funnel_question_bottom','')}\n"
        f"ACTION = {funnel_map.get('funnel_question_action','')}"
    )

    schema = """{
  "cross_page_patterns": [
    {
      "pattern": "a situation that involves comparing data across two pages of this dashboard",
      "interpretation": "what this cross-page combination means operationally and what action it suggests"
    }
  ],
  "funnel_table": [
    {
      "layer": "Top / Mid / Bottom / Action",
      "section": "short section name matching the widget_name",
      "question_it_answers": "the specific question this section answers — concise, 1 sentence"
    }
  ],
  "closing_paragraph": "2-3 sentences connecting all layers into one narrative arc"
}"""

    return f"""Dashboard: {dashboard_name}
Domain: {domain_context}

Funnel questions:
{funnel_questions}

Widget sections (in reading order):
{widgets_text}

Produce the "How the funnel connects" summary.

Return JSON matching this structure:
{schema}

Rules:
- cross_page_patterns: 3-4 patterns that require comparing an entity or metric across
  the overview/diagnostic page AND the action/targeting page together.
  Example: a provider appears both in the BOTTOM entity table AND in the ACTION targeting list —
  what does each combination mean? These patterns help the reader connect the two pages.
  Write patterns using entities and metrics from THIS dashboard — draw from domain_context.
- funnel_table: one row per widget listed above, in the same order
- layer: use "Top", "Mid", "Bottom", or "Action" — not the full word
- section: short name (3-5 words max) — not the full widget_name
- question_it_answers: rewrite sub_question as a crisp single question the reader would ask
- closing_paragraph: explain how each layer answers the question raised by the previous one.
  Use ONLY terminology drawn from the domain_context and funnel questions above.
  Do NOT assume the domain — write in terms that apply to THIS dashboard specifically.
- JSON only"""


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run_funnel_connector(funnel_map: dict) -> dict:
    prompt = build_prompt(funnel_map)

    for attempt in range(1, 4):
        print(f"[funnel_connector] attempt {attempt}/3...")
        raw = call_llm(SYSTEM, prompt)

        if not raw:
            print("[funnel_connector] empty response")
            continue

        try:
            result = parse_json_response(raw)
        except Exception as e:
            print(f"[funnel_connector] parse failed: {e}")
            print(f"[funnel_connector] last 200 chars: ...{raw[-200:]}")
            continue

        if "funnel_table" not in result or not result["funnel_table"]:
            print("[funnel_connector] missing funnel_table")
            continue

        if "closing_paragraph" not in result or not result["closing_paragraph"]:
            print("[funnel_connector] missing closing_paragraph")
            continue

        if "cross_page_patterns" not in result or not result["cross_page_patterns"]:
            print("[funnel_connector] missing cross_page_patterns")
            continue

        rows     = len(result["funnel_table"])
        patterns = len(result["cross_page_patterns"])
        print(f"[funnel_connector] ok — {rows} rows, {patterns} cross-page patterns")
        return result

    raise RuntimeError("funnel_connector failed after 3 attempts")


def main():
    parser = argparse.ArgumentParser(
        description="Generate funnel_connector.json"
    )
    parser.add_argument("--dashboard", default="risk-dash")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if output exists")
    args = parser.parse_args()

    root     = get_project_root()
    stage3   = root / "output" / "dashboards" / args.dashboard / "page_wise"
    in_path  = stage3 / "funnel_map.json"
    out_path = stage3 / "funnel_connector.json"

    print(f"[funnel_connector] dashboard : {args.dashboard}")

    funnel_map = load_json(in_path)
    if not funnel_map:
        raise FileNotFoundError(
            f"funnel_map.json not found at {in_path}\n"
            f"Run funnel_mapper.py first."
        )

    # cache check
    if not args.force and out_path.exists():
        existing = load_json(out_path)
        if (existing and
                existing.get("content_hash") ==
                funnel_map.get("_meta", {}).get("content_hash")):
            print("[funnel_connector] cache hit — use --force to re-run")
            return

    result = run_funnel_connector(funnel_map)

    # attach content_hash for cache
    result["content_hash"] = funnel_map.get("_meta", {}).get("content_hash")
    result["dashboard"]    = args.dashboard

    stage3.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[funnel_connector] written to: {out_path}")
    print()
    print("── Cross-Page Patterns ─────────────────────────────────────")
    for p in result.get("cross_page_patterns", []):
        print(f"  {p['pattern'][:60]}")
        print(f"    -> {p['interpretation'][:70]}")
    print()
    print("── Funnel Table ────────────────────────────────────────────")
    for row in result["funnel_table"]:
        print(f"  {row['layer']:<8} {row['section']:<35} {row['question_it_answers'][:50]}")
    print()
    print("── Closing Paragraph ───────────────────────────────────────")
    print(result["closing_paragraph"])
    print("────────────────────────────────────────────────────────────")


if __name__ == "__main__":
    main()
