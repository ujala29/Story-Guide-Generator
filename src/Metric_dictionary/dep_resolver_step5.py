"""
dep_resolver.py
───────────────
Stage 2 — Step 3

PURPOSE:
    1. Walk every parsed AST and collect:
       - which OTHER measures this measure depends on (MeasureRef nodes)
       - which VAR binding names this measure defines (VarDef nodes)
    2. Build a dependency graph across all measures
    3. Return a topological order (leaves first) so pipeline processes
       measures in the correct bottom-up sequence
    4. Detect circular dependencies

INPUT:
    dict of {measure_name: ParseSuccess}  (from parser.py)

OUTPUT:
    DepResult dataclass:
        order        : list[str]   measure names, leaves first
        deps         : dict        {name: [direct_dep_names]}
        var_bindings : dict        {name: [var_binding_names]}
        circular     : list[str]   names of measures in cycles (usually empty)

WHY THIS MATTERS:
    DAX measures build on each other. Example:
        #Members            → SUM(attribution[member_count])
        #Members PY         → CALCULATE([#Members], SAMEPERIODLASTYEAR(...))
        #Members YoY        → VAR py = [#Members PY] ... RETURN DIVIDE(...)

    Processing order must be: #Members → #Members PY → #Members YoY
    Otherwise when we generate SQL for #Members YoY, we don't yet
    have the SQL for its dependencies.

VAR BINDINGS — why we collect them:
    Parser emits ColumnRef("py", "*") for bare identifiers like `py`.
    semantic_resolver needs to know: "is `py` a VAR binding in this measure,
    or is it a real table name?"

    var_bindings["#Members YoY"] = ["py"]
    → semantic_resolver sees ColumnRef("py","*") → checks var_bindings
    → "py" is in bindings → upgrade to VarRef("py")

ALGORITHM:
    Kahn's BFS topological sort (same as stage1/dependency_graph.py).
    MeasureRef scanning: walk AST recursively, collect all MeasureRef nodes.

REUSE FROM stage1/dependency_graph.py:
    Same Kahn's algorithm.
    Same topological_order() logic.
    ADDITION: var_bindings collection (new in stage2).
"""

from __future__ import annotations
import re as _re
from collections import defaultdict, deque


def _norm_name(name: str) -> str:
    """Normalize spaces around operators so 'Cost / Admit' matches 'Cost/Admit'."""
    return _re.sub(r'\s*([/+\-*])\s*', r'\1', name)
from dataclasses import dataclass, field
from typing import Any

from ast_nodes_step0 import (
    MeasureRef, VarBlock, VarDef, FunctionCall, DivideNode,
    BinaryOp, InSetExpr, CompoundAnd, InlineFilter,
    ScalarMultiplier, ParseSuccess,
)


# ══════════════════════════════════════════════════════════════
# RESULT
# ══════════════════════════════════════════════════════════════

@dataclass
class DepResult:
    """
    Output of resolve().

    Fields:
        order        : measure names sorted leaves-first (safe processing order)
        deps         : {measure_name: [direct_dep_measure_names]}
        var_bindings : {measure_name: [var_binding_names_defined_in_this_measure]}
        circular     : measure names involved in dependency cycles
                       (should be empty for well-formed DAX)
    """
    order:        list[str]
    deps:         dict[str, list[str]]
    var_bindings: dict[str, list[str]]
    circular:     list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# AST WALKERS
# ══════════════════════════════════════════════════════════════

def collect_measure_refs(ast: Any, found: set[str] = None) -> set[str]:
    """
    Walk an AST recursively and collect all MeasureRef.name values.

    These are the OTHER measures this measure depends on.
    e.g. [#Members PY] → adds "#Members PY" to found set.

    Args:
        ast   : any AST node (root of the tree)
        found : accumulator set (created fresh if None)

    Returns:
        set of measure name strings
    """
    if found is None:
        found = set()

    if ast is None:
        return found

    # Leaf: MeasureRef — this is what we're collecting
    if isinstance(ast, MeasureRef):
        found.add(ast.name)
        return found

    # VarBlock: walk bindings + return_expr
    if isinstance(ast, VarBlock):
        for vd in ast.bindings:
            collect_measure_refs(vd.expr, found)
        collect_measure_refs(ast.return_expr, found)
        return found

    # FunctionCall: walk all args
    if isinstance(ast, FunctionCall):
        for arg in ast.args:
            collect_measure_refs(arg, found)
        return found

    # DivideNode: walk numerator + denominator + default_val
    if isinstance(ast, DivideNode):
        collect_measure_refs(ast.numerator,   found)
        collect_measure_refs(ast.denominator, found)
        if ast.default_val is not None:
            pass   # default_val is float — no AST nodes inside
        return found

    # BinaryOp: walk left + right
    if isinstance(ast, BinaryOp):
        collect_measure_refs(ast.left,  found)
        collect_measure_refs(ast.right, found)
        return found

    # InSetExpr: walk column (ColumnRef — no MeasureRefs inside)
    if isinstance(ast, InSetExpr):
        return found   # values are plain strings, column is ColumnRef

    # CompoundAnd: walk left + right
    if isinstance(ast, CompoundAnd):
        collect_measure_refs(ast.left,  found)
        collect_measure_refs(ast.right, found)
        return found

    # InlineFilter: walk expr
    if isinstance(ast, InlineFilter):
        collect_measure_refs(ast.expr, found)
        return found

    # ScalarMultiplier: walk base_expr
    if isinstance(ast, ScalarMultiplier):
        collect_measure_refs(ast.base_expr, found)
        return found

    # Leaf nodes with no children: ColumnRef, VarRef, StringLiteral,
    # NumberLiteral, BoolLiteral — nothing to walk
    return found


def collect_var_bindings(ast: Any) -> list[str]:
    """
    Walk an AST and collect all VAR binding names defined in this measure.

    These names are used by semantic_resolver to identify bare identifiers
    that should become VarRef (not ColumnRef).

    Example:
        VAR py    = CALCULATE(...)
        VAR delta = [#Members] - py
        RETURN DIVIDE(delta, py, 0)

        → ["py", "delta"]

    Returns:
        list of var binding name strings (in declaration order)
    """
    if not isinstance(ast, VarBlock):
        return []
    return [vd.name for vd in ast.bindings]


# ══════════════════════════════════════════════════════════════
# DEPENDENCY RESOLVER
# ══════════════════════════════════════════════════════════════

def resolve(parse_results: dict[str, ParseSuccess]) -> DepResult:
    """
    Build dependency graph and topological order for all parsed measures.

    Args:
        parse_results : dict of {measure_name: ParseSuccess}
                        Only ParseSuccess entries are processed.
                        ParseFailure entries should be excluded before calling.

    Returns:
        DepResult with order, deps, var_bindings, circular

    Algorithm:
        1. For each measure, walk its AST to find MeasureRef nodes.
        2. Filter: only keep refs that point to OTHER known measures.
        3. Build adjacency maps: deps[name] = [dep_names]
        4. Kahn's BFS topological sort (same as stage1).
        5. Collect var_bindings per measure.
        6. Detect any measures not reached by sort (circular deps).
    """
    all_names    = set(parse_results.keys())
    deps         = {}
    var_bindings = {}
    dependents   = defaultdict(list)   # reverse map: dep → [measures that use it]

    # ── Step 1 & 2: collect deps and var bindings ────────────
    for name, result in parse_results.items():
        ast = result.ast

        # MeasureRefs — only those pointing to known measures
        # Case-insensitive match: DAX [% Members] may differ in case from
        # measure name "% members" in parse_results dict
        raw_refs  = collect_measure_refs(ast)
        # Case-insensitive lookup (handles % Members vs % members etc.)
        lower_names = {n.lower(): n for n in all_names}

        def _resolve_ref(r):
            if r in all_names: return r
            found = lower_names.get(r.lower())
            if found: return found
            # Normalize spaces around operators: "Cost / Admit" → "Cost/Admit"
            r_norm = _norm_name(r)
            if r_norm in all_names: return r_norm
            return lower_names.get(r_norm.lower())

        known_refs = [_resolve_ref(r) for r in raw_refs
                      if _resolve_ref(r) and _resolve_ref(r) != name]
        deps[name] = list(set(known_refs))

        # VAR binding names
        var_bindings[name] = collect_var_bindings(ast)

        # Build reverse map for Kahn's
        for dep in deps[name]:
            dependents[dep].append(name)

    # ── Step 3: Kahn's BFS topological sort ──────────────────
    #
    # in_degree[name] = number of dependencies this measure has
    # Start queue with all measures that have 0 dependencies (leaves).
    # Process queue:
    #   - append current to order
    #   - for each measure that depends on current:
    #       decrement its in_degree
    #       if in_degree reaches 0 → add to queue

    in_degree = {name: len(deps[name]) for name in all_names}
    queue     = deque(n for n, d in in_degree.items() if d == 0)
    order     = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for dependent in dependents.get(node, []):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # ── Step 4: detect circular dependencies ─────────────────
    seen     = set(order)
    circular = [n for n in all_names if n not in seen]

    # Append circular measures at the end so pipeline can still attempt them
    order.extend(circular)

    return DepResult(
        order        = order,
        deps         = deps,
        var_bindings = var_bindings,
        circular     = circular,
    )


# ══════════════════════════════════════════════════════════════
# CONVENIENCE HELPERS  — used by pipeline.py
# ══════════════════════════════════════════════════════════════

def get_processing_order(dep_result: DepResult) -> list[str]:
    """Return measure names in safe processing order (leaves first)."""
    return dep_result.order


def get_var_bindings(dep_result: DepResult, measure_name: str) -> list[str]:
    """
    Return VAR binding names for a specific measure.
    Returns [] if measure has no VAR block.
    Used by semantic_resolver to upgrade ColumnRef("py","*") → VarRef("py").
    """
    return dep_result.var_bindings.get(measure_name, [])


def get_deps(dep_result: DepResult, measure_name: str) -> list[str]:
    """Return direct dependency names for a specific measure."""
    return dep_result.deps.get(measure_name, [])


# ══════════════════════════════════════════════════════════════
# SELF-TEST  —  run: python dep_resolver.py
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from ast_nodes import (
        ColumnRef, MeasureRef, VarRef, StringLiteral, NumberLiteral,
        BoolLiteral, FunctionCall, DivideNode, BinaryOp, InSetExpr,
        ScalarMultiplier, VarDef, VarBlock, ParseSuccess,
    )
    from parser import parse

    all_pass = True

    def check(label: str, condition: bool):
        global all_pass
        status = "✅" if condition else "❌"
        print(f"  {status}  {label}")
        if not condition:
            all_pass = False

    def make_success(name: str, dax: str) -> ParseSuccess:
        r = parse(name, dax)
        if not isinstance(r, ParseSuccess):
            print(f"  [SETUP ERROR: parse failed for {name!r}: {r.error}]")
            # Return a minimal ParseSuccess with a MeasureRef AST for testing
            return ParseSuccess(measure_name=name, ast=FunctionCall("SUM", [
                ColumnRef("attribution", "member_count")
            ]))
        return r

    print("=== dep_resolver.py self-test ===\n")

    # ── collect_measure_refs ─────────────────────────────────
    print("collect_measure_refs:")

    # Leaf measure — no MeasureRefs
    ast_leaf = FunctionCall("SUM", [ColumnRef("attribution", "member_count")])
    refs = collect_measure_refs(ast_leaf)
    check("leaf SUM → no refs",               refs == set())

    # Single MeasureRef
    ast_one = FunctionCall("CALCULATE", [
        MeasureRef("#Members"),
        FunctionCall("SAMEPERIODLASTYEAR", [ColumnRef("date", "month_of_date")])
    ])
    refs = collect_measure_refs(ast_one)
    check("CALCULATE([#Members],...) → {#Members}", refs == {"#Members"})

    # VarBlock with two MeasureRefs
    ast_yoy = VarBlock(
        bindings = [
            VarDef("py", FunctionCall("CALCULATE", [
                MeasureRef("#Members"),
                FunctionCall("SAMEPERIODLASTYEAR", [ColumnRef("date", "month_of_date")])
            ]))
        ],
        return_expr = DivideNode(
            BinaryOp("-", MeasureRef("#Members"), ColumnRef("py", "*")),
            ColumnRef("py", "*"),
            0.0
        )
    )
    refs = collect_measure_refs(ast_yoy)
    check("YoY block → {#Members}",            refs == {"#Members"})

    # BinaryOp MeasureRef / MeasureRef
    ast_ratio = BinaryOp("/",
        MeasureRef("Members with open coding gaps"),
        MeasureRef("#Members")
    )
    refs = collect_measure_refs(ast_ratio)
    check("[A]/[B] → {A, B}",                  refs == {
        "Members with open coding gaps", "#Members"
    })

    # InlineFilter — no MeasureRefs inside
    ast_filt = FunctionCall("CALCULATE", [
        FunctionCall("SUM", [ColumnRef("risk_core", "risk_value")]),
        InlineFilter(
            BinaryOp("=", ColumnRef("risk_core","flag"), StringLiteral("Documented")),
            has_keepfilters=True
        )
    ])
    refs = collect_measure_refs(ast_filt)
    check("CALCULATE+KEEPFILTERS → no refs",    refs == set())

    # ScalarMultiplier wrapping DivideNode
    ast_scalar = ScalarMultiplier(
        base_expr  = DivideNode(MeasureRef("A"), MeasureRef("B"), None),
        multiplier = 12000.0
    )
    refs = collect_measure_refs(ast_scalar)
    check("ScalarMultiplier → {A, B}",          refs == {"A", "B"})

    # ── collect_var_bindings ─────────────────────────────────
    print("\ncollect_var_bindings:")

    # Non-VAR measure → empty
    bindings = collect_var_bindings(FunctionCall("SUM", [ColumnRef("t","c")]))
    check("SUM measure → []",                  bindings == [])

    # VAR block with one binding
    ast_one_var = VarBlock(
        bindings    = [VarDef("py", FunctionCall("CALCULATE", [MeasureRef("#Members")]))],
        return_expr = DivideNode(ColumnRef("py","*"), ColumnRef("py","*"), 0.0)
    )
    bindings = collect_var_bindings(ast_one_var)
    check("1-binding VAR → ['py']",            bindings == ["py"])

    # VAR block with two bindings (order preserved)
    ast_two_var = VarBlock(
        bindings = [
            VarDef("Num",   FunctionCall("COUNT", [ColumnRef("t","id")])),
            VarDef("Denom", FunctionCall("SUM",   [ColumnRef("t","mc")])),
        ],
        return_expr = DivideNode(ColumnRef("Num","*"), ColumnRef("Denom","*"), None)
    )
    bindings = collect_var_bindings(ast_two_var)
    check("2-binding VAR order preserved",     bindings == ["Num", "Denom"])

    # ── resolve() — topological sort ────────────────────────
    print("\nresolve() — topological sort:")

    # Build a simple 3-measure chain:
    #   #Members       → leaf (SUM)
    #   #Members PY    → depends on #Members
    #   #Members YoY   → depends on #Members PY and #Members

    results = {
        "#Members": make_success(
            "#Members",
            "SUM(attribution[member_count])"
        ),
        "#Members PY": make_success(
            "#Members PY",
            "CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))"
        ),
        "#Members YoY": make_success(
            "#Members YoY",
            "VAR py = CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))\nRETURN DIVIDE([#Members] - py, py, 0)"
        ),
    }

    dr = resolve(results)

    check("no circular deps",                  dr.circular == [])
    check("order has 3 measures",              len(dr.order) == 3)

    # #Members must come before #Members PY and #Members YoY
    idx = {n: i for i, n in enumerate(dr.order)}
    check("#Members before #Members PY",
          idx["#Members"] < idx["#Members PY"])
    check("#Members before #Members YoY",
          idx["#Members"] < idx["#Members YoY"])
    check("#Members PY before #Members YoY",
          idx["#Members PY"] < idx["#Members YoY"])

    # deps dict
    check("#Members has no deps",              dr.deps["#Members"] == [])
    check("#Members PY depends on #Members",   "#Members" in dr.deps["#Members PY"])
    check("#Members YoY depends on #Members",  "#Members" in dr.deps["#Members YoY"])

    # ── var_bindings ─────────────────────────────────────────
    print("\nvar_bindings:")
    check("#Members has no var bindings",      dr.var_bindings["#Members"] == [])
    check("#Members PY has no var bindings",   dr.var_bindings["#Members PY"] == [])
    check("#Members YoY has var binding 'py'", "py" in dr.var_bindings["#Members YoY"])

    # ── Circular dependency detection ────────────────────────
    print("\nCircular dependency detection:")

    # Manually construct circular: A depends on B, B depends on A
    ast_a = BinaryOp("/", MeasureRef("B"), FunctionCall("SUM",[ColumnRef("t","c")]))
    ast_b = BinaryOp("/", MeasureRef("A"), FunctionCall("SUM",[ColumnRef("t","c")]))

    circular_results = {
        "A": ParseSuccess(measure_name="A", ast=ast_a),
        "B": ParseSuccess(measure_name="B", ast=ast_b),
    }
    dr_circ = resolve(circular_results)
    check("circular detected",                 len(dr_circ.circular) == 2)
    check("A and B in circular",               "A" in dr_circ.circular
                                               and "B" in dr_circ.circular)
    check("still in order (appended)",         len(dr_circ.order) == 2)

    # ── Leaf measures ────────────────────────────────────────
    print("\nLeaf measures (no deps):")
    leaf_results = {
        "PMPM"        : make_success("PMPM",
            "DIVIDE(SUM(attribution[ytd_visit_amount]), SUM(attribution[ytd_member_count]))"),
        "Documented risk": make_success("Documented risk",
            'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))'),
        "Filter"      : make_success("Filter",
            "ABS(SUM(attribution[ytd_visit_amount])) + SUM(attribution[ytd_member_count])"),
    }
    dr_leaf = resolve(leaf_results)
    check("3 leaf measures, no deps",          all(
        dr_leaf.deps[n] == [] for n in leaf_results
    ))
    check("no circular",                       dr_leaf.circular == [])
    check("all 3 in order",                    len(dr_leaf.order) == 3)

    # ── P10: measure ratio ────────────────────────────────────
    print("\nP10 — measure ratio [A]/[B]:")
    ratio_results = {
        "Members with open coding gaps": make_success(
            "Members with open coding gaps",
            "SUM(attribution[member_with_open_coding_gap_count])"
        ),
        "#Members": make_success(
            "#Members",
            "SUM(attribution[member_count])"
        ),
        "% members with open coding gaps": make_success(
            "% members with open coding gaps",
            "[Members with open coding gaps] / [#Members]"
        ),
    }
    dr_ratio = resolve(ratio_results)
    idx2 = {n: i for i, n in enumerate(dr_ratio.order)}
    check("leaf measures before ratio",
          idx2["Members with open coding gaps"] < idx2["% members with open coding gaps"]
          and idx2["#Members"]                  < idx2["% members with open coding gaps"])
    check("ratio deps correct",
          set(dr_ratio.deps["% members with open coding gaps"]) ==
          {"Members with open coding gaps", "#Members"})

    # ── Helper functions ─────────────────────────────────────
    print("\nHelper functions:")
    dr2 = resolve(results)
    check("get_processing_order returns list",      isinstance(get_processing_order(dr2), list))
    check("get_var_bindings('#Members YoY')",       "py" in get_var_bindings(dr2, "#Members YoY"))
    check("get_var_bindings('#Members')",            get_var_bindings(dr2, "#Members") == [])
    check("get_deps('#Members PY')",                 "#Members" in get_deps(dr2, "#Members PY"))
    check("get_deps('#Members')",                    get_deps(dr2, "#Members") == [])

    # ── Summary ─────────────────────────────────────────────
    print()
    if all_pass:
        print("✅  All dep_resolver.py tests passed.")
        print("    Next step: semantic_resolver.py")
    else:
        print("❌  Some tests failed — fix before moving to semantic_resolver.py")