"""
pipeline.py
───────────
Stage 2 — Orchestrator

PURPOSE:
    Runs all Stage 2 steps in order for every measure and produces
    final_measures.json + run_report.json.

PIPELINE ORDER:
    Step 0  scope_classifier   → split in-scope / out-of-scope
    Step 1  cleaner            → raw DAX → CleanResult
    Step 2a lexer              → clean DAX → tokens
    Step 2b parser             → tokens → AST
    Step 3  dep_resolver       → dependency graph + topo order
    Step 4  semantic_resolver  → BI names → SF names + VarRef upgrade
    Step 5  classifier         → dax_pattern label
    Step 6  sql_generator      → AST → SQL (bottom-up, uses sql_cache)
    [Step 7 verifier]          → Snowflake run (optional — requires DB conn)
    [Step 8 llm_fallback]      → COMPLEX/out-of-scope (optional — requires API key)

INPUT FILES (auto-detected from common paths):
    measures_resolved.json     → raw measures from stage1
    bi_snowflakes_naming_matching.json → BI → SF mapping
    relationships.json         → table join paths

OUTPUT FILES:
    output/stage2/final_measures.json   → all measures with SQL
    output/stage2/run_report.json       → summary + stats

USAGE:
    python pipeline.py
    python pipeline.py --dashboard risk_management
    python pipeline.py --dashboard pcp_dashboard
    python pipeline.py --input path/to/measures_resolved.json
    python pipeline.py --dry-run    (parse + classify only, no SQL)

DASHBOARD STRUCTURE:
    output/
      stage2/
        dashboards/
          risk_management/    ← default (current behaviour)
          pcp_dashboard/
          (any future dashboard)
        final_measures.json   ← always written (latest run)
        run_report.json       ← always written (latest run)
"""

from __future__ import annotations
import json
import sys
import time

# Force UTF-8 stdout so Unicode chars (→, ✅, ─) work on Windows cp1252 consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import argparse
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

# ── Stage2 imports ───────────────────────────────────────────
from cleaner_step1           import clean, CleanResult
from lexer_step3             import tokenize
from parser_step4            import parse as parse_dax
from dep_resolver_step5      import resolve as dep_resolve, DepResult
from semantic_resolver_step6 import (
    build_snowflake_lookup, build_rel_graph,
    resolve_one, AnnotatedAST,
)
from classifier_step7        import classify as do_classify, ClassifyResult
from sql_generator_step8     import generate, GenerateResult, load_table_metadata
from scope_classifier        import (
    run_scope_classification, classify_scope,
    SCOPE_IN, write_outputs as write_scope_outputs,
)
from ast_nodes_step0         import ParseSuccess, ParseFailure


# ══════════════════════════════════════════════════════════════
# PATHS  — auto-detect common locations
# ══════════════════════════════════════════════════════════════

_BASE = Path(__file__).resolve().parent.parent.parent

INPUT_CANDIDATES = [
    _BASE / "output" / "metric_dictionary" / "step1_cleaned_measures.json",
    _BASE / "output" / "schema_sections"   / "measures_resolved.json",
    _BASE / "input"  / "measures_resolved.json",
]

SF_MAP_CANDIDATES = [
    _BASE / "input"  / "bi_snowflakes_naming_matching.json",
    _BASE / "config" / "bi_snowflakes_naming_matching.json",
]

REL_CANDIDATES = [
    _BASE / "output" / "dashboards" / "risk-dash" / "stage1" / "schema_sections" / "relationships.json",
    _BASE / "input"  / "relationships.json",
]

DASHBOARDS_DIR  = _BASE / "output" / "dashboards"
OUTPUT_DIR      = DASHBOARDS_DIR / "risk-dash" / "stage2"   # default (latest run)

# Per-dashboard input candidates
# Add new dashboards here — key = dashboard name, value = candidate paths
DASHBOARD_INPUTS = {
    "risk-dash": [
        _BASE / "output" / "dashboards" / "risk-dash" / "stage1" / "schema_sections" / "measures_resolved.json",
        _BASE / "output" / "dashboards" / "risk-dash" / "stage1" / "schema_sections" / "measures.json",
        _BASE / "input"  / "measures_resolved.json",
    ],
    "pac-dash": [
        _BASE / "output" / "dashboards" / "pac-dash" / "stage1" / "schema_sections" / "measures_resolved.json",
        _BASE / "output" / "dashboards" / "pac-dash" / "stage1" / "schema_sections" / "measures.json",
    ],
}

DASHBOARD_SF_MAPS = {
    "risk-dash": [
        _BASE / "input"  / "bi_snowflakes_naming_matching.json",
        _BASE / "config" / "bi_snowflakes_naming_matching.json",
    ],
    "pac-dash": [
        _BASE / "input"  / "pac_dashboard_bi_snowflkes_naming_matching.json",
        _BASE / "input"  / "pac" / "bi_snowflakes_naming_matching.json",
    ],
}

DASHBOARD_RELS = {
    "risk-dash": [
        _BASE / "output" / "dashboards" / "risk-dash" / "stage1" / "schema_sections" / "relationships.json",
    ],
    "pac-dash": [
        _BASE / "output" / "dashboards" / "pac-dash" / "stage1" / "schema_sections" / "relationships.json",
    ],
}


# ══════════════════════════════════════════════════════════════
# LOADERS
# ══════════════════════════════════════════════════════════════

def _find_file(candidates: list[Path], label: str) -> Path:
    for p in candidates:
        if p.exists():
            return p
    paths = "\n".join(f"  {p}" for p in candidates)
    raise FileNotFoundError(f"{label} not found. Tried:\n{paths}")


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_measures(path: Path) -> dict:
    """Load measures — handle both list and dict formats."""
    data = _load_json(path)
    if isinstance(data, list):
        return {m["name"]: m for m in data}
    return data


# ══════════════════════════════════════════════════════════════
# MEASURE RECORD  — one entry in final_measures.json
# ══════════════════════════════════════════════════════════════

def _make_record(
    name        : str,
    measure     : dict,
    clean_result: CleanResult,
    parse_result: ParseSuccess | ParseFailure | None,
    ann         : AnnotatedAST | None,
    clf         : ClassifyResult | None,
    gen         : GenerateResult | None,
    scope       : str,
    scope_reason: str,
    duration_ms : int,
) -> dict:
    """Build a single measure record for final_measures.json."""

    record = {
        # ── Identity ─────────────────────────────────────────
        "measure_name"   : name,
        "table"          : measure.get("table", ""),
        "scope"          : scope,
        "scope_reason"   : scope_reason,

        # ── DAX ──────────────────────────────────────────────
        "raw_dax"        : clean_result.raw_dax,
        "clean_dax"      : clean_result.clean_dax,
        "had_plus_zero"  : clean_result.had_plus_zero,
        "had_metadata"   : clean_result.had_metadata,
        "warnings"       : clean_result.warnings,
        "stripped_comments": clean_result.stripped_comments,

        # ── Parse ─────────────────────────────────────────────
        "parse_status"   : (
            "success" if isinstance(parse_result, ParseSuccess)
            else "failed" if isinstance(parse_result, ParseFailure)
            else "skipped"
        ),
        "parse_error"    : (
            parse_result.error if isinstance(parse_result, ParseFailure) else None
        ),

        # ── Pattern ──────────────────────────────────────────
        "dax_pattern"    : clf.dax_pattern    if clf else None,
        "sql_applicable" : clf.sql_applicable if clf else False,
        "has_time_intel" : clf.has_time_intel if clf else False,
        "has_all"        : clf.has_all        if clf else False,
        "has_static"     : clf.has_static     if clf else False,

        # ── SQL ──────────────────────────────────────────────
        "sql_query"      : gen.sql       if gen else None,
        "needs_llm"      : gen.needs_llm if gen else (scope != SCOPE_IN),
        "llm_role"       : (gen.llm_role if gen else
                            ("DEFINER" if scope != SCOPE_IN else None)),
        "llm_definition" : None,    # filled by llm_fallback.py later
        "cte_blocks"     : gen.cte_blocks if gen else [],
        "sql_error"      : gen.error      if gen else None,

        # ── Resolution ───────────────────────────────────────
        "sf_refs"        : (
            [{"bi_table": r.bi_table, "sf_object": r.sf_object,
              "sf_column": r.sf_column, "ref_type": r.ref_type}
             for r in ann.sf_refs]
            if ann else []
        ),
        "join_paths"     : ann.join_paths    if ann else [],
        "static_tables"  : ann.static_tables if ann else [],
        "unresolved"     : ann.unresolved    if ann else [],

        # ── Meta ─────────────────────────────────────────────
        "depends_on"     : measure.get("depends_on", []),
        "depth"          : measure.get("depth", 0),
        "is_leaf"        : measure.get("is_leaf", True),
        "duration_ms"    : duration_ms,
    }

    return record


# ══════════════════════════════════════════════════════════════
# RUN REPORT
# ══════════════════════════════════════════════════════════════

def _make_report(
    records     : list[dict],
    started_at  : str,
    duration_s  : float,
    input_path  : str,
) -> dict:
    """Build run_report.json."""

    total      = len(records)
    in_scope   = [r for r in records if r["scope"]   == SCOPE_IN]
    out_scope  = [r for r in records if r["scope"]   != SCOPE_IN]

    parsed_ok  = [r for r in in_scope if r["parse_status"] == "success"]
    parsed_fail= [r for r in in_scope if r["parse_status"] == "failed"]

    sql_ok     = [r for r in in_scope if r["sql_query"]  is not None]
    sql_fail   = [r for r in in_scope if r["sql_query"]  is None
                  and r["parse_status"] == "success"]

    needs_llm  = [r for r in records  if r["needs_llm"]]

    # Pattern breakdown
    pattern_counts = defaultdict(int)
    for r in in_scope:
        if r["dax_pattern"]:
            pattern_counts[r["dax_pattern"]] += 1

    # Scope reason breakdown
    scope_counts = defaultdict(int)
    for r in records:
        scope_counts[r["scope"]] += 1

    # Warnings
    all_warnings = []
    for r in records:
        for w in r.get("warnings", []):
            all_warnings.append({"measure": r["measure_name"], "warning": w})

    # Unresolved tables
    all_unresolved = []
    for r in records:
        for t in r.get("unresolved", []):
            all_unresolved.append({"measure": r["measure_name"], "table": t})

    return {
        "run_at"         : started_at,
        "duration_s"     : round(duration_s, 2),
        "input_file"     : input_path,

        "totals": {
            "total_measures"    : total,
            "in_scope"          : len(in_scope),
            "out_of_scope"      : len(out_scope),
            "parsed_ok"         : len(parsed_ok),
            "parsed_failed"     : len(parsed_fail),
            "sql_generated"     : len(sql_ok),
            "sql_failed"        : len(sql_fail),
            "needs_llm"         : len(needs_llm),
            "compiler_handled"  : len(sql_ok),
        },

        "percentages": {
            "in_scope_pct"      : round(len(in_scope)  / total * 100, 1) if total else 0,
            "sql_generated_pct" : round(len(sql_ok)    / total * 100, 1) if total else 0,
            "compiler_pct"      : round(len(sql_ok)    / len(in_scope) * 100, 1)
                                  if in_scope else 0,
        },

        "pattern_breakdown"  : dict(sorted(
            pattern_counts.items(), key=lambda x: -x[1]
        )),
        "scope_breakdown"    : dict(scope_counts),

        "warnings"           : all_warnings,
        "unresolved_tables"  : all_unresolved,

        "measures_needing_llm": [
            {"name": r["measure_name"], "role": r["llm_role"],
             "reason": r.get("sql_error") or r["scope_reason"]}
            for r in needs_llm
        ],

        "sql_failures": [
            {"name": r["measure_name"], "error": r.get("sql_error", ""),
             "pattern": r.get("dax_pattern", "")}
            for r in in_scope
            if r["sql_query"] is None and r["parse_status"] == "success"
        ],

        "parse_failures": [
            {"name": r["measure_name"], "error": r.get("parse_error", "")}
            for r in parsed_fail
        ],
    }


# ══════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════

def run_pipeline(
    input_path : Path,
    sf_map_path: Path,
    rel_path   : Path,
    output_dir : Path,
    dry_run    : bool = False,
    verbose    : bool = True,
) -> dict:
    """
    Run the full Stage 2 pipeline.

    Args:
        input_path  : path to measures_resolved.json or step1_cleaned_measures.json
        sf_map_path : path to bi_snowflakes_naming_matching.json
        rel_path    : path to relationships.json
        output_dir  : where to write final_measures.json + run_report.json
        dry_run     : if True, skip SQL generation (parse + classify only)
        verbose     : print progress

    Returns:
        run_report dict
    """
    started_at  = datetime.now(timezone.utc).isoformat()
    t_start     = time.time()

    # ── Load inputs ──────────────────────────────────────────
    if verbose:
        print("=" * 60)
        print("  Stage 2 — DAX → SQL Pipeline")
        print("=" * 60)
        print(f"\n  Input    : {input_path.name}")
        print(f"  SF map   : {sf_map_path.name}")
        print(f"  Rels     : {rel_path.name}")
        print(f"  Output   : {output_dir}")
        print(f"  Dry run  : {dry_run}\n")

    raw_measures  = _load_measures(input_path)
    sf_map        = _load_json(sf_map_path)
    relationships = _load_json(rel_path)
    if isinstance(relationships, dict):
        relationships = relationships.get("relationships", list(relationships.values()))

    if verbose:
        print(f"  Loaded {len(raw_measures)} measures")

    # Load date_column + max_month_flag from JSON into sql_generator globals
    load_table_metadata(sf_map)

    # Validate metadata was actually loaded — fail fast if JSON is malformed
    from sql_generator_step8 import DATE_COL_MAP, MAX_MONTH_TABLES
    if not DATE_COL_MAP:
        print("\n❌ ERROR: DATE_COL_MAP not populated.")
        print("   Check date_column fields in bi_snowflakes_naming_matching.json")
        sys.exit(1)
    if not MAX_MONTH_TABLES:
        print("\n❌ ERROR: MAX_MONTH_TABLES not populated.")
        print("   Check has_max_month_flag fields in bi_snowflakes_naming_matching.json")
        sys.exit(1)

    sf_lookup = build_snowflake_lookup(sf_map)
    rel_graph = build_rel_graph(relationships)

    # ── Step 0: Scope classification ─────────────────────────
    if verbose:
        print("\n  [Step 0] Scope classification...")

    scope_result = run_scope_classification(raw_measures)
    in_scope_set = {e["measure_name"] for e in scope_result["in_scope"]}

    if verbose:
        s = scope_result["summary"]
        print(f"    In scope    : {s['in_scope_count']}")
        print(f"    Out of scope: {s['out_of_scope_count']}")

    # ── Step 1: Clean all measures ───────────────────────────
    if verbose:
        print("\n  [Step 1] Cleaning DAX...")

    clean_results: dict[str, CleanResult] = {}
    for name, measure in raw_measures.items():
        raw_dax = (measure.get("clean_dax")
                   or measure.get("raw_dax")
                   or measure.get("dax", ""))
        clean_results[name] = clean(name, raw_dax)

    # ── Step 2: Parse in-scope measures ──────────────────────
    if verbose:
        print(f"\n  [Step 2] Parsing {len(in_scope_set)} in-scope measures...")

    parse_results: dict[str, ParseSuccess | ParseFailure] = {}
    for name in in_scope_set:
        cr = clean_results[name]
        parse_results[name] = parse_dax(name, cr.clean_dax)

    parsed_ok   = {n: r for n, r in parse_results.items()
                   if isinstance(r, ParseSuccess)}
    parsed_fail = {n: r for n, r in parse_results.items()
                   if isinstance(r, ParseFailure)}

    if verbose:
        print(f"    Parsed OK  : {len(parsed_ok)}")
        print(f"    Parse fail : {len(parsed_fail)}")
        if parsed_fail:
            for name, r in list(parsed_fail.items())[:3]:
                print(f"      ❌ {name}: {r.error[:60]}")

    # ── Step 3: Dependency resolution ─────────────────────────
    if verbose:
        print("\n  [Step 3] Resolving dependencies...")

    dep_result: DepResult = dep_resolve(parsed_ok)

    if dep_result.circular and verbose:
        print(f"    ⚠️  Circular deps: {dep_result.circular}")

    if verbose:
        print(f"    Topo order : {len(dep_result.order)} measures")
        print(f"    Circular   : {len(dep_result.circular)}")

    # ── Step 4: Semantic resolution ───────────────────────────
    if verbose:
        print("\n  [Step 4] Resolving Snowflake names...")

    ann_map: dict[str, AnnotatedAST] = {}
    for name in dep_result.order:
        if name not in parsed_ok:
            continue
        ann_map[name] = resolve_one(
            name, parsed_ok[name].ast,
            dep_result, sf_lookup, rel_graph,
        )

    unresolved_count = sum(len(a.unresolved) for a in ann_map.values())
    if verbose:
        print(f"    Resolved   : {len(ann_map)}")
        print(f"    Unresolved tables: {unresolved_count}")

    # ── Step 5: Classify ─────────────────────────────────────
    if verbose:
        print("\n  [Step 5] Classifying patterns...")

    clf_map: dict[str, ClassifyResult] = {}
    for name, ann in ann_map.items():
        clf_map[name] = do_classify(ann)

    pattern_counts = defaultdict(int)
    for clf in clf_map.values():
        pattern_counts[clf.dax_pattern] += 1

    if verbose:
        print("    Patterns found:")
        for pat, cnt in sorted(pattern_counts.items(), key=lambda x: -x[1]):
            print(f"      {pat:25} : {cnt}")

    # ── Step 6: SQL generation ────────────────────────────────
    if not dry_run:
        if verbose:
            print("\n  [Step 6] Generating SQL...")

        sql_cache: dict[str, str] = {}
        gen_map:   dict[str, GenerateResult] = {}

        for name in dep_result.order:
            if name not in ann_map:
                continue
            ann = ann_map[name]
            clf = clf_map[name]

            result = generate(ann, clf, sql_cache)
            gen_map[name] = result

            if result.sql:
                sql_cache[name] = result.sql

        sql_ok   = sum(1 for r in gen_map.values() if r.sql)
        sql_fail = sum(1 for r in gen_map.values() if not r.sql)

        if verbose:
            print(f"    SQL generated : {sql_ok}")
            print(f"    Needs LLM     : {sql_fail}")
    else:
        gen_map = {}
        if verbose:
            print("\n  [Step 6] Skipped (dry-run mode)")

    # ── Assemble records ─────────────────────────────────────
    if verbose:
        print("\n  Assembling output...")

    records = []
    t_measure = time.time()

    for name, measure in raw_measures.items():
        t0 = time.time()

        # Scope info
        scope, scope_reason = classify_scope(name, measure)
        cr  = clean_results.get(name)
        pr  = parse_results.get(name)
        ann = ann_map.get(name)
        clf = clf_map.get(name)
        gen = gen_map.get(name)

        if cr is None:
            raw_dax = measure.get("dax", "")
            cr = clean(name, raw_dax)

        duration_ms = int((time.time() - t0) * 1000)

        record = _make_record(
            name=name, measure=measure,
            clean_result=cr, parse_result=pr,
            ann=ann, clf=clf, gen=gen,
            scope=scope, scope_reason=scope_reason,
            duration_ms=duration_ms,
        )
        records.append(record)

    # ── Write outputs ─────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)

    final_path  = output_dir / "final_measures.json"
    report_path = output_dir / "run_report.json"
    scope_dir   = output_dir / "scope"

    final_path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    duration_s = time.time() - t_start
    report     = _make_report(records, started_at, duration_s, str(input_path))

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # Also write scope files
    write_scope_outputs(scope_result, scope_dir)

    # ── Print summary ─────────────────────────────────────────
    if verbose:
        t = report["totals"]
        p = report["percentages"]
        print(f"\n{'─'*60}")
        print(f"  RUN COMPLETE  ({duration_s:.1f}s)")
        print(f"{'─'*60}")
        print(f"  Total measures     : {t['total_measures']}")
        print(f"  In scope           : {t['in_scope']}  ({p['in_scope_pct']}%)")
        print(f"  Out of scope       : {t['out_of_scope']}")
        print(f"  Parsed OK          : {t['parsed_ok']}")
        print(f"  Parse failures     : {t['parsed_failed']}")
        if not dry_run:
            print(f"  SQL generated      : {t['sql_generated']}  ({p['sql_generated_pct']}%)")
            print(f"  Compiler handled   : {t['compiler_handled']}  ({p['compiler_pct']}% of in-scope)")
            print(f"  Needs LLM          : {t['needs_llm']}")
        print(f"\n  Output:")
        print(f"    {final_path}")
        print(f"    {report_path}")
        print(f"    {scope_dir}/")

        if report["parse_failures"]:
            print(f"\n  ⚠️  Parse failures ({len(report['parse_failures'])}):")
            for pf in report["parse_failures"][:5]:
                print(f"    {pf['name']}: {pf['error'][:70]}")

        if not dry_run and report["sql_failures"]:
            print(f"\n  ⚠️  SQL failures ({len(report['sql_failures'])}):")
            for sf in report["sql_failures"][:5]:
                print(f"    {sf['name']} [{sf['pattern']}]: {sf['error'][:60]}")

        if report["unresolved_tables"]:
            tables = list({x["table"] for x in report["unresolved_tables"]})
            print(f"\n  ⚠️  Unresolved BI tables: {tables}")

    return report


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Stage 2 — DAX → SQL Pipeline"
    )
    parser.add_argument(
        "--dashboard", type=str, default=None,
        help="Dashboard name (e.g. risk_management, pcp_dashboard). "
             "Creates output/stage2/dashboards/<name>/ folder. "
             "Auto-selects input files for known dashboards."
    )
    parser.add_argument(
        "--input", type=str, default=None,
        help="Path to measures_resolved.json (auto-detected if not given)"
    )
    parser.add_argument(
        "--sf-map", type=str, default=None,
        help="Path to bi_snowflakes_naming_matching.json"
    )
    parser.add_argument(
        "--rels", type=str, default=None,
        help="Path to relationships.json"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output directory (overrides --dashboard default)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and classify only — skip SQL generation"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress progress output"
    )
    args = parser.parse_args()

    # ── Resolve which dashboards to run ──────────────────────
    dashboard = args.dashboard or "all"

    if dashboard == "all":
        dashboards_to_run = list(DASHBOARD_INPUTS.keys())
    else:
        dashboards_to_run = [dashboard]

    for dash in dashboards_to_run:
        print(f"\n{'='*60}")
        print(f"  Running Stage 2 for: {dash}")
        print(f"{'='*60}")

        # ── Resolve output dir ────────────────────────────────────
        if args.output and len(dashboards_to_run) == 1:
            output_dir = Path(args.output)
        else:
            output_dir = DASHBOARDS_DIR / dash / "stage2"

        # ── Resolve input paths ───────────────────────────────────
        try:
            if args.input and len(dashboards_to_run) == 1:
                input_path = Path(args.input)
            else:
                candidates = DASHBOARD_INPUTS.get(dash, INPUT_CANDIDATES)
                input_path = _find_file(candidates, "measures_resolved.json")

            if args.sf_map and len(dashboards_to_run) == 1:
                sf_map_path = Path(args.sf_map)
            else:
                sf_candidates = DASHBOARD_SF_MAPS.get(dash, SF_MAP_CANDIDATES)
                sf_map_path = _find_file(sf_candidates, "bi_snowflakes_naming_matching.json")

            if args.rels and len(dashboards_to_run) == 1:
                rel_path = Path(args.rels)
            else:
                rel_candidates = DASHBOARD_RELS.get(dash, REL_CANDIDATES)
                rel_path = _find_file(rel_candidates, "relationships.json")

        except FileNotFoundError as e:
            print(f"\nERROR: {e}")
            sys.exit(1)

        run_pipeline(
            input_path  = input_path,
            sf_map_path = sf_map_path,
            rel_path    = rel_path,
            output_dir  = output_dir,
            dry_run     = args.dry_run,
            verbose     = not args.quiet,
        )


# ══════════════════════════════════════════════════════════════
# SELF-TEST  —  run: python pipeline.py --test
# ══════════════════════════════════════════════════════════════

def _run_tests():
    """Quick smoke test using in-memory data — no files needed."""
    from ast_nodes_step0 import FunctionCall, ColumnRef

    print("=== pipeline.py smoke test ===\n")
    all_pass = True

    def check(label, condition):
        nonlocal all_pass
        status = "✅" if condition else "❌"
        print(f"  {status}  {label}")
        if not condition:
            all_pass = False

    # Minimal in-memory measures
    test_measures = {
        "#Members": {
            "name": "#Members", "table": "ALL_DAX",
            "dax": "SUM(attribution[member_count])",
            "clean_dax": "SUM(attribution[member_count])",
            "raw_dax": "SUM(attribution[member_count])",
            "is_leaf": True, "depth": 0, "depends_on": [],
            "referenced_columns": ["attribution[member_count]"],
            "all_referenced_columns": ["attribution[member_count]"],
        },
        "Documented risk": {
            "name": "Documented risk", "table": "ALL_DAX",
            "dax": 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))',
            "clean_dax": 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))',
            "raw_dax": 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))',
            "is_leaf": True, "depth": 0, "depends_on": [],
            "referenced_columns": ["risk_core[risk_value]"],
            "all_referenced_columns": ["risk_core[risk_value]"],
        },
        "#Members YoY Card": {
            "name": "#Members YoY Card", "table": "ALL_DAX",
            "dax": 'VAR py = CALCULATE([#Members], SAMEPERIODLASTYEAR(\'date\'[month_of_date]))\nRETURN IF(ISBLANK(py),"",SWITCH(TRUE(), 1>0, UNICHAR(9650) & FORMAT(1,"0%"),""))',
            "clean_dax": 'VAR py = CALCULATE([#Members], SAMEPERIODLASTYEAR(\'date\'[month_of_date]))\nRETURN IF(ISBLANK(py),"",SWITCH(TRUE(), 1>0, UNICHAR(9650) & FORMAT(1,"0%"),""))',
            "raw_dax": 'VAR py = CALCULATE([#Members], SAMEPERIODLASTYEAR(\'date\'[month_of_date]))\nRETURN IF(ISBLANK(py),"",SWITCH(TRUE(), 1>0, UNICHAR(9650) & FORMAT(1,"0%"),""))',
            "is_leaf": False, "depth": 1,
            "depends_on": [{"measure_name": "#Members", "dax": "SUM(attribution[member_count])", "depends_on": [], "is_leaf": True, "depth": 0, "referenced_columns": [], "table": "ALL_DAX"}],
            "referenced_columns": [],
            "all_referenced_columns": [],
        },
        "Info text": {
            "name": "Info text", "table": "ALL_DAX",
            "dax": '"The cohort is built on latest risk execution data."',
            "clean_dax": '"The cohort is built on latest risk execution data."',
            "raw_dax": '"The cohort is built on latest risk execution data."',
            "is_leaf": True, "depth": 0, "depends_on": [],
            "referenced_columns": [], "all_referenced_columns": [],
        },
    }

    SF_MAP = {
        "attribution": {"snowflake_object": "PCP_VISITS_V4_VIEW", "type": "source"},
        "risk_core"  : {"snowflake_object": {"snowflake": "RISK_CORE_V4_VIEW"}, "type": "source"},
        "date"       : {"snowflake_object": "DATE_VIEW", "type": "source"},
        "ALL_DAX"    : {"type": "measure_container", "snowflake_object": None},
    }
    RELS = []

    sf_lookup = build_snowflake_lookup(SF_MAP)
    rel_graph = build_rel_graph(RELS)

    # ── Scope classification ──────────────────────────────────
    print("Scope classification:")
    scope_result = run_scope_classification(test_measures)
    in_names = {e["measure_name"] for e in scope_result["in_scope"]}
    out_names = {e["measure_name"] for e in scope_result["out_of_scope"]}
    check("#Members in scope",             "#Members" in in_names)
    check("Documented risk in scope",      "Documented risk" in in_names)
    check("#Members YoY Card out of scope","#Members YoY Card" in out_names)
    check("Info text out of scope",        "Info text" in out_names)

    # ── Clean ────────────────────────────────────────────────
    print("\nCleaner:")
    cr = clean("#Members", "SUM(attribution[member_count])")
    check("CleanResult ok",                cr.clean_dax == "SUM(attribution[member_count])")

    # ── Parse + dep_resolve ──────────────────────────────────
    print("\nParse + dep resolve:")
    in_scope_measures = {n: m for n, m in test_measures.items() if n in in_names}
    parse_results = {
        n: parse_dax(n, clean(n, m.get("clean_dax", m.get("dax",""))).clean_dax)
        for n, m in in_scope_measures.items()
    }
    parsed_ok = {n: r for n, r in parse_results.items() if isinstance(r, ParseSuccess)}
    check("both in-scope measures parsed", len(parsed_ok) == 2)

    dep_result = dep_resolve(parsed_ok)
    check("topo order has 2 entries",      len(dep_result.order) == 2)
    check("no circular deps",              dep_result.circular == [])

    # ── Semantic + classify + generate ───────────────────────
    print("\nSemantic + classify + generate:")
    ann_map = {}
    clf_map = {}
    gen_map = {}
    sql_cache = {}

    for name in dep_result.order:
        if name not in parsed_ok:
            continue
        ann = resolve_one(name, parsed_ok[name].ast, dep_result, sf_lookup, rel_graph)
        clf = do_classify(ann)
        gen = generate(ann, clf, sql_cache)
        ann_map[name] = ann
        clf_map[name] = clf
        gen_map[name] = gen
        if gen.sql:
            sql_cache[name] = gen.sql

    check("#Members SQL generated",        gen_map["#Members"].sql is not None)
    check("Documented risk SQL generated", gen_map["Documented risk"].sql is not None)
    check("#Members SQL has SUM",          "SUM" in (gen_map["#Members"].sql or ""))
    check("Documented risk SQL has WHERE", "WHERE" in (gen_map["Documented risk"].sql or ""))

    # ── Run report ───────────────────────────────────────────
    print("\nRun report:")
    records = []
    for name, m in test_measures.items():
        scope, reason = classify_scope(name, m)
        cr2  = clean(name, m.get("clean_dax", m.get("dax","")))
        pr2  = parse_results.get(name)
        ann2 = ann_map.get(name)
        clf2 = clf_map.get(name)
        gen2 = gen_map.get(name)
        records.append(_make_record(
            name=name, measure=m, clean_result=cr2,
            parse_result=pr2, ann=ann2, clf=clf2, gen=gen2,
            scope=scope, scope_reason=reason, duration_ms=0,
        ))

    report = _make_report(records, datetime.now(timezone.utc).isoformat(), 0.1, "test")
    check("total=4",                       report["totals"]["total_measures"] == 4)
    check("in_scope=2",                    report["totals"]["in_scope"] == 2)
    check("out_of_scope=2",                report["totals"]["out_of_scope"] == 2)
    check("sql_generated=2",               report["totals"]["sql_generated"] == 2)
    check("parse_failures=0",              report["totals"]["parsed_failed"] == 0)

    print()
    if all_pass:
        print("✅  All pipeline.py tests passed.")
        print("    Run:  python pipeline.py  to process your actual measures.")
    else:
        print("❌  Some tests failed.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_tests()
    else:
        main()