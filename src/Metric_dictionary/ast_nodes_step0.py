"""
ast_nodes.py
────────────
PURPOSE:
    Pure data shapes for the DAX AST (Abstract Syntax Tree).
    NO logic here. NO parsing here. NO SQL here.
    This file only defines what nodes LOOK LIKE.

RULE:
    Every other stage2 file imports from here.
    Never define AST shapes anywhere else.

HOW TO READ THIS FILE:
    Top -> Bottom = Leaf nodes first, then expression nodes,
    then block nodes, then result nodes.

    Leaf nodes  = no children  (ColumnRef, MeasureRef, literals)
    Expr nodes  = have children (FunctionCall, BinaryOp, etc.)
    Block nodes = structural   (VarDef, VarBlock)
    Result nodes= parser output (ParseSuccess, ParseFailure)

PATTERNS COVERED (from pattern_plus_edgecases.html):
    P1  Plain SUM               -> FunctionCall("SUM", [ColumnRef])
    P2  CALCULATE + COUNT       -> FunctionCall("CALCULATE", [FunctionCall("COUNT",...)])
    P3  DIVIDE simple           -> DivideNode(num, den, default_val=None)
    P4  DIVIDE × scalar         -> ScalarMultiplier(DivideNode(...), 12000)
    P5  CALCULATE + KEEPFILTERS -> FunctionCall("CALCULATE", [..., FunctionCall("KEEPFILTERS",...)])
    P6  KEEPFILTERS IN {set}    -> FunctionCall("KEEPFILTERS", [InSetExpr(...)])
    P7  CALCULATE inline filter -> FunctionCall("CALCULATE", [..., InlineFilter(...)])
    P8  VAR + boolean flag      -> VarBlock + BoolLiteral
    P9  Multi-flag CALCULATE    -> FunctionCall("CALCULATE", [..., InlineFilter, InlineFilter])
    P10 Measure / Measure       -> BinaryOp("/", MeasureRef, MeasureRef)
    P11 SAMEPERIODLASTYEAR      -> FunctionCall("SAMEPERIODLASTYEAR", [ColumnRef])
    P12 YoY / MoM ratio         -> VarBlock + DivideNode
    P13 MAX / MIN               -> FunctionCall("MAX", [ColumnRef])
    P14 ALL() context remover   -> FunctionCall("ALL", [ColumnRef])
    P22 ABS() wrapper           -> FunctionCall("ABS", [...])

EDGE CASES ENCODED IN THESE NODES:
    EC1   +0 suffix         -> stripped by cleaner before parsing; never reaches AST
    EC2   IN {} curly       -> InSetExpr.values (list of strings, braces already stripped)
    EC3   <> operator       -> BinaryOp(op="<>") — sql_generator maps to !=
    EC4   ALL() present     -> FunctionCall("ALL", ...) — sql_generator skips date filter
    EC8   TRUE() vs TRUE    -> both -> BoolLiteral(True) — parser normalizes
    EC9   "true" string     -> StringLiteral("true") — DIFFERENT from BoolLiteral(True)
    EC10  * scalar          -> ScalarMultiplier.multiplier (float)
    EC16  CALCULATE no fil  -> FunctionCall("CALCULATE", args=[one_expr]) — no filter args
    EC18  AVERAGE           -> FunctionCall("AVERAGE", ...) — sql_generator maps to AVG
    EC19  DIVIDE 2 vs 3 arg -> DivideNode.default_val = None vs 0
    EC22  Typo passthrough  -> StringLiteral("Undoumented") — parser doesn't validate values
    EC24  inline vs KEEPF   -> InlineFilter.has_keepfilters tracks this
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


# ══════════════════════════════════════════════════════════════
# LEAF NODES  —  no children, terminal values
# ══════════════════════════════════════════════════════════════

@dataclass
class ColumnRef:
    """
    A reference to a column inside a table.

    Formats parser handles:
        risk_core[risk_value]          -> table="risk_core",  column="risk_value"
        'date'[month_of_date]          -> table="date",       column="month_of_date"
        'Y Axis scatter plot'[Y axis]  -> table="Y Axis scatter plot", column="Y axis"

    NOTE:
        Quotes around table name are STRIPPED by the parser.
        table is always stored without surrounding quotes.

    Used in:
        P1  SUM(attribution[member_count])
        P5  risk_core[risk_documentation_flag]
        P6  KEEPFILTERS(risk_core[risk_documentation_flag] IN {...})
        P8  risk_core[max_month_flag] = TRUE()
        P11 SAMEPERIODLASTYEAR('date'[month_of_date])
        P13 MAX(risk_core[month_of_measurement])
        P14 ALL('DATE')
    """
    table:  str
    column: str


@dataclass
class MeasureRef:
    """
    A reference to another DAX measure by name.
    Written as [MeasureName] in DAX.

    Examples:
        [#Members]                     -> MeasureRef(name="#Members")
        [Members with open coding gaps]-> MeasureRef(name="Members with open coding gaps")
        [IP Discharges]                -> MeasureRef(name="IP Discharges")

    NOTE:
        The parser extracts the name WITHOUT square brackets.
        dep_resolver.py resolves these -> SQL later.
        The parser itself does NOT resolve them.

    Used in:
        P10  [Members with open coding gaps] / [#Members]
        P12  DIVIDE([#Members] - py, py, 0)
        P15  CALCULATE([#Members], SAMEPERIODLASTYEAR(...))
        P16  VAR a = [#Members YoY]
    """
    name: str


@dataclass
class VarRef:
    """
    A reference to a variable defined in the same VAR block.
    Written as just the variable name (no brackets) after VAR...RETURN.

    Examples:
        VAR a = SUM(...)
        VAR b = SUM(...)
        RETURN DIVIDE(a, b)   ← a and b here are VarRef nodes

    NOTE:
        VarRef.name is case-preserved from DAX source.
        sql_generator resolves VarRef -> the SQL of its VarDef.

    Used in:
        P4   RETURN DIVIDE(Num, Denom) * 12000
        P6   RETURN DIVIDE(a, b)
        P12  RETURN DIVIDE([#Members] - py, py, 0)
    """
    name: str


@dataclass
class StringLiteral:
    """
    A DAX string value, written in double quotes.

    Examples:
        "Documented"       -> StringLiteral(value="Documented")
        "Home Health"      -> StringLiteral(value="Home Health")
        "Undoumented"      -> StringLiteral(value="Undoumented")  ← EC22: typo passthrough
        "true"             -> StringLiteral(value="true")          ← EC9: NOT a boolean!

    EC9 CRITICAL:
        "true" (double-quoted string) -> StringLiteral("true")
        TRUE or TRUE()               -> BoolLiteral(True)
        These are DIFFERENT types. SQL column type determines which to use.
        Parser must NOT convert "true" strings to BoolLiteral.

    EC22:
        Typos like "Undoumented" are stored as-is.
        cleaner.py logs a warning but passes through.
        SQL will return no rows silently — known limitation.
    """
    value: str


@dataclass
class NumberLiteral:
    """
    A numeric constant in DAX.

    Examples:
        0        -> NumberLiteral(value=0.0)
        1        -> NumberLiteral(value=1.0)
        12000    -> NumberLiteral(value=12000.0)   ← EC10: annualization multiplier
        0.5      -> NumberLiteral(value=0.5)

    NOTE:
        Always stored as float for uniformity.
        sql_generator emits int when value == int(value), else float.
    """
    value: float


@dataclass
class BoolLiteral:
    """
    A DAX boolean value.

    EC8 — TWO forms that both become BoolLiteral(True):
        TRUE()   -> BoolLiteral(value=True)   ← function call form (File1)
        TRUE     -> BoolLiteral(value=True)   ← keyword form    (File2)
        FALSE()  -> BoolLiteral(value=False)
        FALSE    -> BoolLiteral(value=False)

    EC9 CRITICAL:
        "true"  (string in double quotes) -> StringLiteral("true")  ← NOT this node!
        This node is ONLY for unquoted TRUE / TRUE() / FALSE / FALSE().

    Used in:
        P8  risk_core[max_month_flag] = TRUE()
        P8  pac_opp_patient_view[readmission_flag] = TRUE
    """
    value: bool


# ══════════════════════════════════════════════════════════════
# EXPRESSION NODES  —  have children, build up expressions
# ══════════════════════════════════════════════════════════════

@dataclass
class FunctionCall:
    """
    Any DAX function call: FUNCNAME(arg1, arg2, ...).

    name is ALWAYS stored UPPERCASE regardless of DAX source case.
    (cleaner.py normalizes keywords; parser uppercases function names.)

    Examples:
        SUM(attribution[member_count])
            -> FunctionCall("SUM", [ColumnRef("attribution","member_count")])

        CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(...))
            -> FunctionCall("CALCULATE", [
                FunctionCall("SUM", [ColumnRef(...)]),
                FunctionCall("KEEPFILTERS", [...])
              ])

        COUNTROWS(cohort)
            -> FunctionCall("COUNTROWS", [ColumnRef("cohort", "*")])
            NOTE: COUNTROWS takes a table, not a column. parser sets column="*"

        CALCULATE(count(pac_opp_patient_view[visit_id]))  ← EC16
            -> FunctionCall("CALCULATE", [
                FunctionCall("COUNT", [ColumnRef(...)])
              ])
            No filter args = CALCULATE wrapper adds nothing.
            classifier.py detects this and treats as plain COUNT.

        AVERAGE(pac_view[pac_length_of_stay])  ← EC18
            -> FunctionCall("AVERAGE", [ColumnRef(...)])
            sql_generator maps AVERAGE -> AVG()

        ABS(SUM(attribution[ytd_visit_amount]))  ← EC23
            -> FunctionCall("ABS", [
                FunctionCall("SUM", [ColumnRef(...)])
              ])

        ALL('DATE')  ← EC4
            -> FunctionCall("ALL", [ColumnRef("DATE", "*")])
            sql_generator: if ALL present -> skip date filter injection

        SAMEPERIODLASTYEAR('date'[month_of_date])  ← P11
            -> FunctionCall("SAMEPERIODLASTYEAR", [ColumnRef("date","month_of_date")])

    NOTE on KEEPFILTERS:
        KEEPFILTERS is stored as a FunctionCall like any other.
        Its args contain the filter expression (BinaryOp, InSetExpr, etc.)
        sql_generator recognizes KEEPFILTERS by name and generates WHERE clause.
    """
    name: str          # ALWAYS uppercase
    args: list[Any]    # list of any node type


@dataclass
class DivideNode:
    """
    DAX DIVIDE function — special-cased because 2-arg vs 3-arg
    generates DIFFERENT SQL.

    EC19 — TWO forms:
        DIVIDE(a, b)      -> default_val=None -> SQL: a / NULLIF(b, 0)   returns NULL on /0
        DIVIDE(a, b, 0)   -> default_val=0.0  -> SQL: COALESCE(a / NULLIF(b, 0), 0)

    EC19b — File1 uses DIVIDE(x, py, 0), File2 uses DIVIDE(x, pm) — different behavior!
        Check which is expected before choosing COALESCE vs NULL.

    Examples:
        DIVIDE(SUM(attribution[ytd_visit_amount]), SUM(attribution[ytd_member_count]))
            -> DivideNode(
                numerator   = FunctionCall("SUM", [...ytd_visit_amount]),
                denominator = FunctionCall("SUM", [...ytd_member_count]),
                default_val = None
              )

        DIVIDE([#Members] - py, py, 0)
            -> DivideNode(
                numerator   = BinaryOp("-", MeasureRef("#Members"), VarRef("py")),
                denominator = VarRef("py"),
                default_val = 0.0
              )

    NOTE:
        Parser creates DivideNode instead of FunctionCall("DIVIDE", ...).
        This makes 2-arg vs 3-arg distinction explicit and impossible to lose.
    """
    numerator:   Any
    denominator: Any
    default_val: Optional[float] = None   # None = DIVIDE(a,b), 0.0 = DIVIDE(a,b,0)


@dataclass
class BinaryOp:
    """
    left OPERATOR right — any binary expression.

    Operators seen in actual measures:
        =    equality filter        -> SQL =
        <>   not-equal filter (EC3) -> SQL !=
        >    greater than           -> SQL >
        <    less than              -> SQL <
        >=   greater or equal       -> SQL >=
        <=   less or equal          -> SQL <=
        +    addition               -> SQL +
        -    subtraction            -> SQL -
        *    multiplication         -> SQL *
        /    division               -> SQL / (but use DivideNode for DIVIDE())
        &    string concat (DAX)    -> SQL || (only in DISPLAY measures, out of scope)

    EC3:
        KEEPFILTERS(pac_view[pac_visit_type] <> "Home Health")
            -> BinaryOp(op="<>", left=ColumnRef(...), right=StringLiteral("Home Health"))
        sql_generator maps op "<>" -> "!="

    Examples:
        risk_core[risk_documentation_flag] = "Documented"
            -> BinaryOp("=", ColumnRef("risk_core","risk_documentation_flag"),
                             StringLiteral("Documented"))

        risk_core[max_month_flag] = TRUE()
            -> BinaryOp("=", ColumnRef("risk_core","max_month_flag"),
                             BoolLiteral(True))

        [#Members] - py
            -> BinaryOp("-", MeasureRef("#Members"), VarRef("py"))

        ABS(SUM(x)) + SUM(y)
            -> BinaryOp("+", FunctionCall("ABS",[FunctionCall("SUM",[...])]),
                             FunctionCall("SUM",[...]))
    """
    op:    str    # one of: = <> > < >= <= + - * / &
    left:  Any
    right: Any


@dataclass
class InSetExpr:
    """
    DAX set membership: column IN {"val1", "val2", ...}

    EC2 — DAX uses CURLY BRACES {}, SQL uses PARENTHESES ():
        DAX: KEEPFILTERS(risk_core[risk_documentation_flag] IN {"Undocumented","Suspected"})
        SQL: WHERE risk_documentation_flag IN ('Undocumented', 'Suspected')

    The parser strips curly braces and stores values as plain strings.
    sql_generator emits SQL IN (...) with proper quoting.

    EC22:
        Typo values like "Undoumented" stored as-is in values list.
        Cleaner logs warning. Parser passes through unchanged.

    Examples:
        KEEPFILTERS(risk_core[risk_documentation_flag] IN {"Undocumented","Suspected"})
            -> FunctionCall("KEEPFILTERS", [
                InSetExpr(
                    column = ColumnRef("risk_core", "risk_documentation_flag"),
                    values = ["Undocumented", "Suspected"]
                )
              ])

        cohort[risk_documentation_flag] IN {"Undoumented","Suspected"}  ← EC22 typo
            -> InSetExpr(
                column = ColumnRef("cohort", "risk_documentation_flag"),
                values = ["Undoumented", "Suspected"]   ← stored as-is
              )
    """
    column: ColumnRef
    values: list[str]   # plain strings, quotes stripped, curly braces stripped


@dataclass
class CompoundAnd:
    """
    Two filter conditions joined with && (DAX logical AND).

    EC9 (B9 in old system):
        col = TRUE() && col = "X"
            -> CompoundAnd(
                left  = BinaryOp("=", ColumnRef(...), BoolLiteral(True)),
                right = BinaryOp("=", ColumnRef(...), StringLiteral("X"))
              )
        SQL: WHERE cond1 AND cond2

    NOTE:
        In practice CALCULATE(..., filter1, filter2) with multiple filter args
        also becomes AND in SQL. CompoundAnd is specifically for the &&
        operator INSIDE a single KEEPFILTERS argument.

    Example:
        KEEPFILTERS(risk_core[max_month_flag] = TRUE() && risk_core[flag] = "X")
            -> FunctionCall("KEEPFILTERS", [
                CompoundAnd(
                    left  = BinaryOp("=", ColumnRef(...,"max_month_flag"), BoolLiteral(True)),
                    right = BinaryOp("=", ColumnRef(...,"flag"), StringLiteral("X"))
                )
              ])
    """
    left:  Any
    right: Any


@dataclass
class InlineFilter:
    """
    A filter argument inside CALCULATE that has NO KEEPFILTERS wrapper.

    EC24 — DAX semantic difference (but SQL output is the same):
        WITH    KEEPFILTERS: CALCULATE(expr, KEEPFILTERS(col = "val"))
            -> respects existing report filters (additive)
        WITHOUT KEEPFILTERS: CALCULATE(expr, col = "val")
            -> overrides existing report filters

        Both -> SQL: WHERE col = 'val'
        has_keepfilters flag documents which form was in the source.

    Used in:
        P7  CALCULATE(DIVIDE(...), pac_view[pac_visit_type] = "Hospice")
        P9  CALCULATE(DISTINCTCOUNT(...), pac_view[readmission_flag]="true",
                                          pac_view[last_transfer]="true")

    Examples:
        pac_view[pac_visit_type] = "Hospice"  (bare, inside CALCULATE)
            -> InlineFilter(
                expr            = BinaryOp("=", ColumnRef(...), StringLiteral("Hospice")),
                has_keepfilters = False
              )

        KEEPFILTERS(risk_core[flag] = "Documented")  (inside CALCULATE)
            -> InlineFilter(
                expr            = BinaryOp("=", ColumnRef(...), StringLiteral("Documented")),
                has_keepfilters = True
              )

    NOTE:
        sql_generator uses expr to build the WHERE clause.
        has_keepfilters is metadata only — does not change SQL output.
    """
    expr:            Any    # the filter condition (BinaryOp, InSetExpr, etc.)
    has_keepfilters: bool   # True if originally wrapped in KEEPFILTERS()


@dataclass
class ScalarMultiplier:
    """
    base_expr * scalar — annualization or rate conversion multiplier.

    EC10:
        DIVIDE(Num, Denom) * 12000
            -> ScalarMultiplier(
                base_expr  = DivideNode(...),
                multiplier = 12000.0
              )
        SQL: (divide_sql) * 12000

    WHY A SEPARATE NODE:
        Easy to miss the * 12000 if you only look for DIVIDE().
        Making it a dedicated node forces sql_generator to handle it explicitly.

    NOTE:
        multiplier is always on the RIGHT side of *.
        If the DAX has 12000 * DIVIDE(...), parser normalizes to
        ScalarMultiplier(base_expr=DivideNode(...), multiplier=12000.0).

    Used in:
        P4  DIVIDE(Num, Denom) * 12000  (Utilization measure)
    """
    base_expr:  Any     # the expression being multiplied (usually DivideNode)
    multiplier: float   # the scalar value (12000.0, 100.0, etc.)


# ══════════════════════════════════════════════════════════════
# BLOCK NODES  —  structural, for VAR...RETURN
# ══════════════════════════════════════════════════════════════

@dataclass
class VarDef:
    """
    A single VAR definition inside a VAR block.

    Examples:
        VAR a = SUM(risk_core[risk_value])
            -> VarDef(name="a", expr=FunctionCall("SUM", [ColumnRef(...)]))

        VAR py = CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))
            -> VarDef(name="py", expr=FunctionCall("CALCULATE", [...]))

        VAR Num = CALCULATE(count(pac_view[join_key]))
            -> VarDef(name="Num", expr=FunctionCall("CALCULATE", [FunctionCall("COUNT",[...])]))

    NOTE:
        name is case-preserved from DAX source.
        VarRef uses the same case when referencing this variable.
    """
    name: str
    expr: Any


@dataclass
class VarBlock:
    """
    Full VAR...RETURN structure.

    Examples:
        VAR a = CALCULATE(SUM(risk_core[risk_value]),
                  KEEPFILTERS(risk_core[risk_documentation_flag] IN {"Undocumented","Suspected"}))
        VAR b = CALCULATE(SUM(risk_core[patient_count]),
                  KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))
        RETURN DIVIDE(a, b)

            -> VarBlock(
                bindings = [
                    VarDef("a", FunctionCall("CALCULATE", [...])),
                    VarDef("b", FunctionCall("CALCULATE", [...]))
                ],
                return_expr = DivideNode(VarRef("a"), VarRef("b"), default_val=None)
              )

        VAR Num = CALCULATE(count(pac_view[join_key]))
        VAR Denom = SUM(attribution[member_count])
        RETURN DIVIDE(Num, Denom) * 12000

            -> VarBlock(
                bindings = [
                    VarDef("Num",   FunctionCall("CALCULATE", [...])),
                    VarDef("Denom", FunctionCall("SUM",       [...]))
                ],
                return_expr = ScalarMultiplier(
                    base_expr  = DivideNode(VarRef("Num"), VarRef("Denom")),
                    multiplier = 12000.0
                )
              )

    IMPORTANT:
        bindings is a LIST not a dict — order matters.
        A variable can reference a previously defined variable in the same block.
        VAR c = a + b  (where a and b are defined before c) is valid DAX.
        sql_generator processes bindings in order.
    """
    bindings:    list[VarDef]   # in declaration order — DO NOT reorder
    return_expr: Any


# ══════════════════════════════════════════════════════════════
# RESULT NODES  —  what the parser returns
# ══════════════════════════════════════════════════════════════

@dataclass
class ParseSuccess:
    """
    Parser successfully built an AST for this measure.

    Fields:
        measure_name  : the measure's display name (from measures_resolved.json)
        ast           : the root node of the AST tree

    The ast can be any node type — whatever the top-level expression is:
        Plain SUM   -> FunctionCall("SUM", [...])
        VAR block   -> VarBlock(...)
        Ratio       -> BinaryOp("/", MeasureRef(...), MeasureRef(...))
        CALCULATE   -> FunctionCall("CALCULATE", [...])
    """
    measure_name: str
    ast:          Any


@dataclass
class ParseFailure:
    """
    Parser could not build an AST for this measure.

    Fields:
        measure_name : the measure's display name
        error        : human-readable description of what went wrong
        dax_text     : the clean DAX that failed (for debugging + LLM fallback)

    What happens next:
        ParseFailure -> pipeline routes to Step 8 (llm_fallback.py)
        llm_fallback assigns role="BUILDER" — LLM generates SQL directly
        failure_type logged as PARSE_FAILED in execution_log.db

    RULE:
        Parser NEVER raises an exception outside its own module.
        All failures -> ParseFailure. Never None. Never exception.
    """
    measure_name: str
    error:        str
    dax_text:     str


# ══════════════════════════════════════════════════════════════
# TYPE ALIAS
# ══════════════════════════════════════════════════════════════

# ParseResult is what parser.py returns for each measure.
# Use this in type hints throughout the codebase.
ParseResult = ParseSuccess | ParseFailure


# ══════════════════════════════════════════════════════════════
# QUICK SANITY TEST  —  run: python ast_nodes.py
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    Build a few trees manually to confirm the shapes work.
    If this runs without error, ast_nodes.py is correct.

    Run from stage2/ folder:
        python ast_nodes.py
    """

    # ── P1: SUM(attribution[member_count]) ──────────────────
    p1 = FunctionCall(
        name = "SUM",
        args = [ColumnRef(table="attribution", column="member_count")]
    )
    assert p1.name == "SUM"
    assert p1.args[0].table == "attribution"
    assert p1.args[0].column == "member_count"
    print("P1 ✅  FunctionCall -> ColumnRef")

    # ── P3: DIVIDE(SUM(...), SUM(...)) ───────────────────────
    p3 = DivideNode(
        numerator   = FunctionCall("SUM", [ColumnRef("attribution","ytd_visit_amount")]),
        denominator = FunctionCall("SUM", [ColumnRef("attribution","ytd_member_count")]),
        default_val = None
    )
    assert p3.default_val is None
    print("P3 ✅  DivideNode 2-arg (default_val=None)")

    # ── P3 variant: DIVIDE(a, b, 0) ─────────────────────────
    p3b = DivideNode(
        numerator   = VarRef("a"),
        denominator = VarRef("b"),
        default_val = 0.0
    )
    assert p3b.default_val == 0.0
    print("P3b ✅ DivideNode 3-arg (default_val=0.0)")

    # ── P4: DIVIDE(Num, Denom) * 12000 ──────────────────────
    p4 = ScalarMultiplier(
        base_expr  = DivideNode(VarRef("Num"), VarRef("Denom"), None),
        multiplier = 12000.0
    )
    assert p4.multiplier == 12000.0
    assert isinstance(p4.base_expr, DivideNode)
    print("P4 ✅  ScalarMultiplier -> DivideNode")

    # ── P5: CALCULATE + KEEPFILTERS ─────────────────────────
    p5 = FunctionCall(
        name = "CALCULATE",
        args = [
            FunctionCall("SUM", [ColumnRef("risk_core","risk_value")]),
            InlineFilter(
                expr = BinaryOp(
                    op    = "=",
                    left  = ColumnRef("risk_core","risk_documentation_flag"),
                    right = StringLiteral("Documented")
                ),
                has_keepfilters = True
            )
        ]
    )
    assert p5.args[1].has_keepfilters is True
    assert p5.args[1].expr.right.value == "Documented"
    print("P5 ✅  CALCULATE + InlineFilter(has_keepfilters=True)")

    # ── EC3: <> operator ────────────────────────────────────
    ec3 = BinaryOp(
        op    = "<>",
        left  = ColumnRef("pac_view","pac_visit_type"),
        right = StringLiteral("Home Health")
    )
    assert ec3.op == "<>"
    print("EC3 ✅ BinaryOp op='<>'")

    # ── EC2: IN {set} ────────────────────────────────────────
    ec2 = InSetExpr(
        column = ColumnRef("risk_core","risk_documentation_flag"),
        values = ["Undocumented", "Suspected"]
    )
    assert ec2.values[0] == "Undocumented"
    print("EC2 ✅ InSetExpr with values list")

    # ── EC8: TRUE() and TRUE both -> BoolLiteral ─────────────
    ec8_with_parens    = BoolLiteral(value=True)
    ec8_without_parens = BoolLiteral(value=True)
    assert ec8_with_parens == ec8_without_parens
    print("EC8 ✅ BoolLiteral(True) == BoolLiteral(True)")

    # ── EC9: "true" string -> StringLiteral (NOT BoolLiteral) ─
    ec9_string  = StringLiteral("true")
    ec9_boolean = BoolLiteral(True)
    assert ec9_string != ec9_boolean
    assert type(ec9_string) is not type(ec9_boolean)
    print("EC9 ✅ StringLiteral('true') != BoolLiteral(True)  [different types]")

    # ── P6: VAR block + DIVIDE ──────────────────────────────
    p6 = VarBlock(
        bindings = [
            VarDef("a", FunctionCall("CALCULATE", [
                FunctionCall("SUM", [ColumnRef("risk_core","risk_value")]),
                InlineFilter(
                    expr = InSetExpr(
                        column = ColumnRef("risk_core","risk_documentation_flag"),
                        values = ["Undocumented","Suspected"]
                    ),
                    has_keepfilters = True
                )
            ])),
            VarDef("b", FunctionCall("CALCULATE", [
                FunctionCall("SUM", [ColumnRef("risk_core","patient_count")]),
                InlineFilter(
                    expr = BinaryOp("=",
                        ColumnRef("risk_core","risk_documentation_flag"),
                        StringLiteral("Documented")
                    ),
                    has_keepfilters = True
                )
            ]))
        ],
        return_expr = DivideNode(VarRef("a"), VarRef("b"), None)
    )
    assert p6.bindings[0].name == "a"
    assert p6.bindings[1].name == "b"
    assert isinstance(p6.return_expr, DivideNode)
    print("P6 ✅  VarBlock -> VarDef × 2 -> DivideNode(VarRef,VarRef)")

    # ── P10: [A] / [B] measure division ─────────────────────
    p10 = BinaryOp(
        op    = "/",
        left  = MeasureRef("Members with open coding gaps"),
        right = MeasureRef("#Members")
    )
    assert isinstance(p10.left, MeasureRef)
    assert p10.left.name == "Members with open coding gaps"
    print("P10 ✅ BinaryOp('/') -> MeasureRef, MeasureRef")

    # ── ParseSuccess and ParseFailure ───────────────────────
    ok   = ParseSuccess(measure_name="#Members", ast=p1)
    fail = ParseFailure(
        measure_name = "broken measure",
        error        = "Unexpected token at position 12",
        dax_text     = "SUM(broken["
    )
    assert ok.measure_name == "#Members"
    assert fail.error.startswith("Unexpected")
    print("✅  ParseSuccess and ParseFailure shapes correct")

    # ── EC22: typo passthrough ──────────────────────────────
    ec22 = InSetExpr(
        column = ColumnRef("cohort","risk_documentation_flag"),
        values = ["Undoumented", "Suspected"]    # typo stored as-is
    )
    assert ec22.values[0] == "Undoumented"       # NOT corrected
    print("EC22 ✅ Typo 'Undoumented' stored as-is in InSetExpr")

    print("\n✅  All ast_nodes.py tests passed — shapes are correct.")
    print("    Next step: cleaner.py")