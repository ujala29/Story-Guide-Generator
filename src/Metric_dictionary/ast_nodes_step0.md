# ast_nodes_step0.py — DAX AST Node Definitions

## Purpose
Defines all data shapes for the DAX Abstract Syntax Tree (AST). **No logic, no parsing, no SQL here** — only `@dataclass` definitions. Every other Metric_dictionary step imports from this file. It is the single source of truth for what AST nodes look like.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | None — pure definitions |
| **Output** | Exported dataclass types imported by `cleaner_step1`, `parser_step4`, `dep_resolver_step5`, `semantic_resolver_step6`, `classifier_step7`, `sql_generator_step8` |

---

## Node Hierarchy

```
Leaf nodes (no children)
  ColumnRef          table[column] reference
  MeasureRef         [MeasureName] reference
  VarRef             variable name inside VAR...RETURN
  StringLiteral      "double-quoted string"
  NumberLiteral      numeric constant (stored as float)
  BoolLiteral        TRUE / TRUE() / FALSE / FALSE()

Expression nodes (have children)
  FunctionCall       FUNCNAME(arg1, arg2, ...)
  DivideNode         DIVIDE(num, den) or DIVIDE(num, den, 0)
  BinaryOp           left OP right  (=, <>, >, <, +, -, *, /)
  InSetExpr          col IN {"v1", "v2"}
  CompoundAnd        expr && expr
  InlineFilter       filter arg inside CALCULATE (with/without KEEPFILTERS)
  ScalarMultiplier   expr * scalar  (e.g. DIVIDE(...) * 12000)

Block nodes (structural)
  VarDef             single VAR name = expr definition
  VarBlock           full VAR...RETURN structure (list[VarDef] + return_expr)

Result nodes (parser output)
  ParseSuccess       successful parse — holds measure_name + root AST node
  ParseFailure       failed parse — holds measure_name + error + dax_text
  ParseResult        type alias = ParseSuccess | ParseFailure
```

---

## Node Details

### `ColumnRef`
```python
table:  str   # e.g. "risk_core"  (quotes stripped)
column: str   # e.g. "risk_value" ("*" for table-only refs like COUNTROWS)
```
Formats handled: `risk_core[risk_value]`, `'date'[month_of_date]`, `'Y Axis scatter plot'[Y axis]`

### `MeasureRef`
```python
name: str   # e.g. "#Members PY"  (square brackets stripped)
```
Written as `[MeasureName]` in DAX. Resolved to SQL by `dep_resolver` + `sql_generator`.

### `VarRef`
```python
name: str   # case-preserved from DAX source, e.g. "py", "Num", "Denom"
```
Bare variable name after `RETURN`. Parser emits `ColumnRef("varname","*")` first; `semantic_resolver` upgrades to `VarRef` using `dep_resolver.var_bindings`.

### `DivideNode`
```python
numerator:   Any
denominator: Any
default_val: Optional[float]   # None = DIVIDE(a,b); 0.0 = DIVIDE(a,b,0)
```
**EC19 critical:** 2-arg → `a / NULLIF(b, 0)` returns NULL on zero. 3-arg → `COALESCE(a / NULLIF(b, 0), 0)`.

### `InlineFilter`
```python
expr:            Any    # the filter condition
has_keepfilters: bool   # True if wrapped in KEEPFILTERS(), False if bare
```
Both forms produce the same SQL `WHERE` clause. `has_keepfilters` is metadata only.

### `VarBlock`
```python
bindings:    list[VarDef]   # in declaration order — DO NOT reorder
return_expr: Any
```
`bindings` is a list not a dict — a later VAR can reference an earlier one.

### `ParseFailure`
```python
measure_name: str
error:        str    # human-readable description
dax_text:     str    # the clean DAX that failed — sent to LLM BUILDER
```
Parser **never raises** outside its own module. All failures → `ParseFailure`.

---

## Critical Edge Cases Encoded in These Types

| Code | Issue | Node handling |
|---|---|---|
| EC2 | `IN {}` uses curly braces | `InSetExpr.values` stores plain strings; curly braces stripped |
| EC3 | `<>` not-equal | `BinaryOp(op="<>")` — `sql_generator` maps to `!=` |
| EC8 | `TRUE()` and `TRUE` both valid | Both → `BoolLiteral(True)` |
| EC9 | `"true"` string ≠ `TRUE` boolean | `StringLiteral("true")` vs `BoolLiteral(True)` — different types |
| EC10 | `DIVIDE(...) * 12000` | `ScalarMultiplier(base_expr=DivideNode, multiplier=12000.0)` |
| EC19 | 2-arg vs 3-arg DIVIDE | `default_val=None` vs `default_val=0.0` |
| EC22 | Typo `"Undoumented"` | Stored as-is in `StringLiteral` — cleaner warns, doesn't fix |
| EC24 | `KEEPFILTERS` vs bare filter | `InlineFilter.has_keepfilters` flag |

---

## File Connections

| Imported by | Purpose |
|---|---|
| `cleaner_step1.py` | — (does not need AST; cleaner is pre-AST) |
| `parser_step4.py` | builds all node types |
| `dep_resolver_step5.py` | walks nodes to collect `MeasureRef`, `VarDef` |
| `semantic_resolver_step6.py` | walks nodes to annotate `ColumnRef` |
| `classifier_step7.py` | inspects node types for pattern detection |
| `sql_generator_step8.py` | traverses nodes to emit SQL |
| `pipeline_step9.py` | `ParseSuccess`, `ParseFailure` type checks |

---

## Hardcoded Parts

> **None.** Pure data shapes — no logic, no paths, no dashboard-specific values.
