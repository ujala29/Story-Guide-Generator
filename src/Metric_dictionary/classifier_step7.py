"""
classifier.py
─────────────
Stage 2 — Step 5

PURPOSE:
    Inspect an AnnotatedAST and assign:
      - dax_pattern  : which SQL pattern this measure maps to
      - sql_applicable: True → sql_generator will attempt SQL
                        False → llm_fallback (definitions only)
      - llm_role     : DEFINER | BUILDER | None

INPUT:
    AnnotatedAST (from semantic_resolver.py)

OUTPUT:
    ClassifyResult dataclass

PATTERN LABELS (priority order — first match wins):

    OUT-OF-SCOPE (sql_applicable=False):
        INFO_TEXT          → hardcoded string literal
        DISPLAY            → UNICHAR / color SWITCH / FORMAT+SWITCH
        UNSUPPORTED        → SELECTEDVALUE, RANDBETWEEN, row iterators

    IN-SCOPE (sql_applicable=True):
        SIMPLE_AGG         → SUM / COUNT / COUNTROWS / MAX / MIN / AVERAGE / DISTINCTCOUNT
        SIMPLE_DIVIDE      → DIVIDE(SUM, SUM) — leaf, no VAR
        ARITHMETIC         → ABS(SUM) + SUM, or similar arithmetic on aggregations
        FILTERED_AGG       → CALCULATE + KEEPFILTERS (single or multi filter)
        VAR_FILTERED_DIVIDE→ VAR + CALCULATE + DIVIDE (Gap to potential risk pattern)
        TIME_INTEL_YOY     → SAMEPERIODLASTYEAR
        TIME_INTEL_MOM     → PREVIOUSMONTH
        MEASURE_RATIO      → [A] / [B] direct measure division
        COMPLEX_VAR_DIVIDE → VAR + DIVIDE on measure refs (YoY/MoM computation)
        CONTEXT_REMOVER    → CALCULATE + ALL()
        STATIC_FILTERED    → references static_ tables
        COMPLEX            → everything else compiler handles (needs_llm=BUILDER)

REUSE FROM step3_classifier.py:
    Pattern names         → direct reuse (renamed to UPPER_SNAKE)
    Priority order        → same logic
    CHANGE: string checks → AST node type checks

WHY AST-BASED:
    step3_classifier.py used string scanning:
        'KEEPFILTERS' in dax_upper
    This file uses AST walking:
        _has_function(ast, 'KEEPFILTERS')
    AST checks are exact — no false positives from strings inside comments
    or column names that happen to contain keywords.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional

from ast_nodes_step0 import (
    ColumnRef, MeasureRef, VarRef, StringLiteral, NumberLiteral,
    BoolLiteral, FunctionCall, DivideNode, BinaryOp, InSetExpr,
    CompoundAnd, InlineFilter, ScalarMultiplier, VarBlock,
)
from semantic_resolver_step6 import AnnotatedAST


# ══════════════════════════════════════════════════════════════
# RESULT
# ══════════════════════════════════════════════════════════════

@dataclass
class ClassifyResult:
    """
    Output of classify().

    Fields:
        measure_name    : display name
        dax_pattern     : pattern label string (see module docstring)
        sql_applicable  : True → compiler attempts SQL generation
                          False → LLM handles (definitions only or full SQL)
        llm_role        : None | "DEFINER" | "BUILDER"
                          DEFINER → SQL exists, LLM writes definition only
                          BUILDER → LLM must generate SQL (compiler gave up)
        note            : human-readable explanation of classification
        has_static      : True if measure references static_ tables
        has_time_intel  : True if measure uses SAMEPERIODLASTYEAR / PREVIOUSMONTH
        has_all         : True if measure uses ALL() (EC4 — no date filter)
    """
    measure_name   : str
    dax_pattern    : str
    sql_applicable : bool
    llm_role       : Optional[str]
    note           : str
    has_static     : bool = False
    has_time_intel : bool = False
    has_all        : bool = False


# ══════════════════════════════════════════════════════════════
# AST INSPECTION HELPERS
# ══════════════════════════════════════════════════════════════

def _has_function(ast: Any, *names: str) -> bool:
    """
    Return True if any FunctionCall with name in `names` exists in the AST.
    Names are compared UPPERCASE.
    """
    names_upper = {n.upper() for n in names}

    def _walk(node):
        if node is None:
            return False
        if isinstance(node, FunctionCall):
            if node.name.upper() in names_upper:
                return True
            return any(_walk(a) for a in node.args)
        if isinstance(node, VarBlock):
            return (any(_walk(vd.expr) for vd in node.bindings)
                    or _walk(node.return_expr))
        if isinstance(node, DivideNode):
            return _walk(node.numerator) or _walk(node.denominator)
        if isinstance(node, BinaryOp):
            return _walk(node.left) or _walk(node.right)
        if isinstance(node, InlineFilter):
            return _walk(node.expr)
        if isinstance(node, InSetExpr):
            return False
        if isinstance(node, CompoundAnd):
            return _walk(node.left) or _walk(node.right)
        if isinstance(node, ScalarMultiplier):
            return _walk(node.base_expr)
        return False

    return _walk(ast)


def _root_is(ast: Any, *types) -> bool:
    """Return True if the root AST node is one of the given types."""
    return isinstance(ast, tuple(types))


def _root_func(ast: Any) -> Optional[str]:
    """Return root FunctionCall name (uppercase), or None."""
    if isinstance(ast, FunctionCall):
        return ast.name.upper()
    return None


def _is_simple_agg(ast: Any) -> bool:
    """
    True if root is a plain aggregation function.
    Also handles CALCULATE with no filters wrapping a simple agg (EC16).
    Covers: SUM, COUNT, COUNTROWS, MAX, MIN, AVERAGE, DISTINCTCOUNT, ABS
    """
    SIMPLE_FUNS = {
        "SUM", "COUNT", "COUNTROWS", "MAX", "MIN",
        "AVERAGE", "DISTINCTCOUNT", "ABS",
    }
    if _root_func(ast) in SIMPLE_FUNS:
        return True
    # EC16: CALCULATE(agg) with no filters — treat as plain agg
    if (_root_func(ast) == "CALCULATE"
            and isinstance(ast, FunctionCall)
            and len(ast.args) == 1
            and _root_func(ast.args[0]) in SIMPLE_FUNS):
        return True
    return False


def _is_simple_divide(ast: Any) -> bool:
    """
    True if root is DivideNode where BOTH numerator and denominator
    are simple aggregations (no VAR, no MeasureRef, no CALCULATE).
    Pattern P3.
    """
    if not isinstance(ast, DivideNode):
        return False
    # Both sides must be simple function calls (SUM, COUNT, etc.)
    def _is_agg(node):
        if isinstance(node, FunctionCall):
            return node.name.upper() in {
                "SUM", "COUNT", "COUNTROWS", "MAX", "MIN", "AVERAGE", "DISTINCTCOUNT"
            }
        return False
    return _is_agg(ast.numerator) and _is_agg(ast.denominator)


def _is_arithmetic(ast: Any) -> bool:
    """
    True if root is BinaryOp (+/-) where sides are aggregations or ABS(agg).
    Pattern P22: ABS(SUM(...)) + SUM(...)
    """
    if not isinstance(ast, BinaryOp):
        return False
    if ast.op not in ("+", "-"):
        return False
    # No MeasureRefs inside — that would be MEASURE_RATIO or COMPLEX
    return not _has_measure_refs(ast)


def _is_filtered_agg(ast: Any) -> bool:
    """
    True if root is CALCULATE with at least one InlineFilter arg
    (KEEPFILTERS or bare inline).
    No VAR block, no MeasureRef in main expression.
    Patterns P5, P6, P7, P8, P9.
    """
    if _root_func(ast) != "CALCULATE":
        return False
    if len(ast.args) < 2:
        return False
    # Must have at least one InlineFilter
    has_filter = any(isinstance(a, InlineFilter) for a in ast.args[1:])
    if not has_filter:
        return False
    # Main expression (args[0]) should not be a MeasureRef
    if isinstance(ast.args[0], MeasureRef):
        return False
    return True


def _is_var_filtered_divide(ast: Any) -> bool:
    """
    True if root is VarBlock where:
      - bindings use CALCULATE+KEEPFILTERS (filtered aggs)
      - return is DivideNode of VarRef values
    Pattern P6 full: Gap to potential risk.
    """
    if not isinstance(ast, VarBlock):
        return False
    # Return must be DivideNode
    if not isinstance(ast.return_expr, DivideNode):
        return False
    # Bindings should have CALCULATE
    has_calc = any(
        isinstance(vd.expr, FunctionCall) and vd.expr.name == "CALCULATE"
        for vd in ast.bindings
    )
    # No MeasureRef in bindings (pure column aggs)
    has_mref = any(
        _has_measure_refs(vd.expr) for vd in ast.bindings
    )
    return has_calc and not has_mref


def _is_time_intel_yoy(ast: Any) -> bool:
    """True if AST contains SAMEPERIODLASTYEAR."""
    return _has_function(ast, "SAMEPERIODLASTYEAR")


def _is_time_intel_mom(ast: Any) -> bool:
    """True if AST contains PREVIOUSMONTH."""
    return _has_function(ast, "PREVIOUSMONTH")


def _is_measure_ratio(ast: Any) -> bool:
    """
    True if root is BinaryOp(/) where BOTH sides are MeasureRef.
    Pattern P10: [A] / [B]
    Also covers DIVIDE([A], [B]) where args are MeasureRef.
    """
    if isinstance(ast, BinaryOp) and ast.op == "/":
        return (isinstance(ast.left,  MeasureRef)
                and isinstance(ast.right, MeasureRef))
    if isinstance(ast, DivideNode):
        return (isinstance(ast.numerator,   MeasureRef)
                and isinstance(ast.denominator, MeasureRef))
    return False


def _is_complex_var_divide(ast: Any) -> bool:
    """
    True if root is VarBlock where:
      - bindings reference other measures (MeasureRef)
      - return is DivideNode or ScalarMultiplier(DivideNode)
    Patterns P12 YoY, P4 DIVIDE×scalar.
    """
    if not isinstance(ast, VarBlock):
        return False
    ret = ast.return_expr
    has_divide = (isinstance(ret, DivideNode)
                  or (isinstance(ret, ScalarMultiplier)
                      and isinstance(ret.base_expr, DivideNode)))
    has_mref   = any(_has_measure_refs(vd.expr) for vd in ast.bindings)
    return has_divide and has_mref


def _is_context_remover(ast: Any) -> bool:
    """
    True if CALCULATE contains ALL() — removes date filter context.
    Pattern P14: CALCULATE(MAX(...), ALL('DATE'))
    EC4: no date filter should be injected for this pattern.
    """
    if _root_func(ast) != "CALCULATE":
        return False
    return _has_function(ast, "ALL")


def _is_var_agg_divide(ast: Any) -> bool:
    """
    True if root is VarBlock where:
      - bindings are pure column aggregations (no MeasureRef)
      - return is DivideNode or ScalarMultiplier(DivideNode)
    Pattern P4: Utilization (VAR Num = COUNT(...) VAR Denom = SUM(...) RETURN DIVIDE(Num,Denom)*12000)
    No inter-measure dependencies — purely column-level computation.
    """
    if not isinstance(ast, VarBlock):
        return False
    ret = ast.return_expr
    has_divide = (isinstance(ret, DivideNode)
                  or (isinstance(ret, ScalarMultiplier)
                      and isinstance(ret.base_expr, DivideNode)))
    if not has_divide:
        return False
    # Bindings must NOT reference other measures
    has_mref = any(_has_measure_refs(vd.expr) for vd in ast.bindings)
    return not has_mref


def _has_measure_refs(ast: Any) -> bool:
    """True if any MeasureRef exists anywhere in the AST."""
    if ast is None:
        return False
    if isinstance(ast, MeasureRef):
        return True
    if isinstance(ast, VarBlock):
        return (any(_has_measure_refs(vd.expr) for vd in ast.bindings)
                or _has_measure_refs(ast.return_expr))
    if isinstance(ast, FunctionCall):
        return any(_has_measure_refs(a) for a in ast.args)
    if isinstance(ast, DivideNode):
        return (_has_measure_refs(ast.numerator)
                or _has_measure_refs(ast.denominator))
    if isinstance(ast, BinaryOp):
        return _has_measure_refs(ast.left) or _has_measure_refs(ast.right)
    if isinstance(ast, InlineFilter):
        return _has_measure_refs(ast.expr)
    if isinstance(ast, ScalarMultiplier):
        return _has_measure_refs(ast.base_expr)
    if isinstance(ast, CompoundAnd):
        return _has_measure_refs(ast.left) or _has_measure_refs(ast.right)
    return False


# ══════════════════════════════════════════════════════════════
# MAIN CLASSIFIER
# ══════════════════════════════════════════════════════════════

def classify(annotated: AnnotatedAST) -> ClassifyResult:
    """
    Classify a resolved measure into a DAX pattern.

    Args:
        annotated : AnnotatedAST from semantic_resolver.resolve_one()

    Returns:
        ClassifyResult — always. Never raises.

    Priority order (first match wins):
        1. Static filtered          → STATIC_FILTERED
        2. Time intel YoY           → TIME_INTEL_YOY
        3. Time intel MoM           → TIME_INTEL_MOM
        4. Context remover ALL()    → CONTEXT_REMOVER
        5. Simple aggregation       → SIMPLE_AGG
        6. Simple divide            → SIMPLE_DIVIDE
        7. Arithmetic               → ARITHMETIC
        8. Filtered aggregation     → FILTERED_AGG
        9. VAR filtered divide      → VAR_FILTERED_DIVIDE
       10. Measure ratio            → MEASURE_RATIO
       11. Complex VAR divide       → COMPLEX_VAR_DIVIDE
       12. Fallback                 → COMPLEX (BUILDER)
    """
    name      = annotated.measure_name
    ast       = annotated.ast
    has_static = bool(annotated.static_tables)
    has_all    = _has_function(ast, "ALL")
    has_yoy    = _is_time_intel_yoy(ast)
    has_mom    = _is_time_intel_mom(ast)

    # ── 1. STATIC_FILTERED ───────────────────────────────────
    if has_static:
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "STATIC_FILTERED",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = (
                "References static Power BI table. SQL uses CTE substitution. "
                "LLM writes definition."
            ),
            has_static     = True,
            has_time_intel = has_yoy or has_mom,
            has_all        = has_all,
        )

    # ── 2. TIME_INTEL_YOY ────────────────────────────────────
    if has_yoy:
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "TIME_INTEL_YOY",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = (
                "Year-over-year using SAMEPERIODLASTYEAR. "
                "SQL uses DATEADD(year,-1,:selected_month). "
                "Date parameter required (EC_DATE)."
            ),
            has_static     = False,
            has_time_intel = True,
            has_all        = has_all,
        )

    # ── 3. TIME_INTEL_MOM ────────────────────────────────────
    if has_mom:
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "TIME_INTEL_MOM",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = (
                "Month-over-month using PREVIOUSMONTH. "
                "SQL uses DATEADD(month,-1,:selected_month). "
                "Date parameter required (EC_DATE)."
            ),
            has_static     = False,
            has_time_intel = True,
            has_all        = has_all,
        )

    # ── 4. CONTEXT_REMOVER ───────────────────────────────────
    if _is_context_remover(ast):
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "CONTEXT_REMOVER",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = (
                "CALCULATE with ALL() removes date filter context. "
                "SQL must NOT inject date WHERE clause (EC4)."
            ),
            has_static     = False,
            has_time_intel = False,
            has_all        = True,
        )

    # ── 5. SIMPLE_AGG ────────────────────────────────────────
    if _is_simple_agg(ast):
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "SIMPLE_AGG",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = "Direct aggregation — straightforward SQL equivalent.",
            has_static     = False,
            has_time_intel = False,
            has_all        = False,
        )

    # ── 6. SIMPLE_DIVIDE ─────────────────────────────────────
    if _is_simple_divide(ast):
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "SIMPLE_DIVIDE",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = (
                "DIVIDE of two aggregations. "
                "SQL uses a/NULLIF(b,0) or COALESCE(a/NULLIF(b,0),0) (EC19)."
            ),
            has_static     = False,
            has_time_intel = False,
            has_all        = False,
        )

    # ── 7. ARITHMETIC ────────────────────────────────────────
    if _is_arithmetic(ast):
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "ARITHMETIC",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = "Arithmetic combination of aggregations. Direct SQL translation.",
            has_static     = False,
            has_time_intel = False,
            has_all        = False,
        )

    # ── 8. FILTERED_AGG ──────────────────────────────────────
    if _is_filtered_agg(ast):
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "FILTERED_AGG",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = (
                "CALCULATE with KEEPFILTERS or inline filter. "
                "SQL uses WHERE clause. EC24: both forms → same SQL."
            ),
            has_static     = False,
            has_time_intel = False,
            has_all        = False,
        )

    # ── 9. VAR_FILTERED_DIVIDE ───────────────────────────────
    if _is_var_filtered_divide(ast):
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "VAR_FILTERED_DIVIDE",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = (
                "VAR block with CALCULATE filters, RETURN DIVIDE. "
                "SQL uses CASE WHEN or subquery per VAR. Pattern P6."
            ),
            has_static     = False,
            has_time_intel = False,
            has_all        = False,
        )

    # ── 9.5 VAR_AGG_DIVIDE (P4 Utilization pattern) ────────
    if _is_var_agg_divide(ast):
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "VAR_AGG_DIVIDE",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = (
                "VAR block with column aggregations, RETURN DIVIDE or x scalar. "
                "No inter-measure deps. SQL resolves VARs as subexpressions. Pattern P4."
            ),
            has_static     = False,
            has_time_intel = False,
            has_all        = False,
        )

    # ── 10. MEASURE_RATIO ────────────────────────────────────
    if _is_measure_ratio(ast):
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "MEASURE_RATIO",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = (
                "Direct measure-to-measure division. "
                "SQL resolves each measure independently then divides. "
                "Requires dep resolution (EC_DEP)."
            ),
            has_static     = False,
            has_time_intel = False,
            has_all        = False,
        )

    # ── 11. COMPLEX_VAR_DIVIDE ───────────────────────────────
    if _is_complex_var_divide(ast):
        return ClassifyResult(
            measure_name   = name,
            dax_pattern    = "COMPLEX_VAR_DIVIDE",
            sql_applicable = True,
            llm_role       = "DEFINER",
            note           = (
                "VAR block referencing other measures, RETURN DIVIDE or ×scalar. "
                "SQL resolves measure deps then computes. Patterns P4, P12."
            ),
            has_static     = False,
            has_time_intel = False,
            has_all        = False,
        )

    # ── 12. COMPLEX (fallback) ───────────────────────────────
    return ClassifyResult(
        measure_name   = name,
        dax_pattern    = "COMPLEX",
        sql_applicable = True,
        llm_role       = "BUILDER",
        note           = (
            "Pattern not matched by compiler rules. "
            "LLM will generate SQL directly."
        ),
        has_static     = False,
        has_time_intel = has_yoy or has_mom,
        has_all        = has_all,
    )


# ══════════════════════════════════════════════════════════════
# BATCH CLASSIFIER
# ══════════════════════════════════════════════════════════════

def classify_all(
    annotated_map: dict[str, AnnotatedAST]
) -> dict[str, ClassifyResult]:
    """
    Classify all measures.

    Args:
        annotated_map : {measure_name: AnnotatedAST}

    Returns:
        {measure_name: ClassifyResult}
    """
    return {name: classify(ann) for name, ann in annotated_map.items()}


# ══════════════════════════════════════════════════════════════
# SELF-TEST  —  run: python classifier.py
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from ast_nodes import (
        ColumnRef, MeasureRef, VarRef, StringLiteral, BoolLiteral,
        FunctionCall, DivideNode, BinaryOp, InSetExpr, InlineFilter,
        ScalarMultiplier, VarDef, VarBlock, ParseSuccess,
    )
    from parser import parse
    from dep_resolver import resolve as dep_resolve, DepResult
    from semantic_resolver import (
        AnnotatedAST, SFRef, build_snowflake_lookup,
        build_rel_graph, resolve_one,
    )

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
        "static_tables": {"static_risk_bucket": {}, "static_care_gap_bucket": {}},
        "X Axis scatter plot": {"type": "parameter"},
    }
    RELS = []

    def annotate(name: str, dax: str, extra_measures: dict = None) -> AnnotatedAST:
        """Helper: clean → parse → dep_resolve → semantic_resolve."""
        measures = {name: parse(name, dax)}
        if extra_measures:
            measures.update(extra_measures)
        dr  = dep_resolve(measures)
        sf  = build_snowflake_lookup(SF_MAP)
        rg  = build_rel_graph(RELS)
        return resolve_one(name, measures[name].ast, dr, sf, rg)

    def clf(name: str, dax: str, extra_measures: dict = None) -> ClassifyResult:
        return classify(annotate(name, dax, extra_measures))

    print("=== classifier.py self-test ===\n")

    # ── P1: SIMPLE_AGG ───────────────────────────────────────
    print("P1 — SIMPLE_AGG:")
    r = clf("#Members", "SUM(attribution[member_count])")
    check("pattern=SIMPLE_AGG",         r.dax_pattern    == "SIMPLE_AGG")
    check("sql_applicable=True",        r.sql_applicable is True)
    check("llm_role=DEFINER",           r.llm_role       == "DEFINER")

    r = clf("MAX date", "MAX(risk_core[month_of_measurement])")
    check("MAX → SIMPLE_AGG",           r.dax_pattern == "SIMPLE_AGG")

    r = clf("Targeted gaps", "COUNTROWS(cohort)")
    check("COUNTROWS → SIMPLE_AGG",     r.dax_pattern == "SIMPLE_AGG")

    r = clf("Distinct", "DISTINCTCOUNT(attribution[member_count])")
    check("DISTINCTCOUNT → SIMPLE_AGG", r.dax_pattern == "SIMPLE_AGG")

    # ── P3: SIMPLE_DIVIDE ────────────────────────────────────
    print("\nP3 — SIMPLE_DIVIDE:")
    r = clf("PMPM", "DIVIDE(SUM(attribution[ytd_visit_amount]), SUM(attribution[ytd_member_count]))")
    check("pattern=SIMPLE_DIVIDE",      r.dax_pattern    == "SIMPLE_DIVIDE")
    check("sql_applicable=True",        r.sql_applicable is True)

    # ── P22: ARITHMETIC ──────────────────────────────────────
    print("\nP22 — ARITHMETIC:")
    r = clf("Filter", "ABS(SUM(attribution[ytd_visit_amount])) + SUM(attribution[ytd_member_count])")
    check("pattern=ARITHMETIC",         r.dax_pattern == "ARITHMETIC")
    check("sql_applicable=True",        r.sql_applicable is True)

    # ── P5: FILTERED_AGG (KEEPFILTERS) ───────────────────────
    print("\nP5 — FILTERED_AGG:")
    dax5 = 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))'
    r = clf("Documented risk", dax5)
    check("pattern=FILTERED_AGG",       r.dax_pattern == "FILTERED_AGG")
    check("sql_applicable=True",        r.sql_applicable is True)

    # ── EC18: AVERAGE → FILTERED_AGG ─────────────────────────
    print("\nEC18 — AVERAGE:")
    dax18 = 'CALCULATE(AVERAGE(risk_core[risk_value]), KEEPFILTERS(risk_core[flag] = "Documented"))'
    r = clf("Avg risk", dax18)
    check("AVERAGE+KEEPFILTERS → FILTERED_AGG", r.dax_pattern == "FILTERED_AGG")

    # ── P7: FILTERED_AGG (inline, no KEEPFILTERS) ────────────
    print("\nP7 — FILTERED_AGG inline:")
    dax7 = 'CALCULATE(SUM(risk_core[risk_value]), risk_core[flag] = "Documented")'
    r = clf("inline filter", dax7)
    check("inline filter → FILTERED_AGG", r.dax_pattern == "FILTERED_AGG")

    # ── P6: VAR_FILTERED_DIVIDE ──────────────────────────────
    print("\nP6 — VAR_FILTERED_DIVIDE:")
    dax6 = (
        'VAR a = CALCULATE(SUM(risk_core[risk_value]),\n'
        '  KEEPFILTERS(risk_core[risk_documentation_flag] IN {"Undocumented","Suspected"}))\n'
        'VAR b = CALCULATE(SUM(risk_core[patient_count]),\n'
        '  KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))\n'
        'RETURN DIVIDE(a, b)'
    )
    r = clf("Gap to potential risk", dax6)
    check("pattern=VAR_FILTERED_DIVIDE", r.dax_pattern == "VAR_FILTERED_DIVIDE")
    check("sql_applicable=True",         r.sql_applicable is True)

    # ── P10: MEASURE_RATIO ───────────────────────────────────
    print("\nP10 — MEASURE_RATIO:")
    extra = {
        "Members with open coding gaps": parse("Members with open coding gaps",
            "SUM(attribution[member_with_open_coding_gap_count])"),
        "#Members": parse("#Members", "SUM(attribution[member_count])"),
    }
    r = clf("% members", "[Members with open coding gaps] / [#Members]", extra)
    check("pattern=MEASURE_RATIO",      r.dax_pattern == "MEASURE_RATIO")
    check("sql_applicable=True",        r.sql_applicable is True)

    # ── P11: TIME_INTEL_YOY ──────────────────────────────────
    print("\nP11 — TIME_INTEL_YOY:")
    extra_m = {"#Members": parse("#Members", "SUM(attribution[member_count])")}
    dax11 = "CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))"
    r = clf("#Members PY", dax11, extra_m)
    check("pattern=TIME_INTEL_YOY",     r.dax_pattern    == "TIME_INTEL_YOY")
    check("has_time_intel=True",        r.has_time_intel is True)
    check("sql_applicable=True",        r.sql_applicable is True)

    # ── TIME_INTEL_MOM ───────────────────────────────────────
    print("\nTIME_INTEL_MOM:")
    dax_mom = "CALCULATE([#Members], PREVIOUSMONTH('date'[month_of_date]))"
    r = clf("#Members PM", dax_mom, extra_m)
    check("pattern=TIME_INTEL_MOM",     r.dax_pattern    == "TIME_INTEL_MOM")
    check("has_time_intel=True",        r.has_time_intel is True)

    # ── P14: CONTEXT_REMOVER ─────────────────────────────────
    print("\nP14 — CONTEXT_REMOVER:")
    dax14 = "CALCULATE(MAX(cohort[month_of_measurement]), ALL('DATE'))"
    r = clf("Latest month", dax14)
    check("pattern=CONTEXT_REMOVER",    r.dax_pattern == "CONTEXT_REMOVER")
    check("has_all=True",               r.has_all     is True)
    check("sql_applicable=True",        r.sql_applicable is True)

    # ── P12: COMPLEX_VAR_DIVIDE ──────────────────────────────
    print("\nP12 — COMPLEX_VAR_DIVIDE:")
    extra_yoy = {"#Members": parse("#Members", "SUM(attribution[member_count])")}
    dax12 = ("VAR py = CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))\n"
             "RETURN DIVIDE([#Members] - py, py, 0)")
    r = clf("#Members YoY", dax12, extra_yoy)
    check("pattern=TIME_INTEL_YOY",     r.dax_pattern    == "TIME_INTEL_YOY")
    check("has_time_intel=True",        r.has_time_intel is True)
    # NOTE: TIME_INTEL_YOY wins over COMPLEX_VAR_DIVIDE because SPILY is present
    # and time intel has higher priority (step 2 in classifier)

    # ── P4: COMPLEX_VAR_DIVIDE (scalar, no time intel) ───────
    print("\nP4 — VAR_AGG_DIVIDE (no time intel, column aggs only):")
    dax4 = ("VAR Num = CALCULATE(COUNT(risk_core[risk_value]))\n"
            "VAR Denom = SUM(attribution[member_count])\n"
            "RETURN DIVIDE(Num, Denom) * 12000")
    r = clf("Utilization", dax4)
    check("pattern=VAR_AGG_DIVIDE", r.dax_pattern == "VAR_AGG_DIVIDE")
    check("sql_applicable=True",        r.sql_applicable is True)

    # ── STATIC_FILTERED (highest priority) ───────────────────
    print("\nSTATIC_FILTERED:")
    # Manually build AnnotatedAST with static table
    static_ann = AnnotatedAST(
        measure_name  = "static test",
        ast           = FunctionCall("SUM", [ColumnRef("risk_core","risk_value")]),
        sf_refs       = [],
        join_paths    = [],
        static_tables = ["static_risk_bucket"],
        unresolved    = [],
        warnings      = [],
    )
    r = classify(static_ann)
    check("pattern=STATIC_FILTERED",    r.dax_pattern == "STATIC_FILTERED")
    check("has_static=True",            r.has_static  is True)

    # ── COMPLEX fallback ─────────────────────────────────────
    print("\nCOMPLEX fallback:")
    # CALCULATE with MeasureRef as main expression but no recognized pattern
    complex_ann = AnnotatedAST(
        measure_name  = "complex test",
        ast           = FunctionCall("CALCULATE", [
            MeasureRef("#Members"),
            InlineFilter(
                BinaryOp("=", ColumnRef("t","flag"), StringLiteral("x")),
                has_keepfilters=True
            )
        ]),
        sf_refs       = [],
        join_paths    = [],
        static_tables = [],
        unresolved    = [],
        warnings      = [],
    )
    r = classify(complex_ann)
    # CALCULATE with MeasureRef as main expr → FILTERED_AGG check fails
    # (because _is_filtered_agg excludes MeasureRef as main expr)
    # → falls to COMPLEX
    check("MeasureRef in CALCULATE → COMPLEX", r.dax_pattern == "COMPLEX")
    check("llm_role=BUILDER",          r.llm_role == "BUILDER")

    # ── has_* flags ──────────────────────────────────────────
    print("\nhas_* flags:")
    r_yoy = clf("#Members PY", "CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))", extra_m)
    check("has_time_intel flag correct", r_yoy.has_time_intel is True)
    check("has_all=False for non-ALL",   r_yoy.has_all is False)

    r_all = clf("Latest month", "CALCULATE(MAX(cohort[month_of_measurement]), ALL('DATE'))")
    check("has_all=True for ALL()",      r_all.has_all is True)

    # ── EC2: IN {set} → FILTERED_AGG ─────────────────────────
    print("\nEC2 — IN {set} → FILTERED_AGG:")
    dax_in = ('CALCULATE(SUM(risk_core[risk_value]), '
              'KEEPFILTERS(risk_core[flag] IN {"Undocumented","Suspected"}))')
    r = clf("flagged risk", dax_in)
    check("IN {set} → FILTERED_AGG",    r.dax_pattern == "FILTERED_AGG")

    # ── EC8: boolean filter → FILTERED_AGG ───────────────────
    print("\nEC8 — boolean filter → FILTERED_AGG:")
    dax_bool = 'CALCULATE(SUM(risk_core[patient_count]), KEEPFILTERS(risk_core[max_month_flag] = TRUE()))'
    r = clf("current month", dax_bool)
    check("boolean filter → FILTERED_AGG", r.dax_pattern == "FILTERED_AGG")

    # ── Summary ─────────────────────────────────────────────
    print()
    if all_pass:
        print("✅  All classifier.py tests passed.")
        print("    Next step: sql_generator.py")
    else:
        print("❌  Some tests failed — fix before moving to sql_generator.py")