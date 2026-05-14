# classifier_step7.py — DAX Pattern Classifier (Step 5)

## Purpose
Inspects an `AnnotatedAST` and assigns a `dax_pattern` label, `sql_applicable` flag, and `llm_role`. The pattern label controls which SQL template `sql_generator_step8` uses. Uses **AST node type inspection** (not string scanning) to avoid false positives from keywords appearing inside column names or string literals.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `AnnotatedAST` from `semantic_resolver_step6` |
| **Output** | `ClassifyResult` dataclass |

---

## `ClassifyResult` Schema

```python
measure_name   : str
dax_pattern    : str            # pattern label (see table below)
sql_applicable : bool           # True → sql_generator attempts SQL
llm_role       : Optional[str]  # None | "DEFINER" | "BUILDER"
note           : str            # human-readable classification explanation
has_static     : bool           # True if measure references static_ tables
has_time_intel : bool           # True if SAMEPERIODLASTYEAR / PREVIOUSMONTH present
has_all        : bool           # True if ALL() present (EC4 — no date filter)
```

---

## Pattern Labels (Priority Order — First Match Wins)

### Out-of-scope (sql_applicable=False)

| Pattern | Trigger | llm_role |
|---|---|---|
| `INFO_TEXT` | `CleanResult.is_hardcoded_string = True` | `DEFINER` |
| `DISPLAY` | `UNICHAR` or color `SWITCH(TRUE(),...)` in AST | `DEFINER` |
| `UNSUPPORTED` | `SELECTEDVALUE`, `RANDBETWEEN`, row iterators | `DEFINER` |

### In-scope (sql_applicable=True)

| Pattern | Trigger | SQL approach |
|---|---|---|
| `SIMPLE_AGG` | Root is `FunctionCall("SUM"/"COUNT"/"MAX"/"MIN"/"AVERAGE"/"DISTINCTCOUNT"/"COUNTROWS"/"ABS")` | `SELECT AGG(col) FROM table` |
| `SIMPLE_DIVIDE` | Root is `DivideNode`, no `VarBlock`, no `MeasureRef` | `SELECT num/NULLIF(den,0)` |
| `ARITHMETIC` | Root is `BinaryOp` or `ScalarMultiplier` with aggregations | arithmetic on aggregations |
| `FILTERED_AGG` | `CALCULATE` + `KEEPFILTERS` or `InlineFilter`, no `SAMEPERIODLASTYEAR` | `SELECT AGG(col) WHERE conditions` |
| `VAR_FILTERED_DIVIDE` | `VarBlock` + `CALCULATE` + `DivideNode` — gap-to-potential pattern | CASE WHEN divide |
| `TIME_INTEL_YOY` | `SAMEPERIODLASTYEAR` in AST | `WHERE date = DATEADD(year,-1,:param)` |
| `TIME_INTEL_MOM` | `PREVIOUSMONTH` in AST | `WHERE date = DATEADD(month,-1,:param)` |
| `MEASURE_RATIO` | Root is `BinaryOp("/", MeasureRef, MeasureRef)` | `(sql_A)/NULLIF((sql_B),0)` |
| `COMPLEX_VAR_DIVIDE` | `VarBlock` + `DivideNode` on `MeasureRef`/`VarRef` | YoY/MoM CTE computation |
| `CONTEXT_REMOVER` | `ALL()` in AST | `SELECT AGG(col)` — no date filter |
| `STATIC_FILTERED` | Any `sf_ref.ref_type == "static"` | CTE placeholder for static lookup |
| `COMPLEX` | Anything not matched above | `needs_llm=True` → BUILDER role |

---

## Function Flow

```
classify(annotated_ast) → ClassifyResult
  ├── check has_static   (any SFRef.ref_type == "static")
  ├── check has_time_intel (_has_function(ast, "SAMEPERIODLASTYEAR", "PREVIOUSMONTH"))
  ├── check has_all      (_has_function(ast, "ALL"))
  │
  ├── try patterns in priority order:
  │     _is_info_text()        → INFO_TEXT
  │     _is_display()          → DISPLAY
  │     _is_unsupported()      → UNSUPPORTED
  │     _is_simple_agg()       → SIMPLE_AGG
  │     _is_simple_divide()    → SIMPLE_DIVIDE
  │     _is_arithmetic()       → ARITHMETIC
  │     _is_context_remover()  → CONTEXT_REMOVER
  │     _is_time_intel_yoy()   → TIME_INTEL_YOY
  │     _is_time_intel_mom()   → TIME_INTEL_MOM
  │     _is_measure_ratio()    → MEASURE_RATIO
  │     _is_filtered_agg()     → FILTERED_AGG
  │     _is_var_filtered_div() → VAR_FILTERED_DIVIDE
  │     _is_complex_var_div()  → COMPLEX_VAR_DIVIDE
  │     _is_static_filtered()  → STATIC_FILTERED
  └── fallback                 → COMPLEX (needs_llm=True, llm_role="BUILDER")
```

---

## Helper Functions

### `_has_function(ast, *names) → bool`
Recursive AST walk. Returns `True` if any `FunctionCall.name` (uppercased) matches any of the given names. Walks `VarBlock`, `DivideNode`, `BinaryOp`, `InlineFilter`, `CompoundAnd`, `ScalarMultiplier`.

### `_root_is(ast, *types) → bool`
Returns `True` if the root AST node is one of the given Python types. Used for `SIMPLE_AGG`, `SIMPLE_DIVIDE`, `MEASURE_RATIO` detection.

---

## File Connections

| Imports from | Used by |
|---|---|
| `ast_nodes_step0` | all node types for AST inspection |
| `semantic_resolver_step6` | `AnnotatedAST` input type |

**Called by:** `pipeline_step9.py` — `do_classify(annotated_ast)` per measure

---

## Hardcoded Parts

> **None.** DAX patterns are fixed by the grammar — no dashboard-specific classification rules needed. If a new dashboard introduces a new DAX function, a new pattern may need to be added here and a corresponding SQL template added to `sql_generator_step8.py`.
