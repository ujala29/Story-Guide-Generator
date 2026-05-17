"""
prompt_generator.py
-------------------
Auto-generates dashboard-specific LLM prompt files from bi_sf_naming_matching.json.

Writes to prompt/<dashboard>/:
  - builder_system.txt     SQL generation rules
  - schema_rules_only.txt  Date filter rules for validator
  - validator_checklist.txt Validation checklist

Called automatically at the end of Stage 1 (Extraction/runner.py).
All content is derived from the SF map — no manual input needed.
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── Data extraction ───────────────────────────────────────────────────────────

# BI table names that are date dimensions — never include in SQL filter rules
_DATE_DIM_BI_NAMES = {"date", "dates", "calendar", "date_dim", "date_dimension"}


def _get_source_tables(sf_map: dict) -> list[dict]:
    """
    Extract unique source tables that have a date_column from the SF map.
    Deduplicates by SF object name (multiple BI tables can point to same SF view).
    Excludes date dimension tables (DATE_VIEW etc.) — they are slicers, not SQL sources.
    """
    seen_sf: set[str] = set()
    tables: list[dict] = []

    for bi_name, val in sf_map.items():
        if not isinstance(val, dict) or bi_name == "static_tables":
            continue
        if val.get("type") != "source":
            continue
        if bi_name.lower() in _DATE_DIM_BI_NAMES:
            continue

        sf_obj = val.get("snowflake_object")
        if isinstance(sf_obj, dict):
            sf_obj = sf_obj.get("snowflake") or sf_obj.get("postgres")

        date_col = val.get("date_column")
        if not sf_obj or not date_col:
            continue
        if sf_obj in seen_sf:
            continue

        seen_sf.add(sf_obj)
        tables.append({
            "bi_table"          : bi_name,
            "sf_object"         : sf_obj,
            "date_column"       : date_col,
            "has_max_month_flag": val.get("has_max_month_flag"),  # True | False | None
        })

    return tables


# ── Helpers ───────────────────────────────────────────────────────────────────

def _where_base(t: dict) -> str:
    """Return the BASE WHERE clause for a table."""
    if t["has_max_month_flag"] is True:
        return f"WHERE MAX_MONTH_FLAG = TRUE AND {t['date_column']} = :selected_month"
    return f"WHERE {t['date_column']} = :selected_month"


def _where_py(t: dict) -> str:
    return f"WHERE {t['date_column']} = DATEADD(year,  -1, :selected_month)"


def _where_pm(t: dict) -> str:
    return f"WHERE {t['date_column']} = DATEADD(month, -1, :selected_month)"


# ── builder_system.txt ────────────────────────────────────────────────────────

def _build_builder_system(source_tables: list[dict]) -> str:
    any_max = any(t["has_max_month_flag"] is True for t in source_tables)
    none_max = not any_max

    L = []
    L.append("You are a SQL expert converting Power BI DAX measures to Snowflake SQL.")
    L.append("You will be given a DAX measure and Snowflake schema context.")
    L.append("")
    L.append("Rules:")
    L.append("  1. Return ONLY the SQL query — no explanation, no markdown, no comments")
    L.append("  2. Use SELECT ... FROM ... format")
    L.append("  3. Use NULLIF for all division: a / NULLIF(b, 0)")

    # Per-table date col rules
    n = 4
    for t in source_tables:
        L.append(f"  {n}. Date column for {t['sf_object']} = {t['date_column']}")
        n += 1

    L.append(f"  {n}. Use :selected_month as date parameter")
    n += 1

    if none_max:
        L.append(f"  !! NONE of the tables have MAX_MONTH_FLAG — never add it !!")

    L.append("")
    L.append("  DATE FILTER — follow exactly:")

    for t in source_tables:
        if t["has_max_month_flag"] is True:
            L.append(f"  BASE measures ({t['sf_object']})"
                     f" : WHERE MAX_MONTH_FLAG = TRUE AND {t['date_column']} = :selected_month")
        else:
            note = " (NO MAX_MONTH_FLAG)" if any_max else ""
            L.append(f"  BASE measures ({t['sf_object']})"
                     f" : WHERE {t['date_column']} = :selected_month{note}")

    L.append("  PY  (prior year)  : same date col but DATEADD(year,  -1, :selected_month)  — NO MAX_MONTH_FLAG")
    L.append("  PM  (prior month) : same date col but DATEADD(month, -1, :selected_month)  — NO MAX_MONTH_FLAG")
    L.append("  YoY current part  : base date filter with :selected_month                   — NO MAX_MONTH_FLAG")
    L.append("  YoY prior part    : base date filter with DATEADD(year,  -1, :selected_month)")
    L.append("  MoM current part  : base date filter with :selected_month                   — NO MAX_MONTH_FLAG")
    L.append("  MoM prior part    : base date filter with DATEADD(month, -1, :selected_month)")
    L.append("")
    L.append(f"  {n}. If measure depends on other measures, use their SQL as subqueries")

    return "\n".join(L)


# ── schema_rules_only.txt ─────────────────────────────────────────────────────

def _build_schema_rules(source_tables: list[dict]) -> str:
    any_max  = any(t["has_max_month_flag"] is True  for t in source_tables)
    none_max = not any_max
    pad = max((len(t["sf_object"]) for t in source_tables), default=20)

    L = []
    L.append("━━━ DATE FILTER RULES — apply exactly as written ━━━")
    L.append("")
    L.append("  RULE A — BASE measures (no time-intel suffix):")
    L.append("")

    for t in source_tables:
        L.append(f"    {t['sf_object']}")
        if t["has_max_month_flag"] is True:
            L.append(f"        WHERE MAX_MONTH_FLAG = TRUE AND {t['date_column']} = :selected_month")
        else:
            note = "  !! NO MAX_MONTH_FLAG column — never add it !!" if any_max else ""
            L.append(f"        WHERE {t['date_column']} = :selected_month{note}")
        L.append("")

    if none_max:
        L.append("    !! NONE of the tables have MAX_MONTH_FLAG — never add it !!")
        L.append("")

    L.append("  RULE B — TIME-INTEL measures (PY, PM, YoY, MoM):")
    L.append("")

    if any_max:
        L.append("    !! NEVER use MAX_MONTH_FLAG in any time-intel measure or subquery !!")
        L.append("    MAX_MONTH_FLAG = TRUE marks ONLY the latest month in the table.")
        L.append("    Pairing it with a prior-period date always returns 0 rows.")
        L.append("")

    L.append("    PY — prior year (SAMEPERIODLASTYEAR):")
    for t in source_tables:
        L.append(f"        {t['sf_object']:<{pad}} : WHERE {t['date_column']} = DATEADD(year,  -1, :selected_month)")
    L.append("")

    L.append("    PM — prior month (PREVIOUSMONTH):")
    for t in source_tables:
        L.append(f"        {t['sf_object']:<{pad}} : WHERE {t['date_column']} = DATEADD(month, -1, :selected_month)")
    L.append("")

    L.append("    YoY ratio = (current - prior) / prior:")
    L.append("        current subquery → base date filter with :selected_month")
    L.append("        prior   subquery → base date filter with DATEADD(year,  -1, :selected_month)")
    L.append("")

    L.append("    MoM ratio = (current - prior) / prior:")
    L.append("        current subquery → base date filter with :selected_month")
    L.append("        prior   subquery → base date filter with DATEADD(month, -1, :selected_month)")
    L.append("")

    if none_max:
        L.append("    !! NO MAX_MONTH_FLAG anywhere in any time-intel subquery !!")
        L.append("")

    L.append("  RULE C — CONTEXT_REMOVER (ALL / ALL('DATE')):")
    L.append("    No date filter whatsoever — omit WHERE clause entirely.")
    L.append("")
    L.append("━━━ SQL CONVENTIONS ━━━")
    L.append("")
    L.append("  - DIVIDE(a, b)    → a / NULLIF(b, 0)")
    L.append("  - DIVIDE(a, b, 0) → COALESCE(a / NULLIF(b, 0), 0)")
    L.append("  - Always use SELECT ... FROM ... (no CTEs unless strictly necessary)")

    # Tables with pre-computed month cols don't need DATE_TRUNC
    no_trunc = [t["sf_object"] for t in source_tables
                if not t["date_column"].upper().startswith("DATE_TRUNC")]
    if no_trunc:
        L.append(f"  - Never use DATE_TRUNC on {', '.join(no_trunc)}"
                 f" — they have pre-computed month columns")

    if none_max:
        L.append("  - Never add MAX_MONTH_FLAG to any table — that column does not exist")

    return "\n".join(L)


# ── validator_checklist.txt ───────────────────────────────────────────────────

def _build_validator_checklist(source_tables: list[dict]) -> str:
    any_max  = any(t["has_max_month_flag"] is True for t in source_tables)
    none_max = not any_max

    table_list = " vs ".join(t["sf_object"] for t in source_tables)
    pad = max((len(t["sf_object"]) for t in source_tables), default=20)

    L = []
    L.append("Does this SQL correctly implement the DAX measure? Check for:")
    L.append(f"1. Correct table ({table_list})")
    L.append("2. Correct date column:")

    for t in source_tables:
        L.append(f"   - {t['sf_object']:<{pad}} → {t['date_column']}")

    L.append("3. Date filter — apply RULE A / B / C from the schema context above:")

    for t in source_tables:
        if t["has_max_month_flag"] is True:
            L.append(f"   - Base on {t['sf_object']:<{pad}}"
                     f" → MAX_MONTH_FLAG = TRUE AND {t['date_column']} = :selected_month")
        else:
            note = " (NO MAX_MONTH_FLAG — column doesn't exist)" if any_max else ""
            L.append(f"   - Base on {t['sf_object']:<{pad}}"
                     f" → {t['date_column']} = :selected_month{note}")

    L.append("   - PY / PM measure               → same date col but DATEADD filter, NO MAX_MONTH_FLAG")
    L.append("   - YoY / MoM current subquery    → base date filter with :selected_month, NO MAX_MONTH_FLAG")
    L.append("   - YoY / MoM prior subquery      → base date filter with DATEADD(...)")
    L.append("   - CONTEXT_REMOVER               → no date filter at all")

    if none_max:
        L.append("   !! NONE of the tables have MAX_MONTH_FLAG — never add it !!")

    L.append("4. Correct aggregation function and column")
    L.append("5. Correct WHERE conditions matching KEEPFILTERS")
    L.append("6. NULLIF for division safety")
    L.append("7. For YoY/MoM: ratio must be (current − prior) / NULLIF(prior, 0)")
    L.append("8. IMPORTANT — NULL handling convention:")
    L.append("  DAX <> operator includes NULLs. In SQL always translate as:")
    L.append("  (col IS NULL OR col <> 'value')")
    L.append("")
    L.append("  NEVER use IS DISTINCT FROM — use the IS NULL OR <> pattern consistently.")
    L.append("")
    L.append("  When fixing a time-intel variant (PM, PY, MoM, YoY), the NULL handling")
    L.append("  must exactly match the approved base measure.")

    return "\n".join(L)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_dashboard_prompts(dashboard: str, sf_map: dict, prompts_root: Path) -> None:
    """
    Generate builder_system.txt, schema_rules_only.txt, validator_checklist.txt
    for a dashboard from its bi_sf_naming_matching.json SF map.

    Args:
        dashboard   : dashboard name, e.g. "risk-dash"
        sf_map      : loaded bi_sf_naming_matching.json dict
        prompts_root: project-level prompt/ folder (files go into prompts_root/dashboard/)
    """
    source_tables = _get_source_tables(sf_map)
    if not source_tables:
        print(f"  [prompt_generator] No source tables with date_column found — skipping prompt generation")
        return

    out_dir = prompts_root / dashboard
    out_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "builder_system.txt"    : _build_builder_system(source_tables),
        "schema_rules_only.txt" : _build_schema_rules(source_tables),
        "validator_checklist.txt": _build_validator_checklist(source_tables),
    }

    for fname, content in files.items():
        path = out_dir / fname
        path.write_text(content, encoding="utf-8")
        print(f"  [prompt_generator] Written → {path.relative_to(prompts_root.parent)}")
