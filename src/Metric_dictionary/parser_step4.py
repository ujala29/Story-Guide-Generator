"""
parser.py
─────────
Stage 2 — Step 2 (Part 2 of 2)

PURPOSE:
    Takes a LexResult (token list from lexer.py) and builds an AST
    using the node types defined in ast_nodes.py.

INPUT:
    LexResult from lexer.tokenize()

OUTPUT:
    ParseResult = ParseSuccess | ParseFailure
    (imported from ast_nodes.py)

ALGORITHM:
    Recursive Descent Parser — hand-written, no grammar library.
    One parse_* method per construct. Each method:
      - Consumes tokens from self._tokens via peek() / consume()
      - Returns an AST node on success
      - Raises _ParseError (internal only) on failure
      - _ParseError is always caught at the top level -> ParseFailure

NEVER raises outside this module.
All failures -> ParseFailure. Never None. Never Exception to caller.

PARSING RULES (what each method handles):

    parse()                 -> top-level entry point
    _parse_expr()           -> VAR block OR expression
    _parse_var_block()      -> VAR ... RETURN ...
    _parse_atom()           -> lowest precedence: binary ops / comparisons
    _parse_additive()       -> + and - (left-associative)
    _parse_multiplicative() -> * and / and ScalarMultiplier
    _parse_unary()          -> ABS(expr), unary minus
    _parse_primary()        -> function calls, column refs, literals, measure refs
    _parse_function_call()  -> FUNCNAME(arg, arg, ...)
    _parse_divide()         -> DIVIDE(num, den) or DIVIDE(num, den, default)
    _parse_calculate()      -> CALCULATE(expr, filter, filter, ...)
    _parse_column_ref()     -> table[column] or 'table'[column]
    _parse_measure_ref()    -> [MeasureName]
    _parse_in_set()         -> col IN {"v1", "v2"}
    _parse_filter_arg()     -> KEEPFILTERS(expr) or bare filter expression
    _parse_bool_literal()   -> TRUE / TRUE() / FALSE / FALSE()

EDGE CASES HANDLED:
    EC2   IN {set}             -> InSetExpr
    EC3   <> operator          -> BinaryOp(op="<>")
    EC4   ALL() present        -> FunctionCall("ALL", ...) — sql_generator uses this
    EC8   TRUE() and TRUE      -> BoolLiteral(True) — both forms
    EC9   "true" string        -> StringLiteral (NOT BoolLiteral)
    EC10  * scalar after DIVIDE -> ScalarMultiplier
    EC16  CALCULATE no filters -> FunctionCall("CALCULATE", [expr]) only
    EC18  AVERAGE              -> FunctionCall("AVERAGE", ...) — maps to AVG in SQL
    EC19  DIVIDE 2 vs 3 args   -> DivideNode.default_val = None vs 0.0
    EC24  inline filter        -> InlineFilter(has_keepfilters=False)
          with KEEPFILTERS     -> InlineFilter(has_keepfilters=True)
"""

from __future__ import annotations
from typing import Any, Optional

from ast_nodes_step0 import (
    ColumnRef, MeasureRef, VarRef, StringLiteral, NumberLiteral, BoolLiteral,
    FunctionCall, DivideNode, BinaryOp, InSetExpr, CompoundAnd,
    InlineFilter, ScalarMultiplier, VarDef, VarBlock,
    ParseSuccess, ParseFailure,
)
from lexer_step3 import Token, LexResult, tokenize


# ══════════════════════════════════════════════════════════════
# INTERNAL EXCEPTION  (never leaves this module)
# ══════════════════════════════════════════════════════════════

class _ParseError(Exception):
    """Internal parse error — always caught inside parse(), never raised to caller."""
    pass


# ══════════════════════════════════════════════════════════════
# PARSER CLASS
# ══════════════════════════════════════════════════════════════

class _Parser:
    """
    Recursive descent parser for DAX.

    Usage (internal — call module-level parse() instead):
        p      = _Parser(lex_result.tokens)
        result = p.parse(measure_name)
    """

    def __init__(self, tokens: list[Token]):
        self._tokens = tokens
        self._pos    = 0

    # ── Token navigation ────────────────────────────────────

    def _peek(self, offset: int = 0) -> Optional[Token]:
        """Return token at current pos + offset without consuming. None if past end."""
        idx = self._pos + offset
        return self._tokens[idx] if idx < len(self._tokens) else None

    def _peek_type(self, offset: int = 0) -> Optional[str]:
        """Return type of token at current pos + offset. None if past end."""
        t = self._peek(offset)
        return t.type if t else None

    def _peek_val(self, offset: int = 0) -> Optional[str]:
        """Return value of token at current pos + offset. None if past end."""
        t = self._peek(offset)
        return t.value if t else None

    def _consume(self, expected_type: str = None, expected_val: str = None) -> Token:
        """
        Consume and return the current token.
        Raises _ParseError if:
          - No more tokens
          - expected_type given and type doesn't match
          - expected_val given and value doesn't match
        """
        t = self._peek()
        if t is None:
            raise _ParseError(
                f"Unexpected end of input"
                + (f" — expected {expected_type}" if expected_type else "")
            )
        if expected_type and t.type != expected_type:
            raise _ParseError(
                f"Expected {expected_type} at pos {t.pos}, got {t.type}:{t.value!r}"
            )
        if expected_val and t.value != expected_val:
            raise _ParseError(
                f"Expected {expected_val!r} at pos {t.pos}, got {t.value!r}"
            )
        self._pos += 1
        return t

    def _at_end(self) -> bool:
        return self._pos >= len(self._tokens)

    def _remaining(self) -> int:
        return len(self._tokens) - self._pos

    # ── Top-level entry ─────────────────────────────────────

    def parse(self, measure_name: str, dax_text: str) -> ParseSuccess | ParseFailure:
        """
        Parse the token list into a ParseSuccess or ParseFailure.
        Never raises.
        """
        try:
            ast = self._parse_expr()
            # After parsing, there should be no tokens left
            if not self._at_end():
                leftover = self._peek()
                raise _ParseError(
                    f"Unexpected token after expression: "
                    f"{leftover.type}:{leftover.value!r} at pos {leftover.pos}"
                )
            return ParseSuccess(measure_name=measure_name, ast=ast)

        except _ParseError as e:
            return ParseFailure(
                measure_name=measure_name,
                error=str(e),
                dax_text=dax_text,
            )
        except Exception as e:
            return ParseFailure(
                measure_name=measure_name,
                error=f"Internal parser error: {e}",
                dax_text=dax_text,
            )

    # ── Expression levels (low -> high precedence) ───────────

    def _parse_expr(self) -> Any:
        """
        Top-level expression dispatcher.
        Handles VAR blocks — everything else goes to _parse_comparison.
        """
        if self._peek_type() == "IDENT" and self._peek_val() == "VAR":
            return self._parse_var_block()
        return self._parse_comparison()

    def _parse_comparison(self) -> Any:
        """
        Handles: expr = expr, expr <> expr, expr > expr, expr < expr,
                 expr >= expr, expr <= expr
        Also handles: expr IN {"v1","v2"}  (EC2)
        Also handles: expr && expr         (CompoundAnd)
        """
        left = self._parse_additive()

        # IN {set}  (EC2)
        # Fix2b: check uppercase IN (cleaner normalizes, but belt-and-suspenders)
        if (self._peek_type() == "IDENT"
                and self._peek_val().upper() == "IN"
                and self._peek_type(1) == "LBRACE"):
            if not isinstance(left, ColumnRef):
                raise _ParseError(
                    f"IN operator requires a column reference on the left, "
                    f"got {type(left).__name__}"
                )
            self._consume("IDENT")   # consume "IN"
            return self._parse_in_set_body(left)

        # Comparison operators
        op_map = {
            "EQ":  "=",
            "NEQ": "<>",   # EC3
            "GT":  ">",
            "LT":  "<",
            "GTE": ">=",
            "LTE": "<=",
        }
        if self._peek_type() in op_map:
            op_tok = self._consume()
            op     = op_map[op_tok.type]
            right  = self._parse_additive()
            left   = BinaryOp(op=op, left=left, right=right)

        # Compound AND:  left && right  (chain: a && b && c)
        # Fix4: after any comparison, check for && to chain conditions
        # e.g. t[f1] = TRUE() && t[f2] = "x"
        while self._peek_type() == "AND_AND":
            self._consume("AND_AND")
            right = self._parse_comparison()   # recursive for next condition
            left  = CompoundAnd(left=left, right=right)

        return left

    def _parse_additive(self) -> Any:
        """Handles + and - and & (left-associative).
        Fix3: & is DAX string concat — treat as BinaryOp like +
        Appears in: 'text' & [Measure], measure_a & measure_b
        """
        left = self._parse_multiplicative()

        while self._peek_type() in ("PLUS", "MINUS", "AMP"):
            op_tok = self._consume()
            if op_tok.type == "PLUS":
                op = "+"
            elif op_tok.type == "MINUS":
                op = "-"
            else:
                op = "&"   # string concat
            right = self._parse_multiplicative()
            left  = BinaryOp(op=op, left=left, right=right)

        return left

    def _parse_multiplicative(self) -> Any:
        """
        Handles * and /.
        Special case: DivideNode * NUMBER -> ScalarMultiplier (EC10).
        """
        left = self._parse_primary()

        while self._peek_type() in ("STAR", "SLASH"):
            op_tok = self._consume()

            if op_tok.type == "STAR":
                right = self._parse_primary()
                # EC10: DivideNode * scalar -> ScalarMultiplier
                if isinstance(right, NumberLiteral):
                    left = ScalarMultiplier(base_expr=left, multiplier=right.value)
                elif isinstance(left, NumberLiteral):
                    # scalar * expr — normalize to expr * scalar
                    left = ScalarMultiplier(base_expr=right, multiplier=left.value)
                else:
                    left = BinaryOp(op="*", left=left, right=right)
            else:
                # SLASH: plain division (not DIVIDE function)
                right = self._parse_primary()
                left  = BinaryOp(op="/", left=left, right=right)

        return left

    # ── Primary expressions ──────────────────────────────────

    def _parse_primary(self) -> Any:
        """
        Lowest-level expressions:
          - Function calls: SUM(...), CALCULATE(...), etc.
          - Column refs:    table[col] or 'table'[col]
          - Measure refs:   [MeasureName]
          - Var refs:       bare identifier inside VAR block
          - Literals:       string, number, bool
          - Parenthesised:  (expr)
        """
        t = self._peek()
        if t is None:
            raise _ParseError("Unexpected end of input in expression")

        # ── Parenthesised expression ─────────────────────────
        if t.type == "LPAREN":
            self._consume("LPAREN")
            inner = self._parse_expr()
            self._consume("RPAREN")
            return inner

        # ── Measure ref  [MeasureName] ───────────────────────
        if t.type == "LBRACKET":
            return self._parse_measure_ref()

        # ── String literal  "value" ──────────────────────────
        if t.type == "STRING":
            self._consume("STRING")
            return StringLiteral(value=t.value)

        # ── Number literal ───────────────────────────────────
        if t.type == "NUMBER":
            self._consume("NUMBER")
            val = float(t.value)
            return NumberLiteral(value=val)

        # ── Quoted table name  'table'[col] ──────────────────
        if t.type == "QUOTED_NAME":
            return self._parse_column_ref()

        # ── Identifier: function call, column ref, keyword, var ref ─
        if t.type == "IDENT":
            return self._parse_ident()

        raise _ParseError(
            f"Unexpected token {t.type}:{t.value!r} at pos {t.pos}"
        )

    def _parse_ident(self) -> Any:
        """
        Dispatches based on what follows the current IDENT:
          IDENT (          -> function call
          IDENT [          -> column ref (unquoted table)
          TRUE / FALSE     -> BoolLiteral (with or without ())
          VAR              -> shouldn't reach here (handled in _parse_expr)
          anything else    -> VarRef (variable reference inside VAR block)
        """
        t = self._peek()
        name_upper = t.value.upper()

        # ── TRUE / FALSE -> BoolLiteral (EC8) ─────────────────
        if name_upper in ("TRUE", "FALSE"):
            return self._parse_bool_literal()

        # ── Function call: IDENT followed by ( ───────────────
        if self._peek_type(1) == "LPAREN":
            return self._parse_function_call()

        # ── Column ref: IDENT followed by [ ──────────────────
        if self._peek_type(1) == "LBRACKET":
            return self._parse_column_ref()

        # ── VarRef vs bare table name (ColumnRef with col="*") ────
        # Rule: if NEXT token after this IDENT is RPAREN or COMMA,
        # this could be EITHER a VarRef (DIVIDE(a, b)) or a bare
        # table name (COUNTROWS(cohort)).
        #
        # We distinguish by checking if the identifier was defined
        # as a VAR name — but the parser doesn't track that scope.
        # Instead we use this heuristic:
        #   - lowercase / mixed-case short name  -> likely VarRef
        #   - but we cannot be sure at parse time
        #
        # Solution: return ColumnRef(name, "*") for bare identifiers
        # that look like table names (appear as sole arg to a function).
        # semantic_resolver will look them up; if not found as a table,
        # it stays as-is.
        #
        # For VAR references (DIVIDE(a, b)): these identifiers appear
        # INSIDE expressions where a table[col] would not make sense.
        # We check: if the PREVIOUS consumed token context suggests we're
        # inside a DIVIDE/arithmetic expression, return VarRef.
        #
        # Simplest correct approach: look at next token —
        #   RPAREN or COMMA -> could be either; return ColumnRef(name, "*")
        #   anything else   -> VarRef
        #
        # semantic_resolver will resolve: if it finds a table mapping -> ColumnRef
        # if no table found AND name matches a VAR binding -> treat as VarRef
        self._consume("IDENT")
        next_type = self._peek_type()
        if next_type in ("RPAREN", "COMMA", None):
            # Bare identifier as sole/last argument -> table-name-only ColumnRef
            return ColumnRef(table=t.value, column="*")
        # Otherwise: used in arithmetic/comparison context -> VarRef
        return VarRef(name=t.value)

    # ── Specific parsers ────────────────────────────────────

    def _parse_function_call(self) -> Any:
        """
        Parse any DAX function call: FUNCNAME(arg, arg, ...).

        Special cases dispatched here:
          DIVIDE    -> _parse_divide()   (EC19: 2 vs 3 args)
          CALCULATE -> _parse_calculate() (EC16, EC24)
        """
        name_tok = self._consume("IDENT")
        name     = name_tok.value.upper()

        # Special dispatch
        if name == "DIVIDE":
            return self._parse_divide()
        if name == "CALCULATE":
            return self._parse_calculate()

        # Generic function call
        self._consume("LPAREN")
        args = self._parse_arg_list()
        self._consume("RPAREN")

        return FunctionCall(name=name, args=args)

    def _parse_divide(self) -> Any:
        """
        Parse DIVIDE(numerator, denominator)
           or DIVIDE(numerator, denominator, default_val)

        EC19:
            DIVIDE(a, b)      -> DivideNode(a, b, default_val=None)  -> NULL on /0
            DIVIDE(a, b, 0)   -> DivideNode(a, b, default_val=0.0)   -> 0 on /0
        """
        self._consume("LPAREN")
        numerator = self._parse_expr()
        self._consume("COMMA")
        denominator = self._parse_expr()

        default_val = None
        if self._peek_type() == "COMMA":
            self._consume("COMMA")
            default_tok = self._parse_expr()
            if isinstance(default_tok, NumberLiteral):
                default_val = default_tok.value
            else:
                default_val = 0.0   # fallback if non-numeric default

        self._consume("RPAREN")
        return DivideNode(
            numerator   = numerator,
            denominator = denominator,
            default_val = default_val,
        )

    def _parse_calculate(self) -> Any:
        """
        Parse CALCULATE(expr, filter1, filter2, ...)

        EC16: CALCULATE(expr)  — no filters, just evaluation context wrapper
              -> FunctionCall("CALCULATE", [expr])  — classifier handles this

        EC24: filters can be:
              KEEPFILTERS(condition)  -> InlineFilter(expr=cond, has_keepfilters=True)
              bare condition          -> InlineFilter(expr=cond, has_keepfilters=False)
              other functions         -> passed as-is (ALL(), SAMEPERIODLASTYEAR(), etc.)
        """
        self._consume("LPAREN")
        # First arg is always the main expression
        main_expr = self._parse_expr()
        args = [main_expr]

        while self._peek_type() == "COMMA":
            self._consume("COMMA")
            arg = self._parse_filter_arg()
            args.append(arg)

        self._consume("RPAREN")
        return FunctionCall(name="CALCULATE", args=args)

    def _parse_filter_arg(self) -> Any:
        """
        Parse a CALCULATE filter argument.

        Three forms:
          1. KEEPFILTERS(condition)
                -> InlineFilter(expr=condition, has_keepfilters=True)
          2. ALL(...)  or  SAMEPERIODLASTYEAR(...)  or other functions
                -> parsed as regular function call (not wrapped in InlineFilter)
          3. bare condition: col = "val" or col IN {"v1"} or col = TRUE
                -> InlineFilter(expr=condition, has_keepfilters=False)
        """
        t = self._peek()

        # KEEPFILTERS(condition)
        if (t and t.type == "IDENT" and t.value.upper() == "KEEPFILTERS"
                and self._peek_type(1) == "LPAREN"):
            self._consume("IDENT")   # consume KEEPFILTERS
            self._consume("LPAREN")
            condition = self._parse_comparison()
            self._consume("RPAREN")
            return InlineFilter(expr=condition, has_keepfilters=True)

        # Other known CALCULATE modifiers that are NOT filter conditions
        # e.g. ALL('DATE'), SAMEPERIODLASTYEAR(...), USERELATIONSHIP(...)
        NON_FILTER_FUNCS = {
            "ALL", "ALLEXCEPT", "ALLSELECTED", "ALLNOBLANKROW",
            "SAMEPERIODLASTYEAR", "PREVIOUSMONTH", "PREVIOUSYEAR",
            "DATEADD", "USERELATIONSHIP", "CROSSFILTER",
            "REMOVEFILTERS",
        }
        if (t and t.type == "IDENT"
                and t.value.upper() in NON_FILTER_FUNCS
                and self._peek_type(1) == "LPAREN"):
            return self._parse_function_call()

        # Bare condition -> InlineFilter (EC24)
        condition = self._parse_comparison()
        return InlineFilter(expr=condition, has_keepfilters=False)

    def _parse_arg_list(self) -> list:
        """
        Parse comma-separated argument list (already past opening paren).
        Stops when RPAREN reached. Empty args allowed (e.g. TRUE()).
        """
        args = []
        if self._peek_type() == "RPAREN":
            return args   # empty arg list: TRUE()

        args.append(self._parse_expr())
        while self._peek_type() == "COMMA":
            self._consume("COMMA")
            args.append(self._parse_expr())

        return args

    def _parse_column_ref(self) -> ColumnRef:
        """
        Parse table[column] or 'table'[column].

        Handles:
            attribution[member_count]          -> ColumnRef("attribution","member_count")
            'date'[month_of_date]              -> ColumnRef("date","month_of_date")
            'Y Axis scatter plot'[Y axis]      -> ColumnRef("Y Axis scatter plot","Y axis")

        For COUNTROWS(table) — table name without [column]:
            The lexer produces IDENT:cohort.
            _parse_ident dispatches here when followed by [.
            But COUNTROWS arg has no [col] — handled in _parse_ident as VarRef fallback.
            We handle it here: if no LBRACKET after table name, treat as table-only ref.
        """
        # Table part
        t = self._peek()
        if t.type == "QUOTED_NAME":
            self._consume("QUOTED_NAME")
            table = t.value
        else:
            self._consume("IDENT")
            table = t.value

        # Column part: must have [col]
        if self._peek_type() != "LBRACKET":
            # Table reference without column (e.g. COUNTROWS(cohort))
            # Return ColumnRef with "*" as column sentinel
            return ColumnRef(table=table, column="*")

        self._consume("LBRACKET")

        # Column name — collect tokens until RBRACKET
        # Column names can contain spaces: 'Y Axis scatter plot'[Y axis]
        col_parts = []
        while self._peek_type() not in ("RBRACKET", None):
            col_parts.append(self._consume().value)
        self._consume("RBRACKET")

        column = " ".join(col_parts)
        return ColumnRef(table=table, column=column)

    def _parse_measure_ref(self) -> MeasureRef:
        """
        Parse [MeasureName] — a reference to another measure.

        Examples:
            [#Members]                     -> MeasureRef("#Members")
            [Members with open coding gaps]-> MeasureRef("Members with open coding gaps")
            [IP Discharges]                -> MeasureRef("IP Discharges")

        Measure names can contain spaces, #, %, and other special chars.
        We collect ALL tokens between [ and ] as the name.
        """
        self._consume("LBRACKET")
        parts = []
        while self._peek_type() not in ("RBRACKET", None):
            parts.append(self._consume().value)
        self._consume("RBRACKET")
        name = " ".join(parts)
        # Fix: "RAF recapture rate ( GROUP )" -> "RAF recapture rate (GROUP)"
        # Tokens join adds spaces inside parens — remove inner spaces only
        # " ( " -> " (" and " ) " -> ")"
        import re as _re_p
        name = _re_p.sub(r' [(] ', ' (', name)   # " ( " -> " ("
        name = _re_p.sub(r' [)] ', ') ', name)   # " ) " -> ") "
        name = _re_p.sub(r'[(] ', '(', name)     # "( " -> "("
        name = _re_p.sub(r' [)]', ')', name)     # " )" -> ")"
        name = name.strip()
        return MeasureRef(name=name)

    def _parse_in_set_body(self, column: ColumnRef) -> InSetExpr:
        """
        Parse {"val1", "val2", ...} after IN keyword.
        column is already parsed by the caller.

        EC2: DAX uses {} curly braces for sets.
        Values are stored as plain strings (quotes already stripped by lexer).
        """
        self._consume("LBRACE")
        values = []

        if self._peek_type() != "RBRACE":
            first = self._consume("STRING")
            values.append(first.value)
            while self._peek_type() == "COMMA":
                self._consume("COMMA")
                val = self._consume("STRING")
                values.append(val.value)

        self._consume("RBRACE")
        return InSetExpr(column=column, values=values)

    def _parse_bool_literal(self) -> BoolLiteral:
        """
        Parse TRUE, TRUE(), FALSE, FALSE() -> BoolLiteral.

        EC8: Both TRUE (keyword) and TRUE() (function call) map to BoolLiteral(True).
        EC9: "true" (string) is handled by _parse_primary as StringLiteral — NOT here.
        """
        t = self._consume("IDENT")
        value = t.value.upper() == "TRUE"

        # Consume () if present (TRUE() form)
        if self._peek_type() == "LPAREN":
            self._consume("LPAREN")
            self._consume("RPAREN")

        return BoolLiteral(value=value)

    def _parse_var_block(self) -> VarBlock:
        """
        Parse VAR name = expr ... VAR name = expr ... RETURN expr

        Examples:
            VAR a = SUM(risk_core[risk_value])
            VAR b = SUM(risk_core[patient_count])
            RETURN DIVIDE(a, b)

            VAR Num = CALCULATE(COUNT(pac_view[join_key]))
            VAR Denom = SUM(attribution[member_count])
            RETURN DIVIDE(Num, Denom) * 12000

        Rules:
            - bindings is a list (ORDER matters — vars can reference prior vars)
            - RETURN is required at the end
            - After RETURN, parse the full expression including ScalarMultiplier
        """
        bindings = []

        while (self._peek_type() == "IDENT"
               and self._peek_val() == "VAR"):
            self._consume("IDENT")  # consume VAR
            name_tok = self._consume("IDENT")
            self._consume("EQ")
            expr = self._parse_expr()
            bindings.append(VarDef(name=name_tok.value, expr=expr))

        # RETURN keyword
        if not (self._peek_type() == "IDENT" and self._peek_val() == "RETURN"):
            raise _ParseError(
                f"Expected RETURN after VAR bindings, "
                f"got {self._peek_type()}:{self._peek_val()!r}"
            )
        self._consume("IDENT")   # consume RETURN

        return_expr = self._parse_expr()
        return VarBlock(bindings=bindings, return_expr=return_expr)


# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════

def parse(measure_name: str, clean_dax: str) -> ParseSuccess | ParseFailure:
    """
    Parse a clean DAX string into a ParseSuccess or ParseFailure.

    Args:
        measure_name : display name of the measure (stored in result)
        clean_dax    : cleaned DAX string from CleanResult.clean_dax

    Returns:
        ParseSuccess(measure_name, ast)   on success
        ParseFailure(measure_name, error, dax_text)  on failure

    Never raises. Never returns None.

    Pipeline usage:
        from cleaner import clean
        from parser  import parse

        cr     = clean(name, raw_dax)
        result = parse(name, cr.clean_dax)

        if isinstance(result, ParseSuccess):
            ast = result.ast   # -> pass to semantic_resolver
        else:
            # result.error has the message
            # -> pipeline routes to llm_fallback
    """
    # Step 1: Lex
    lex_result = tokenize(clean_dax)
    if not lex_result.ok:
        return ParseFailure(
            measure_name = measure_name,
            error        = f"Lex error: {lex_result.error}",
            dax_text     = clean_dax,
        )

    if not lex_result.tokens:
        return ParseFailure(
            measure_name = measure_name,
            error        = "Empty token list — DAX is blank after cleaning",
            dax_text     = clean_dax,
        )

    # Step 2: Parse
    parser = _Parser(lex_result.tokens)
    return parser.parse(measure_name, clean_dax)


def parse_all(measures: dict) -> dict:
    """
    Parse all in-scope measures.

    Args:
        measures : dict of {name: {"clean_dax": str, ...}}
                   (from measures_in_scope.json)

    Returns:
        dict of {name: ParseSuccess | ParseFailure}
    """
    results = {}
    for name, m in measures.items():
        dax = m.get("clean_dax") or m.get("dax", "")
        results[name] = parse(name, dax)
    return results


# ══════════════════════════════════════════════════════════════
# SELF-TEST  —  run: python parser.py
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from ast_nodes import (
        ColumnRef, MeasureRef, VarRef, StringLiteral, NumberLiteral,
        BoolLiteral, FunctionCall, DivideNode, BinaryOp, InSetExpr,
        CompoundAnd, InlineFilter, ScalarMultiplier, VarDef, VarBlock,
        ParseSuccess, ParseFailure,
    )

    all_pass = True

    def check(label: str, condition: bool):
        global all_pass
        status = "✅" if condition else "❌"
        print(f"  {status}  {label}")
        if not condition:
            all_pass = False

    def ok(dax: str) -> Any:
        """Parse and return AST or raise if failed."""
        r = parse("test", dax)
        if isinstance(r, ParseFailure):
            print(f"      [PARSE FAILED: {r.error}]")
            return None
        return r.ast

    print("=== parser.py self-test ===\n")

    # ── P1: Plain SUM ────────────────────────────────────────
    print("P1 — Plain SUM:")
    ast = ok("SUM(attribution[member_count])")
    check("FunctionCall",               isinstance(ast, FunctionCall))
    check("name=SUM",                   ast and ast.name == "SUM")
    check("arg is ColumnRef",           ast and isinstance(ast.args[0], ColumnRef))
    check("table=attribution",          ast and ast.args[0].table == "attribution")
    check("column=member_count",        ast and ast.args[0].column == "member_count")

    # ── P1: MAX ──────────────────────────────────────────────
    print("\nP13 — MAX:")
    ast = ok("MAX(risk_core[month_of_measurement])")
    check("FunctionCall MAX",           isinstance(ast, FunctionCall) and ast.name == "MAX")
    check("ColumnRef correct",          ast and ast.args[0].table == "risk_core")

    # ── P2: COUNTROWS ────────────────────────────────────────
    print("\nP2 — COUNTROWS:")
    ast = ok("COUNTROWS(cohort)")
    check("FunctionCall COUNTROWS",     isinstance(ast, FunctionCall) and ast.name == "COUNTROWS")
    check("table=cohort, col=*",        ast and ast.args[0].table == "cohort"
                                        and ast.args[0].column == "*")

    # ── P2: CALCULATE + COUNT (EC16) ─────────────────────────
    print("\nEC16 — CALCULATE no filters:")
    ast = ok("CALCULATE(COUNT(pac_opp_patient_view[visit_id]))")
    check("FunctionCall CALCULATE",     isinstance(ast, FunctionCall) and ast.name == "CALCULATE")
    check("1 arg (no filters)",         ast and len(ast.args) == 1)
    check("inner is FunctionCall COUNT",ast and isinstance(ast.args[0], FunctionCall)
                                        and ast.args[0].name == "COUNT")

    # ── P3: DIVIDE 2-arg (EC19) ─────────────────────────────
    print("\nP3 — DIVIDE 2-arg (EC19):")
    ast = ok("DIVIDE(SUM(attribution[ytd_visit_amount]), SUM(attribution[ytd_member_count]))")
    check("DivideNode",                 isinstance(ast, DivideNode))
    check("default_val=None",           ast and ast.default_val is None)
    check("numerator is FunctionCall",  ast and isinstance(ast.numerator, FunctionCall))
    check("denominator is FunctionCall",ast and isinstance(ast.denominator, FunctionCall))

    # ── P3: DIVIDE 3-arg (EC19) ─────────────────────────────
    print("\nP3b — DIVIDE 3-arg (EC19):")
    ast = ok("DIVIDE(SUM(a[x]), SUM(a[y]), 0)")
    check("DivideNode",                 isinstance(ast, DivideNode))
    check("default_val=0.0",            ast and ast.default_val == 0.0)

    # ── P4: DIVIDE × scalar (EC10) ───────────────────────────
    print("\nP4 — DIVIDE × scalar (EC10):")
    dax = ("VAR Num = CALCULATE(COUNT(pac_view[join_key]))\n"
           "VAR Denom = SUM(attribution[member_count])\n"
           "RETURN DIVIDE(Num, Denom) * 12000")
    ast = ok(dax)
    check("VarBlock",                   isinstance(ast, VarBlock))
    check("2 bindings",                 ast and len(ast.bindings) == 2)
    check("binding[0] name=Num",        ast and ast.bindings[0].name == "Num")
    check("binding[1] name=Denom",      ast and ast.bindings[1].name == "Denom")
    check("return is ScalarMultiplier", ast and isinstance(ast.return_expr, ScalarMultiplier))
    check("multiplier=12000.0",         ast and ast.return_expr.multiplier == 12000.0)
    check("base_expr is DivideNode",    ast and isinstance(ast.return_expr.base_expr, DivideNode))
    check("num is ColumnRef(Num,*)",     ast and isinstance(ast.return_expr.base_expr.numerator, ColumnRef)
                                        and ast.return_expr.base_expr.numerator.table == "Num")  # VarRef resolved later by semantic_resolver

    # ── P5: CALCULATE + KEEPFILTERS ─────────────────────────
    print("\nP5 — CALCULATE + KEEPFILTERS:")
    dax = 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))'
    ast = ok(dax)
    check("FunctionCall CALCULATE",     isinstance(ast, FunctionCall) and ast.name == "CALCULATE")
    check("2 args",                     ast and len(ast.args) == 2)
    check("arg[0] is SUM",              ast and isinstance(ast.args[0], FunctionCall)
                                        and ast.args[0].name == "SUM")
    check("arg[1] is InlineFilter",     ast and isinstance(ast.args[1], InlineFilter))
    check("has_keepfilters=True",       ast and ast.args[1].has_keepfilters is True)
    f = ast.args[1].expr if ast else None
    check("filter is BinaryOp(=)",      isinstance(f, BinaryOp) and f.op == "=")
    check("right is StringLiteral",     isinstance(f.right, StringLiteral)
                                        and f.right.value == "Documented")

    # ── EC3: <> operator ─────────────────────────────────────
    print("\nEC3 — <> not-equal:")
    dax = 'CALCULATE(SUM(t[v]), KEEPFILTERS(t[type] <> "Home Health"))'
    ast = ok(dax)
    f = ast.args[1].expr if ast else None
    check("BinaryOp op='<>'",           isinstance(f, BinaryOp) and f.op == "<>")
    check("right=StringLiteral",        isinstance(f.right, StringLiteral)
                                        and f.right.value == "Home Health")

    # ── P6: KEEPFILTERS IN {set} (EC2) ──────────────────────
    print("\nP6 — KEEPFILTERS IN {set} (EC2):")
    dax = 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] IN {"Undocumented","Suspected"}))'
    ast = ok(dax)
    check("CALCULATE",                  isinstance(ast, FunctionCall) and ast.name == "CALCULATE")
    f = ast.args[1].expr if ast else None
    check("filter is InSetExpr",        isinstance(f, InSetExpr))
    check("values correct",             f and f.values == ["Undocumented", "Suspected"])
    check("column correct",             f and f.column.column == "risk_documentation_flag")

    # ── P7: Inline filter (EC24) ─────────────────────────────
    print("\nP7 — Inline filter no KEEPFILTERS (EC24):")
    dax = 'CALCULATE(SUM(t[v]), t[type] = "Hospice")'
    ast = ok(dax)
    check("CALCULATE",                  isinstance(ast, FunctionCall))
    check("arg[1] is InlineFilter",     ast and isinstance(ast.args[1], InlineFilter))
    check("has_keepfilters=False",      ast and ast.args[1].has_keepfilters is False)

    # ── P8: boolean flag (EC8) ───────────────────────────────
    print("\nEC8 — TRUE() and TRUE both -> BoolLiteral:")
    dax1 = "CALCULATE(SUM(t[v]), KEEPFILTERS(t[flag] = TRUE()))"
    dax2 = "CALCULATE(SUM(t[v]), KEEPFILTERS(t[flag] = TRUE))"
    ast1 = ok(dax1)
    ast2 = ok(dax2)
    f1 = ast1.args[1].expr if ast1 else None
    f2 = ast2.args[1].expr if ast2 else None
    check("TRUE() -> BoolLiteral(True)", isinstance(f1.right, BoolLiteral) and f1.right.value is True)
    check("TRUE  -> BoolLiteral(True)", isinstance(f2.right, BoolLiteral) and f2.right.value is True)

    # ── EC9: "true" string (EC9) ─────────────────────────────
    print('\nEC9 — "true" string -> StringLiteral:')
    dax = 'CALCULATE(COUNTROWS(t), t[flag] = "true")'
    ast = ok(dax)
    f = ast.args[1].expr if ast else None
    check("StringLiteral not BoolLiteral", isinstance(f.right, StringLiteral))
    check("value = 'true'",             f.right.value == "true")

    # ── P9: Multi-flag CALCULATE ─────────────────────────────
    print("\nP9 — Multi-flag CALCULATE:")
    dax = 'CALCULATE(DISTINCTCOUNT(t[id]), t[flag1] = "true", t[flag2] = "true")'
    ast = ok(dax)
    check("CALCULATE",                  isinstance(ast, FunctionCall))
    check("3 args",                     ast and len(ast.args) == 3)
    check("arg[1] InlineFilter",        ast and isinstance(ast.args[1], InlineFilter))
    check("arg[2] InlineFilter",        ast and isinstance(ast.args[2], InlineFilter))

    # ── P10: Measure / Measure ───────────────────────────────
    print("\nP10 — [A] / [B] measure division:")
    ast = ok("[Members with open coding gaps] / [#Members]")
    check("BinaryOp /",                 isinstance(ast, BinaryOp) and ast.op == "/")
    check("left is MeasureRef",         isinstance(ast.left, MeasureRef))
    check("left name correct",          ast.left.name == "Members with open coding gaps")
    check("right is MeasureRef",        isinstance(ast.right, MeasureRef))
    check("right name=#Members",        ast.right.name == "#Members")

    # ── P11: Time intelligence ───────────────────────────────
    print("\nP11 — SAMEPERIODLASTYEAR:")
    dax = "CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))"
    ast = ok(dax)
    check("CALCULATE",                  isinstance(ast, FunctionCall))
    check("arg[0] is MeasureRef",       ast and isinstance(ast.args[0], MeasureRef))
    check("arg[1] is InlineFilter(SPILY)", ast and isinstance(ast.args[1], FunctionCall)
                                        and ast.args[1].name == "SAMEPERIODLASTYEAR")
    spily = ast.args[1] if ast else None
    check("SPILY arg is ColumnRef",     spily and isinstance(spily.args[0], ColumnRef))
    check("SPILY table=date",           spily and spily.args[0].table == "date")

    # ── P12: YoY ratio ───────────────────────────────────────
    print("\nP12 — YoY VAR block:")
    dax = ("VAR py = CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))\n"
           "RETURN DIVIDE([#Members] - py, py, 0)")
    ast = ok(dax)
    check("VarBlock",                   isinstance(ast, VarBlock))
    check("1 binding",                  ast and len(ast.bindings) == 1)
    check("binding name=py",            ast and ast.bindings[0].name == "py")
    check("return is DivideNode",       ast and isinstance(ast.return_expr, DivideNode))
    check("default_val=0.0",            ast and ast.return_expr.default_val == 0.0)
    num = ast.return_expr.numerator if ast else None
    check("numerator is BinaryOp(-)",   isinstance(num, BinaryOp) and num.op == "-")
    check("left is MeasureRef(#Members)", isinstance(num.left, MeasureRef)
                                         and num.left.name == "#Members")
    check("right is ColumnRef(py,*)",   isinstance(num.right, ColumnRef)
                                        and num.right.table == "py")  # VarRef resolved by semantic_resolver

    # ── P14: ALL() ───────────────────────────────────────────
    print("\nP14 — ALL() context remover (EC4):")
    dax = "CALCULATE(MAX(cohort[month_of_measurement]), ALL('DATE'))"
    ast = ok(dax)
    check("CALCULATE",                  isinstance(ast, FunctionCall))
    # ALL is a NON_FILTER_FUNC so passed as FunctionCall, not InlineFilter
    all_arg = ast.args[1] if ast else None
    check("ALL arg is FunctionCall",    isinstance(all_arg, FunctionCall)
                                        and all_arg.name == "ALL")

    # ── P22: ABS ─────────────────────────────────────────────
    print("\nP22 — ABS() wrapper:")
    ast = ok("ABS(SUM(attribution[ytd_visit_amount])) + SUM(attribution[ytd_member_count])")
    check("BinaryOp +",                 isinstance(ast, BinaryOp) and ast.op == "+")
    check("left is FunctionCall ABS",   isinstance(ast.left, FunctionCall)
                                        and ast.left.name == "ABS")
    check("ABS inner is SUM",           isinstance(ast.left.args[0], FunctionCall)
                                        and ast.left.args[0].name == "SUM")

    # ── ParseFailure on bad input ────────────────────────────
    print("\nParseFailure:")
    r = parse("bad", "SUM(attribution[")
    check("returns ParseFailure",       isinstance(r, ParseFailure))
    check("error message set",          bool(r.error))
    check("dax_text preserved",         r.dax_text == "SUM(attribution[")

    # ── Quoted table name in measure ─────────────────────────
    print("\nQuoted table names:")
    ast = ok("SAMEPERIODLASTYEAR('date'[month_of_date])")
    check("FunctionCall SAMEPERIODLASTYEAR", isinstance(ast, FunctionCall))
    check("arg ColumnRef table=date",   ast and ast.args[0].table == "date")
    check("arg ColumnRef col=month_of_date", ast and ast.args[0].column == "month_of_date")

    # ── P6 full: VAR + IN {set} + DIVIDE ────────────────────
    print("\nP6 full — VAR + IN {set} + DIVIDE:")
    dax = (
        'VAR a = CALCULATE(SUM(risk_core[risk_value]),\n'
        '  KEEPFILTERS(risk_core[risk_documentation_flag] IN {"Undocumented","Suspected"}))\n'
        'VAR b = CALCULATE(SUM(risk_core[patient_count]),\n'
        '  KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))\n'
        'RETURN DIVIDE(a, b)'
    )
    ast = ok(dax)
    check("VarBlock",                   isinstance(ast, VarBlock))
    check("2 bindings",                 ast and len(ast.bindings) == 2)
    check("return is DivideNode",       ast and isinstance(ast.return_expr, DivideNode))
    check("default_val=None",           ast and ast.return_expr.default_val is None)
    a_expr = ast.bindings[0].expr if ast else None
    filt   = a_expr.args[1] if a_expr else None
    check("filter has_keepfilters=True", filt and filt.has_keepfilters is True)
    check("filter expr is InSetExpr",   filt and isinstance(filt.expr, InSetExpr))
    check("IN values correct",          filt and filt.expr.values == ["Undocumented","Suspected"])

    # ── Summary ─────────────────────────────────────────────
    print()
    if all_pass:
        print("✅  All parser.py tests passed.")
        print("    Next step: dep_resolver.py")
    else:
        print("❌  Some tests failed — fix before moving to dep_resolver.py")