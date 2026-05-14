"""
Glossary Generator
==================
Input:
  - stage3/widget_content/*.json     -> metric name + rich definition (primary source)
  - stage2/final_measures_with_llm.json -> llm_definition for remaining measures
  - stage3/funnel_map.json           -> domain_context (acronym vocabulary)

Output:
  - stage3/glossary.md

The LLM receives all collected terms and their definitions, then produces a
clean glossary table: acronyms first, then domain terms, then metric definitions.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_SRC = str(Path(__file__).resolve().parent.parent)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from utils.llm_client import llm_chat

_ROOT      = Path(__file__).resolve().parent.parent.parent
PROMPT_DIR = _ROOT / "prompt" / "system_prompt"

SKIP_PAGES = {"additional dimensions", "additional_dimensions",
              "scatter plot tooltip", "scatter_plot_tooltip"}


# ============================================================
# STEP 1 — Collect terms from all sources
# ============================================================

def collect_terms(dashboard: str, root: Path) -> dict:
    page_wise = root / "output" / "dashboards" / dashboard / "page_wise"
    stage2 = root / "output" / "dashboards" / dashboard / "metric_dictionary"

    # ── Source A: widget_content (richest definitions) ────────
    widget_dir  = page_wise / "widget_content"
    widget_terms: dict[str, str] = {}   # name -> definition

    if widget_dir.exists():
        for wf in sorted(widget_dir.glob("*.json")):
            try:
                with open(wf, encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"  [WARN] Malformed JSON in {wf.name}, skipping: {e}")
                continue
            page = data.get("page", "")
            if page.lower().replace(" ", "_") in SKIP_PAGES:
                continue
            for widget in data.get("widgets", []):
                for metric in widget.get("metrics", []):
                    name = metric.get("name", "").strip()
                    defn = metric.get("definition", "").strip()
                    if name and defn and name not in widget_terms:
                        widget_terms[name] = defn
    else:
        print(f"  [WARN] widget_content/ not found at {widget_dir}")

    # ── Source B: metric_catalog (business_definition — clean, short) ──
    # Priority: widget_content > metric_catalog > final_measures_with_llm
    catalog_terms: dict[str, str] = {}
    catalog_path = stage2 / "metric_catalog.json"
    if catalog_path.exists():
        try:
            with open(catalog_path, encoding="utf-8") as f:
                catalog = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  [WARN] Malformed JSON in metric_catalog.json, skipping: {e}")
            catalog = []
        entries = catalog if isinstance(catalog, list) else catalog.get("measures", [])
        for entry in entries:
            name = entry.get("measure_name", "").strip()
            defn = (entry.get("business_definition") or "").strip()
            if name and defn and name not in widget_terms:
                catalog_terms[name] = defn
        print(f"  metric_catalog terms : {len(catalog_terms)}")
    else:
        print(f"  [INFO] metric_catalog.json not found — skipping (run metric_catalog_step12.py to generate)")

    # ── Source C: final_measures_with_llm (fills anything still missing) ──
    llm_measures: dict[str, str] = {}
    llm_path = stage2 / "final_measures_with_llm.json"
    if llm_path.exists():
        try:
            with open(llm_path, encoding="utf-8") as f:
                measures = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  [WARN] Malformed JSON in final_measures_with_llm.json, skipping: {e}")
            measures = []
        if isinstance(measures, list):
            for m in measures:
                name = m.get("measure_name", "").strip()
                defn = (m.get("llm_definition") or "").strip()
                # Only use if not already covered by widget_content or metric_catalog
                if name and defn and name not in widget_terms and name not in catalog_terms:
                    llm_measures[name] = defn
    else:
        print(f"  [WARN] final_measures_with_llm.json not found at {llm_path}")

    # ── Source D: funnel_map domain_context ───────────────────
    domain_context = ""
    funnel_path = page_wise / "funnel_map.json"
    if funnel_path.exists():
        with open(funnel_path, encoding="utf-8") as f:
            funnel_map = json.load(f)
        domain_context = funnel_map.get("domain_context", "")
    else:
        print(f"  [WARN] funnel_map.json not found at {funnel_path}")

    return {
        "widget_terms"   : widget_terms,    # {name: definition} — primary (visual-level context)
        "catalog_terms"  : catalog_terms,   # {name: definition} — secondary (metric_catalog business_def)
        "llm_measures"   : llm_measures,    # {name: definition} — tertiary (llm_fallback definitions)
        "domain_context" : domain_context,
    }


# ============================================================
# STEP 2 — System prompt
# ============================================================

GLOSSARY_SYSTEM_INLINE = """\
You are a documentation writer for a healthcare risk adjustment dashboard.

Your task: produce a "Glossary of Terms" section for a Story Guide.

## STRUCTURE — produce exactly this, in this order

### Acronyms & Abbreviations
| Term | Meaning |
|------|---------|
[one row per acronym — HCC, RAF, PMPM, YoY, MoM, YTD, KPI, LOB, PCP, etc.]

### Domain Terms
| Term | Meaning |
|------|---------|
[one row per domain concept — Documented risk, Potential risk, Recapture rate,
 Gap to potential risk, Attribution, Eligible population, Open coding gap,
 Risk score, Coding window, Period mode, YTD, Rolling, etc.]

### Metric Definitions
| Metric Name | Definition |
|-------------|------------|
[one row per dashboard metric — use the provided definitions, condense to ≤ 30 words]

## RULES
- Business English — no SQL, no DAX, no code
- Table cells only — no bullets, no narrative paragraphs
- Metric Definitions column: ≤ 30 words, plain English, present tense
- Never duplicate a term across sections
- Do NOT include display/colour/format measures (their names usually end in "Color", "Card", or contain "UNICHAR")
- If a definition is already ≤ 30 words keep it verbatim; if longer, condense without losing the core meaning
"""


def load_glossary_prompt(dashboard: str = "risk-dash") -> str:
    path = PROMPT_DIR / "glossary.txt"
    if path.exists():
        _cfg_path = PROMPT_DIR.parent / "dashboard_config.json"
        _dash_cfg = json.loads(_cfg_path.read_text(encoding="utf-8")).get(dashboard, {}) if _cfg_path.exists() else {}
        domain_block = (
            f"Domain context:\n"
            f"- This dashboard is used by {_dash_cfg.get('users', 'Care Manager, Medical Director')}\n"
            f"- Domain: {_dash_cfg.get('domain', 'Healthcare dashboard')}\n"
        )
        base_rules = (PROMPT_DIR / "base_context.txt").read_text(encoding="utf-8") if (PROMPT_DIR / "base_context.txt").exists() else ""
        base = (domain_block + "\n" + base_rules).strip()
        return (base + "\n\n" + path.read_text(encoding="utf-8")).strip()
    return GLOSSARY_SYSTEM_INLINE


# ============================================================
# STEP 3 — Build user prompt
# ============================================================

def _format_metric_list(terms: dict[str, str], label: str) -> str:
    if not terms:
        return f"({label}: none found)"
    lines = [f"  - {name}: {defn[:200]}" for name, defn in sorted(terms.items())]
    return "\n".join(lines)


def build_glossary_prompt(data: dict, system_prompt: str) -> tuple[str, str]:
    user_prompt = f"""Generate a Glossary of Terms for the Risk Management Dashboard.

─── DOMAIN CONTEXT ──────────────────────────────────────────
{data['domain_context'] or '(Healthcare risk adjustment — HCC coding, RAF scores, value-based care)'}

─── METRIC DEFINITIONS — SOURCE A: widget content (primary — use verbatim, condense if > 30 words) ──
{_format_metric_list(data['widget_terms'], 'widget_content metrics')}

─── METRIC DEFINITIONS — SOURCE B: metric catalog business definitions (secondary) ──
{_format_metric_list(data['catalog_terms'], 'metric_catalog business_definition')}

─── METRIC DEFINITIONS — SOURCE C: LLM fallback definitions (tertiary — fill any gaps) ──
{_format_metric_list(data['llm_measures'], 'llm_fallback definitions')}

─── USERS ───────────────────────────────────────────────────
Medical Director, Care Manager, Payer Analyst, Practice Manager

Produce the three-section glossary table now.
"""
    return system_prompt, user_prompt


# ============================================================
# STEP 4 — LLM call
# ============================================================

def generate_glossary(data: dict, llm_client, dashboard: str = "risk-dash") -> str:
    system_prompt = load_glossary_prompt(dashboard)
    system_prompt, user_prompt = build_glossary_prompt(data, system_prompt)

    return llm_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.2,
        client=llm_client,
    )


# ============================================================
# STEP 5 — Save
# ============================================================

def save_glossary(content: str, dashboard: str, root: Path) -> Path:
    out_dir  = root / "output" / "dashboards" / dashboard / "glossary_faq"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "glossary.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"  [SAVED] {out_path}")
    return out_path


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate glossary.md from widget_content + final_measures_with_llm"
    )
    parser.add_argument("--dashboard", default="risk-dash",
                        help="Dashboard name (default: risk-dash)")
    args = parser.parse_args()

    llm_client = OpenAI(
        api_key=os.environ["TF_API_KEY"],
        base_url=os.environ["TF_BASE_URL"],
    )

    data = collect_terms(args.dashboard, _ROOT)

    print(f"  Dashboard      : {args.dashboard}")
    print(f"  Widget terms   : {len(data['widget_terms'])}")
    print(f"  Catalog terms  : {len(data['catalog_terms'])}")
    print(f"  LLM measures   : {len(data['llm_measures'])}")
    print(f"  Domain context : {bool(data['domain_context'])}")

    print("\nGenerating glossary...")
    result = generate_glossary(data, llm_client, dashboard=args.dashboard)

    save_glossary(result, args.dashboard, _ROOT)
    print("\nDONE")


if __name__ == "__main__":
    main()
