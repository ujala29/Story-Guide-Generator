"""
llm_fallback.py
───────────────
Stage 2 — Step 7

PURPOSE:
    Four roles using TrueFoundry LLM API (OpenAI-compatible):

    1. VALIDATOR  — Review compiler-generated SQL for logic errors
    2. FIXER      — Fix SQL that VALIDATOR flagged
    3. BUILDER    — Generate SQL for COMPLEX measures compiler couldn't handle
    4. DEFINER    — Generate plain English definitions for out-of-scope measures

    + REGISTRY    — Cache all results in registry.json for future reuse
                    (no API call if answer already in registry)

SETUP:
    pip install openai python-dotenv

    .env file:
        TF_BASE_URL=https://your-truefoundry-endpoint.com
        TF_API_KEY=your-api-key
        TF_MODEL=your-model-name

USAGE:
    python llm_fallback.py                    # full run
    python llm_fallback.py --validate-only    # only validate compiler SQL
    python llm_fallback.py --build-only       # only build COMPLEX measures
    python llm_fallback.py --define-only      # only write definitions
    python llm_fallback.py --measure "#Members YoY Card"  # one measure
    python llm_fallback.py --dry-run          # print prompts, no API calls

REGISTRY:
    output/stage2/registry.json
    - Stores all LLM outputs keyed by measure name
    - On re-run: registry hit → skip API call → use cached result
    - Tracks: sql, definition, validation verdict, fix history, timestamps
"""

from __future__ import annotations
import json
import os
import sys
import time
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

WORKERS = 5
SKIP_OUT_OF_SCOPE = False  # Set to True to skip DEFINER role and save API calls on out-of-scope measures
try:
    from dotenv import load_dotenv
    # Walk up from this file's directory to find .env at project root
    _env_path = Path(__file__).resolve().parent
    for _ in range(4):
        candidate = _env_path / ".env"
        if candidate.exists():
            load_dotenv(candidate)
            break
        _env_path = _env_path.parent
    else:
        load_dotenv()  # fallback: let python-dotenv search
except ImportError:
    pass

# Fix Windows console Unicode issues with emoji characters
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):
    try:
        _sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️  openai not installed. Run: pip install openai")


import re

def strip_markdown_fences(sql: str) -> str:
    """Remove markdown code fences from LLM-generated SQL before storage."""
    if not sql:
        return sql
    sql = re.sub(
        r'^```(?:sql)?\s*\n?(.*?)\n?```\s*$',
        r'\1',
        sql.strip(),
        flags=re.DOTALL | re.IGNORECASE,
    )
    sql = re.sub(r'^`(.*)`$', r'\1', sql.strip(), flags=re.DOTALL)
    return sql.strip()


def clean_llm_sql(sql: str) -> str:
    """Strip markdown fences and angle-bracket placeholders from LLM SQL."""
    sql = strip_markdown_fences(sql)
    sql, _ = resolve_placeholders(sql)
    return sql


def resolve_placeholders(sql: str) -> tuple[str, list[str]]:
    """
    Strip angle-bracket placeholders left by LLM (e.g. <PAC_TABLE> → PAC_TABLE).

    Only strips tokens that look like valid SQL identifiers (word chars + dots).
    Returns (cleaned_sql, list_of_tokens_that_could_not_be_stripped).
    """
    if not sql:
        return sql, []

    unresolved = []
    def _replace(m):
        token = m.group(1).strip()
        if re.fullmatch(r'[\w.]+', token):
            return token
        unresolved.append(m.group(0))
        return m.group(0)

    cleaned = re.sub(r'<([^>]+)>', _replace, sql)
    return cleaned, unresolved


def trim_schema_to_tables(schema: str, sql: str, dax: str = "") -> str:
    """
    Return only the table blocks from schema_context that are actually
    referenced in the SQL or DAX, plus the DATE FILTER RULES and
    SQL CONVENTIONS sections (always needed).

    Reduces prompt size by ~600 tokens for single-table measures.
    """
    # Known table names to scan for
    TABLE_NAMES = [
        "PAC_TABLE", "INPATIENT_PAC_V4_VIEW", "PCP_VISITS_VIEW",
        "PCP_VISITS_V4_VIEW", "PCP", "PAYER", "DATE_VIEW",
        "USER_PERMISSION_FILTERED",
        # risk-dash tables
        "RISK_CORE_V4_VIEW", "RISK_GROUP_V4_VIEW", "RISK_COHORT_V4_VIEW",
        "PCP_VISITS_V4_VIEW",
    ]
    combined = (sql + " " + dax).upper()
    referenced = {t for t in TABLE_NAMES if t in combined}

    if not referenced:
        return schema  # can't determine — send full schema

    lines = schema.splitlines()
    result = []
    in_table_block = False
    current_table_included = False
    in_rules_section = False

    for line in lines:
        # Once we hit DATE FILTER RULES or SQL CONVENTIONS, include everything
        if "DATE FILTER RULES" in line or "SQL CONVENTIONS" in line:
            in_rules_section = True

        if in_rules_section:
            result.append(line)
            continue

        # Detect start of a table block (line that names a known table)
        stripped = line.strip()
        matched_table = next((t for t in TABLE_NAMES if stripped.startswith(t)), None)
        if matched_table:
            in_table_block = True
            current_table_included = matched_table in referenced

        if in_table_block:
            if current_table_included:
                result.append(line)
        else:
            result.append(line)

    return "\n".join(result).strip()


# ══════════════════════════════════════════════════════════════
# PATHS
# ══════════════════════════════════════════════════════════════

BASE_DIR     = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR  = BASE_DIR / "prompts"

# Per-dashboard path configs
DASHBOARD_LLM_CONFIGS = {
    "risk-dash": {
        "final_json"   : BASE_DIR / "output" / "dashboards" / "risk-dash" / "stage2" / "final_measures.json",
        "output_dir"   : BASE_DIR / "output" / "dashboards" / "risk-dash" / "stage2",
    },
    "pac-dash": {
        "final_json"   : BASE_DIR / "output" / "dashboards" / "pac-dash" / "stage2" / "final_measures.json",
        "output_dir"   : BASE_DIR / "output" / "dashboards" / "pac-dash" / "stage2",
    },
}

# Defaults (risk-dash for backward compat)
FINAL_JSON    = DASHBOARD_LLM_CONFIGS["risk-dash"]["final_json"]
OUTPUT_DIR    = DASHBOARD_LLM_CONFIGS["risk-dash"]["output_dir"]
REGISTRY_PATH = OUTPUT_DIR / "registry.json"
UPDATED_FINAL = OUTPUT_DIR / "final_measures_with_llm.json"


# ══════════════════════════════════════════════════════════════
# LLM CLIENT
# ══════════════════════════════════════════════════════════════

def get_client() -> OpenAI:
    """Create TrueFoundry OpenAI-compatible client from env vars."""
    base_url = os.getenv("TF_BASE_URL")
    api_key  = os.getenv("TF_API_KEY")
    model    = os.getenv("TF_MODEL")

    missing = []
    if not base_url: missing.append("TF_BASE_URL")
    if not api_key:  missing.append("TF_API_KEY")
    if not model:    missing.append("TF_MODEL")

    if missing:
        print(f"\n[ERROR] Missing env vars: {missing}")
        print("Add to .env file:")
        for k in missing:
            print(f"  {k}=your_value")
        sys.exit(1)

    return OpenAI(base_url=base_url, api_key=api_key)


def call_llm(
    client   : OpenAI,
    system   : str,
    user     : str,
    model    : str = None,
    max_tokens: int = 4500,
    dry_run  : bool = False,
) -> str:
    """
    Call TrueFoundry LLM API.
    Returns response text, or prompt preview if dry_run=True.
    """
    if dry_run:
        print(f"\n  [DRY RUN] System: {system[:100]}...")
        print(f"  [DRY RUN] User: {user[:200]}...")
        return "[DRY RUN — no API call made]"

    model = model or os.getenv("TF_MODEL")

    try:
        response = client.chat.completions.create(
            model                = model,
            max_completion_tokens = max_tokens,
            messages             = [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature = 0.1,   # low temp for deterministic SQL
        )
        content       = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason
        if not content:
            return f"ERROR: empty response (finish_reason={finish_reason})"
        return content.strip()
    except Exception as e:
        return f"ERROR: {e}"


# ══════════════════════════════════════════════════════════════
# REGISTRY
# ══════════════════════════════════════════════════════════════

def load_registry() -> dict:
    """Load registry.json or return empty registry."""
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {
        "version"   : "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "measures"  : {},
        "patterns"  : {},
        "fixes"     : {},
        "stats"     : {
            "total_api_calls" : 0,
            "registry_hits"   : 0,
            "validations"     : 0,
            "fixes"           : 0,
            "builds"          : 0,
            "definitions"     : 0,
        }
    }


def save_registry(registry: dict) -> None:
    """Save registry to disk."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    registry["updated_at"] = datetime.now(timezone.utc).isoformat()
    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def registry_get(registry: dict, measure_name: str) -> Optional[dict]:
    """Get measure entry from registry. Returns None if not found."""
    return registry["measures"].get(measure_name)


def registry_set(
    registry     : dict,
    measure_name : str,
    role         : str,
    sql          : Optional[str]   = None,
    definition   : Optional[str]   = None,
    validation   : Optional[str]   = None,   # "approved" | "needs_fix" | "error"
    fix_applied  : Optional[str]   = None,
    original_sql : Optional[str]   = None,
    notes        : Optional[str]   = None,
) -> None:
    """Upsert a measure entry in the registry."""
    existing = registry["measures"].get(measure_name, {})
    now      = datetime.now(timezone.utc).isoformat()

    entry = {
        **existing,
        "measure_name" : measure_name,
        "role"         : role,
        "updated_at"   : now,
    }

    if sql        is not None: entry["sql"]         = sql
    if definition is not None: entry["definition"]  = definition
    if validation is not None: entry["validation"]  = validation
    if fix_applied is not None:
        entry["fix_applied"]  = fix_applied
        entry["original_sql"] = original_sql
    if notes      is not None: entry["notes"]       = notes

    if "created_at" not in entry:
        entry["created_at"] = now

    registry["measures"][measure_name] = entry


# ══════════════════════════════════════════════════════════════
# PROMPT LOADER
# ══════════════════════════════════════════════════════════════

def load_prompts(dashboard: str) -> dict:
    """
    Load prompt files for a dashboard from prompts/<dashboard>/.
    Falls back to inline constants when files are absent.

    Returns dict with keys:
        schema_context, validator_system, validator_checklist,
        builder_system, definer_system, schema_rules_only
    """
    d = PROMPTS_DIR / dashboard

    # Inline fallbacks — used when prompts/<dashboard>/ files don't exist yet.
    # DASHBOARD_SCHEMA_CONTEXT / VALIDATOR_SYSTEM / BUILDER_SYSTEM / DEFINER_SYSTEM
    # are defined later in this file; resolved at call time, not definition time.
    _fallbacks = {
        "schema_context"     : lambda: DASHBOARD_SCHEMA_CONTEXT.get(dashboard, SCHEMA_CONTEXT_RISK),
        "validator_system"   : lambda: VALIDATOR_SYSTEM,
        "validator_checklist": lambda: (
            "Does this SQL correctly implement the DAX measure? "
            "Check table, date column, date filter, aggregation, WHERE, NULLIF."
        ),
        "builder_system"     : lambda: BUILDER_SYSTEM,
        "definer_system"     : lambda: DEFINER_SYSTEM,
    }

    prompts = {}
    for key, fallback_fn in _fallbacks.items():
        path = d / f"{key}.txt"
        if path.exists():
            prompts[key] = path.read_text(encoding="utf-8").strip()
        else:
            prompts[key] = fallback_fn()

    # Validator only needs date rules + SQL conventions — not full table descriptions.
    # Use schema_rules_only.txt if it exists, otherwise fall back to full schema_context.
    rules_only_path = d / "schema_rules_only.txt"
    prompts["schema_rules_only"] = (
        rules_only_path.read_text(encoding="utf-8").strip()
        if rules_only_path.exists()
        else prompts["schema_context"]
    )

    return prompts


# ══════════════════════════════════════════════════════════════
# SNOWFLAKE SCHEMA CONTEXT  (kept as fallback — loaded from files at runtime)
# ══════════════════════════════════════════════════════════════

SCHEMA_CONTEXT_RISK = """
Snowflake tables available:
  PCP_VISITS_V4_VIEW    — Attribution data. Key cols: MEMBER_COUNT, YTD_VISIT_AMOUNT,
                          YTD_MEMBER_COUNT, MEMBER_WITH_OPEN_CODING_GAP_COUNT,
                          MONTH_OF_DATE (date filter col), ORG_HIERARCHY_MASTER_ID
                          NO max_month_flag column.

  RISK_CORE_V4_VIEW     — Risk core data. Key cols: RISK_VALUE, PATIENT_COUNT,
                          RISK_DOCUMENTATION_FLAG ('Documented','Undocumented','Suspected'),
                          RECAPTURE_NUMERATOR, RECAPTURE_DENOMINATOR,
                          SUSPECT_NUMERATOR, SUSPECT_DENOMINATOR,
                          MONTH_OF_MEASUREMENT (date filter col),
                          MAX_MONTH_FLAG (TRUE only on the latest month's rows in the table)

  RISK_GROUP_V4_VIEW    — Risk group data. Same cols as RISK_CORE_V4_VIEW.

  RISK_COHORT_V4_VIEW   — Cohort data. Key cols: EMPI, RECAPTURE_NUMERATOR,
                          RECAPTURE_DENOMINATOR, OPEN_GAP_FLAG,
                          MONTH_OF_MEASUREMENT, MAX_MONTH_FLAG, RISK_DOCUMENTATION_FLAG

  DATE_VIEW             — Date dimension. Key cols: MONTH_OF_DATE

━━━ DATE FILTER RULES — apply exactly as written ━━━

  RULE A — BASE measures (no time-intel suffix, e.g. "Documented risk", "#Members"):
    Attribution (PCP_VISITS_V4_VIEW)              : WHERE MONTH_OF_DATE = :selected_month
    Risk tables WITH max_month_flag               : WHERE MAX_MONTH_FLAG = TRUE AND MONTH_OF_MEASUREMENT = :selected_month
      → applies to: RISK_CORE_V4_VIEW, RISK_GROUP_V4_VIEW
    RISK_COHORT_V4_VIEW (NO max_month_flag col)   : WHERE MONTH_OF_MEASUREMENT = :selected_month only
      !! RISK_COHORT_V4_VIEW does NOT have a MAX_MONTH_FLAG column — never add it !!

  RULE B — TIME-INTEL measures: PY, PM, YoY, MoM
    !! NEVER use MAX_MONTH_FLAG in any time-intel measure or subquery !!
    MAX_MONTH_FLAG = TRUE marks ONLY the latest month in the table.
    Pairing it with a prior-period date always returns 0 rows.

    PY  (prior year,  SAMEPERIODLASTYEAR) : WHERE MONTH_OF_MEASUREMENT = DATEADD(year,  -1, :selected_month)
    PM  (prior month, PREVIOUSMONTH)      : WHERE MONTH_OF_MEASUREMENT = DATEADD(month, -1, :selected_month)
    YoY ratio = (current − prior_year) / prior_year:
        current subquery  → WHERE MONTH_OF_MEASUREMENT = :selected_month          ← NO MAX_MONTH_FLAG
        prior   subquery  → WHERE MONTH_OF_MEASUREMENT = DATEADD(year,  -1, :selected_month)
    MoM ratio = (current − prior_month) / prior_month:
        current subquery  → WHERE MONTH_OF_MEASUREMENT = :selected_month          ← NO MAX_MONTH_FLAG
        prior   subquery  → WHERE MONTH_OF_MEASUREMENT = DATEADD(month, -1, :selected_month)

  RULE C — CONTEXT_REMOVER (ALL / ALL('DATE')):
    No date filter whatsoever — ALL() removes date context by design.

━━━ OTHER CONVENTIONS ━━━
  - DIVIDE(a,b)   → a / NULLIF(b, 0)
  - DIVIDE(a,b,0) → COALESCE(a / NULLIF(b, 0), 0)
  - Always use SELECT ... FROM ... (no CTEs unless necessary)
"""

SCHEMA_CONTEXT_PAC = """
Snowflake tables available:
  PAC_TABLE             — PAC visit data. Key cols: PAC_VISIT_START_DATE, PAC_VISIT_END_DATE,
                          IP_VISIT_START_DATE, PAC_HOSPITAL_NAME, and various PAC metrics.
                          Date filter col: DATE_TRUNC('month', PAC_VISIT_START_DATE)
                          NO max_month_flag column.

  INPATIENT_PAC_V4_VIEW — Inpatient PAC opportunity data (deduplicated on join_key).
                          Key cols: MONTH_OF_VISIT (date filter col), join_key, and PAC opportunity metrics.
                          NO max_month_flag column.

  PCP_VISITS_VIEW       — Attribution/PCP visit data.
                          Key cols: MONTH_OF_ATTRIBUTION (date filter col), member and visit counts.
                          NO max_month_flag column.

  PCP                   — Provider/PCP dimension table. Key cols: provider attributes.

  PAYER                 — Payer dimension table. Key cols: payer attributes.

  DATE_VIEW             — Date dimension. Key cols: MONTH_OF_DATE, MONTH_OF_YEAR, YEAR.

  USER_PERMISSION_FILTERED — User access control. Key cols: PRVID, USER_EMAIL.

━━━ DATE FILTER RULES — apply exactly as written ━━━

  RULE A — BASE measures (no time-intel suffix):
    PAC_TABLE            : WHERE DATE_TRUNC('month', PAC_VISIT_START_DATE) = :selected_month
    INPATIENT_PAC_V4_VIEW: WHERE MONTH_OF_VISIT = :selected_month
    PCP_VISITS_VIEW      : WHERE MONTH_OF_ATTRIBUTION = :selected_month
    !! NONE of the PAC tables have MAX_MONTH_FLAG — never add it !!

  RULE B — TIME-INTEL measures: PY, PM, YoY, MoM
    PY  (prior year,  SAMEPERIODLASTYEAR):
        PAC_TABLE            : WHERE DATE_TRUNC('month', PAC_VISIT_START_DATE) = DATEADD(year,  -1, :selected_month)
        INPATIENT_PAC_V4_VIEW: WHERE MONTH_OF_VISIT = DATEADD(year,  -1, :selected_month)
        PCP_VISITS_VIEW      : WHERE MONTH_OF_ATTRIBUTION = DATEADD(year,  -1, :selected_month)
    PM  (prior month, PREVIOUSMONTH): same as PY but DATEADD(month, -1, ...)
    YoY/MoM ratio = (current − prior) / prior — use two subqueries, no MAX_MONTH_FLAG anywhere.

  RULE C — CONTEXT_REMOVER (ALL / ALL('DATE')):
    No date filter whatsoever.

━━━ OTHER CONVENTIONS ━━━
  - DIVIDE(a,b)   → a / NULLIF(b, 0)
  - DIVIDE(a,b,0) → COALESCE(a / NULLIF(b, 0), 0)
  - Always use SELECT ... FROM ... (no CTEs unless necessary)
"""

DASHBOARD_SCHEMA_CONTEXT = {
    "risk-dash": SCHEMA_CONTEXT_RISK,
    "pac-dash" : SCHEMA_CONTEXT_PAC,
}

# Default for backward compat
SCHEMA_CONTEXT = SCHEMA_CONTEXT_RISK


# ══════════════════════════════════════════════════════════════
# ROLE 1: VALIDATOR
# ══════════════════════════════════════════════════════════════

VALIDATOR_SYSTEM = """You are a SQL expert reviewing auto-generated Snowflake SQL for correctness.
You will be given:
  - A DAX measure and its meaning
  - Auto-generated SQL
  - Snowflake schema context

Your job: Verify the SQL correctly implements the DAX measure semantics.

Respond in this exact JSON format (no markdown, no explanation outside JSON):
{
  "verdict": "approved" | "needs_fix",
  "confidence": "high" | "medium" | "low",
  "issues": ["issue 1", "issue 2"],
  "corrected_sql": "SELECT ... (only if needs_fix, else null)",
  "explanation": "brief explanation"
}"""


def validate_sql(
    client            : OpenAI,
    measure_name      : str,
    dax               : str,
    sql               : str,
    pattern           : str,
    dep_sqls          : dict,
    dry_run           : bool = False,
    schema_context    : str  = None,
    validator_system  : str  = None,
    validator_checklist: str = None,
) -> dict:
    """
    Validate compiler-generated SQL against DAX semantics.

    Returns dict with: verdict, confidence, issues, corrected_sql, explanation
    """
    _schema    = schema_context     or SCHEMA_CONTEXT
    _system    = validator_system   or VALIDATOR_SYSTEM
    _checklist = validator_checklist or (
        "Does this SQL correctly implement the DAX measure? "
        "Check table, date column, date filter, aggregation, WHERE, NULLIF."
    )

    deps_text = ""
    if dep_sqls:
        deps_text = "\nDependent measures SQL (already verified):\n"
        for dep_name, dep_sql in dep_sqls.items():
            deps_text += f"  [{dep_name}]:\n    {dep_sql}\n"

    _schema = trim_schema_to_tables(_schema, sql, dax)

    user = f"""Measure: {measure_name}
DAX pattern: {pattern}
DAX expression:
{dax}
{deps_text}
Generated SQL:
{sql}

Schema context:
{_schema}

{_checklist}"""

    response = call_llm(
        client, _system, user,
        max_tokens=4500, dry_run=dry_run  # 600 was too small: model uses thinking tokens first
    )

    if dry_run:
        return {"verdict": "dry_run", "issues": [], "corrected_sql": None}

    if not response or not response.strip() or response.startswith("ERROR:"):
        return {
            "verdict"      : "error",
            "confidence"   : "low",
            "issues"       : [f"LLM returned no usable content: {(response or '')[:200]}"],
            "corrected_sql": None,
            "explanation"  : response or "Empty response — model may have refused or timed out",
        }

    try:
        clean = response.strip()
        # Extract JSON from markdown fence if present (handles trailing newlines too)
        import re as _re
        fence_match = _re.search(r"```(?:json)?\s*\n([\s\S]*?)(?:\n```|$)", clean)
        if fence_match:
            clean = fence_match.group(1).strip()
        return json.loads(clean)
    except Exception as exc:
        return {
            "verdict"      : "error",
            "confidence"   : "low",
            "issues"       : [f"Could not parse LLM response: {response[:300]}"],
            "corrected_sql": None,
            "explanation"  : f"JSON parse error: {exc}",
        }


# ══════════════════════════════════════════════════════════════
# ROLE 2/3: BUILDER
# ══════════════════════════════════════════════════════════════

BUILDER_SYSTEM = """You are a SQL expert converting Power BI DAX measures to Snowflake SQL.
You will be given a DAX measure and Snowflake schema context.

Rules:
  1. Return ONLY the SQL query — no explanation, no markdown, no comments
  2. Use SELECT ... FROM ... format
  3. Use NULLIF for all division: a / NULLIF(b, 0)
  4. Date column for PCP_VISITS_V4_VIEW = MONTH_OF_DATE
  5. Date column for RISK_* tables = MONTH_OF_MEASUREMENT
  6. Use :selected_month as date parameter

  DATE FILTER — follow exactly:
  BASE measures (risk tables) : WHERE MAX_MONTH_FLAG = TRUE AND MONTH_OF_MEASUREMENT = :selected_month
  BASE measures (attribution) : WHERE MONTH_OF_DATE = :selected_month
  PY  (prior year)  : WHERE MONTH_OF_MEASUREMENT = DATEADD(year,  -1, :selected_month)  — NO MAX_MONTH_FLAG
  PM  (prior month) : WHERE MONTH_OF_MEASUREMENT = DATEADD(month, -1, :selected_month)  — NO MAX_MONTH_FLAG
  YoY current part  : WHERE MONTH_OF_MEASUREMENT = :selected_month                       — NO MAX_MONTH_FLAG
  YoY prior part    : WHERE MONTH_OF_MEASUREMENT = DATEADD(year,  -1, :selected_month)
  MoM current part  : WHERE MONTH_OF_MEASUREMENT = :selected_month                       — NO MAX_MONTH_FLAG
  MoM prior part    : WHERE MONTH_OF_MEASUREMENT = DATEADD(month, -1, :selected_month)

  7. If measure depends on other measures, use their SQL as subqueries"""


def build_sql(
    client         : OpenAI,
    measure_name   : str,
    dax            : str,
    pattern        : str,
    dep_sqls       : dict,
    dry_run        : bool = False,
    schema_context : str  = None,
    builder_system : str  = None,
) -> str:
    """Generate SQL for a COMPLEX measure that compiler couldn't handle."""
    _schema  = schema_context or SCHEMA_CONTEXT
    _system  = builder_system or BUILDER_SYSTEM

    deps_text = ""
    if dep_sqls:
        deps_text = "\nDependent measures (use as subqueries if needed):\n"
        for dep_name, dep_sql in dep_sqls.items():
            deps_text += f"  [{dep_name}]:\n    {dep_sql}\n"

    _schema = trim_schema_to_tables(_schema, dax)

    user = f"""Convert this DAX measure to Snowflake SQL:

Measure name: {measure_name}
DAX pattern: {pattern}
DAX:
{dax}
{deps_text}
Schema:
{_schema}

Return ONLY the SQL query, nothing else."""

    return call_llm(
        client, _system, user,
        max_tokens=4500, dry_run=dry_run
    )


# ══════════════════════════════════════════════════════════════
# ROLE 4: DEFINER
# ══════════════════════════════════════════════════════════════

DEFINER_SYSTEM = """You are a healthcare analytics documentation expert.
Write clear, concise metric definitions for a metric dictionary.
Audience: business users (not technical).

Rules:
  1. 2-3 sentences maximum
  2. Plain English — no SQL, no DAX, no code
  3. Explain WHAT the metric measures and WHY it matters
  4. For display/color/format measures: explain their UI purpose
  5. Return ONLY the definition text — no labels, no markdown"""


def _ascii_safe(text: str) -> str:
    """Replace non-ASCII characters so Bedrock endpoints don't reject the request."""
    return text.encode("ascii", errors="replace").decode("ascii")


def build_definition(
    client         : OpenAI,
    measure_name   : str,
    dax            : str,
    scope_reason   : str,
    dry_run        : bool = False,
    definer_system : str  = None,
) -> str:
    """Generate plain English definition for an out-of-scope measure."""
    _system = definer_system or DEFINER_SYSTEM

    # Sanitize: Bedrock via TrueFoundry rejects non-ASCII in prompt body
    safe_reason = _ascii_safe(scope_reason)
    safe_dax    = _ascii_safe(dax[:300]) if dax else "N/A"

    user = f"""Write a metric dictionary definition for:

Metric name: {measure_name}
Type: {safe_reason}
DAX (for context, do not mention in definition):
{safe_dax}

Write a 2-3 sentence plain English definition explaining what this metric represents."""

    return call_llm(
        client, _system, user,
        max_tokens=4500, dry_run=dry_run
    )


# ══════════════════════════════════════════════════════════════
# DEPENDENCY SQL LOOKUP
# ══════════════════════════════════════════════════════════════

def get_dep_sqls(measure: dict, all_measures: dict) -> dict:
    """
    Get SQL for all dependencies of a measure.
    Looks in final_measures.json sql_query field.
    """
    deps = {}
    for dep in measure.get("depends_on", []):
        dep_name = dep.get("measure_name") if isinstance(dep, dict) else dep
        if dep_name and dep_name in all_measures:
            dep_sql = all_measures[dep_name].get("sql_query")
            if dep_sql:
                deps[dep_name] = dep_sql
    return deps


# ══════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════

def run_llm_fallback(
    validate_only : bool = False,
    build_only    : bool = False,
    define_only   : bool = False,
    measure_filter: str  = None,
    dry_run       : bool = False,
    skip_registry : bool = False,
    dashboard     : str  = "risk-dash",
) -> dict:
    """
    Main entry point. Runs all 4 LLM roles.

    Args:
        validate_only  : only run VALIDATOR on compiler SQL
        build_only     : only run BUILDER on COMPLEX measures
        define_only    : only run DEFINER on out-of-scope measures
        measure_filter : process only this measure
        dry_run        : print prompts, no API calls
        skip_registry  : ignore registry cache (force re-run)
        dashboard      : which dashboard to run (risk-dash | pac-dash)
    """
    # Resolve paths and schema context for this dashboard
    dash_cfg       = DASHBOARD_LLM_CONFIGS.get(dashboard, DASHBOARD_LLM_CONFIGS["risk-dash"])
    final_json     = dash_cfg["final_json"]
    output_dir     = dash_cfg["output_dir"]
    registry_path  = output_dir / "registry.json"
    updated_final  = output_dir / "final_measures_with_llm.json"
    schema_context = DASHBOARD_SCHEMA_CONTEXT.get(dashboard, SCHEMA_CONTEXT_RISK)

    print("=" * 60)
    print(f"  LLM Fallback — {dashboard} — Validator + Builder + Definer")
    print("=" * 60)

    # Load inputs
    if not final_json.exists():
        print(f"\n❌ {final_json} not found. Run pipeline.py first.")
        sys.exit(1)

    all_measures_list = json.loads(final_json.read_text(encoding="utf-8"))
    all_measures = {m["measure_name"]: m for m in all_measures_list}
    print(f"\n  Loaded {len(all_measures)} measures")

    # Load prompts from files
    prompts = load_prompts(dashboard)
    schema_context      = prompts["schema_context"]       # full schema — BUILDER only
    schema_rules_only   = prompts["schema_rules_only"]    # rules only  — VALIDATOR
    validator_system    = prompts["validator_system"]
    validator_checklist = prompts["validator_checklist"]
    builder_system      = prompts["builder_system"]
    definer_system      = prompts["definer_system"]
    print(f"  Prompts loaded from: prompts/{dashboard}/")

    def _load_reg():
        if registry_path.exists():
            return json.loads(registry_path.read_text(encoding="utf-8"))
        return {
            "version": "1.0", "created_at": datetime.now(timezone.utc).isoformat(),
            "measures": {}, "patterns": {}, "fixes": {},
            "stats": {"total_api_calls": 0, "registry_hits": 0,
                      "validations": 0, "fixes": 0, "builds": 0, "definitions": 0}
        }

    def _save_reg(reg):
        output_dir.mkdir(parents=True, exist_ok=True)
        reg["updated_at"] = datetime.now(timezone.utc).isoformat()
        registry_path.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")

    registry = _load_reg()
    print(f"  Registry entries: {len(registry['measures'])}")

    if not dry_run:
        if not OPENAI_AVAILABLE:
            sys.exit(1)
        client = get_client()
        model  = os.getenv("TF_MODEL")
        print(f"  Model: {model}")
        print(f"  Base URL: {os.getenv('TF_BASE_URL', '')[:50]}...")
    else:
        client = None
        print("  DRY RUN mode — no API calls")

    print()

    # Categorize measures
    compiler_sql    = []   # VALIDATOR targets
    complex_measures = []  # BUILDER targets
    definer_measures = []  # DEFINER targets

    for name, m in all_measures.items():
        if measure_filter and name != measure_filter:
            continue

        scope = m.get("scope", "IN_SCOPE")
        sql   = m.get("sql_query")
        role  = m.get("llm_role")
        pat   = m.get("dax_pattern", "")

        if scope == "IN_SCOPE" and sql and not build_only and not define_only:
            compiler_sql.append(m)
        elif scope == "IN_SCOPE" and not sql and role == "BUILDER":
            if not validate_only and not define_only:
                complex_measures.append(m)
        elif scope != "IN_SCOPE" and role == "DEFINER":
            if not SKIP_OUT_OF_SCOPE and not validate_only and not build_only:
                definer_measures.append(m)

    print(f"  Compiler SQL to validate : {len(compiler_sql)}")
    print(f"  COMPLEX to build         : {len(complex_measures)}")
    print(f"  DEFINER to define        : {len(definer_measures)}")
    print()

    results   = {}
    api_calls = [0]
    lock      = threading.Lock()

    # ── ROLE 1+2: VALIDATE + FIX compiler SQL ──────────────
    if not build_only and not define_only and compiler_sql:
        print(f"  {'─'*50}")
        print(f"  VALIDATING {len(compiler_sql)} compiler-generated SQLs...")
        print(f"  {'─'*50}")

        to_validate = compiler_sql

        print(f"  (validating {len(to_validate)} measures, {WORKERS} workers)")
        print()

        def _validate_one(m):
            name    = m["measure_name"]
            sql     = m["sql_query"]
            pattern = m.get("dax_pattern", "")
            dax     = m.get("clean_dax", "")

            with lock:
                reg_entry = registry_get(registry, name)
                cached_status = reg_entry.get("validation") if reg_entry else None
                if cached_status and cached_status not in ("error",) and not skip_registry:
                    registry["stats"]["registry_hits"] += 1
                    results[name] = reg_entry
                    return name, "registry", cached_status, []

            # Build dep_sqls, blocking if any dep is known-bad in the registry.
            # Statuses that are safe to use as dependencies:
            _APPROVED = {"approved", "fixed"}
            dep_sqls   = {}
            blocked_by = None

            for dep in m.get("depends_on", []):
                dep_name = dep.get("measure_name") if isinstance(dep, dict) else dep
                if not dep_name or dep_name not in all_measures:
                    continue
                dep_sql = all_measures[dep_name].get("sql_query")
                if not dep_sql:
                    continue  # dep has no SQL (COMPLEX/out-of-scope) — skip

                with lock:
                    dep_reg = registry_get(registry, dep_name)
                dep_status = dep_reg.get("validation") if dep_reg else None

                # If the dep has been evaluated and is NOT clean, block this measure.
                if dep_status and dep_status not in _APPROVED:
                    blocked_by = (dep_name, dep_status)
                    break

                dep_sqls[dep_name] = dep_sql

            if blocked_by:
                dep_name, dep_status = blocked_by
                block_note = (
                    f"Dependency '{dep_name}' is {dep_status} — resolve it first"
                )
                with lock:
                    registry_set(registry, name, "VALIDATOR",
                        sql=sql, validation="blocked", notes=block_note)
                    results[name] = registry["measures"][name]
                    _save_reg(registry)
                return name, "blocked", None, [block_note]

            # API call — outside lock (I/O bound)
            val = validate_sql(client, name, dax, sql, pattern, dep_sqls, dry_run,
                               schema_context=schema_rules_only,
                               validator_system=validator_system,
                               validator_checklist=validator_checklist)

            verdict   = val.get("verdict", "error")
            corrected = val.get("corrected_sql")
            issues    = val.get("issues", [])

            with lock:
                api_calls[0] += 1
                registry["stats"]["api_calls"] = registry["stats"].get("api_calls", 0) + 1
                registry["stats"]["validations"] += 1

                if verdict == "approved":
                    registry_set(registry, name, "VALIDATOR",
                        sql=sql, validation="approved",
                        notes=val.get("explanation", ""))
                elif verdict == "needs_fix" and corrected:
                    corrected = clean_llm_sql(corrected)
                    registry["stats"]["fixes"] += 1
                    registry_set(registry, name, "FIXER",
                        sql=corrected, original_sql=sql, validation="fixed",
                        fix_applied="; ".join(issues), notes=val.get("explanation", ""))
                    all_measures[name]["sql_query"]  = corrected
                    all_measures[name]["llm_fixed"]  = True
                    all_measures[name]["fix_reason"] = "; ".join(issues)
                else:
                    registry_set(registry, name, "VALIDATOR",
                        sql=sql, validation=verdict, notes=str(issues))

                results[name] = registry["measures"][name]
                _save_reg(registry)

            return name, verdict, corrected, issues

        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(_validate_one, m): m for m in to_validate}
            for j, future in enumerate(as_completed(futures), 1):
                m    = futures[future]
                name = m["measure_name"]
                try:
                    _name, verdict, corrected, issues = future.result()
                    if verdict == "registry":
                        print(f"  [{j:3}/{len(to_validate)}] {_name[:45]:<45} 📋 REGISTRY  — {issues}")
                    elif verdict == "approved":
                        print(f"  [{j:3}/{len(to_validate)}] {_name[:45]:<45} ✅ APPROVED")
                    elif verdict == "needs_fix" and corrected:
                        iss = "; ".join(issues[:1])[:50] if isinstance(issues, list) else str(issues)[:50]
                        print(f"  [{j:3}/{len(to_validate)}] {_name[:45]:<45} 🔧 FIXED      — {iss}")
                    elif verdict == "blocked":
                        reason = issues[0] if issues else "unknown dependency issue"
                        print(f"  [{j:3}/{len(to_validate)}] {_name[:45]:<45} 🚫 BLOCKED    — {reason[:60]}")
                    else:
                        print(f"  [{j:3}/{len(to_validate)}] {_name[:45]:<45} ⚠️  {str(verdict).upper():<10} — {str(issues)[:50]}")
                except Exception as exc:
                    print(f"  [{j:3}/{len(to_validate)}] {name[:45]:<45} ❌ THREAD ERROR — {exc}")

    # ── ROLE 3: BUILD complex measures ─────────────────────
    if not validate_only and not define_only and complex_measures:
        print(f"\n  {'─'*50}")
        print(f"  BUILDING {len(complex_measures)} COMPLEX measures ({WORKERS} workers)...")
        print(f"  {'─'*50}\n")

        def _build_one(m):
            name    = m["measure_name"]
            dax     = m.get("clean_dax", "")
            pattern = m.get("dax_pattern", "COMPLEX")

            with lock:
                reg_entry = registry_get(registry, name)
                if reg_entry and reg_entry.get("sql") and not skip_registry:
                    all_measures[name]["sql_query"] = reg_entry["sql"]
                    all_measures[name]["llm_built"] = True
                    registry["stats"]["registry_hits"] += 1
                    results[name] = reg_entry
                    return name, "registry", None

            dep_sqls = get_dep_sqls(m, all_measures)

            # API call 1: build — outside lock
            sql = clean_llm_sql(build_sql(
                client, name, dax, pattern, dep_sqls, dry_run,
                schema_context=schema_context,
                builder_system=builder_system,
            ))

            with lock:
                api_calls[0] += 1
                registry["stats"]["api_calls"] = registry["stats"].get("api_calls", 0) + 1
                registry["stats"]["builds"] += 1

            if sql.startswith("ERROR:"):
                with lock:
                    registry_set(registry, name, "BUILDER", notes=sql)
                    results[name] = registry["measures"].get(name, {})
                    _save_reg(registry)
                return name, "build_failed", sql

            # API call 2: validate — outside lock
            val = validate_sql(client, name, dax, sql, pattern, dep_sqls, dry_run,
                               schema_context=schema_rules_only,
                               validator_system=validator_system,
                               validator_checklist=validator_checklist)

            with lock:
                api_calls[0] += 1
                registry["stats"]["api_calls"] = registry["stats"].get("api_calls", 0) + 1

                verdict = val.get("verdict", "unknown")
                if verdict == "approved":
                    final_sql = sql
                elif verdict == "needs_fix" and val.get("corrected_sql"):
                    final_sql = clean_llm_sql(val["corrected_sql"])
                else:
                    final_sql = sql

                registry_set(registry, name, "BUILDER",
                    sql=final_sql, validation=verdict,
                    notes=val.get("explanation", ""))

                all_measures[name]["sql_query"]    = final_sql
                all_measures[name]["needs_llm"]    = verdict not in ("approved", "needs_fix")
                all_measures[name]["llm_built"]    = True
                all_measures[name]["llm_validated"] = verdict
                all_measures[name]["needs_review"] = verdict not in ("approved",)

                results[name] = registry["measures"].get(name, {})
                _save_reg(registry)

            return name, "built", verdict

        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(_build_one, m): m for m in complex_measures}
            for j, future in enumerate(as_completed(futures), 1):
                m    = futures[future]
                name = m["measure_name"]
                try:
                    _name, status, detail = future.result()
                    if status == "registry":
                        print(f"  [{j:3}/{len(complex_measures)}] {_name[:45]:<45} 📋 REGISTRY")
                    elif status == "build_failed":
                        print(f"  [{j:3}/{len(complex_measures)}] {_name[:45]:<45} ❌ BUILD FAILED — {str(detail)[:60]}")
                    else:
                        verdict = detail
                        if verdict == "approved":
                            print(f"  [{j:3}/{len(complex_measures)}] {_name[:45]:<45} ✅ BUILT")
                        elif verdict == "needs_fix":
                            print(f"  [{j:3}/{len(complex_measures)}] {_name[:45]:<45} ✅ BUILT → auto-corrected")
                        else:
                            print(f"  [{j:3}/{len(complex_measures)}] {_name[:45]:<45} ✅ BUILT ⚠️  manual review needed")
                except Exception as exc:
                    print(f"  [{j:3}/{len(complex_measures)}] {name[:45]:<45} ❌ THREAD ERROR — {exc}")

    # ── ROLE 4: DEFINE out-of-scope measures ───────────────
    if not validate_only and not build_only and definer_measures:
        print(f"\n  {'─'*50}")
        print(f"  DEFINING {len(definer_measures)} out-of-scope measures ({WORKERS} workers)...")
        print(f"  {'─'*50}\n")

        def _define_one(m):
            name         = m["measure_name"]
            dax          = m.get("clean_dax", m.get("raw_dax", ""))
            scope_reason = m.get("scope_reason", "")

            with lock:
                reg_entry = registry_get(registry, name)
                if reg_entry and reg_entry.get("definition") and not skip_registry:
                    all_measures[name]["llm_definition"] = reg_entry["definition"]
                    registry["stats"]["registry_hits"] += 1
                    results[name] = reg_entry
                    return name, "registry", None

            # API call — outside lock
            defn = build_definition(client, name, dax, scope_reason, dry_run,
                                    definer_system=definer_system)

            with lock:
                api_calls[0] += 1
                registry["stats"]["api_calls"] = registry["stats"].get("api_calls", 0) + 1
                registry["stats"]["definitions"] += 1

                if defn.startswith("ERROR:"):
                    registry_set(registry, name, "DEFINER", notes=defn)
                else:
                    registry_set(registry, name, "DEFINER", definition=defn)
                    all_measures[name]["llm_definition"] = defn

                results[name] = registry["measures"].get(name, {})
                _save_reg(registry)

            return name, "failed" if defn.startswith("ERROR:") else "defined", defn

        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {executor.submit(_define_one, m): m for m in definer_measures}
            for j, future in enumerate(as_completed(futures), 1):
                m    = futures[future]
                name = m["measure_name"]
                try:
                    _name, status, defn = future.result()
                    if status == "registry":
                        print(f"  [{j:3}/{len(definer_measures)}] {_name[:45]:<45} 📋 REGISTRY")
                    elif status == "failed":
                        print(f"  [{j:3}/{len(definer_measures)}] {_name[:45]:<45} ❌ FAILED — {str(defn)[:200]}")
                    else:
                        print(f"  [{j:3}/{len(definer_measures)}] {_name[:45]:<45} ✅ DEFINED")
                except Exception as exc:
                    print(f"  [{j:3}/{len(definer_measures)}] {name[:45]:<45} ❌ THREAD ERROR — {exc}")

    # ── Save updated final_measures ─────────────────────────
    updated_list = list(all_measures.values())
    output_dir.mkdir(parents=True, exist_ok=True)
    updated_final.write_text(
        json.dumps(updated_list, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # ── Summary ─────────────────────────────────────────────
    stats = registry["stats"]
    print(f"\n{'─'*60}")
    print(f"  COMPLETE")
    print(f"{'─'*60}")
    print(f"  API calls this run  : {api_calls[0]}")
    print(f"  Registry hits       : {stats.get('registry_hits', 0)}")
    print(f"  Total validations   : {stats.get('validations', 0)}")
    print(f"  Total fixes         : {stats.get('fixes', 0)}")
    print(f"  Total builds        : {stats.get('builds', 0)}")
    print(f"  Total definitions   : {stats.get('definitions', 0)}")
    print(f"\n  Output:")
    print(f"    {updated_final}")
    print(f"    {registry_path}")

    return {
        "api_calls"   : api_calls[0],
        "results"     : results,
        "registry"    : registry,
    }


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LLM Fallback — Validate, Fix, Build, Define"
    )
    parser.add_argument("--dashboard", type=str, default="risk-dash",
        help="Dashboard to run: risk-dash | pac-dash | all (default: pac-dash)")
    parser.add_argument("--validate-only", action="store_true",
        help="Only validate compiler-generated SQL")
    parser.add_argument("--build-only", action="store_true",
        help="Only build COMPLEX measures")
    parser.add_argument("--define-only", action="store_true",
        help="Only generate definitions for out-of-scope measures")
    parser.add_argument("--measure", type=str, default=None,
        help="Process only this measure name")
    parser.add_argument("--dry-run", action="store_true",
        help="Print prompts only, no API calls")
    parser.add_argument("--skip-registry", action="store_true",
        help="Ignore registry cache, force re-run")

    args = parser.parse_args()

    dashboards_to_run = (
        list(DASHBOARD_LLM_CONFIGS.keys())
        if args.dashboard == "all"
        else [args.dashboard]
    )

    for _dash in dashboards_to_run:
        run_llm_fallback(
            validate_only  = args.validate_only,
            build_only     = args.build_only,
            define_only    = args.define_only,
            measure_filter = args.measure,
            dry_run        = args.dry_run,
            skip_registry  = args.skip_registry,
            dashboard      = _dash,
        )