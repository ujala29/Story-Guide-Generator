"""
scope_classifier.py
────────────────────
Stage 2 — Pre-Step (runs BEFORE lexer/parser)

PURPOSE:
    Reads cleaned measures and splits them into two groups:
      measures_in_scope.json     → compiler will process these (lexer → parser → SQL)
      measures_out_of_scope.json → LLM definitions only, no SQL generation

    Also writes scope_summary.json — counts + reason breakdown for reporting.

INPUT:
    output/dashboards/<dash>/stage1/schema_sections/measures_resolved.json

OUTPUT:
    output/dashboards/<dash>/stage2/scope/
        measures_in_scope.json
        measures_out_of_scope.json
        scope_summary.json

SCOPE DECISION RULES (priority order — first match wins):

    OUT OF SCOPE:
      HARDCODED_STRING    → entire DAX is a string literal
      DISPLAY_SYMBOL      → UNICHAR present
      COLOR_CODE          → SWITCH(TRUE(), x < 0, 1, 2)
      DISPLAY_FORMAT      → FORMAT + SWITCH (without KEEPFILTERS)
      RUNTIME_ROUTER      → SELECTEDVALUE present
      ROW_ITERATOR        → SUMX, AVERAGEX, CONCATENATEX, MINX, MAXX
      DEMO_MEASURE        → RANDBETWEEN present

    IN SCOPE:
      Everything else → compiler attempts parse + SQL generation
"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict


# ══════════════════════════════════════════════════════════════
# PATHS
# ══════════════════════════════════════════════════════════════

BASE_DIR    = Path(__file__).resolve().parent.parent.parent
INPUT_PATHS = [
    BASE_DIR / "output" / "dashboards" / "risk-dash" / "stage1" / "schema_sections" / "measures_resolved.json",
    BASE_DIR / "output" / "dashboards" / "risk-dash" / "stage1" / "schema_sections" / "measures.json",
]
OUTPUT_DIR  = BASE_DIR / "output" / "dashboards" / "risk-dash" / "stage2" / "scope"


# ══════════════════════════════════════════════════════════════
# SCOPE REASON CODES
# ══════════════════════════════════════════════════════════════

SCOPE_IN = "IN_SCOPE"

REASON_HARDCODED_STRING = "HARDCODED_STRING"
REASON_DISPLAY_SYMBOL   = "DISPLAY_SYMBOL"
REASON_COLOR_CODE       = "COLOR_CODE"
REASON_DISPLAY_FORMAT   = "DISPLAY_FORMAT"
REASON_RUNTIME_ROUTER   = "RUNTIME_ROUTER"
REASON_ROW_ITERATOR     = "ROW_ITERATOR"
REASON_DEMO_MEASURE     = "DEMO_MEASURE"

REASON_DESCRIPTIONS = {
    REASON_HARDCODED_STRING : "Pure string literal — no DAX logic, no SQL equivalent",
    REASON_DISPLAY_SYMBOL   : "Uses UNICHAR() — produces display symbols (▲▼), not a metric",
    REASON_COLOR_CODE       : "SWITCH(TRUE(),...) returning integer — conditional formatting color code",
    REASON_DISPLAY_FORMAT   : "FORMAT/SWITCH combination — produces display string, not a number",
    REASON_RUNTIME_ROUTER   : "Uses SELECTEDVALUE — depends on user slicer at runtime, SQL cannot resolve",
    REASON_ROW_ITERATOR     : "Uses row iterator (SUMX/CONCATENATEX/etc.) — no direct SQL equivalent",
    REASON_DEMO_MEASURE     : "Uses RANDBETWEEN — non-deterministic demo measure, must not be translated",
    SCOPE_IN                : "Compiler will attempt parse + SQL generation",
}

LLM_ROLE_DEFINER = "DEFINER"


# ══════════════════════════════════════════════════════════════
# SCOPE DECISION FUNCTION
# ══════════════════════════════════════════════════════════════

def classify_scope(measure_name: str, measure: dict) -> tuple[str, str]:
    """
    Decide whether a measure is in-scope or out-of-scope for the compiler.

    Returns:
        (scope, reason)
        scope  = "IN_SCOPE" or one of the REASON_* constants
        reason = human-readable explanation string
    """
    dax = (measure.get("clean_dax") or measure.get("dax") or "").strip()

    if not dax:
        return REASON_HARDCODED_STRING, REASON_DESCRIPTIONS[REASON_HARDCODED_STRING]

    dax_upper = dax.upper()

    if dax.startswith('"') or dax.startswith("'"):
        return REASON_HARDCODED_STRING, REASON_DESCRIPTIONS[REASON_HARDCODED_STRING]

    if "RANDBETWEEN" in dax_upper:
        return REASON_DEMO_MEASURE, REASON_DESCRIPTIONS[REASON_DEMO_MEASURE]

    if "UNICHAR" in dax_upper:
        return REASON_DISPLAY_SYMBOL, REASON_DESCRIPTIONS[REASON_DISPLAY_SYMBOL]

    if re.search(
        r'SWITCH\s*\(\s*TRUE\s*\(\s*\)\s*,\s*\w+\s*[<>]=?\s*\d+\s*,\s*\d',
        dax_upper
    ):
        return REASON_COLOR_CODE, REASON_DESCRIPTIONS[REASON_COLOR_CODE]

    if (
        "FORMAT" in dax_upper
        and "SWITCH" in dax_upper
        and "KEEPFILTERS" not in dax_upper
    ):
        return REASON_DISPLAY_FORMAT, REASON_DESCRIPTIONS[REASON_DISPLAY_FORMAT]

    if "SELECTEDVALUE" in dax_upper:
        return REASON_RUNTIME_ROUTER, REASON_DESCRIPTIONS[REASON_RUNTIME_ROUTER]

    ROW_ITERATORS = ["SUMX", "AVERAGEX", "CONCATENATEX", "MINX", "MAXX",
                     "COUNTX", "RANKX", "TOPN", "GENERATE"]
    for fn in ROW_ITERATORS:
        if re.search(r'\b' + fn + r'\s*\(', dax_upper):
            return (
                REASON_ROW_ITERATOR,
                f"{REASON_DESCRIPTIONS[REASON_ROW_ITERATOR]} (function: {fn})"
            )

    return SCOPE_IN, REASON_DESCRIPTIONS[SCOPE_IN]


# ══════════════════════════════════════════════════════════════
# MEASURE ENTRY BUILDER
# ══════════════════════════════════════════════════════════════

def _build_entry(name: str, measure: dict, scope: str, reason: str) -> dict:
    dax_clean = (measure.get("clean_dax") or measure.get("dax") or "").strip()
    dax_raw   = (measure.get("raw_dax")   or measure.get("dax") or "").strip()

    entry = {
        "measure_name"           : name,
        "table"                  : measure.get("table", ""),
        "raw_dax"                : dax_raw,
        "clean_dax"              : dax_clean,
        "scope"                  : scope,
        "scope_reason"           : reason,
        "is_leaf"                : measure.get("is_leaf",  True),
        "depth"                  : measure.get("depth",    0),
        "depends_on"             : measure.get("depends_on", []),
        "referenced_columns"     : measure.get("referenced_columns", []),
        "all_referenced_columns" : measure.get("all_referenced_columns", []),
    }

    if scope != SCOPE_IN:
        entry["llm_role"]       = LLM_ROLE_DEFINER
        entry["sql_applicable"] = False
        entry["sql_query"]      = None
        entry["llm_definition"] = None
    else:
        entry["sql_applicable"] = True
        entry["sql_query"]      = None
        entry["parse_status"]   = None
        entry["verified"]       = False

    return entry


# ══════════════════════════════════════════════════════════════
# MAIN CLASSIFIER
# ══════════════════════════════════════════════════════════════

def run_scope_classification(measures: dict) -> dict:
    """
    Classify all measures into in-scope and out-of-scope.

    Returns:
        {
          "in_scope"     : list of in-scope measure entries
          "out_of_scope" : list of out-of-scope measure entries
          "summary"      : aggregate stats dict
        }
    """
    in_scope      = []
    out_of_scope  = []
    reason_counts = defaultdict(int)
    reason_names  = defaultdict(list)

    for name, measure in measures.items():
        scope, reason = classify_scope(name, measure)
        entry = _build_entry(name, measure, scope, reason)

        if scope == SCOPE_IN:
            in_scope.append(entry)
            reason_counts[SCOPE_IN] += 1
            reason_names[SCOPE_IN].append(name)
        else:
            out_of_scope.append(entry)
            reason_counts[scope] += 1
            reason_names[scope].append(name)

    in_scope.sort(    key=lambda x: x["measure_name"])
    out_of_scope.sort(key=lambda x: x["measure_name"])

    total = len(in_scope) + len(out_of_scope)

    summary = {
        "generated_at"       : datetime.now(timezone.utc).isoformat(),
        "total_measures"     : total,
        "in_scope_count"     : len(in_scope),
        "out_of_scope_count" : len(out_of_scope),
        "in_scope_pct"       : round(len(in_scope)     / total * 100, 1) if total else 0,
        "out_of_scope_pct"   : round(len(out_of_scope) / total * 100, 1) if total else 0,
        "breakdown" : {
            reason: {
                "count"       : reason_counts[reason],
                "description" : REASON_DESCRIPTIONS.get(reason, ""),
                "measures"    : sorted(reason_names[reason]),
            }
            for reason in [
                SCOPE_IN,
                REASON_HARDCODED_STRING,
                REASON_DISPLAY_SYMBOL,
                REASON_COLOR_CODE,
                REASON_DISPLAY_FORMAT,
                REASON_RUNTIME_ROUTER,
                REASON_ROW_ITERATOR,
                REASON_DEMO_MEASURE,
            ]
            if reason_counts[reason] > 0
        }
    }

    return {
        "in_scope"     : in_scope,
        "out_of_scope" : out_of_scope,
        "summary"      : summary,
    }


# ══════════════════════════════════════════════════════════════
# FILE WRITER
# ══════════════════════════════════════════════════════════════

def write_outputs(result: dict, output_dir: Path) -> tuple[Path, Path, Path]:
    """Write all three output files. Returns (in_scope_path, out_of_scope_path, summary_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    in_scope_path     = output_dir / "measures_in_scope.json"
    out_of_scope_path = output_dir / "measures_out_of_scope.json"
    summary_path      = output_dir / "scope_summary.json"

    in_scope_path.write_text(
        json.dumps(result["in_scope"], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    out_of_scope_path.write_text(
        json.dumps(result["out_of_scope"], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    summary_path.write_text(
        json.dumps(result["summary"], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return in_scope_path, out_of_scope_path, summary_path


# ══════════════════════════════════════════════════════════════
# LOADER
# ══════════════════════════════════════════════════════════════

def _load_measures() -> tuple[dict, Path]:
    """Try input paths in order, return (measures_dict, path_used)."""
    for path in INPUT_PATHS:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {m["name"]: m for m in data}, path
            return data, path
    raise FileNotFoundError(
        "No input file found. Tried:\n" +
        "\n".join(f"  {p}" for p in INPUT_PATHS)
    )


# ══════════════════════════════════════════════════════════════
# PUBLIC API  — used by pipeline_step9.py
# ══════════════════════════════════════════════════════════════

def get_in_scope(output_dir: Path = OUTPUT_DIR) -> list[dict]:
    """Load and return in-scope measures."""
    path = output_dir / "measures_in_scope.json"
    if not path.exists():
        raise FileNotFoundError(f"Run scope_classifier.py first: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def get_out_of_scope(output_dir: Path = OUTPUT_DIR) -> list[dict]:
    """Load and return out-of-scope measures."""
    path = output_dir / "measures_out_of_scope.json"
    if not path.exists():
        raise FileNotFoundError(f"Run scope_classifier.py first: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════
# MAIN  — direct run
# ══════════════════════════════════════════════════════════════

def main():
    print("[scope_classifier] Starting...")
    try:
        measures, input_path = _load_measures()
    except FileNotFoundError as e:
        print(f"[scope_classifier] ERROR: {e}")
        return

    print(f"[scope_classifier] Loaded {len(measures)} measures from {input_path.name}")

    result  = run_scope_classification(measures)
    summary = result["summary"]

    p_in, p_out, p_sum = write_outputs(result, OUTPUT_DIR)

    print(f"[scope_classifier] In scope    : {summary['in_scope_count']}")
    print(f"[scope_classifier] Out of scope: {summary['out_of_scope_count']}")
    for reason, info in summary["breakdown"].items():
        print(f"[scope_classifier]   {reason}: {info['count']}")
    print(f"[scope_classifier] Outputs written to {OUTPUT_DIR}/")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        print("[scope_classifier] Self-test mode")
        test_measures = {
            "#Members"    : {"dax": "SUM(attribution[member_count])", "clean_dax": "SUM(attribution[member_count])"},
            "YoY Card"    : {"dax": 'RETURN UNICHAR(9650) & FORMAT(yoy,"0%")', "clean_dax": 'RETURN UNICHAR(9650)'},
            "Info text"   : {"dax": '"The cohort is built on..."', "clean_dax": '"The cohort is built on..."'},
        }
        result = run_scope_classification(test_measures)
        assert len(result["in_scope"]) == 1, "Expected 1 in-scope"
        assert len(result["out_of_scope"]) == 2, "Expected 2 out-of-scope"
        print("[scope_classifier] All tests passed.")
    else:
        main()
