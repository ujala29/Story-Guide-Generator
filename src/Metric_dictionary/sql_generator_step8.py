"""
sql_generator.py
────────────────
Stage 2 — Step 6

PURPOSE:
    Walk an AnnotatedAST + ClassifyResult and emit Snowflake SQL.
    NO regex. NO string scanning. Pure AST navigation.

INPUT:
    AnnotatedAST  (from semantic_resolver.py)
    ClassifyResult (from classifier.py)
    sql_cache     (dict of {measure_name: sql_string} for already-resolved deps)

OUTPUT:
    GenerateResult dataclass:
        sql          : str | None   — generated SQL
        needs_llm    : bool         — True if compiler gave up
        llm_role     : str | None   — "BUILDER" if needs_llm
        cte_blocks   : list[str]    — WITH block CTEs for static tables
        error        : str | None   — reason if needs_llm

EDGE CASES HANDLED:
    EC2   IN {} → IN ()            (InSetExpr → SQL IN clause)
    EC3   <> → !=                  (BinaryOp op mapping)
    EC4   ALL() → no date filter   (ClassifyResult.has_all)
    EC8   TRUE/TRUE() → TRUE       (BoolLiteral → SQL TRUE/FALSE)
    EC9   "true" string → 'true'   (StringLiteral → quoted)
    EC10  * scalar after DIVIDE    (ScalarMultiplier → (...) * N)
    EC16  CALCULATE no filters     (plain aggregation)
    EC18  AVERAGE → AVG()          (function name mapping)
    EC19  DIVIDE 2-arg → NULLIF    (DivideNode.default_val=None)
          DIVIDE 3-arg → COALESCE  (DivideNode.default_val=0.0)
    EC24  inline filter = KEEPFILTERS → both → WHERE

SQL TEMPLATES (from step4_sql_builder.py — adapted):
    SIMPLE_AGG:
        SELECT {AGG}({col}) FROM {table}
    SIMPLE_DIVIDE:
        SELECT {num} / NULLIF({den}, 0) FROM {table}
    FILTERED_AGG:
        SELECT {AGG}({col}) FROM {table} WHERE {conditions}
    VAR_FILTERED_DIVIDE:
        SELECT
          SUM(CASE WHEN {filter_a} THEN {col_a} END)
          / NULLIF(SUM(CASE WHEN {filter_b} THEN {col_b} END), 0)
        FROM {table}
    MEASURE_RATIO:
        ({sql_A}) / NULLIF(({sql_B}), 0)
    TIME_INTEL_YOY:
        SELECT {AGG}({col}) FROM {table}
        WHERE {date_col} = DATEADD(year, -1, :{param})
    TIME_INTEL_MOM:
        SELECT {AGG}({col}) FROM {table}
        WHERE {date_col} = DATEADD(month, -1, :{param})
    CONTEXT_REMOVER:
        SELECT {AGG}({col}) FROM {table}   ← no date filter
    COMPLEX_VAR_DIVIDE:
        WITH
          {var_name} AS ({var_sql}),
          ...
        SELECT {return_expr_sql}
    STATIC_FILTERED:
        WITH {static_cte} AS (...placeholder...)
        SELECT ... WHERE col IN (SELECT col FROM {static_cte})
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from ast_nodes_step0 import (
    ColumnRef, MeasureRef, VarRef, StringLiteral, NumberLiteral,
    BoolLiteral, FunctionCall, DivideNode, BinaryOp, InSetExpr,
    CompoundAnd, InlineFilter, ScalarMultiplier, VarDef, VarBlock,
)
from semantic_resolver_step6 import AnnotatedAST, SFRef
from classifier_step7 import ClassifyResult


# ══════════════════════════════════════════════════════════════
# RESULT
# ══════════════════════════════════════════════════════════════

@dataclass
class GenerateResult:
    """
    Output of generate(). Always returned — never raises.

    Fields:
        measure_name : display name
        sql          : generated Snowflake SQL (None if needs_llm)
        needs_llm    : True if compiler could not generate SQL
        llm_role     : "BUILDER" if needs_llm, else None
        cte_blocks   : WITH block CTEs for static tables
        error        : reason string if needs_llm
        pattern      : dax_pattern label for logging
    """
    measure_name : str
    sql          : Optional[str]
    needs_llm    : bool
    llm_role     : Optional[str]
    cte_blocks   : list[str]     = field(default_factory=list)
    error        : Optional[str] = None
    pattern      : str           = ""


# ══════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
# CACHE LOOKUP — single function used everywhere
# ══════════════════════════════════════════════════════════════

def _normalize_measure_name(name: str) -> str:
    """Normalize spaces around operators so 'Cost / Admit' matches 'Cost/Admit'."""
    return re.sub(r'\s*([/+\-*])\s*', r'\1', name)
# A- B → A-B (also handles A -B, A- B, A / B → A/B etc.)

def _cache_get(name: str, sql_cache: dict) -> "str | None":
    """
    Look up measure SQL from cache.
    Case-insensitive and operator-space-normalized —
    handles 'Cost / Admit' (parser adds spaces) matching 'Cost/Admit' (model key).
    """
    if not name:
        return None
    if name in sql_cache:
        return sql_cache[name]
    name_lower = name.lower()
    name_norm  = _normalize_measure_name(name_lower)
    for k, v in sql_cache.items():
        k_lower = k.lower()
        if k_lower == name_lower or _normalize_measure_name(k_lower) == name_norm:
            return v
    return None


# DAX function → SQL function name mapping
FUNC_MAP = {
    "SUM"          : "SUM",
    "COUNT"        : "COUNT",
    "COUNTROWS"    : "COUNT",   # COUNTROWS(table) → COUNT(*)
    "DISTINCTCOUNT": "COUNT(DISTINCT {})",
    "MAX"          : "MAX",
    "MIN"          : "MIN",
    "AVERAGE"      : "AVG",     # EC18: AVERAGE → AVG
    "ABS"          : "ABS",
}

# Binary operator mapping (DAX → SQL)
OP_MAP = {
    "="  : "=",
    "<>" : "!=",   # EC3
    ">"  : ">",
    "<"  : "<",
    ">=" : ">=",
    "<=" : "<=",
    "+"  : "+",
    "-"  : "-",
    "*"  : "*",
    "/"  : "/",
}

# Per-table date column mapping — loaded from bi_snowflakes_naming_matching.json
# Fallback hardcoded values used if load_table_metadata() not called
# DATE_COL_MAP = {
#     'PCP_VISITS_V4_VIEW'  : 'MONTH_OF_DATE',
#     'RISK_CORE_V4_VIEW'   : 'MONTH_OF_MEASUREMENT',
#     'RISK_GROUP_V4_VIEW'  : 'MONTH_OF_MEASUREMENT',
#     'RISK_COHORT_V4_VIEW' : 'MONTH_OF_MEASUREMENT',
#     'DATE_VIEW'           : 'MONTH_OF_DATE',
# }

# Tables with MAX_MONTH_FLAG — loaded from bi_snowflakes_naming_matching.json
MAX_MONTH_TABLES = {
    'RISK_CORE_V4_VIEW',
    'RISK_GROUP_V4_VIEW',
    'RISK_COHORT_V4_VIEW',
    # PCP_VISITS_V4_VIEW excluded — no max_month_flag column (confirmed DAX Studio)
}

DATE_COL_MAP = {
    # Confirmed from SHOW COLUMNS output
    'PCP_VISITS_V4_VIEW'    : 'MONTH_OF_DATE',        # ✅ confirmed from schema

    # Confirmed from Image 2 — column exists, query ran clean
    'PCP_VISITS_VIEW'       : 'MONTH_OF_ATTRIBUTION', # ✅ confirmed from Snowflake

    # Confirmed from Image 4 — column exists, query ran clean
    'INPATIENT_PAC_V4_VIEW' : 'MONTH_OF_VISIT',       # ✅ confirmed from Snowflake

    # Unchanged — these were already correct
    'RISK_CORE_V4_VIEW'     : 'MONTH_OF_MEASUREMENT',
    'RISK_GROUP_V4_VIEW'    : 'MONTH_OF_MEASUREMENT',
    'RISK_COHORT_V4_VIEW'   : 'MONTH_OF_MEASUREMENT',
    'DATE_VIEW'             : 'MONTH_OF_DATE',

    # PAC_TABLE intentionally NOT in this map —
    # its DATE_TRUNC('month', PAC_VISIT_START_DATE) pattern
    # is handled separately and confirmed valid (Image 5)
}
def load_table_metadata(sf_map: dict) -> None:
    """
    Load DATE_COL_MAP and MAX_MONTH_TABLES from bi_snowflakes_naming_matching.json.
    Call once at pipeline startup. Overrides hardcoded defaults above.

    Usage in pipeline.py:
        sf_map = json.loads(Path(sf_map_path).read_text())
        load_table_metadata(sf_map)
        sf_lookup = build_snowflake_lookup(sf_map)
    """
    global DATE_COL_MAP, MAX_MONTH_TABLES

    for bi_name, val in sf_map.items():
        if not isinstance(val, dict) or bi_name == 'static_tables':
            continue

        sf_obj = val.get('snowflake_object')
        if isinstance(sf_obj, dict):
            sf_obj = sf_obj.get('snowflake') or sf_obj.get('postgres')

        if not sf_obj:
            continue

        date_col = val.get('date_column')
        if date_col:
            DATE_COL_MAP[sf_obj] = date_col

        if val.get('has_max_month_flag', False):
            MAX_MONTH_TABLES.add(sf_obj)
        else:
            # Explicitly remove if JSON says False — overrides hardcoded default
            MAX_MONTH_TABLES.discard(sf_obj)

# Static CTE placeholder template
STATIC_CTE_TEMPLATE = (
    "-- {table} (Power BI static table — not in Snowflake)\n"
    "-- TODO: Replace with actual values from Power BI Desktop → Table view → '{table}'\n"
    "{table} AS (\n"
    "    SELECT '<placeholder_value>' AS placeholder_col\n"
    "    -- UNION ALL SELECT '<value2>'\n"
    ")"
)


# ══════════════════════════════════════════════════════════════
# SF REF LOOKUP HELPER
# ══════════════════════════════════════════════════════════════

def _sf_name(
    bi_table  : str,
    bi_column : str,
    sf_refs   : list[SFRef],
) -> tuple[Optional[str], Optional[str]]:
    """
    Look up Snowflake object + column name for a BI table/column pair.
    Returns (sf_object, sf_column) or (None, None) if not found.
    """
    for ref in sf_refs:
        if ref.bi_table == bi_table and ref.bi_column == bi_column:
            return ref.sf_object, ref.sf_column
    # Try table-only match (column="*")
    for ref in sf_refs:
        if ref.bi_table == bi_table:
            return ref.sf_object, None
    return None, None


def _sf_table(bi_table: str, sf_refs: list[SFRef]) -> Optional[str]:
    """Return just the Snowflake object name for a BI table."""
    for ref in sf_refs:
        if ref.bi_table == bi_table and ref.sf_object:
            return ref.sf_object
    return None


# ══════════════════════════════════════════════════════════════
# EXPRESSION EMITTER
# ══════════════════════════════════════════════════════════════

class _Emitter:
    """
    Walks AST nodes and emits SQL expression fragments.
    Used for building WHERE conditions, aggregations, etc.
    """

    def __init__(self, sf_refs: list[SFRef], sql_cache: dict[str, str],
                 var_sql: dict[str, str] = None):
        self.sf_refs   = sf_refs
        self.sql_cache = sql_cache        # {measure_name: sql}
        self.var_sql   = var_sql or {}    # {var_binding_name: sql_fragment}

    def emit(self, node: Any) -> str:
        """Dispatch to correct emit method based on node type."""
        if isinstance(node, ColumnRef):
            return self._emit_column(node)
        if isinstance(node, MeasureRef):
            return self._emit_measure_ref(node)
        if isinstance(node, VarRef):
            return self._emit_var_ref(node)
        if isinstance(node, StringLiteral):
            return f"'{node.value}'"    # EC9: quoted string
        if isinstance(node, NumberLiteral):
            v = int(node.value) if node.value == int(node.value) else node.value
            return str(v)
        if isinstance(node, BoolLiteral):
            return "TRUE" if node.value else "FALSE"   # EC8
        if isinstance(node, BinaryOp):
            return self._emit_binary(node)
        if isinstance(node, FunctionCall):
            return self._emit_function(node)
        if isinstance(node, DivideNode):
            return self._emit_divide(node)
        if isinstance(node, InSetExpr):
            return self._emit_in_set(node)
        if isinstance(node, CompoundAnd):
            left  = self.emit(node.left)
            right = self.emit(node.right)
            return f"{left} AND {right}"
        if isinstance(node, InlineFilter):
            return self.emit(node.expr)
        if isinstance(node, ScalarMultiplier):
            base = self.emit(node.base_expr)
            mult = int(node.multiplier) if node.multiplier == int(node.multiplier) else node.multiplier
            return f"({base}) * {mult}"
        return f"/* unsupported node: {type(node).__name__} */"

    def _emit_column(self, node: ColumnRef) -> str:
        """Emit a column reference as SNOWFLAKE_COLUMN or table.COLUMN."""
        if node.column == "*":
            # Table-only reference (COUNTROWS)
            sf_obj = _sf_table(node.table, self.sf_refs)
            return sf_obj or node.table.upper()
        _, sf_col = _sf_name(node.table, node.column, self.sf_refs)
        return sf_col or node.column.upper()

    def _emit_measure_ref(self, node: MeasureRef) -> str:
        """Emit a reference to another measure as its SQL (from sql_cache)."""
        # Single module-level _cache_get — case-insensitive
        cached_val = _cache_get(node.name, self.sql_cache)
        if cached_val is not None:
            cached = cached_val.strip()
            if cached.upper().startswith("SELECT"):
                return f"({cached})"
            return cached

        # Not yet resolved — return placeholder
        return f"/* unresolved measure: {node.name} */"

    def _emit_var_ref(self, node: VarRef) -> str:
        """Emit a VAR reference as its SQL fragment."""
        if node.name in self.var_sql:
            return self.var_sql[node.name]
        return f"/* unresolved var: {node.name} */"

    def _emit_binary(self, node: BinaryOp) -> str:
        """Emit a binary operation."""
        left  = self.emit(node.left)
        right = self.emit(node.right)
        op    = OP_MAP.get(node.op, node.op)
        return f"{left} {op} {right}"

    def _emit_function(self, node: FunctionCall) -> str:
        """Emit a function call."""
        name = node.name.upper()

        # COUNTROWS(table) → COUNT(*)
        if name == "COUNTROWS":
            return "COUNT(*)"

        # DISTINCTCOUNT(col) → COUNT(DISTINCT col)
        if name == "DISTINCTCOUNT" and node.args:
            col = self.emit(node.args[0])
            return f"COUNT(DISTINCT {col})"

        # AVERAGE → AVG  (EC18)
        if name == "AVERAGE":
            name = "AVG"

        # ABS, SUM, COUNT, MAX, MIN, AVG — standard
        if name in ("SUM", "COUNT", "MAX", "MIN", "AVG", "ABS"):
            args = ", ".join(self.emit(a) for a in node.args)
            return f"{name}({args})"

        # KEEPFILTERS — emit inner expression
        if name == "KEEPFILTERS":
            return self.emit(node.args[0]) if node.args else ""

        # ALL — emit nothing (date filter removal is handled at template level)
        if name == "ALL":
            return ""

        # SAMEPERIODLASTYEAR / PREVIOUSMONTH — time intel handled at template level
        if name in ("SAMEPERIODLASTYEAR", "PREVIOUSMONTH"):
            return ""

        # CALCULATE — emit first arg only (filters handled separately)
        if name == "CALCULATE":
            return self.emit(node.args[0]) if node.args else ""

        # Generic fallback
        args = ", ".join(self.emit(a) for a in node.args)
        return f"{name}({args})"

    def _emit_divide(self, node: DivideNode) -> str:
        """
        EC19: DIVIDE(a, b)    → a / NULLIF(b, 0)
              DIVIDE(a, b, 0) → COALESCE(a / NULLIF(b, 0), 0)

        Fix 2: If numerator is BinaryOp (e.g. a - b), wrap in parens
        to ensure correct operator precedence.
        Without: a - b / NULLIF(c, 0) → a - (b/c)  [WRONG]
        With:    (a - b) / NULLIF(c, 0)             [CORRECT]
        """
        num = self.emit(node.numerator)
        den = self.emit(node.denominator)
        # Wrap numerator in parens if it contains arithmetic operators
        if isinstance(node.numerator, BinaryOp) and node.numerator.op in ("+", "-"):
            num = f"({num})"
        core = f"{num} / NULLIF({den}, 0)"
        if node.default_val is not None:
            return f"COALESCE({core}, 0)"
        return core

    def _emit_in_set(self, node: InSetExpr) -> str:
        """EC2: IN {} → IN ()"""
        col    = self._emit_column(node.column)
        values = ", ".join(f"'{v}'" for v in node.values)
        return f"{col} IN ({values})"


# ══════════════════════════════════════════════════════════════
# FILTER COLLECTOR
# ══════════════════════════════════════════════════════════════

def _collect_filters(args: list, emitter: _Emitter) -> list[str]:
    """
    Extract WHERE conditions from CALCULATE filter arguments.
    Handles InlineFilter, InSetExpr, BinaryOp, CompoundAnd.
    Returns list of SQL condition strings.
    """
    conditions = []
    for arg in args[1:]:   # skip first arg (main expression)
        if isinstance(arg, InlineFilter):
            conditions.append(emitter.emit(arg.expr))
        elif isinstance(arg, (BinaryOp, InSetExpr, CompoundAnd)):
            conditions.append(emitter.emit(arg))
        elif isinstance(arg, FunctionCall):
            if arg.name in ("KEEPFILTERS",):
                conditions.append(emitter.emit(arg.args[0]) if arg.args else "")
            # ALL, SAMEPERIODLASTYEAR etc. → skip (not WHERE conditions)
    return [c for c in conditions if c]


# ══════════════════════════════════════════════════════════════
# PATTERN GENERATORS
# ══════════════════════════════════════════════════════════════

def _finalize_sql(sql: str, sf_refs: list[SFRef]) -> str:
    """
    Central post-processor called by _ok() for every pattern.

    Ensures date_col = :selected_month is present for tables that have a
    date column mapping. This is the SINGLE place for date-filter rules —
    individual pattern generators no longer need to handle it.

    Skipped automatically when:
      - SQL has DATEADD (time-intel)
      - Exact date_filter already present in main SELECT body
      - Table has no entry in DATE_COL_MAP

    CTE-aware: for SQL starting with WITH, checks only the main SELECT body
    (after the last top-level CTE closing paren) so that :selected_month inside
    a CTE subquery for a different table doesn't suppress the outer query filter.
    """
    if not sql:
        return sql
    if "DATEADD" in sql.upper():
        return sql  # time-intel

    # Primary source table — exclude DATE_VIEW (only used for date-col resolution)
    tables = [r.sf_object for r in sf_refs
              if r.ref_type == "source" and r.sf_object
              and r.sf_object != "DATE_VIEW"]
    if not tables:
        return sql

    primary  = tables[0]
    date_col = DATE_COL_MAP.get(primary)
    if not date_col:
        return sql

    date_filter = f"{date_col} = :selected_month"

    # For WITH-CTE SQL the date_col may appear in a CTE for a different table.
    # Extract the main SELECT body (after the last CTE closing paren) so
    # the checks are scoped to the outer query only.
    if re.match(r'\s*WITH\b', sql, re.IGNORECASE):
        idx = sql.rfind('\n)')
        main_body = sql[idx + 2:].strip() if idx >= 0 else sql
    else:
        main_body = sql

    if ":selected_month" in main_body:
        return sql  # already filtered in main query
    if date_col.upper() in main_body.upper():
        return sql  # date column already present in main query

    # For risk tables (RISK_CORE, RISK_GROUP) also add MAX_MONTH_FLAG if missing.
    # MAX_MONTH_FLAG marks only the latest month — required for point-in-time queries.
    # _gen_filtered_agg / _gen_var_filtered_divide add it themselves; _gen_simple_agg
    # does not, so this is the only place that covers the SIMPLE_AGG gap.
    add_max_flag = (
        primary in MAX_MONTH_TABLES
        and "MAX_MONTH_FLAG" not in main_body.upper()
    )

    if re.search(r'\bWHERE\b', sql, re.IGNORECASE):
        if add_max_flag:
            sql = sql.rstrip() + f"\n  AND MAX_MONTH_FLAG = TRUE\n  AND {date_filter}"
        else:
            sql = sql.rstrip() + f"\n  AND {date_filter}"
    else:
        if add_max_flag:
            sql = sql.rstrip() + f"\nWHERE MAX_MONTH_FLAG = TRUE\n  AND {date_filter}"
        else:
            sql = sql.rstrip() + f"\nWHERE {date_filter}"

    return sql


def _strip_date_filter(sql: str) -> str:
    """
    Remove col = :selected_month conditions from a base-measure SQL before
    injecting a time-intel date filter (DATEADD).  Without this, the base SQL
    (already finalized with :selected_month by _finalize_sql) would accumulate
    BOTH col = :selected_month AND col = DATEADD(...) — an unsatisfiable WHERE.

    Uses [^=\n]+? instead of \w+ so expression-based date columns are also matched,
    e.g. DATE_TRUNC('month', PAC_VISIT_START_DATE) = :selected_month.
    """
    # WHERE expr = :selected_month  AND rest  →  WHERE rest
    sql = re.sub(
        r'WHERE\s+[^=\n]+?\s*=\s*:selected_month\s*\n?\s*AND\s+',
        'WHERE ', sql, flags=re.IGNORECASE
    )
    # rest  AND expr = :selected_month  →  rest
    sql = re.sub(r'\s*AND\s+[^=\n]+?\s*=\s*:selected_month', '', sql, flags=re.IGNORECASE)
    # WHERE expr = :selected_month  (standalone — may be followed by ) — no $ anchor)
    sql = re.sub(
        r'\s*WHERE\s+[^=\n]+?\s*=\s*:selected_month\s*', '',
        sql, flags=re.IGNORECASE
    )
    return sql.strip()


def _strip_max_month_flag(sql: str) -> str:
    """
    Remove MAX_MONTH_FLAG = TRUE from a SQL string before adding
    a time-intel date filter (YoY/MoM). MAX_MONTH_FLAG marks only
    the latest month — combining it with MONTH_OF_MEASUREMENT = prior_month
    produces 0 rows. The explicit date filter is sufficient.
    """
    # WHERE MAX_MONTH_FLAG = TRUE AND other → WHERE other
    sql = re.sub(r'WHERE\s+MAX_MONTH_FLAG\s*=\s*TRUE\s+AND\s+', 'WHERE ', sql, flags=re.IGNORECASE)
    # WHERE other AND MAX_MONTH_FLAG = TRUE → WHERE other
    sql = re.sub(r'\s+AND\s+MAX_MONTH_FLAG\s*=\s*TRUE', '', sql, flags=re.IGNORECASE)
    # WHERE MAX_MONTH_FLAG = TRUE (standalone — may be followed by ) from subquery)
    sql = re.sub(r'\s*WHERE\s+MAX_MONTH_FLAG\s*=\s*TRUE\s*', '', sql, flags=re.IGNORECASE)
    return sql.strip()

def _gen_simple_agg(
    ast      : Any,
    sf_refs  : list[SFRef],
    sql_cache: dict,
) -> Optional[str]:
    """
    SIMPLE_AGG: SELECT AGG(col) FROM table
    Handles: SUM, COUNT, COUNTROWS, MAX, MIN, AVERAGE, DISTINCTCOUNT, ABS
    """
    emitter = _Emitter(sf_refs, sql_cache)

    # Root function
    if not isinstance(ast, FunctionCall):
        return None

    name = ast.name.upper()

    # COUNTROWS(table)
    if name == "COUNTROWS":
        if ast.args and isinstance(ast.args[0], ColumnRef):
            sf_obj = _sf_table(ast.args[0].table, sf_refs)
            table  = sf_obj or ast.args[0].table.upper()
            # Fix 8: add MAX_MONTH_FLAG for risk tables
            if table in MAX_MONTH_TABLES:
                return f"SELECT COUNT(*)\nFROM {table}\nWHERE MAX_MONTH_FLAG = TRUE"
            return f"SELECT COUNT(*)\nFROM {table}"
        return None

    # CALCULATE with no filters (EC16) — treat inner as plain agg
    if name == "CALCULATE" and len(ast.args) == 1:
        return _gen_simple_agg(ast.args[0], sf_refs, sql_cache)

    # Standard agg: SUM/COUNT/MAX/MIN/AVERAGE/DISTINCTCOUNT
    if name in FUNC_MAP and ast.args:
        inner = ast.args[0]
        if isinstance(inner, ColumnRef):
            sf_obj, sf_col = _sf_name(inner.table, inner.column, sf_refs)
            table  = sf_obj  or inner.table.upper()
            col    = sf_col  or inner.column.upper()

            if name == "DISTINCTCOUNT":
                if table in MAX_MONTH_TABLES:
                    return f"SELECT COUNT(DISTINCT {col})\nFROM {table}\nWHERE MAX_MONTH_FLAG = TRUE"
                return f"SELECT COUNT(DISTINCT {col})\nFROM {table}"
            if name == "AVERAGE":
                if table in MAX_MONTH_TABLES:
                    return f"SELECT AVG({col})\nFROM {table}\nWHERE MAX_MONTH_FLAG = TRUE"
                return f"SELECT AVG({col})\nFROM {table}"
            if name == "ABS":
                # ABS(SUM(col))
                if isinstance(inner, FunctionCall) and inner.name == "SUM":
                    inner_col = inner.args[0]
                    sf_obj2, sf_col2 = _sf_name(inner_col.table, inner_col.column, sf_refs)
                    t2 = sf_obj2 or inner_col.table.upper()
                    c2 = sf_col2 or inner_col.column.upper()
                    return f"SELECT ABS(SUM({c2}))\nFROM {t2}"
                return None
            sql_fn = FUNC_MAP.get(name, name)
            # Fix3: add MAX_MONTH_FLAG for risk tables (latest month only)
            if table in MAX_MONTH_TABLES:
                return f"SELECT {sql_fn}({col})\nFROM {table}\nWHERE MAX_MONTH_FLAG = TRUE"
            return f"SELECT {sql_fn}({col})\nFROM {table}"

    # ABS(SUM(col))
    if name == "ABS" and ast.args:
        inner = ast.args[0]
        if isinstance(inner, FunctionCall) and inner.name == "SUM":
            col_ref = inner.args[0] if inner.args else None
            if isinstance(col_ref, ColumnRef):
                sf_obj, sf_col = _sf_name(col_ref.table, col_ref.column, sf_refs)
                table = sf_obj or col_ref.table.upper()
                col   = sf_col or col_ref.column.upper()
                return f"SELECT ABS(SUM({col}))\nFROM {table}"

    return None


def _gen_arithmetic(
    ast      : Any,
    sf_refs  : list[SFRef],
    sql_cache: dict,
) -> Optional[str]:
    """
    ARITHMETIC: ABS(SUM(col)) + SUM(col) etc.
    Walk BinaryOp tree, emit each side, combine.
    """
    emitter = _Emitter(sf_refs, sql_cache)

    # Get all tables used
    tables = list({r.sf_object for r in sf_refs
                   if r.ref_type == "source" and r.sf_object})
    if not tables:
        return None

    expr = emitter.emit(ast)
    from_clause = ", ".join(tables) if len(tables) > 1 else tables[0]

    # Add MAX_MONTH_FLAG for single risk table
    if len(tables) == 1 and tables[0] in MAX_MONTH_TABLES:
        return f"SELECT {expr}\nFROM {from_clause}\nWHERE MAX_MONTH_FLAG = TRUE"
    return f"SELECT {expr}\nFROM {from_clause}"


def _gen_simple_divide(
    ast      : DivideNode,
    sf_refs  : list[SFRef],
    sql_cache: dict,
) -> Optional[str]:
    """
    SIMPLE_DIVIDE: DIVIDE(SUM(col_a), SUM(col_b))
    → SELECT SUM(col_a) / NULLIF(SUM(col_b), 0) FROM table
    """
    emitter = _Emitter(sf_refs, sql_cache)

    num_node = ast.numerator
    den_node = ast.denominator

    # Resolve which SF table each side of the divide comes from
    def _agg_table(node):
        if isinstance(node, FunctionCall) and node.args and isinstance(node.args[0], ColumnRef):
            sf_obj, _ = _sf_name(node.args[0].table, node.args[0].column, sf_refs)
            return sf_obj, emitter.emit(node)
        return None, emitter.emit(node)

    num_sf_obj, num_sql = _agg_table(num_node)
    den_sf_obj, den_sql = _agg_table(den_node)

    # ── CROSS-TABLE: independent subqueries (no cartesian join) ──
    if num_sf_obj and den_sf_obj and num_sf_obj != den_sf_obj:
        # Inject date filters inside each subquery so _finalize_sql
        # sees :selected_month already present and skips the outer append.
        def _sub(agg, table):
            date_col = DATE_COL_MAP.get(table)
            where = f"\n  WHERE {date_col} = :selected_month" if date_col else ""
            return f"SELECT {agg}\n  FROM {table}{where}"

        num_sub = _sub(num_sql, num_sf_obj)
        den_sub = _sub(den_sql, den_sf_obj)

        if ast.default_val is not None:
            return (
                f"SELECT COALESCE(\n"
                f"  (\n    {num_sub}\n  )\n"
                f"  / NULLIF(\n    (\n      {den_sub}\n    ), 0\n  ), 0\n)"
            )
        else:
            return (
                f"SELECT\n"
                f"  (\n    {num_sub}\n  )\n"
                f"  / NULLIF(\n    (\n      {den_sub}\n    ), 0\n  )"
            )

    # ── SINGLE TABLE: original logic ─────────────────────────────
    tables = list({r.sf_object for r in sf_refs
                   if r.ref_type == "source" and r.sf_object})
    if not tables:
        return None

    if ast.default_val is not None:
        expr = f"COALESCE({num_sql} / NULLIF({den_sql}, 0), 0)"
    else:
        expr = f"{num_sql} / NULLIF({den_sql}, 0)"

    single_table = tables[0] if len(tables) == 1 else None
    if single_table and single_table in MAX_MONTH_TABLES:
        return f"SELECT {expr}\nFROM {single_table}\nWHERE MAX_MONTH_FLAG = TRUE"
    return f"SELECT {expr}\nFROM {tables[0]}"
def _gen_filtered_agg(
    ast      : FunctionCall,
    sf_refs  : list[SFRef],
    sql_cache: dict,
) -> Optional[str]:
    """
    FILTERED_AGG: CALCULATE(AGG(col), KEEPFILTERS(condition))
    → SELECT AGG(col) FROM table WHERE condition

    Special case — DIVIDE inside CALCULATE with two DIFFERENT source tables:
        CALCULATE(DIVIDE(SUM(pac_view[amount]), SUM(attribution[members])), filter)
    These tables have no join path → must use independent subqueries, NOT a
    comma-join (which produces a Cartesian product and inflated numbers).

    Single-table measures are unaffected — they fall through to the original
    FROM + WHERE logic unchanged.
    """
    emitter = _Emitter(sf_refs, sql_cache)

    if not isinstance(ast, FunctionCall) or ast.name != "CALCULATE":
        return None
    if not ast.args:
        return None

    main_expr  = ast.args[0]
    conditions = _collect_filters(ast.args, emitter)

    # ══════════════════════════════════════════════════════════
    # CROSS-TABLE DIVIDE — independent subquery pattern
    # Fires only when DIVIDE references two DIFFERENT Snowflake tables.
    # e.g. CALCULATE(DIVIDE(SUM(pac_view[pac_visit_amount]),
    #                        SUM(attribution[member_count])),
    #               pac_view[pac_visit_type] = "SNF")
    # ══════════════════════════════════════════════════════════
    if isinstance(main_expr, DivideNode):
        num_node = main_expr.numerator
        den_node = main_expr.denominator

        def _resolve_agg_table(node):
            """
            For a FunctionCall(AGG, [ColumnRef(table, col)]) node,
            return (sf_object, sf_column, agg_sql).
            Returns (None, None, None) if node is not that shape.
            """
            if not (isinstance(node, FunctionCall) and node.args):
                return None, None, None
            inner = node.args[0]
            if not isinstance(inner, ColumnRef):
                return None, None, None
            sf_obj, sf_col = _sf_name(inner.table, inner.column, sf_refs)
            if not sf_obj:
                return None, None, None
            agg_sql = emitter.emit(node)
            return sf_obj, sf_col, agg_sql

        num_sf_obj, _, num_agg_sql = _resolve_agg_table(num_node)
        den_sf_obj, _, den_agg_sql = _resolve_agg_table(den_node)

        # Only enter this branch when tables are confirmed DIFFERENT.
        # Same-table DIVIDE falls through to the original logic below.
        if num_sf_obj and den_sf_obj and num_sf_obj != den_sf_obj:

            # Filters from CALCULATE args (e.g. PAC_VISIT_TYPE = 'SNF') belong
            # to the NUMERATOR table only. Denominator (member count) is unfiltered
            # by type — it only needs the date filter which _finalize_sql will add.
            num_conditions = []
            den_conditions = []

            for cond in conditions:
                # Heuristic: assign condition to numerator table if any column
                # referenced in that condition exists in num_sf_obj's sf_refs.
                # Denominator conditions would need explicit handling — currently
                # all non-date filter args in PMPM-style measures belong to numerator.
                num_conditions.append(cond)
                # den_conditions intentionally left empty — extend here if needed.

            # Build numerator subquery — type filter + date filter both inside
            num_date_col = DATE_COL_MAP.get(num_sf_obj)
            num_where = list(num_conditions)
            if num_date_col:
                num_where.append(f"{num_date_col} = :selected_month")
            num_sql = f"SELECT {num_agg_sql}\n  FROM {num_sf_obj}"
            if num_where:
                num_sql += f"\n  WHERE {' AND '.join(num_where)}"

            # Build denominator subquery — date filter only (no type filter)
            den_date_col = DATE_COL_MAP.get(den_sf_obj)
            den_sql = f"SELECT {den_agg_sql}\n  FROM {den_sf_obj}"
            if den_date_col:
                den_sql += f"\n  WHERE {den_date_col} = :selected_month"

            # Date filters are now inside each subquery — _finalize_sql will see
            # :selected_month already present and skip the outer append.
            #
            # EC19: DIVIDE 3-arg → COALESCE, 2-arg → plain NULLIF
            if main_expr.default_val is not None:
                return (
                    f"SELECT COALESCE(\n"
                    f"  (\n"
                    f"    {num_sql}\n"
                    f"  )\n"
                    f"  / NULLIF(\n"
                    f"    (\n"
                    f"      {den_sql}\n"
                    f"    ), 0\n"
                    f"  ), 0\n"
                    f")"
                )
            else:
                return (
                    f"SELECT\n"
                    f"  (\n"
                    f"    {num_sql}\n"
                    f"  )\n"
                    f"  / NULLIF(\n"
                    f"    (\n"
                    f"      {den_sql}\n"
                    f"    ), 0\n"
                    f"  )"
                )

    # ══════════════════════════════════════════════════════════
    # ORIGINAL LOGIC — single-table AGG or same-table DIVIDE
    # Everything below is UNCHANGED from original sql_generator.py
    # ══════════════════════════════════════════════════════════

    # Main expression SQL
    agg_sql = emitter.emit(main_expr)

    # Source table(s)
    tables = list({r.sf_object for r in sf_refs
                   if r.ref_type == "source" and r.sf_object})
    if not tables:
        return None

    from_clause = ", ".join(tables)

    # Add MAX_MONTH_FLAG for risk tables (latest month only).
    # Dedup: don't add if already in conditions (e.g. from KEEPFILTERS).
    max_flag_cond = "MAX_MONTH_FLAG = TRUE"
    already_has   = any("MAX_MONTH_FLAG" in c.upper() for c in conditions)
    if len(tables) == 1 and tables[0] in MAX_MONTH_TABLES and not already_has:
        conditions = [max_flag_cond] + conditions

    sql = f"SELECT {agg_sql}\nFROM {from_clause}"
    if conditions:
        sql += f"\nWHERE {' AND '.join(conditions)}"

    # ── P6 fix ────────────────────────────────────────────────
    # Snowflake cannot have a scalar subquery inside SUM() without GROUP BY.
    # e.g. SUM(col) + (SELECT COUNT(*) FROM ...) → invalid group by expression
    # Rewrite: pre-compute scalar as CTE, reference in main query via CROSS JOIN.
    import re as _re_p6
    _p6_pat = r'[(]SELECT\s+COUNT[(][*][)][\s\S]*?FROM\s+[A-Z_0-9]+[\s\S]*?[)]'
    sub_match = _re_p6.search(_p6_pat, sql)
    if sub_match:
        sub_full  = sub_match.group(0)
        # Flatten subquery to single line for CTE body
        cte_inner = _re_p6.sub(r'\s+', ' ', sub_full[1:-1]).strip()
        sql_fixed = sql.replace(sub_full, "cte_val.n")
        # CROSS JOIN must come before WHERE — insert after FROM clause
        sql_fixed = _re_p6.sub(
            r'(FROM\s+[A-Z_0-9]+)',
            r'\1\nCROSS JOIN cte_val',
            sql_fixed,
            count=1,
        )
        sql = (
            f"WITH cte_val AS (\n"
            f"    SELECT ({cte_inner}) AS n\n"
            f")\n"
            f"{sql_fixed}"
        )

    return sql
def _gen_var_filtered_divide(
    ast      : VarBlock,
    sf_refs  : list[SFRef],
    sql_cache: dict,
) -> Optional[str]:
    """
    VAR_FILTERED_DIVIDE: VAR a = CALCULATE(AGG, filter) VAR b = ... RETURN DIVIDE(a,b)
    → SELECT
        AGG(CASE WHEN filter_a THEN col_or_1 END)
        / NULLIF(AGG(CASE WHEN filter_b THEN col_or_1 END), 0)
      FROM table

    Bug 2 fix: COUNTROWS(table) has no column arg — previously fell back to
    col = "*" which emits THEN * (invalid Snowflake syntax).
    Fix: col = "1" so COUNTROWS becomes COUNT(CASE WHEN ... THEN 1 END).

    All other VAR bindings (SUM, DISTINCTCOUNT etc.) are unaffected —
    they always have a ColumnRef arg and never reach the else branch.
    """
    emitter = _Emitter(sf_refs, sql_cache)

    # Source table(s)
    all_source_tables = list({r.sf_object for r in sf_refs
                               if r.ref_type == "source" and r.sf_object})
    if not all_source_tables:
        return None

    # Use only one table in FROM — if multiple tables exist, use the primary one.
    # Cartesian joins are always wrong. Multi-table measures need subquery handling.
    tables = all_source_tables[:1] if len(all_source_tables) > 1 else all_source_tables

    # ── Pre-resolve scalar VAR bindings (MAX/MIN) as subqueries ──────────────
    # e.g. VAR latest_month = CALCULATE(MAX(cohort[month_of_measurement]), ALL('DATE'))
    # → (SELECT MAX(MONTH_OF_MEASUREMENT) FROM RISK_COHORT_V4_VIEW)
    # Without this, unresolved VARs emit as /* comment */ breaking CASE WHEN syntax.
    scalar_vars = {}
    for vd in ast.bindings:
        expr = vd.expr
        inner_agg = None
        if isinstance(expr, FunctionCall) and expr.name in ("MAX", "MIN"):
            inner_agg = expr
        elif isinstance(expr, FunctionCall) and expr.name == "CALCULATE":
            if expr.args and isinstance(expr.args[0], FunctionCall):
                if expr.args[0].name in ("MAX", "MIN"):
                    inner_agg = expr.args[0]
        if inner_agg and inner_agg.args and isinstance(inner_agg.args[0], ColumnRef):
            col_ref = inner_agg.args[0]
            sf_obj_s, sf_col_s = _sf_name(col_ref.table, col_ref.column, sf_refs)
            tbl_s = sf_obj_s or col_ref.table.upper()
            col_s = sf_col_s or col_ref.column.upper()
            scalar_vars[vd.name] = (
                f"(SELECT {inner_agg.name.upper()}({col_s}) FROM {tbl_s})"
            )

    # Build emitter with scalar vars so CASE WHEN can reference them
    emitter = _Emitter(sf_refs, sql_cache, var_sql=scalar_vars)

    # ── Build CASE WHEN SQL for each VAR binding ──────────────────────────────
    var_case_sqls = {}
    for vd in ast.bindings:
        expr = vd.expr

        # Skip scalar vars (MAX/MIN) — already pre-resolved above
        if vd.name in scalar_vars:
            continue

        # ── Fix A: plain AGG binding (no CALCULATE wrapper) ──────────────────
        # e.g. VAR a = SUM(risk_core[risk_value]) — no filter, no CASE WHEN
        if isinstance(expr, FunctionCall) and expr.name != "CALCULATE":
            agg_name = FUNC_MAP.get(expr.name.upper(), expr.name.upper())
            if expr.args and isinstance(expr.args[0], ColumnRef):
                col_ref = expr.args[0]
                _, sf_col = _sf_name(col_ref.table, col_ref.column, sf_refs)
                col = sf_col or col_ref.column.upper()
                var_case_sqls[vd.name] = f"{agg_name}({col})"
            else:
                var_case_sqls[vd.name] = emitter.emit(expr)
            continue

        if not (isinstance(expr, FunctionCall) and expr.name == "CALCULATE"):
            return None
        if not expr.args:
            return None

        main_agg = expr.args[0]
        conds    = _collect_filters(expr.args, emitter)

        # ── Resolve aggregation function and column ───────────────────────────
        if isinstance(main_agg, FunctionCall):
            agg_name = FUNC_MAP.get(main_agg.name.upper(), main_agg.name.upper())

            if main_agg.args and isinstance(main_agg.args[0], ColumnRef):
                # Normal case: SUM(col), DISTINCTCOUNT(col), AVG(col) etc.
                # Always has a ColumnRef — use the resolved Snowflake column name.
                col_ref = main_agg.args[0]
                _, sf_col = _sf_name(col_ref.table, col_ref.column, sf_refs)
                col = sf_col or col_ref.column.upper()

            else:
                # ── Bug 2 fix ─────────────────────────────────────────────────
                # COUNTROWS(table) passes a TABLE reference, not a ColumnRef.
                # main_agg.args[0] is a ColumnRef with column="*" (table-only ref),
                # or args is empty — either way there is no metric column.
                #
                # WRONG (previous):  col = "*"
                #   → COUNT(CASE WHEN flag = TRUE THEN * END)  ← invalid Snowflake
                #
                # CORRECT (fix):     col = "1"
                #   → COUNT(CASE WHEN flag = TRUE THEN 1 END)  ← counts matching rows
                #
                # "1" is the standard SQL idiom for conditional row counting.
                # No other aggregation (SUM/AVG/MAX/MIN/DISTINCTCOUNT) reaches
                # this branch because they always operate on a named column.
                col = "1"

        else:
            # Fallback: main_agg is not a FunctionCall (rare/unexpected shape)
            agg_name = "SUM"
            col      = emitter.emit(main_agg)

        # ── Build CASE WHEN expression ────────────────────────────────────────
        if conds:
            where    = " AND ".join(conds)
            case_sql = f"{agg_name}(CASE WHEN {where} THEN {col} END)"
        else:
            # No filter conditions — plain aggregation, no CASE needed
            case_sql = f"{agg_name}({col})"

        var_case_sqls[vd.name] = case_sql

    # ── Build RETURN expression ───────────────────────────────────────────────
    ret = ast.return_expr
    if not isinstance(ret, DivideNode):
        return None

    # Numerator and denominator should be VarRef or ColumnRef("varname", "*")
    def _get_var_sql(node):
        if isinstance(node, VarRef):
            return var_case_sqls.get(node.name)
        if isinstance(node, ColumnRef) and node.column == "*":
            return var_case_sqls.get(node.table)
        return None

    num_sql = _get_var_sql(ret.numerator)
    den_sql = _get_var_sql(ret.denominator)

    if not num_sql or not den_sql:
        return None

    from_clause = ", ".join(tables)

    # EC19: DIVIDE 3-arg → COALESCE, 2-arg → plain NULLIF
    if ret.default_val is not None:
        divide_sql = f"COALESCE({num_sql} / NULLIF({den_sql}, 0), 0)"
    else:
        divide_sql = f"{num_sql} / NULLIF({den_sql}, 0)"

    # Add MAX_MONTH_FLAG for risk tables (latest month only)
    single_table = tables[0] if len(tables) == 1 else None
    if single_table and single_table in MAX_MONTH_TABLES:
        return (
            f"SELECT\n"
            f"    {divide_sql}\n"
            f"FROM {from_clause}\n"
            f"WHERE MAX_MONTH_FLAG = TRUE"
        )

    return (
        f"SELECT\n"
        f"    {divide_sql}\n"
        f"FROM {from_clause}"
    )



def _gen_measure_ratio(
    ast      : Any,
    sf_refs  : list[SFRef],
    sql_cache: dict,
) -> Optional[str]:
    """
    MEASURE_RATIO: [A] / [B]
    → (sql_A) / NULLIF((sql_B), 0)
    Both measures must be in sql_cache.
    """
    emitter = _Emitter(sf_refs, sql_cache)

    if isinstance(ast, BinaryOp) and ast.op == "/":
        left_sql  = emitter.emit(ast.left)
        right_sql = emitter.emit(ast.right)
        return f"SELECT {left_sql} / NULLIF({right_sql}, 0)"

    if isinstance(ast, DivideNode):
        num_sql = emitter.emit(ast.numerator)
        den_sql = emitter.emit(ast.denominator)
        if ast.default_val is not None:
            return f"SELECT COALESCE({num_sql} / NULLIF({den_sql}, 0), 0)"
        return f"SELECT {num_sql} / NULLIF({den_sql}, 0)"

    return None


def _gen_time_intel(
    ast      : Any,
    sf_refs  : list[SFRef],
    sql_cache: dict,
    is_yoy   : bool,
) -> Optional[str]:
    """
    TIME_INTEL_YOY / TIME_INTEL_MOM:
    CALCULATE([Measure], SAMEPERIODLASTYEAR('date'[month_of_date]))
    → SELECT AGG(col) FROM table
      WHERE DATE_COL = DATEADD(year, -1, :selected_month)

    If main expr is MeasureRef → use sql_cache SQL + add date filter.
    """
    emitter = _Emitter(sf_refs, sql_cache)

    # Get source tables from sf_refs to pick correct date column
    source_tables = [r.sf_object for r in sf_refs
                     if r.ref_type == "source" and r.sf_object]

    # Pick date column from DATE_COL_MAP based on the primary source table
    # Priority: use the table that has a date column mapping
    date_col = "MONTH_OF_DATE"   # fallback default
    for tbl in source_tables:
        if tbl in DATE_COL_MAP:
            date_col = DATE_COL_MAP[tbl]
            break

    # Date filter clause
    if is_yoy:
        date_filter = f"{date_col} = DATEADD(year, -1, :selected_month)"
    else:
        date_filter = f"{date_col} = DATEADD(month, -1, :selected_month)"

    # ── VarBlock: YoY/MoM = (current - prior) / prior ──────
    # e.g. VAR py = CALCULATE([#Members], SPILY(...))
    #      RETURN DIVIDE([#Members] - py, py, 0)
    # → Need full (current_sql - prior_sql) / NULLIF(prior_sql, 0)
    if isinstance(ast, VarBlock):
        # Find the VAR binding that has time intel (CALCULATE + SPILY/PREVMONTH)
        prior_measure_name = None
        current_measure_name = None

        for vd in ast.bindings:
            expr = vd.expr
            if isinstance(expr, FunctionCall) and expr.name == "CALCULATE":
                if expr.args and isinstance(expr.args[0], MeasureRef):
                    prior_measure_name = expr.args[0].name

        # Find current measure from return expression
        if isinstance(ast.return_expr, DivideNode):
            ret = ast.return_expr
            # DIVIDE([current] - py, py) → numerator is BinaryOp(-, MeasureRef, VarRef/ColumnRef)
            if isinstance(ret.numerator, BinaryOp) and ret.numerator.op == "-":
                left = ret.numerator.left
                if isinstance(left, MeasureRef):
                    current_measure_name = left.name

        # Module-level _cache_get — case-insensitive
        prior_sql_base   = _cache_get(prior_measure_name, sql_cache)
        current_sql_base = _cache_get(current_measure_name, sql_cache)

        # Both must be in sql_cache
        if (prior_measure_name and current_measure_name
                and prior_sql_base is not None
                and current_sql_base is not None):

            current_base = current_sql_base.strip()
            prior_base   = prior_sql_base.strip()

            # Build prior SQL = base + date filter
            for sf_table, col in DATE_COL_MAP.items():
                if sf_table in prior_base:
                    date_filter = (
                        f"{col} = DATEADD(year, -1, :selected_month)"
                        if is_yoy else
                        f"{col} = DATEADD(month, -1, :selected_month)"
                    )
                    break

            # Build prior period SQL
            import re as _re_prior
            prior_date_table = ""
            for sf_table in DATE_COL_MAP:
                if sf_table in prior_base:
                    prior_date_table = sf_table
                    break
            _prior_nested = (
                prior_base.strip().startswith("(SELECT") or
                prior_base.strip().startswith("SELECT (SELECT") or
                (prior_date_table and prior_base.count(f"FROM {prior_date_table}") > 1)
            )
            # Strip both MAX_MONTH_FLAG and :selected_month from base SQL.
            # _finalize_sql adds :selected_month to cached base measures; if we
            # then append AND DATEADD(...) the WHERE becomes unsatisfiable.
            prior_base_clean = _strip_max_month_flag(_strip_date_filter(prior_base))

            if prior_date_table and _prior_nested:
                _pf  = date_filter
                pat  = rf"(FROM {prior_date_table})(\s*)(\))"
                prior_sql = _re_prior.sub(
                    pat,
                    lambda m: f"{m.group(1)}\nWHERE {_pf}{m.group(2)}{m.group(3)}",
                    prior_base_clean
                )
            elif "WHERE" in prior_base_clean.upper():
                prior_sql = prior_base_clean + f"\n  AND {date_filter}"
            else:
                prior_sql = prior_base_clean + f"\nWHERE {date_filter}"

            # Build current period SQL = base + :selected_month filter
            current_date_filter = None
            current_date_table  = ""
            for sf_table, col in DATE_COL_MAP.items():
                if sf_table in current_base:
                    current_date_filter = f"{col} = :selected_month"
                    current_date_table  = sf_table
                    break

            # Always add explicit date filter for current period
            import re as _re_cur
            def _is_nested(sql):
                # Nested ratio: has multiple FROM clauses (subqueries inside expression)
                stripped = sql.strip()
                return (stripped.startswith("(SELECT") or
                        stripped.startswith("SELECT (SELECT") or
                        stripped.count(f"FROM {current_date_table}") > 1)

            current_base_clean = _strip_max_month_flag(_strip_date_filter(current_base))

            if current_date_filter:
                if current_date_table and _is_nested(current_base_clean):
                    # Push WHERE inside each FROM subquery
                    _cdf = current_date_filter
                    pat  = rf"(FROM {current_date_table})(\s*)(\))"
                    current_sql = _re_cur.sub(
                        pat,
                        lambda m: f"{m.group(1)}\nWHERE {_cdf}{m.group(2)}{m.group(3)}",
                        current_base_clean
                    )
                elif "WHERE" in current_base_clean.upper():
                    current_sql = current_base_clean + f"\n  AND {current_date_filter}"
                else:
                    current_sql = current_base_clean + f"\nWHERE {current_date_filter}"
            else:
                current_sql = current_base

            # (current - prior) / NULLIF(prior, 0)
            use_coalesce = (isinstance(ast.return_expr, DivideNode)
                            and ast.return_expr.default_val is not None)
            core = (f"({current_sql})\n"
                    f"- ({prior_sql})\n"
                    f") / NULLIF((\n{prior_sql}\n), 0)")

            if use_coalesce:
                return f"SELECT COALESCE((\n{core},\n0)"
            else:
                return f"SELECT (\n{core}"

        # Fallback: return prior period SQL only
        for vd in ast.bindings:
            expr = vd.expr
            if isinstance(expr, FunctionCall) and expr.name == "CALCULATE":
                if expr.args and isinstance(expr.args[0], MeasureRef):
                    mref_name = expr.args[0].name
                    base_sql_val = _cache_get(mref_name, sql_cache)
                    if base_sql_val is not None:
                        base_sql = _strip_max_month_flag(
                            _strip_date_filter(base_sql_val.strip())
                        )
                        for sf_table, col in DATE_COL_MAP.items():
                            if sf_table in base_sql:
                                date_filter = (
                                    f"{col} = DATEADD(year, -1, :selected_month)"
                                    if is_yoy else
                                    f"{col} = DATEADD(month, -1, :selected_month)"
                                )
                                break
                        if "WHERE" in base_sql.upper():
                            return base_sql + f"\n  AND {date_filter}"
                        else:
                            return base_sql + f"\nWHERE {date_filter}"
        return None

    # ── CALCULATE([Measure], SPILY/PREVMONTH) → prior period SQL ─
    main_expr = None
    if isinstance(ast, FunctionCall) and ast.name == "CALCULATE":
        main_expr = ast.args[0] if ast.args else None

    if main_expr is None:
        return None

    # If main expr is MeasureRef → use its cached SQL as base
    # Parser normalizes GROUP spacing — just need case-insensitive lookup
    _mref_cached = _cache_get(main_expr.name, sql_cache) if isinstance(main_expr, MeasureRef) else None
    if isinstance(main_expr, MeasureRef) and _mref_cached is not None:
        base_sql = _mref_cached.strip()

        # Pick date column from the table used in base_sql (not from sf_refs)
        date_col   = "MONTH_OF_DATE"  # fallback
        date_table = ""
        for sf_table, col in DATE_COL_MAP.items():
            if sf_table in base_sql:
                date_col   = col
                date_table = sf_table
                date_filter = (
                    f"{col} = DATEADD(year, -1, :selected_month)"
                    if is_yoy else
                    f"{col} = DATEADD(month, -1, :selected_month)"
                )
                break

        # Fix 2: If base_sql is a MEASURE_RATIO (nested subqueries),
        # WHERE must go INSIDE each inner subquery that has a FROM clause.
        # The outer expression is scalar arithmetic — it has no FROM clause.
        #
        # base_sql pattern:
        #   SELECT (SELECT SUM(A) FROM T) / NULLIF((SELECT SUM(B) FROM T), 0)
        #
        # We must inject WHERE inside each "(... FROM T)" subquery.
        import re as _re_time

        _is_nested = (
            "SELECT (SELECT" in base_sql or
            base_sql.strip().startswith("(SELECT")
        )

        if _is_nested:
            # Find all tables referenced in the subqueries
            _tables_in_sql = _re_time.findall(r"FROM\s+([A-Z_0-9]+)", base_sql)
            _inner_table   = _tables_in_sql[0] if _tables_in_sql else None

            if _inner_table:
                # Get date column for the inner table
                _inner_date_col = DATE_COL_MAP.get(_inner_table)
                if _inner_date_col:
                    _inner_filter = date_filter.replace(
                        next(iter(DATE_COL_MAP.get(date_table, date_filter).split("=")[0].strip().split()),
                             ""),
                        _inner_date_col
                    ) if date_table != _inner_table else date_filter

                    # Inject WHERE inside each "FROM TABLE)" occurrence
                    def _inject(m):
                        table_name = m.group(1)
                        col        = DATE_COL_MAP.get(table_name, _inner_date_col)
                        filt       = date_filter.replace(
                            list(DATE_COL_MAP.keys())[0] if date_table else col, col
                        ) if date_table else f"{col} = {date_filter.split('= ', 1)[-1]}"
                        return f"FROM {table_name}\nWHERE {date_filter})"

                    injected = _re_time.sub(
                        r"FROM ([A-Z_0-9]+)\s*\)",
                        lambda m: f"FROM {m.group(1)}\nWHERE {date_filter})",
                        base_sql
                    )
                    return injected

        base_sql = _strip_max_month_flag(_strip_date_filter(base_sql))
        if "WHERE" in base_sql.upper():
            return base_sql + f"\n  AND {date_filter}"
        else:
            return base_sql + f"\nWHERE {date_filter}"

    # Otherwise emit the aggregation directly
    agg_sql = emitter.emit(main_expr)
    # Fix 5: exclude DATE_VIEW from FROM clause — it has no metric data
    # DATE_VIEW in sf_refs comes from SAMEPERIODLASTYEAR/PREVIOUSMONTH arg
    # It should NOT appear in FROM — it only provides the date column name
    tables  = list({r.sf_object for r in sf_refs
                    if r.ref_type == "source" and r.sf_object
                    and r.sf_object != "DATE_VIEW"})
    if not tables:
        return None

    from_clause = ", ".join(tables)
    return (f"SELECT {agg_sql}\n"
            f"FROM {from_clause}\n"
            f"WHERE {date_filter}")


def _gen_context_remover(
    ast      : Any,
    sf_refs  : list[SFRef],
    sql_cache: dict,
) -> Optional[str]:
    """
    CONTEXT_REMOVER: CALCULATE(AGG(col), ALL('DATE'))
    EC4: NO date filter — ALL() removes it.
    → SELECT AGG(col) FROM table  (no WHERE)
    """
    emitter = _Emitter(sf_refs, sql_cache)

    if not (isinstance(ast, FunctionCall) and ast.name == "CALCULATE"):
        return None

    main_expr = ast.args[0] if ast.args else None
    if main_expr is None:
        return None

    agg_sql = emitter.emit(main_expr)
    tables  = list({r.sf_object for r in sf_refs
                    if r.ref_type == "source" and r.sf_object})
    if not tables:
        return None

    from_clause = ", ".join(tables)
    return f"SELECT {agg_sql}\nFROM {from_clause}"
    # Deliberately NO WHERE — EC4: ALL() means no date filter


def _gen_complex_var_divide(
    ast      : VarBlock,
    sf_refs  : list[SFRef],
    sql_cache: dict,
) -> Optional[str]:
    """
    COMPLEX_VAR_DIVIDE: VAR ... RETURN DIVIDE/expr
    Uses WITH blocks for each VAR binding that is a full aggregation.
    For VarRef nodes that are simple column aggs, inline them.
    """
    emitter = _Emitter(sf_refs, sql_cache)

    # Build SQL for each VAR binding
    var_sqls = {}
    for vd in ast.bindings:
        expr = vd.expr
        if isinstance(expr, FunctionCall) and expr.name == "CALCULATE":
            # CALCULATE([Measure], time_intel) → time intel handled separately
            var_sqls[vd.name] = emitter.emit(expr)
        else:
            var_sqls[vd.name] = emitter.emit(expr)

    # If any VAR binding resolved to a prior-period SQL (contains DATEADD),
    # strip MAX_MONTH_FLAG from current-period measures in cache so the
    # current subquery doesn't carry MAX_MONTH_FLAG = TRUE in a ratio.
    is_time_intel_ratio = any(
        "DATEADD" in (s or "").upper()
        for s in var_sqls.values()
    )
    effective_cache = sql_cache
    if is_time_intel_ratio:
        effective_cache = {
            k: (_strip_max_month_flag(v) if v and "DATEADD" not in v.upper() else v)
            for k, v in sql_cache.items()
        }

    # Emitter with var_sql filled in
    full_emitter = _Emitter(sf_refs, effective_cache, var_sql=var_sqls)
    return_sql   = full_emitter.emit(ast.return_expr)

    tables = list({r.sf_object for r in sf_refs
                   if r.ref_type == "source" and r.sf_object})
    # MeasureRef-only → no direct sf_refs, subqueries carry their own FROM
    if not tables:
        return f"SELECT {return_sql}"

    # Single table — original logic
    if len(tables) == 1:
        return f"SELECT {return_sql}\nFROM {tables[0]}"

    # Multi-table: build each VAR binding as an independent subquery so we
    # avoid a cartesian join. Each binding's subquery includes its own date filter.
    # The return_expr then references var names whose values are scalar subqueries.
    var_sub_sqls = {}
    for vd in ast.bindings:
        # Collect sf_refs used by this binding's expression
        binding_bi_tables = set()
        def _walk_bi(node):
            if isinstance(node, ColumnRef):
                binding_bi_tables.add(node.table)
            for attr in ("args", "bindings"):
                for child in (getattr(node, attr, None) or []):
                    _walk_bi(child)
            for attr in ("numerator", "denominator", "left", "right",
                         "expr", "return_expr", "base_expr"):
                child = getattr(node, attr, None)
                if child:
                    _walk_bi(child)
        _walk_bi(vd.expr)

        binding_sf_refs = [r for r in sf_refs if r.bi_table in binding_bi_tables]
        if not binding_sf_refs:
            binding_sf_refs = sf_refs  # fallback

        binding_tables = list({r.sf_object for r in binding_sf_refs
                               if r.ref_type == "source" and r.sf_object})

        if len(binding_tables) == 1:
            tbl = binding_tables[0]
            agg_sql = emitter.emit(vd.expr)
            date_col = DATE_COL_MAP.get(tbl)
            where = f"\n  WHERE {date_col} = :selected_month" if date_col else ""
            var_sub_sqls[vd.name] = f"(\n  SELECT {agg_sql}\n  FROM {tbl}{where}\n)"
        else:
            # Can't split cleanly — fall back to inline emit
            var_sub_sqls[vd.name] = var_sqls[vd.name]

    # Rebuild emitter with subquery-wrapped var sqls and re-emit return expr
    sub_emitter = _Emitter(sf_refs, effective_cache, var_sql=var_sub_sqls)
    return_sql  = sub_emitter.emit(ast.return_expr)
    return f"SELECT {return_sql}"


def _gen_static_cte(table_name: str) -> str:
    """Generate a static table CTE placeholder."""
    return STATIC_CTE_TEMPLATE.format(table=table_name)


# ══════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ══════════════════════════════════════════════════════════════

# Measure name patterns that should NOT have MAX_MONTH_FLAG
# These measures show data across all months (trend charts)
NO_MAX_MONTH_PATTERNS = {"trend", "all months", "historic"}

def _is_trend_measure(name: str) -> bool:
    """Return True if this measure should NOT have MAX_MONTH_FLAG."""
    name_lower = name.lower()
    return any(p in name_lower for p in NO_MAX_MONTH_PATTERNS)


def generate(
    annotated : AnnotatedAST,
    classify  : ClassifyResult,
    sql_cache : dict[str, str],
) -> GenerateResult:
    """
    Generate Snowflake SQL for one measure.

    Args:
        annotated  : AnnotatedAST from semantic_resolver
        classify   : ClassifyResult from classifier
        sql_cache  : {measure_name: sql} for already-processed dependencies

    Returns:
        GenerateResult — always. Never raises.
    """
    name     = annotated.measure_name
    ast      = annotated.ast
    sf_refs  = annotated.sf_refs
    pattern  = classify.dax_pattern

    # Build static CTEs if needed
    cte_blocks = [_gen_static_cte(t) for t in annotated.static_tables]

    def _fail(reason: str) -> GenerateResult:
        return GenerateResult(
            measure_name = name,
            sql          = None,
            needs_llm    = True,
            llm_role     = "BUILDER",
            cte_blocks   = cte_blocks,
            error        = reason,
            pattern      = pattern,
        )

    def _ok(sql: str, finalize: bool = True) -> GenerateResult:
        if finalize:
            sql = _finalize_sql(sql, sf_refs)
        if cte_blocks:
            with_block = "WITH\n" + ",\n\n".join(cte_blocks) + "\n\n"
            sql = with_block + sql
        return GenerateResult(
            measure_name = name,
            sql          = sql,
            needs_llm    = False,
            llm_role     = classify.llm_role,
            cte_blocks   = cte_blocks,
            error        = None,
            pattern      = pattern,
        )

    # Temporarily exclude tables from MAX_MONTH_TABLES for trend measures
    _saved_max = set()
    if _is_trend_measure(name):
        _saved_max = set(MAX_MONTH_TABLES)
        MAX_MONTH_TABLES.clear()

    try:
        # ── COMPLEX → LLM BUILDER ────────────────────────────
        if pattern == "COMPLEX":
            return _fail("Pattern COMPLEX — LLM will generate SQL directly.")

        # ── SIMPLE_AGG ───────────────────────────────────────
        if pattern == "SIMPLE_AGG":
            sql = _gen_simple_agg(ast, sf_refs, sql_cache)
            return _ok(sql) if sql else _fail("SIMPLE_AGG: could not emit SQL")

        # ── SIMPLE_DIVIDE ────────────────────────────────────
        if pattern == "SIMPLE_DIVIDE":
            if not isinstance(ast, DivideNode):
                return _fail("SIMPLE_DIVIDE: root is not DivideNode")
            sql = _gen_simple_divide(ast, sf_refs, sql_cache)
            return _ok(sql) if sql else _fail("SIMPLE_DIVIDE: could not emit SQL")

        # ── ARITHMETIC ───────────────────────────────────────
        if pattern == "ARITHMETIC":
            sql = _gen_arithmetic(ast, sf_refs, sql_cache)
            return _ok(sql) if sql else _fail("ARITHMETIC: could not emit SQL")

        # ── FILTERED_AGG ─────────────────────────────────────
        if pattern == "FILTERED_AGG":
            sql = _gen_filtered_agg(ast, sf_refs, sql_cache)
            return _ok(sql) if sql else _fail("FILTERED_AGG: could not emit SQL")

        # ── VAR_FILTERED_DIVIDE ──────────────────────────────
        if pattern == "VAR_FILTERED_DIVIDE":
            if not isinstance(ast, VarBlock):
                return _fail("VAR_FILTERED_DIVIDE: root is not VarBlock")
            sql = _gen_var_filtered_divide(ast, sf_refs, sql_cache)
            return _ok(sql) if sql else _fail("VAR_FILTERED_DIVIDE: could not emit SQL")

        # ── MEASURE_RATIO ────────────────────────────────────
        # No outer FROM — subquery deps already carry their own date filters
        if pattern == "MEASURE_RATIO":
            sql = _gen_measure_ratio(ast, sf_refs, sql_cache)
            return _ok(sql, finalize=False) if sql else _fail("MEASURE_RATIO: could not emit SQL")

        # ── TIME_INTEL_YOY ───────────────────────────────────
        # Already emits DATEADD(year, -1, :selected_month) — skip _finalize_sql
        if pattern == "TIME_INTEL_YOY":
            sql = _gen_time_intel(ast, sf_refs, sql_cache, is_yoy=True)
            return _ok(sql, finalize=False) if sql else _fail("TIME_INTEL_YOY: could not emit SQL")

        # ── TIME_INTEL_MOM ───────────────────────────────────
        # Already emits DATEADD(month, -1, :selected_month) — skip _finalize_sql
        if pattern == "TIME_INTEL_MOM":
            sql = _gen_time_intel(ast, sf_refs, sql_cache, is_yoy=False)
            return _ok(sql, finalize=False) if sql else _fail("TIME_INTEL_MOM: could not emit SQL")

        # ── CONTEXT_REMOVER ──────────────────────────────────
        # ALL('DATE') explicitly removes date context — no filter should be added
        if pattern == "CONTEXT_REMOVER":
            sql = _gen_context_remover(ast, sf_refs, sql_cache)
            return _ok(sql, finalize=False) if sql else _fail("CONTEXT_REMOVER: could not emit SQL")

        # ── COMPLEX_VAR_DIVIDE (MeasureRef deps — YoY/MoM type) ─
        # Component SQLs in sql_cache already carry date filters
        if pattern == "COMPLEX_VAR_DIVIDE":
            if not isinstance(ast, VarBlock):
                return _fail("COMPLEX_VAR_DIVIDE: root is not VarBlock")
            sql = _gen_complex_var_divide(ast, sf_refs, sql_cache)
            return _ok(sql, finalize=False) if sql else _fail("COMPLEX_VAR_DIVIDE: could not emit SQL")

        # ── VAR_AGG_DIVIDE (column aggs only — P4 Utilization) ──
        if pattern == "VAR_AGG_DIVIDE":
            if not isinstance(ast, VarBlock):
                return _fail("VAR_AGG_DIVIDE: root is not VarBlock")
            sql = _gen_complex_var_divide(ast, sf_refs, sql_cache)
            return _ok(sql, finalize=False) if sql else _fail("VAR_AGG_DIVIDE: could not emit SQL")

        # ── STATIC_FILTERED ──────────────────────────────────
        if pattern == "STATIC_FILTERED":
            # Use the inner pattern's generator + prepend WITH
            # (classifier already built cte_blocks)
            # Try FILTERED_AGG first, then SIMPLE_AGG
            sql = _gen_filtered_agg(ast, sf_refs, sql_cache)
            if not sql:
                sql = _gen_simple_agg(ast, sf_refs, sql_cache)
            return _ok(sql) if sql else _fail("STATIC_FILTERED: could not emit SQL")

        return _fail(f"Unknown pattern: {pattern}")

    except Exception as exc:
        return _fail(f"Generator internal error: {exc}")
    finally:
        # Restore MAX_MONTH_TABLES if it was cleared for trend measure
        if _saved_max:
            MAX_MONTH_TABLES.update(_saved_max)


def generate_all(
    annotated_map : dict[str, AnnotatedAST],
    classify_map  : dict[str, ClassifyResult],
    dep_order     : list[str],
) -> dict[str, GenerateResult]:
    """
    Generate SQL for all measures in topological order.
    Each measure's SQL is added to sql_cache before processing dependents.

    Args:
        annotated_map : {name: AnnotatedAST}
        classify_map  : {name: ClassifyResult}
        dep_order     : processing order from dep_resolver

    Returns:
        {name: GenerateResult}
    """
    sql_cache = {}
    results   = {}

    for name in dep_order:
        if name not in annotated_map:
            continue
        ann = annotated_map[name]
        clf = classify_map[name]

        result = generate(ann, clf, sql_cache)
        results[name] = result

        # Add to cache for downstream dependents
        if result.sql:
            sql_cache[name] = result.sql
            # Also store normalized key for GROUP variants
            # "Overall gaps closed (GROUP)" → also accessible as "Overall gaps closed ( GROUP )"
            # and vice versa
            normalized = name.replace("(GROUP)", "( GROUP )").replace("(group)", "( group )")
            if normalized != name:
                sql_cache[normalized] = result.sql
            denormalized = name.replace("( GROUP )", "(GROUP)").replace("( group )", "(GROUP)")
            if denormalized != name:
                sql_cache[denormalized] = result.sql

    return results


# ══════════════════════════════════════════════════════════════
# SELF-TEST  —  run: python sql_generator.py
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from parser import parse
    from dep_resolver import resolve as dep_resolve
    from semantic_resolver import (
        build_snowflake_lookup, build_rel_graph, resolve_one,
    )
    from classifier import classify as do_classify

    all_pass = True

    def check(label: str, condition: bool):
        global all_pass
        status = "✅" if condition else "❌"
        print(f"  {status}  {label}")
        if not condition:
            all_pass = False

    SF_MAP = {
        "date"       : {"snowflake_object": "DATE_VIEW",          "type": "source"},
        "attribution": {"snowflake_object": "PCP_VISITS_V4_VIEW", "type": "source"},
        "risk_core"  : {"snowflake_object": {"snowflake":"RISK_CORE_V4_VIEW"},
                        "type": "source"},
        "cohort"     : {"snowflake_object": {"snowflake":"RISK_COHORT_V4_VIEW"},
                        "type": "source"},
        "ALL_DAX"    : {"type": "measure_container", "snowflake_object": None},
        "static_tables": {"static_risk_bucket": {}},
    }
    RELS = []

    def pipeline(name: str, dax: str, extra: dict = None,
                 cache: dict = None) -> GenerateResult:
        """Run full pipeline for one measure."""
        measures = {name: parse(name, dax)}
        if extra:
            measures.update(extra)
        dr  = dep_resolve(measures)
        sf  = build_snowflake_lookup(SF_MAP)
        rg  = build_rel_graph(RELS)
        ann = resolve_one(name, measures[name].ast, dr, sf, rg)
        clf = do_classify(ann)
        return generate(ann, clf, cache or {})

    print("=== sql_generator.py self-test ===\n")

    # ── P1: SIMPLE_AGG — SUM ─────────────────────────────────
    print("P1 — SIMPLE_AGG SUM:")
    r = pipeline("#Members", "SUM(attribution[member_count])")
    check("ok (no needs_llm)",          not r.needs_llm)
    check("pattern=SIMPLE_AGG",         r.pattern == "SIMPLE_AGG")
    check("SELECT SUM present",         r.sql and "SELECT SUM" in r.sql)
    check("PCP_VISITS_V4_VIEW in SQL",  r.sql and "PCP_VISITS_V4_VIEW" in r.sql)
    check("MEMBER_COUNT uppercase",     r.sql and "MEMBER_COUNT" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── P2: COUNTROWS ────────────────────────────────────────
    print("\nP2 — COUNTROWS:")
    r = pipeline("Targeted gaps", "COUNTROWS(cohort)")
    check("ok",                         not r.needs_llm)
    check("COUNT(*) present",           r.sql and "COUNT(*)" in r.sql)
    check("RISK_COHORT_V4_VIEW",        r.sql and "RISK_COHORT_V4_VIEW" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── P13: MAX ─────────────────────────────────────────────
    print("\nP13 — MAX:")
    r = pipeline("Latest date", "MAX(risk_core[month_of_measurement])")
    check("ok",                         not r.needs_llm)
    check("SELECT MAX",                 r.sql and "SELECT MAX" in r.sql)
    check("RISK_CORE_V4_VIEW",          r.sql and "RISK_CORE_V4_VIEW" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── EC16: CALCULATE no filters ───────────────────────────
    print("\nEC16 — CALCULATE no filters:")
    r = pipeline("IP Discharges", "CALCULATE(COUNT(risk_core[risk_value]))")
    check("ok",                         not r.needs_llm)
    check("COUNT present",              r.sql and "COUNT" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── P3: SIMPLE_DIVIDE ────────────────────────────────────
    print("\nP3 — SIMPLE_DIVIDE:")
    r = pipeline("PMPM",
        "DIVIDE(SUM(attribution[ytd_visit_amount]), SUM(attribution[ytd_member_count]))")
    check("ok",                         not r.needs_llm)
    check("NULLIF present",             r.sql and "NULLIF" in r.sql)
    check("PCP_VISITS_V4_VIEW",         r.sql and "PCP_VISITS_V4_VIEW" in r.sql)
    check("YTD_VISIT_AMOUNT",           r.sql and "YTD_VISIT_AMOUNT" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── EC19: DIVIDE 3-arg → COALESCE ────────────────────────
    print("\nEC19 — DIVIDE 3-arg → COALESCE:")
    r = pipeline("PMPM safe",
        "DIVIDE(SUM(attribution[ytd_visit_amount]), SUM(attribution[ytd_member_count]), 0)")
    check("ok",                         not r.needs_llm)
    check("COALESCE present",           r.sql and "COALESCE" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── P22: ARITHMETIC ──────────────────────────────────────
    print("\nP22 — ARITHMETIC:")
    r = pipeline("Filter",
        "ABS(SUM(attribution[ytd_visit_amount])) + SUM(attribution[ytd_member_count])")
    check("ok",                         not r.needs_llm)
    check("ABS present",                r.sql and "ABS" in r.sql)
    check("+ present",                  r.sql and "+" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── P5: FILTERED_AGG ─────────────────────────────────────
    print("\nP5 — FILTERED_AGG KEEPFILTERS:")
    dax5 = 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))'
    r = pipeline("Documented risk", dax5)
    check("ok",                         not r.needs_llm)
    check("WHERE present",              r.sql and "WHERE" in r.sql)
    check("RISK_DOCUMENTATION_FLAG",    r.sql and "RISK_DOCUMENTATION_FLAG" in r.sql)
    check("'Documented' quoted",        r.sql and "'Documented'" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── EC3: <> → != ─────────────────────────────────────────
    print("\nEC3 — <> not-equal:")
    dax3 = 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[flag] <> "Documented"))'
    r = pipeline("Not Documented", dax3)
    check("ok",                         not r.needs_llm)
    check("!= present",                 r.sql and "!=" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── EC8: TRUE → SQL TRUE ─────────────────────────────────
    print("\nEC8 — TRUE literal:")
    dax8 = "CALCULATE(SUM(risk_core[patient_count]), KEEPFILTERS(risk_core[max_month_flag] = TRUE()))"
    r = pipeline("current month", dax8)
    check("ok",                         not r.needs_llm)
    check("TRUE in WHERE",              r.sql and "TRUE" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── EC2: IN {set} ─────────────────────────────────────────
    print("\nEC2 — IN set:")
    dax2 = 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[flag] IN {"Undocumented","Suspected"}))'
    r = pipeline("flagged risk", dax2)
    check("ok",                         not r.needs_llm)
    check("IN present",                 r.sql and " IN " in r.sql)
    check("Undocumented in SQL",        r.sql and "'Undocumented'" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── P6: VAR_FILTERED_DIVIDE ──────────────────────────────
    print("\nP6 — VAR_FILTERED_DIVIDE:")
    dax6 = (
        'VAR a = CALCULATE(SUM(risk_core[risk_value]),\n'
        '  KEEPFILTERS(risk_core[risk_documentation_flag] IN {"Undocumented","Suspected"}))\n'
        'VAR b = CALCULATE(SUM(risk_core[patient_count]),\n'
        '  KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))\n'
        'RETURN DIVIDE(a, b)'
    )
    r = pipeline("Gap to potential risk", dax6)
    check("ok",                         not r.needs_llm)
    check("CASE WHEN present",          r.sql and "CASE WHEN" in r.sql)
    check("NULLIF present",             r.sql and "NULLIF" in r.sql)
    check("RISK_CORE_V4_VIEW",          r.sql and "RISK_CORE_V4_VIEW" in r.sql)
    print(f"  SQL:\n{r.sql}")

    # ── P10: MEASURE_RATIO ───────────────────────────────────
    print("\nP10 — MEASURE_RATIO:")
    cache10 = {
        "Members with open coding gaps":
            "SELECT SUM(MEMBER_WITH_OPEN_CODING_GAP_COUNT)\nFROM PCP_VISITS_V4_VIEW",
        "#Members":
            "SELECT SUM(MEMBER_COUNT)\nFROM PCP_VISITS_V4_VIEW",
    }
    extra10 = {
        "Members with open coding gaps": parse("Members with open coding gaps",
            "SUM(attribution[member_with_open_coding_gap_count])"),
        "#Members": parse("#Members", "SUM(attribution[member_count])"),
    }
    r = pipeline("% members", "[Members with open coding gaps] / [#Members]",
                 extra=extra10, cache=cache10)
    check("ok",                         not r.needs_llm)
    check("NULLIF present",             r.sql and "NULLIF" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── P14: CONTEXT_REMOVER (no WHERE) ──────────────────────
    print("\nP14 — CONTEXT_REMOVER (EC4 no date filter):")
    r = pipeline("Latest month", "CALCULATE(MAX(cohort[month_of_measurement]), ALL('DATE'))")
    check("ok",                         not r.needs_llm)
    check("no WHERE clause",            r.sql and "WHERE" not in r.sql)
    check("MAX present",                r.sql and "MAX" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── P11: TIME_INTEL_YOY ──────────────────────────────────
    print("\nP11 — TIME_INTEL_YOY:")
    cache11 = {"#Members": "SELECT SUM(MEMBER_COUNT)\nFROM PCP_VISITS_V4_VIEW"}
    extra11 = {"#Members": parse("#Members", "SUM(attribution[member_count])")}
    r = pipeline("#Members PY",
        "CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))",
        extra=extra11, cache=cache11)
    check("ok",                         not r.needs_llm)
    check("DATEADD year -1",            r.sql and "DATEADD(year, -1" in r.sql)
    check(":selected_month param",      r.sql and ":selected_month" in r.sql)
    print(f"  SQL: {r.sql}")

    # ── Static CTE ───────────────────────────────────────────
    print("\nSTATIC CTE:")
    cte = _gen_static_cte("static_risk_bucket")
    check("CTE has table name",         "static_risk_bucket" in cte)
    check("CTE has TODO comment",       "TODO" in cte)
    check("CTE has AS (",               "AS (" in cte)

    # ── GenerateResult fields ─────────────────────────────────
    print("\nGenerateResult fields:")
    r = pipeline("#Members", "SUM(attribution[member_count])")
    check("needs_llm=False",            r.needs_llm is False)
    check("error=None",                 r.error is None)
    check("llm_role=DEFINER",           r.llm_role == "DEFINER")
    check("sql is str",                 isinstance(r.sql, str))
    check("cte_blocks is list",         isinstance(r.cte_blocks, list))

    # ── Summary ─────────────────────────────────────────────
    print()
    if all_pass:
        print("✅  All sql_generator.py tests passed.")
        print("    Next step: pipeline.py (orchestrator)")
    else:
        print("❌  Some tests failed — fix before moving to pipeline.py")