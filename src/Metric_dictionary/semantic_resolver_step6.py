"""
semantic_resolver.py
────────────────────
Stage 2 — Step 4

PURPOSE:
    Walk every AST node and annotate it with Snowflake information:
      - ColumnRef("attribution","member_count")
          -> sf_table="PCP_VISITS_V4_VIEW", sf_column="MEMBER_COUNT"
      - ColumnRef("py","*")  where "py" is a VAR binding
          -> upgrade to VarRef("py")
      - ColumnRef("static_risk_bucket","*")
          -> tag as static, attach CTE placeholder
      - ColumnRef("X Axis scatter plot","Y axis")
          -> tag as parameter, skip

INPUT:
    - ParseSuccess (AST from parser.py)
    - dep_result (DepResult from dep_resolver.py)
    - sf_map (dict from bi_snowflakes_naming_matching.json)
    - relationships (list from relationships.json)

OUTPUT:
    - AnnotatedAST dataclass:
        ast              : original AST (not mutated)
        sf_refs          : list[SFRef] — every column reference resolved
        join_paths       : list[str]   — SQL join conditions between source tables
        static_tables    : list[str]   — static_ table names referenced
        unresolved       : list[str]   — BI table names not found in sf_map
        warnings         : list[str]   — non-fatal issues

REUSE FROM step2_enricher.py:
    build_snowflake_lookup()  -> direct copy, adapted for new JSON structure
    build_rel_graph()         -> direct copy
    get_join_paths()          -> direct copy

ADDITION vs step2_enricher.py:
    VarRef upgrade  -> ColumnRef("py","*") -> VarRef("py") using dep_resolver output
    AST walking     -> instead of scanning raw DAX strings, walks AST nodes
    SFRef dataclass -> structured per-column resolution result
"""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any, Optional

from ast_nodes_step0 import (
    ColumnRef, MeasureRef, VarRef, StringLiteral, NumberLiteral,
    BoolLiteral, FunctionCall, DivideNode, BinaryOp, InSetExpr,
    CompoundAnd, InlineFilter, ScalarMultiplier, VarDef, VarBlock,
)
from dep_resolver_step5 import DepResult


# ══════════════════════════════════════════════════════════════
# RESULT DATACLASSES
# ══════════════════════════════════════════════════════════════

@dataclass
class SFRef:
    """
    A single resolved column reference.

    Fields:
        bi_table    : BI table name  e.g. "attribution"
        bi_column   : BI column name e.g. "member_count"  ("*" for table-only)
        sf_object   : Snowflake object name e.g. "PCP_VISITS_V4_VIEW"
        sf_column   : Snowflake column name e.g. "MEMBER_COUNT"  (uppercase)
        ref_type    : "source" | "static" | "parameter" | "measure_container"
                      | "var_ref" | "unresolved"
        cte_name    : set for static tables — the CTE block name
    """
    bi_table  : str
    bi_column : str
    sf_object : Optional[str]
    sf_column : Optional[str]
    ref_type  : str
    cte_name  : Optional[str] = None


@dataclass
class AnnotatedAST:
    """
    Output of resolve_one(). Wraps the original AST with resolution metadata.

    Fields:
        measure_name  : display name
        ast           : original AST (not mutated)
        sf_refs       : all column references resolved
        join_paths    : SQL join strings between source tables used
        static_tables : static_ table names referenced in this measure
        unresolved    : BI table names not found in sf_map (need human fix)
        warnings      : non-fatal issues (e.g. parameter table referenced)
    """
    measure_name  : str
    ast           : Any
    sf_refs       : list[SFRef]        = field(default_factory=list)
    join_paths    : list[str]          = field(default_factory=list)
    static_tables : list[str]          = field(default_factory=list)
    unresolved    : list[str]          = field(default_factory=list)
    warnings      : list[str]          = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# SNOWFLAKE LOOKUP BUILDER
# (reused from step2_enricher.py — adapted for new JSON structure)
# ══════════════════════════════════════════════════════════════

# Tables that have no SQL object — skip entirely
_NO_SQL_TABLES = {"ALL_DAX", "ALL DAX"}

# Tables that are parameter-only (user slicer values)
_PARAMETER_TABLES = {"X Axis scatter plot", "Y Axis scatter plot"}


def build_snowflake_lookup(sf_map: dict) -> dict[str, dict]:
    """
    Build flat lookup: bi_table_name -> {sf_object, type}

    Handles the actual bi_snowflakes_naming_matching.json structure:
      - Regular source tables:  {"snowflake_object": "VIEW_NAME", "type": "source"}
      - Dual-DB tables:         {"snowflake_object": {"snowflake": "X", "postgres": "Y"}}
      - Measure containers:     {"type": "measure_container", "snowflake_object": null}
      - Static tables:          nested under "static_tables" key
      - Parameter tables:       {"type": "parameter"}

    Returns:
        {
          "attribution": {"sf_object": "PCP_VISITS_V4_VIEW", "type": "source"},
          "risk_core":   {"sf_object": "RISK_CORE_V4_VIEW",  "type": "source"},
          "ALL_DAX":     {"sf_object": None, "type": "measure_container"},
          "static_risk_bucket": {"sf_object": None, "type": "static"},
          ...
        }
    """
    lookup = {}

    for key, val in sf_map.items():
        if not isinstance(val, dict):
            continue

        # ── static_tables block ──────────────────────────────
        if key == "static_tables":
            for st_name in val:
                lookup[st_name] = {"sf_object": None, "type": "static"}
            continue

        # ── parameter tables ─────────────────────────────────
        if key in _PARAMETER_TABLES or val.get("type") == "parameter":
            lookup[key] = {"sf_object": None, "type": "parameter"}
            continue

        # ── measure_container ────────────────────────────────
        if val.get("type") == "measure_container" or key in _NO_SQL_TABLES:
            lookup[key] = {"sf_object": None, "type": "measure_container"}
            continue

        # ── source tables ────────────────────────────────────
        sf_obj = val.get("snowflake_object")

        # Handle dual-DB: {"snowflake": "X", "postgres": "Y"}
        if isinstance(sf_obj, dict):
            sf_obj = sf_obj.get("snowflake") or sf_obj.get("postgres")

        lookup[key] = {
            "sf_object"          : sf_obj,
            "type"               : val.get("type", "source"),
            "date_column"        : val.get("date_column"),
            "has_max_month_flag" : val.get("has_max_month_flag", False),
        }

    return lookup


# ══════════════════════════════════════════════════════════════
# RELATIONSHIP GRAPH BUILDER
# (reused from step2_enricher.py — direct copy)
# ══════════════════════════════════════════════════════════════

def build_rel_graph(relationships: list) -> dict[str, list]:
    """
    Build adjacency map from active relationships.
    graph[from_table] = [{to_table, from_column, to_column}]

    Only active relationships (is_active=True) are included.
    """
    graph = defaultdict(list)
    for r in relationships:
        if not r.get("is_active", True):
            continue
        graph[r["from_table"]].append({
            "to_table"   : r["to_table"],
            "from_column": r["from_column"],
            "to_column"  : r["to_column"],
        })
    return graph


def get_join_paths(source_tables: set[str], rel_graph: dict) -> list[str]:
    """
    Find active relationships between source tables used in a measure.
    Returns human-readable join strings.

    e.g. "attribution.ORG_HIERARCHY_MASTER_ID = pcp.ORG_HIERARCHY_MASTER_ID"

    Only between SOURCE tables — skip static/parameter/measure_container.
    """
    join_paths = []
    seen       = set()

    for from_table, connections in rel_graph.items():
        if from_table not in source_tables:
            continue
        for conn in connections:
            to_table = conn["to_table"]
            if to_table not in source_tables:
                continue
            key = f"{from_table}.{conn['from_column']}={to_table}.{conn['to_column']}"
            if key in seen:
                continue
            seen.add(key)
            join_paths.append(
                f"{from_table}.{conn['from_column'].upper()} = "
                f"{to_table}.{conn['to_column'].upper()}"
            )

    return join_paths


# ══════════════════════════════════════════════════════════════
# AST WALKER — collect all ColumnRef nodes
# ══════════════════════════════════════════════════════════════

def _collect_column_refs(ast: Any, found: list = None) -> list[ColumnRef]:
    """
    Walk AST and collect all ColumnRef nodes.
    Returns list (with duplicates — caller deduplicates if needed).
    """
    if found is None:
        found = []

    if ast is None:
        return found

    if isinstance(ast, ColumnRef):
        found.append(ast)
        return found

    if isinstance(ast, VarBlock):
        for vd in ast.bindings:
            _collect_column_refs(vd.expr, found)
        _collect_column_refs(ast.return_expr, found)
        return found

    if isinstance(ast, FunctionCall):
        for arg in ast.args:
            _collect_column_refs(arg, found)
        return found

    if isinstance(ast, DivideNode):
        _collect_column_refs(ast.numerator,   found)
        _collect_column_refs(ast.denominator, found)
        return found

    if isinstance(ast, BinaryOp):
        _collect_column_refs(ast.left,  found)
        _collect_column_refs(ast.right, found)
        return found

    if isinstance(ast, InSetExpr):
        found.append(ast.column)
        return found

    if isinstance(ast, CompoundAnd):
        _collect_column_refs(ast.left,  found)
        _collect_column_refs(ast.right, found)
        return found

    if isinstance(ast, InlineFilter):
        _collect_column_refs(ast.expr, found)
        return found

    if isinstance(ast, ScalarMultiplier):
        _collect_column_refs(ast.base_expr, found)
        return found

    return found


# ══════════════════════════════════════════════════════════════
# VAR REF UPGRADER
# ══════════════════════════════════════════════════════════════

def _upgrade_var_refs(ast: Any, var_names: set[str]) -> Any:
    """
    Walk AST and replace ColumnRef(name, "*") with VarRef(name)
    when name is a known VAR binding in this measure.

    This fixes the parser's limitation: bare identifiers like `py`, `Num`,
    `Denom` are emitted as ColumnRef(name, "*") because the parser cannot
    distinguish VAR names from table names at parse time.

    Args:
        ast       : any AST node
        var_names : set of VAR binding names from dep_resolver

    Returns:
        new AST with VarRef nodes substituted (original not mutated)
    """
    if ast is None:
        return ast

    # The target: ColumnRef(name, "*") where name is a VAR binding
    if isinstance(ast, ColumnRef):
        if ast.column == "*" and ast.table in var_names:
            return VarRef(name=ast.table)
        return ast

    if isinstance(ast, VarBlock):
        new_bindings = [
            VarDef(name=vd.name, expr=_upgrade_var_refs(vd.expr, var_names))
            for vd in ast.bindings
        ]
        new_return = _upgrade_var_refs(ast.return_expr, var_names)
        return VarBlock(bindings=new_bindings, return_expr=new_return)

    if isinstance(ast, FunctionCall):
        return FunctionCall(
            name = ast.name,
            args = [_upgrade_var_refs(a, var_names) for a in ast.args]
        )

    if isinstance(ast, DivideNode):
        return DivideNode(
            numerator   = _upgrade_var_refs(ast.numerator,   var_names),
            denominator = _upgrade_var_refs(ast.denominator, var_names),
            default_val = ast.default_val,
        )

    if isinstance(ast, BinaryOp):
        return BinaryOp(
            op    = ast.op,
            left  = _upgrade_var_refs(ast.left,  var_names),
            right = _upgrade_var_refs(ast.right, var_names),
        )

    if isinstance(ast, InSetExpr):
        return InSetExpr(
            column = _upgrade_var_refs(ast.column, var_names),
            values = ast.values,
        )

    if isinstance(ast, CompoundAnd):
        return CompoundAnd(
            left  = _upgrade_var_refs(ast.left,  var_names),
            right = _upgrade_var_refs(ast.right, var_names),
        )

    if isinstance(ast, InlineFilter):
        return InlineFilter(
            expr            = _upgrade_var_refs(ast.expr, var_names),
            has_keepfilters = ast.has_keepfilters,
        )

    if isinstance(ast, ScalarMultiplier):
        return ScalarMultiplier(
            base_expr  = _upgrade_var_refs(ast.base_expr, var_names),
            multiplier = ast.multiplier,
        )

    # Leaf nodes (MeasureRef, VarRef, StringLiteral, NumberLiteral,
    # BoolLiteral) — return as-is
    return ast


# ══════════════════════════════════════════════════════════════
# COLUMN RESOLVER
# ══════════════════════════════════════════════════════════════

def _resolve_column(
    col      : ColumnRef,
    sf_lookup: dict[str, dict],
) -> SFRef:
    """
    Resolve one ColumnRef to a SFRef.

    Rules:
      1. column == "*" AND table in var_names -> already upgraded to VarRef
         (this function never called for those)
      2. table is static_ prefix -> type=static, sf_object=None, cte_name=table
      3. table in sf_lookup -> map to SF object, uppercase column
      4. not found -> type=unresolved
    """
    bi_table  = col.table
    bi_column = col.column

    # Static table — has static_ prefix or is in static section of lookup
    info = sf_lookup.get(bi_table)

    if info is None:
        # Not found at all
        return SFRef(
            bi_table  = bi_table,
            bi_column = bi_column,
            sf_object = None,
            sf_column = None,
            ref_type  = "unresolved",
        )

    ref_type = info["type"]
    sf_obj   = info["sf_object"]

    # Static table
    if ref_type == "static":
        return SFRef(
            bi_table  = bi_table,
            bi_column = bi_column,
            sf_object = None,
            sf_column = bi_column.upper() if bi_column != "*" else None,
            ref_type  = "static",
            cte_name  = bi_table,
        )

    # Parameter table (SELECTEDVALUE-dependent — scope_classifier should
    # have caught these, but handle gracefully)
    if ref_type == "parameter":
        return SFRef(
            bi_table  = bi_table,
            bi_column = bi_column,
            sf_object = None,
            sf_column = None,
            ref_type  = "parameter",
        )

    # Measure container (ALL_DAX etc.)
    if ref_type == "measure_container":
        return SFRef(
            bi_table  = bi_table,
            bi_column = bi_column,
            sf_object = None,
            sf_column = None,
            ref_type  = "measure_container",
        )

    # Source table — map to SF object + uppercase column
    sf_col = bi_column.upper() if bi_column and bi_column != "*" else None

    return SFRef(
        bi_table  = bi_table,
        bi_column = bi_column,
        sf_object = sf_obj,
        sf_column = sf_col,
        ref_type  = "source",
    )


# ══════════════════════════════════════════════════════════════
# MAIN RESOLVER
# ══════════════════════════════════════════════════════════════

def resolve_one(
    measure_name : str,
    ast          : Any,
    dep_result   : DepResult,
    sf_lookup    : dict[str, dict],
    rel_graph    : dict[str, list],
) -> AnnotatedAST:
    """
    Resolve one measure's AST — annotate with Snowflake info.

    Steps:
      1. Get VAR binding names for this measure from dep_result
      2. Upgrade ColumnRef(var_name,"*") -> VarRef(var_name)
      3. Collect all remaining ColumnRef nodes
      4. Resolve each ColumnRef -> SFRef
      5. Find join paths between source tables used
      6. Return AnnotatedAST

    Args:
        measure_name : display name
        ast          : ParseSuccess.ast
        dep_result   : from dep_resolver.resolve()
        sf_lookup    : from build_snowflake_lookup()
        rel_graph    : from build_rel_graph()

    Returns:
        AnnotatedAST — always. Never raises.
    """
    warnings      = []
    unresolved    = []
    static_tables = []

    # Step 1 & 2: upgrade VAR refs
    var_names    = set(dep_result.var_bindings.get(measure_name, []))
    upgraded_ast = _upgrade_var_refs(ast, var_names)

    # Step 3: collect ColumnRefs from upgraded AST
    col_refs = _collect_column_refs(upgraded_ast)

    # Step 4: resolve each ColumnRef
    sf_refs      = []
    source_tables = set()
    seen_refs    = set()   # avoid duplicate SFRef entries

    for col in col_refs:
        key = (col.table, col.column)
        if key in seen_refs:
            continue
        seen_refs.add(key)

        ref = _resolve_column(col, sf_lookup)
        sf_refs.append(ref)

        if ref.ref_type == "source" and ref.sf_object:
            source_tables.add(col.table)

        elif ref.ref_type == "static":
            if col.table not in static_tables:
                static_tables.append(col.table)

        elif ref.ref_type == "unresolved":
            if col.table not in unresolved:
                unresolved.append(col.table)
            warnings.append(
                f"UNRESOLVED_TABLE: '{col.table}' not found in SF mapping. "
                f"Column: '{col.column}'. SQL generation may fail."
            )

        elif ref.ref_type == "parameter":
            warnings.append(
                f"PARAMETER_TABLE: '{col.table}' is a parameter table "
                f"(user slicer). No SQL equivalent."
            )

    # Step 5: join paths between source tables
    join_paths = get_join_paths(source_tables, rel_graph)

    return AnnotatedAST(
        measure_name  = measure_name,
        ast           = upgraded_ast,   # use upgraded AST downstream
        sf_refs       = sf_refs,
        join_paths    = join_paths,
        static_tables = static_tables,
        unresolved    = unresolved,
        warnings      = warnings,
    )


def resolve_all(
    parse_results : dict,       # {name: ParseSuccess}
    dep_result    : DepResult,
    sf_map        : dict,
    relationships : list,
) -> dict[str, AnnotatedAST]:
    """
    Resolve all measures in topological order.

    Args:
        parse_results : {name: ParseSuccess}
        dep_result    : from dep_resolver.resolve()
        sf_map        : loaded from bi_snowflakes_naming_matching.json
        relationships : loaded from relationships.json

    Returns:
        {measure_name: AnnotatedAST}  in topological order
    """
    sf_lookup = build_snowflake_lookup(sf_map)
    rel_graph = build_rel_graph(relationships)
    results   = {}

    for name in dep_result.order:
        if name not in parse_results:
            continue
        result = resolve_one(
            measure_name = name,
            ast          = parse_results[name].ast,
            dep_result   = dep_result,
            sf_lookup    = sf_lookup,
            rel_graph    = rel_graph,
        )
        results[name] = result

    return results


# ══════════════════════════════════════════════════════════════
# SELF-TEST  —  run: python semantic_resolver.py
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from ast_nodes import ParseSuccess
    from parser import parse
    from dep_resolver import resolve as dep_resolve

    all_pass = True

    def check(label: str, condition: bool):
        global all_pass
        status = "✅" if condition else "❌"
        print(f"  {status}  {label}")
        if not condition:
            all_pass = False

    # Actual SF map (from bi_snowflakes_naming_matching.json)
    SF_MAP = {
        "date"       : {"snowflake_object": "DATE_VIEW",          "type": "source"},
        "attribution": {"snowflake_object": "PCP_VISITS_V4_VIEW", "type": "source"},
        "risk_core"  : {"snowflake_object": {"snowflake": "RISK_CORE_V4_VIEW",
                                              "postgres":  "risk_core_aggregate_view"},
                        "type": "source"},
        "cohort"     : {"snowflake_object": {"snowflake": "RISK_COHORT_V4_VIEW",
                                              "postgres":  "risk_core_aggregate_view"},
                        "type": "source"},
        "pac_view"   : {"snowflake_object": "PAC_VIEW",            "type": "source"},
        "ALL_DAX"    : {"type": "measure_container", "snowflake_object": None},
        "static_tables": {
            "static_risk_bucket"     : {"table_id": 711307},
            "static_care_gap_bucket" : {"table_id": 702372},
        },
        "X Axis scatter plot": {"type": "parameter"},
        "Y Axis scatter plot": {"type": "parameter"},
    }

    RELATIONSHIPS = [
        {"from_table": "attribution", "from_column": "org_hierarchy_master_id",
         "to_table": "pcp", "to_column": "org_hierarchy_master_id", "is_active": True},
        {"from_table": "risk_core", "from_column": "month_of_measurement",
         "to_table": "date", "to_column": "month_of_date", "is_active": True},
    ]

    print("=== semantic_resolver.py self-test ===\n")

    # ── build_snowflake_lookup ───────────────────────────────
    print("build_snowflake_lookup:")
    lookup = build_snowflake_lookup(SF_MAP)
    check("attribution -> PCP_VISITS_V4_VIEW",
          lookup["attribution"]["sf_object"] == "PCP_VISITS_V4_VIEW")
    check("risk_core -> RISK_CORE_V4_VIEW (dual-DB)",
          lookup["risk_core"]["sf_object"] == "RISK_CORE_V4_VIEW")
    check("ALL_DAX -> measure_container",
          lookup["ALL_DAX"]["type"] == "measure_container")
    check("static_risk_bucket -> static",
          lookup["static_risk_bucket"]["type"] == "static")
    check("X Axis scatter plot -> parameter",
          lookup["X Axis scatter plot"]["type"] == "parameter")

    # ── VarRef upgrade ───────────────────────────────────────
    print("\nVarRef upgrade:")
    from ast_nodes import VarBlock, VarDef, DivideNode, ColumnRef, VarRef

    ast_with_var = VarBlock(
        bindings = [
            VarDef("py", FunctionCall("CALCULATE", [
                MeasureRef("#Members"),
                FunctionCall("SAMEPERIODLASTYEAR",
                             [ColumnRef("date","month_of_date")])
            ]))
        ],
        return_expr = DivideNode(
            BinaryOp("-", MeasureRef("#Members"), ColumnRef("py","*")),
            ColumnRef("py","*"),
            0.0
        )
    )

    from dep_resolver import DepResult
    dr = DepResult(
        order        = ["#Members YoY"],
        deps         = {"#Members YoY": ["#Members"]},
        var_bindings = {"#Members YoY": ["py"]},
    )

    upgraded = _upgrade_var_refs(ast_with_var, {"py"})
    # After upgrade: ColumnRef("py","*") -> VarRef("py")
    ret = upgraded.return_expr
    check("numerator right is VarRef(py)",
          isinstance(ret.numerator.right, VarRef)
          and ret.numerator.right.name == "py")
    check("denominator is VarRef(py)",
          isinstance(ret.denominator, VarRef)
          and ret.denominator.name == "py")
    check("date ColumnRef NOT upgraded",
          isinstance(upgraded.bindings[0].expr.args[1].args[0], ColumnRef)
          and upgraded.bindings[0].expr.args[1].args[0].table == "date")

    # ── P1: Plain SUM — source table resolution ──────────────
    print("\nP1 — SUM resolution:")
    p1_parse = {
        "#Members": parse("#Members", "SUM(attribution[member_count])")
    }
    p1_dr = dep_resolve(p1_parse)
    p1_ast = resolve_one(
        "#Members", p1_parse["#Members"].ast, p1_dr,
        build_snowflake_lookup(SF_MAP), build_rel_graph(RELATIONSHIPS)
    )
    sf_ref = p1_ast.sf_refs[0]
    check("sf_object=PCP_VISITS_V4_VIEW",  sf_ref.sf_object == "PCP_VISITS_V4_VIEW")
    check("sf_column=MEMBER_COUNT",         sf_ref.sf_column == "MEMBER_COUNT")
    check("ref_type=source",                sf_ref.ref_type  == "source")
    check("no unresolved",                  p1_ast.unresolved == [])
    check("no warnings",                    p1_ast.warnings   == [])

    # ── P5: CALCULATE + KEEPFILTERS — risk_core ──────────────
    print("\nP5 — CALCULATE+KEEPFILTERS resolution:")
    p5_dax = 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))'
    p5_parse = {"Documented risk": parse("Documented risk", p5_dax)}
    p5_dr    = dep_resolve(p5_parse)
    p5_ast   = resolve_one(
        "Documented risk", p5_parse["Documented risk"].ast, p5_dr,
        build_snowflake_lookup(SF_MAP), build_rel_graph(RELATIONSHIPS)
    )
    check("risk_core -> RISK_CORE_V4_VIEW",
          any(r.sf_object == "RISK_CORE_V4_VIEW" for r in p5_ast.sf_refs))
    check("risk_value -> RISK_VALUE",
          any(r.sf_column == "RISK_VALUE" for r in p5_ast.sf_refs))
    check("flag col -> RISK_DOCUMENTATION_FLAG",
          any(r.sf_column == "RISK_DOCUMENTATION_FLAG" for r in p5_ast.sf_refs))

    # ── P12: YoY — VarRef upgrade in full parse flow ─────────
    print("\nP12 — YoY with VarRef upgrade:")
    yoy_dax = ("VAR py = CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))\n"
               "RETURN DIVIDE([#Members] - py, py, 0)")
    yoy_results = {
        "#Members" : parse("#Members",      "SUM(attribution[member_count])"),
        "#Members YoY": parse("#Members YoY", yoy_dax),
    }
    yoy_dr  = dep_resolve(yoy_results)
    yoy_ann = resolve_one(
        "#Members YoY",
        yoy_results["#Members YoY"].ast,
        yoy_dr,
        build_snowflake_lookup(SF_MAP),
        build_rel_graph(RELATIONSHIPS),
    )
    # After upgrade, "py" refs should be VarRef, not ColumnRef
    # So they should NOT appear in sf_refs as unresolved
    check("py not in unresolved",          "py" not in yoy_ann.unresolved)
    # date[month_of_date] should be resolved
    check("date -> DATE_VIEW",
          any(r.sf_object == "DATE_VIEW" for r in yoy_ann.sf_refs))
    # attribution lives in [#Members] — a separate measure.
    # resolve_one only walks THIS measure's AST, not its dependencies.
    check("only date ref in YoY measure itself",
          all(r.bi_table == "date" for r in yoy_ann.sf_refs))

    # ── Static table detection ───────────────────────────────
    print("\nStatic table:")
    static_ast = FunctionCall("CALCULATE", [
        FunctionCall("SUM", [ColumnRef("risk_core", "risk_value")]),
        InlineFilter(
            InSetExpr(
                ColumnRef("static_risk_bucket", "bucket_name"),
                ["High", "Medium"]
            ),
            has_keepfilters=True
        )
    ])
    static_dr = DepResult(
        order        = ["test"],
        deps         = {"test": []},
        var_bindings = {"test": []},
    )
    static_ann = resolve_one(
        "test", static_ast, static_dr,
        build_snowflake_lookup(SF_MAP), build_rel_graph(RELATIONSHIPS)
    )
    check("static_risk_bucket in static_tables",
          "static_risk_bucket" in static_ann.static_tables)
    check("static ref_type=static",
          any(r.ref_type == "static" for r in static_ann.sf_refs))
    check("static cte_name set",
          any(r.cte_name == "static_risk_bucket" for r in static_ann.sf_refs))

    # ── Unresolved table ─────────────────────────────────────
    print("\nUnresolved table:")
    unres_ast = FunctionCall("SUM", [ColumnRef("unknown_table", "some_col")])
    unres_dr  = DepResult(order=["x"], deps={"x":[]}, var_bindings={"x":[]})
    unres_ann = resolve_one(
        "x", unres_ast, unres_dr,
        build_snowflake_lookup(SF_MAP), build_rel_graph(RELATIONSHIPS)
    )
    check("unknown_table in unresolved",  "unknown_table" in unres_ann.unresolved)
    check("warning added",                len(unres_ann.warnings) > 0)

    # ── Join paths ───────────────────────────────────────────
    print("\nJoin paths:")
    rels = [
        {"from_table": "attribution", "from_column": "month_of_attribution",
         "to_table": "date", "to_column": "month_of_date", "is_active": True},
    ]
    rg   = build_rel_graph(rels)
    tabs = {"attribution", "date"}
    jps  = get_join_paths(tabs, rg)
    check("1 join path found",            len(jps) == 1)
    check("join path correct",
          "attribution.MONTH_OF_ATTRIBUTION = date.MONTH_OF_DATE" in jps)

    # inactive relationship not included
    rels_inactive = [
        {"from_table": "attribution", "from_column": "x",
         "to_table": "date", "to_column": "y", "is_active": False},
    ]
    rg2  = build_rel_graph(rels_inactive)
    jps2 = get_join_paths({"attribution","date"}, rg2)
    check("inactive relationship excluded", jps2 == [])

    # ── Column uppercase ─────────────────────────────────────
    print("\nColumn name uppercase:")
    ref = _resolve_column(ColumnRef("attribution","member_count"),
                          build_snowflake_lookup(SF_MAP))
    check("bi_column=member_count",        ref.bi_column == "member_count")
    check("sf_column=MEMBER_COUNT",        ref.sf_column == "MEMBER_COUNT")

    # ── Summary ─────────────────────────────────────────────
    print()
    if all_pass:
        print("✅  All semantic_resolver.py tests passed.")
        print("    Next step: classifier.py")
    else:
        print("❌  Some tests failed — fix before moving to classifier.py")