"""
snowflake_verifier.py
─────────────────────
PURPOSE:
    1. final_measures.json se har measure ka sql_query padhta hai
    2. Snowflake pe run karta hai
    3. DAX Studio ground truth se compare karta hai
    4. verification_report.json mein save karta hai

SETUP:
    pip install snowflake-connector-python python-dotenv

    .env file banao stage2/ folder mein:
        SNOWFLAKE_ACCOUNT=xxxx.snowflakecomputing.com
        SNOWFLAKE_USER=your_username
        SNOWFLAKE_PASSWORD=your_password
        SNOWFLAKE_WAREHOUSE=your_warehouse
        SNOWFLAKE_DATABASE=your_database
        SNOWFLAKE_SCHEMA=your_schema
        SNOWFLAKE_ROLE=your_role

USAGE:
    python snowflake_verifier.py
    python snowflake_verifier.py --limit 10        (sirf pehle 10 measures)
    python snowflake_verifier.py --measure "#Members"  (ek measure)
    python snowflake_verifier.py --dry-run         (SQL print karo, run mat)
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import json
import os
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# ── Try to load dotenv ────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass   # dotenv optional — env vars direct bhi set kar sakte ho

# ── Try to import snowflake connector ────────────────────────
try:
    import snowflake.connector
    SNOWFLAKE_AVAILABLE = True
except ImportError:
    SNOWFLAKE_AVAILABLE = False
    print("⚠️  snowflake-connector-python not installed.")
    print("    Run: pip install snowflake-connector-python")


# ══════════════════════════════════════════════════════════════
# PATHS
# ══════════════════════════════════════════════════════════════

BASE_DIR    = Path(__file__).resolve().parent.parent.parent
FINAL_JSON  = BASE_DIR / "output" / "dashboards" / "risk-dash" / "metric_dictionary" / "final_measures.json"
OUTPUT_DIR  = BASE_DIR / "output" / "dashboards" / "risk-dash" / "metric_dictionary"
REPORT_PATH = OUTPUT_DIR / "verification_report.json"


# ══════════════════════════════════════════════════════════════
# DAX STUDIO GROUND TRUTH
# (DAX Studio se nikali gayi unfiltered values — ALL() applied)
# Update these values from your DAX Studio results
# ══════════════════════════════════════════════════════════════

DAX_GROUND_TRUTH = {
    "Members"          : 2_390_624,
    "#Members"         : 2_390_624,
    "Documented risk"  : 0.7647413105392060,
    "Potential risk"   : 0.9652988774408191,
    "PMPM"             : 478.878443395427,
    "Risk recapture rate": 0.492157006902749,
    # Add more as you get them from DAX Studio:
    # "Gap to potential risk" : ?,
    # "RAF recapture rate"    : ?,
    # "Overall gaps closed"   : ?,
    # "#Members PY"           : ?,
}

# Tolerance for float comparison (0.1% difference allowed)
TOLERANCE_PCT = 0.1


# ══════════════════════════════════════════════════════════════
# SNOWFLAKE CONNECTION
# ══════════════════════════════════════════════════════════════

def get_connection():
    """
    Create Snowflake connection from environment variables.
    Set these in .env file or system environment.
    """
    required = [
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_PASSWORD",
        "SNOWFLAKE_DATABASE",
        "SNOWFLAKE_SCHEMA",
        "SNOWFLAKE_WAREHOUSE",
    ]

    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"\n❌ Missing environment variables: {missing}")
        print("\nCreate a .env file with:")
        for k in required:
            print(f"  {k}=your_value")
        sys.exit(1)

    # Account format:
    # - Satoricyber proxy: set SNOWFLAKE_HOST to full proxy URL
    #   SNOWFLAKE_ACCOUNT = scb87951.innova3.us-east-1
    #   SNOWFLAKE_HOST    = scb87951.innova3.us-east-1.a.p1.satoricyber.net
    # - Direct Snowflake: only SNOWFLAKE_ACCOUNT needed
    #   SNOWFLAKE_ACCOUNT = xyz12345.us-east-1

    account = os.getenv("SNOWFLAKE_ACCOUNT", "")
    host    = os.getenv("SNOWFLAKE_HOST", "")

    # If host is full URL, extract account from it
    if not account and host:
        # e.g. scb87951.innova3.us-east-1.a.p1.satoricyber.net
        # -> account = scb87951.innova3.us-east-1
        parts   = host.replace(".snowflakecomputing.com", "").split(".")
        account = ".".join(parts[:3])   # first 3 segments

    conn_params = {
        "account"  : account,
        "user"     : os.getenv("SNOWFLAKE_USER"),
        "password" : os.getenv("SNOWFLAKE_PASSWORD"),
        "database" : os.getenv("SNOWFLAKE_DATABASE"),
        "schema"   : os.getenv("SNOWFLAKE_SCHEMA"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
    }

    # Satoricyber / custom proxy: pass host explicitly
    if host:
        conn_params["host"] = host
        conn_params["port"] = int(os.getenv("SNOWFLAKE_PORT", "443"))

    role = os.getenv("SNOWFLAKE_ROLE")
    if role:
        conn_params["role"] = role

    # Login timeout (seconds) — increase for slow proxies
    conn_params["login_timeout"] = int(os.getenv("SNOWFLAKE_LOGIN_TIMEOUT", "60"))

    host_display = host or account
    print(f"  Connecting to  : {host_display}")
    print(f"  Account        : {account}")
    print(f"  Database       : {conn_params['database']}")
    print(f"  Schema         : {conn_params['schema']}")
    print(f"  Warehouse      : {conn_params['warehouse']}")

    return snowflake.connector.connect(**conn_params)


# ══════════════════════════════════════════════════════════════
# SQL RUNNER
# ══════════════════════════════════════════════════════════════

def run_sql(cursor, sql: str, measure_name: str) -> dict:
    """
    Run one SQL query on Snowflake.

    Returns dict with:
        success     : bool
        value       : float | None
        row_count   : int
        error       : str | None
        duration_ms : int
    """
    t0 = time.time()
    try:
        # Add LIMIT 1 safety — our SQLs return single row already
        safe_sql = sql.strip().rstrip(";")

        # If SQL has subqueries (MEASURE_RATIO pattern), wrap it
        if safe_sql.upper().startswith("SELECT (SELECT"):
            safe_sql = f"SELECT ({safe_sql}) AS result"
        
        cursor.execute(safe_sql)
        rows = cursor.fetchall()
        duration_ms = int((time.time() - t0) * 1000)

        if not rows:
            return {
                "success"    : False,
                "value"      : None,
                "row_count"  : 0,
                "error"      : "No rows returned",
                "duration_ms": duration_ms,
            }

        # First column of first row is the metric value
        raw_value = rows[0][0]
        # Handle different return types:
        # float/int   -> numeric metric (normal case)
        # datetime    -> date measure (Latest attribution date etc.)
        # str         -> string measure (Risk factor etc.)
        if raw_value is None:
            value = None
        elif isinstance(raw_value, (int, float)):
            value = float(raw_value)
        else:
            # date or string — store as string, not comparable as float
            value = str(raw_value)

        return {
            "success"    : True,
            "value"      : value,
            "row_count"  : len(rows),
            "error"      : None,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        duration_ms = int((time.time() - t0) * 1000)
        return {
            "success"    : False,
            "value"      : None,
            "row_count"  : 0,
            "error"      : str(e),
            "duration_ms": duration_ms,
        }


# ══════════════════════════════════════════════════════════════
# COMPARISON
# ══════════════════════════════════════════════════════════════

def compare_with_ground_truth(
    measure_name : str,
    sql_value    : Optional[float],
    ground_truth : dict,
) -> dict:
    """
    Compare SQL result with DAX Studio ground truth.

    Returns:
        has_ground_truth : bool
        expected         : float | None
        match            : bool | None  (None = no ground truth)
        diff_pct         : float | None
        verdict          : "MATCH" | "MISMATCH" | "NO_GROUND_TRUTH" | "SQL_FAILED"
    """
    if sql_value is None:
        return {
            "has_ground_truth": measure_name in ground_truth,
            "expected"        : ground_truth.get(measure_name),
            "match"           : False,
            "diff_pct"        : None,
            "verdict"         : "SQL_FAILED",
        }

    expected = ground_truth.get(measure_name)

    if expected is None:
        return {
            "has_ground_truth": False,
            "expected"        : None,
            "match"           : None,
            "diff_pct"        : None,
            "verdict"         : "NO_GROUND_TRUTH",
        }

    # Non-numeric result (date/string) — can only do string match
    if isinstance(sql_value, str):
        match    = str(sql_value) == str(expected)
        diff_pct = 0.0 if match else 100.0
        return {
            "has_ground_truth": True,
            "expected"        : expected,
            "match"           : match,
            "diff_pct"        : diff_pct,
            "verdict"         : "MATCH" if match else "MISMATCH",
        }

    # Numeric: percentage difference
    if expected == 0:
        diff_pct = 0.0 if sql_value == 0 else 100.0
    else:
        diff_pct = abs(float(sql_value) - float(expected)) / abs(float(expected)) * 100

    match = diff_pct <= TOLERANCE_PCT

    return {
        "has_ground_truth": True,
        "expected"        : expected,
        "match"           : match,
        "diff_pct"        : round(diff_pct, 6),
        "verdict"         : "MATCH" if match else "MISMATCH",
    }


# ══════════════════════════════════════════════════════════════
# MAIN VERIFIER
# ══════════════════════════════════════════════════════════════

def run_verification(
    limit      : int  = None,
    measure_filter: str = None,
    dry_run    : bool = False,
    skip_no_sql: bool = True,
) -> dict:
    """
    Main verification function.

    Args:
        limit         : max measures to run (None = all)
        measure_filter: run only this measure name
        dry_run       : print SQL, don't run
        skip_no_sql   : skip measures with no sql_query

    Returns:
        verification report dict
    """
    print("=" * 60)
    print("  Snowflake SQL Verifier")
    print("=" * 60)

    # Load final_measures.json
    if not FINAL_JSON.exists():
        print(f"\n❌ File not found: {FINAL_JSON}")
        print("   Run pipeline.py first.")
        sys.exit(1)

    all_measures = json.loads(FINAL_JSON.read_text(encoding="utf-8"))
    print(f"\n  Loaded {len(all_measures)} measures from {FINAL_JSON.name}")

    # Filter measures to verify
    to_verify = []
    for m in all_measures:
        name = m["measure_name"]
        sql  = m.get("sql_query")

        if measure_filter and name != measure_filter:
            continue
        if skip_no_sql and not sql:
            continue
        to_verify.append(m)

    if limit:
        to_verify = to_verify[:limit]

    print(f"  Measures to verify: {len(to_verify)}")
    print(f"  Ground truth available for: {len(DAX_GROUND_TRUTH)} measures")
    print(f"  Tolerance: {TOLERANCE_PCT}%\n")

    if dry_run:
        print("  DRY RUN — SQL will be printed, not executed\n")
        for m in to_verify:
            print(f"  {'─'*50}")
            print(f"  Measure : {m['measure_name']}")
            print(f"  Pattern : {m.get('dax_pattern', 'N/A')}")
            print(f"  SQL:\n{m['sql_query']}\n")
        return {}

    # Connect to Snowflake
    if not SNOWFLAKE_AVAILABLE:
        sys.exit(1)

    print("  Connecting to Snowflake...")
    conn   = get_connection()
    cursor = conn.cursor()
    print("  ✅ Connected\n")

    # Run each SQL
    results     = []
    matches     = 0
    mismatches  = 0
    sql_errors  = 0
    no_gt       = 0

    for i, m in enumerate(to_verify, 1):
        name    = m["measure_name"]
        sql     = m["sql_query"]
        pattern = m.get("dax_pattern", "")

        print(f"  [{i:3}/{len(to_verify)}] {name[:45]:<45}", end=" ")

        # Fix 10: strip markdown backticks from LLM-generated SQL
        if "```" in sql:
            lines = sql.split("\n")
            sql = "\n".join(l for l in lines
                            if not l.strip().startswith("```"))

        # Inject :selected_month parameter for time intel measures
        selected_month = os.getenv("SELECTED_MONTH", "2026-02-01")
        sql = sql.replace(":selected_month", f"'{selected_month}'")

        # Run SQL
        run_result = run_sql(cursor, sql, name)

        # Compare
        cmp = compare_with_ground_truth(name, run_result["value"], DAX_GROUND_TRUTH)

        # Status display
        def _fmt(v):
            return f"{v:.6g}" if isinstance(v, (int, float)) else str(v)

        if not run_result["success"]:
            print(f"❌ SQL ERROR  — {run_result['error'][:50]}")
            sql_errors += 1
        elif cmp["verdict"] == "MATCH":
            print(f"✅ MATCH      — {_fmt(run_result['value'])}")
            matches += 1
        elif cmp["verdict"] == "MISMATCH":
            print(f"❌ MISMATCH   — got={_fmt(run_result['value'])}  expected={_fmt(cmp['expected'])}  diff={cmp['diff_pct']:.3f}%")
            mismatches += 1
        else:
            print(f"⚪ NO GT      — {_fmt(run_result['value'])}  (add to DAX_GROUND_TRUTH)")
            no_gt += 1

        results.append({
            "measure_name"    : name,
            "dax_pattern"     : pattern,
            "sql_query"       : sql,
            "sql_success"     : run_result["success"],
            "sql_value"       : run_result["value"],
            "sql_error"       : run_result["error"],
            "duration_ms"     : run_result["duration_ms"],
            "has_ground_truth": cmp["has_ground_truth"],
            "expected_value"  : cmp["expected"],
            "match"           : cmp["match"],
            "diff_pct"        : cmp["diff_pct"],
            "verdict"         : cmp["verdict"],
        })

    cursor.close()
    conn.close()

    # Build report
    total_with_gt = matches + mismatches
    report = {
        "run_at"      : datetime.now(timezone.utc).isoformat(),
        "input_file"  : str(FINAL_JSON),
        "tolerance_pct": TOLERANCE_PCT,

        "totals": {
            "verified"       : len(results),
            "sql_errors"     : sql_errors,
            "matches"        : matches,
            "mismatches"     : mismatches,
            "no_ground_truth": no_gt,
            "match_rate_pct" : round(matches / total_with_gt * 100, 1) if total_with_gt else 0,
        },

        "matches"   : [r for r in results if r["verdict"] == "MATCH"],
        "mismatches": [r for r in results if r["verdict"] == "MISMATCH"],
        "sql_errors": [r for r in results if not r["sql_success"]],
        "no_ground_truth": [r for r in results if r["verdict"] == "NO_GROUND_TRUTH"],
        "all_results": results,
    }

    # Save report
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # Print summary
    print(f"\n{'─'*60}")
    print(f"  VERIFICATION SUMMARY")
    print(f"{'─'*60}")
    print(f"  Total verified    : {len(results)}")
    print(f"  SQL errors        : {sql_errors}")
    print(f"  ✅ Match          : {matches}")
    print(f"  ❌ Mismatch       : {mismatches}")
    print(f"  ⚪ No ground truth: {no_gt}")
    if total_with_gt:
        print(f"  Match rate        : {report['totals']['match_rate_pct']}%")

    if mismatches:
        print(f"\n  MISMATCHES:")
        for r in report["mismatches"]:
            print(f"    {r['measure_name']}")
            print(f"      SQL    : {r['sql_value']}")
            print(f"      DAX    : {r['expected_value']}")
            print(f"      Diff   : {r['diff_pct']}%")
            print(f"      Pattern: {r['dax_pattern']}")

    if sql_errors:
        print(f"\n  SQL ERRORS:")
        for r in report["sql_errors"]:
            print(f"    {r['measure_name']}: {r['sql_error'][:80]}")

    print(f"\n  Report saved: {REPORT_PATH}")
    return report


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify generated SQL against Snowflake"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max measures to verify (default: all)"
    )
    parser.add_argument(
        "--measure", type=str, default=None,
        help="Verify only this specific measure name"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print SQL only, don't run on Snowflake"
    )
    parser.add_argument(
        "--include-no-sql", action="store_true",
        help="Include measures with no SQL (shows as skipped)"
    )
    parser.add_argument(
        "--tolerance", type=float, default=TOLERANCE_PCT,
        help=f"Match tolerance in percent (default: {TOLERANCE_PCT})"
    )
    args = parser.parse_args()

    if args.tolerance != TOLERANCE_PCT:
        TOLERANCE_PCT = args.tolerance

    run_verification(
        limit          = args.limit,
        measure_filter = args.measure,
        dry_run        = args.dry_run,
        skip_no_sql    = not args.include_no_sql,
    )