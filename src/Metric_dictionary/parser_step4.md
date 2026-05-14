# parser_step4.py — DAX Parser (Step 2b)

## Purpose
Takes a `LexResult` (token list from `lexer_step3.py`) and builds an AST using node types from `ast_nodes_step0.py`. Returns `ParseSuccess | ParseFailure` — **never raises outside this module**. Uses a recursive descent algorithm; one `parse_*` method per DAX construct.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `LexResult` from `lexer_step3.tokenize()` |
| **Output** | `ParseResult = ParseSuccess | ParseFailure` (imported from `ast_nodes_step0`) |

---

## Algorithm

**Recursive Descent Parser** — hand-written, no grammar library. Each `parse_*` method:
- Consumes tokens from `self._tokens` via `peek()` / `consume()`
- Returns an AST node on success
- Raises `_ParseError` (internal only) on failure
- All `_ParseError` caught at top level → `ParseFailure`

---

## Parsing Methods

| Method | Handles |
|---|---|
| `parse()` | Top-level entry point |
| `_parse_expr()` | VAR block OR expression |
| `_parse_var_block()` | `VAR ... RETURN ...` → `VarBlock` |
| `_parse_atom()` | Lowest precedence — binary ops / comparisons |
| `_parse_additive()` | `+` and `-` (left-associative) |
| `_parse_multiplicative()` | `*` and `/` → `ScalarMultiplier` for `DIVIDE * scalar` |
| `_parse_unary()` | `ABS(expr)`, unary minus |
| `_parse_primary()` | Function calls, column refs, literals, measure refs |
| `_parse_function_call()` | `FUNCNAME(arg, arg, ...)` → `FunctionCall` |
| `_parse_divide()` | `DIVIDE(num, den)` or `DIVIDE(num, den, default)` → `DivideNode` |
| `_parse_calculate()` | `CALCULATE(expr, filter, ...)` → `FunctionCall("CALCULATE", [...])` |
| `_parse_column_ref()` | `table[column]` or `'table'[column]` → `ColumnRef` |
| `_parse_measure_ref()` | `[MeasureName]` → `MeasureRef` |
| `_parse_in_set()` | `col IN {"v1","v2"}` → `InSetExpr` |
| `_parse_filter_arg()` | `KEEPFILTERS(expr)` or bare filter expression → `InlineFilter` |
| `_parse_bool_literal()` | `TRUE` / `TRUE()` / `FALSE` / `FALSE()` → `BoolLiteral` |

---

## Edge Cases Handled

| Code | Issue | Handling |
|---|---|---|
| EC2 | `IN {"v1","v2"}` curly braces | `_parse_in_set()` → `InSetExpr` |
| EC3 | `<>` not-equal | `BinaryOp(op="<>")` |
| EC4 | `ALL()` context remover | `FunctionCall("ALL", [ColumnRef("ALL","*")])` |
| EC8 | `TRUE()` and bare `TRUE` | Both → `BoolLiteral(True)` via `_parse_bool_literal()` |
| EC9 | `"true"` string | `StringLiteral("true")` — NOT `BoolLiteral(True)` |
| EC10 | `DIVIDE(...) * 12000` | `_parse_multiplicative()` detects `DivideNode * NUMBER` → `ScalarMultiplier` |
| EC16 | `CALCULATE` with no filter args | `FunctionCall("CALCULATE", [expr_only])` |
| EC18 | `AVERAGE` | `FunctionCall("AVERAGE", [...])` — `sql_generator` maps to `AVG()` |
| EC19 | 2-arg vs 3-arg `DIVIDE` | `DivideNode.default_val = None` vs `0.0` |
| EC24 | Inline filter vs KEEPFILTERS | `InlineFilter(has_keepfilters=False/True)` |

---

## Function Flow

```
parse(lex_result) → ParseSuccess | ParseFailure
  ├── if lex_result.error → ParseFailure
  ├── self._tokens = lex_result.tokens
  ├── try:
  │     ast = _parse_expr()
  │       ├── if next token is VAR → _parse_var_block()
  │       └── else → _parse_atom() → _parse_additive() → ... → _parse_primary()
  │     return ParseSuccess(measure_name, ast)
  └── except _ParseError → ParseFailure(measure_name, error, dax_text)
```

---

## File Connections

| Imports from | Used by |
|---|---|
| `ast_nodes_step0` | all node types (`FunctionCall`, `DivideNode`, `VarBlock`, etc.) |

**Called by:** `pipeline_step9.py` — `parse_dax(lex_result)` per measure

---

## Hardcoded Parts

> **None.** DAX grammar is fixed — no dashboard-specific parsing rules needed.
