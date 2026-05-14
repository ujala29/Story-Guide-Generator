# sql_generator_step8.py — SQL Generator (Step 6)

## Purpose
Walks an `AnnotatedAST` + `ClassifyResult` and emits Snowflake SQL. **No regex, no string scanning** — pure AST node navigation. Uses a `sql_cache` dict so that previously generated dependency SQL is reused inline when a measure references another measure's SQL.

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `AnnotatedAST` from `semantic_resolver_step6` |
| **Input B** | `ClassifyResult` from `classifier_step7` |
| **Input C** | `sql_cache: dict[str, str]` — already-generated SQL keyed by measure name |
| **Output** | `GenerateResult` dataclass |

---

## `GenerateResult` Schema

```python
measure_name : str
sql          : Optional[str]    # generated Snowflake SQL; None if needs_llm
needs_llm    : bool             # True if compiler gave up
llm_role     : Optional[str]    # "BUILDER" if needs_llm
cte_blocks   : list[str]        # WITH block CTEs for static tables
error        : Optional[str]    # reason string if needs_llm
pattern      : str              # dax_pattern label for logging
```
Always returned — never raises.

---

## SQL Templates by Pattern

| Pattern | SQL Template |
|---|---|
| `SIMPLE_AGG` | `SELECT {AGG}({col}) FROM {table} WHERE {date_filter}` |
| `SIMPLE_DIVIDE` | `SELECT {num_sql} / NULLIF({den_sql}, 0) FROM {table}` |
| `ARITHMETIC` | arithmetic operations on aggregation subqueries |
| `FILTERED_AGG` | `SELECT {AGG}({col}) FROM {table} WHERE {conditions} AND {date_filter}` |
| `VAR_FILTERED_DIVIDE` | `SELECT SUM(CASE WHEN {filter_a} THEN {col_a} END) / NULLIF(SUM(CASE WHEN {filter_b} THEN {col_b} END), 0) FROM {table}` |
| `MEASURE_RATIO` | `({sql_A}) / NULLIF(({sql_B}), 0)` — both sub-SQLs from `sql_cache` |
| `TIME_INTEL_YOY` | `SELECT {AGG}({col}) FROM {table} WHERE {date_col} = DATEADD(year, -1, :{param})` |
| `TIME_INTEL_MOM` | `SELECT {AGG}({col}) FROM {table} WHERE {date_col} = DATEADD(month, -1, :{param})` |
| `CONTEXT_REMOVER` | `SELECT {AGG}({col}) FROM {table}` ← no date filter (EC4) |
| `COMPLEX_VAR_DIVIDE` | `WITH {var_name} AS ({var_sql}), ... SELECT {return_expr_sql}` |
| `STATIC_FILTERED` | `WITH {static_cte} AS (...placeholder...) SELECT ... WHERE col IN (SELECT col FROM {static_cte})` |

---

## Function Flow

```
generate(annotated_ast, classify_result, sql_cache) → GenerateResult
  ├── if not sql_applicable → return GenerateResult(needs_llm=True, llm_role=BUILDER)
  │
  ├── dispatch by dax_pattern:
  │     SIMPLE_AGG       → _gen_simple_agg(ast, sf_refs)
  │     SIMPLE_DIVIDE    → _gen_simple_divide(ast, sf_refs)
  │     ARITHMETIC       → _gen_arithmetic(ast, sf_refs)
  │     FILTERED_AGG     → _gen_filtered_agg(ast, sf_refs)
  │     VAR_FILTERED_DIVIDE → _gen_var_filtered_divide(ast, sf_refs)
  │     MEASURE_RATIO    → _gen_measure_ratio(ast, sql_cache)
  │     TIME_INTEL_YOY   → _gen_time_intel(ast, sf_refs, "year")
  │     TIME_INTEL_MOM   → _gen_time_intel(ast, sf_refs, "month")
  │     CONTEXT_REMOVER  → _gen_context_remover(ast, sf_refs)
  │     COMPLEX_VAR_DIVIDE → _gen_complex_var_divide(ast, sf_refs, sql_cache)
  │     STATIC_FILTERED  → _gen_static_filtered(ast, sf_refs)
  │     COMPLEX          → GenerateResult(needs_llm=True, llm_role="BUILDER")
  │
  └── on any exception → GenerateResult(needs_llm=True, error=str(e))
```

---

## Key Helper Functions

### `_cache_get(name, sql_cache) → str | None`
Case-insensitive, operator-space-normalized lookup. Handles `"Cost / Admit"` (parser adds spaces) matching `"Cost/Admit"` (model key). Prevents missed dependency SQL lookups.

### `_expr_to_sql(node, sf_refs, sql_cache) → str`
Recursive AST traversal — the core function. Dispatches on node type:
- `FunctionCall` → `FUNC_MAP[name](args_sql)`
- `DivideNode` → `num_sql / NULLIF(den_sql, 0)` or `COALESCE(... , 0)` (EC19)
- `BinaryOp` → `left_sql OP_MAP[op] right_sql` (EC3: `<>` → `!=`)
- `InSetExpr` → `col IN ('v1', 'v2')` (EC2: curly → parens)
- `VarRef` → looks up var SQL from local `var_sql_map`
- `MeasureRef` → `_cache_get(name, sql_cache)`
- `BoolLiteral` → `TRUE` / `FALSE` (EC8)
- `StringLiteral` → `'value'` (EC9: always quoted)
- `NumberLiteral` → int or float string
- `ScalarMultiplier` → `(base_sql) * N` (EC10)

---

## Function Maps

### `FUNC_MAP` — DAX → SQL function names
```python
FUNC_MAP = {
    "SUM": "SUM", "COUNT": "COUNT",
    "COUNTROWS": "COUNT",        # COUNTROWS(table) → COUNT(*)
    "DISTINCTCOUNT": "COUNT(DISTINCT {})",
    "MAX": "MAX", "MIN": "MIN",
    "AVERAGE": "AVG",            # EC18
    "ABS": "ABS",
}
```

### `OP_MAP` — DAX operator → SQL operator
```python
OP_MAP = {
    "=": "=", "<>": "!=",   # EC3
    ">": ">", "<": "<", ">=": ">=", "<=": "<=",
    "+": "+", "-": "-", "*": "*", "/": "/",
}
```

---

## File Connections

| Imports from | Used by |
|---|---|
| `ast_nodes_step0` | all node types for AST traversal |
| `semantic_resolver_step6` | `AnnotatedAST`, `SFRef` |
| `classifier_step7` | `ClassifyResult` |

**Called by:** `pipeline_step9.py` — `generate(annotated_ast, clf, sql_cache)` per measure (in topological order)

---

## Hardcoded Parts (Change for New Dashboards)

> **No dashboard-specific logic here.** SQL template shapes are driven by the DAX pattern assigned by `classifier_step7`. Date filter column names and table names come from `AnnotatedAST.sf_refs` which are resolved from the BI→SF mapping JSON. If a new dashboard uses a different Snowflake date column naming convention, update `bi_snowflakes_naming_matching.json` accordingly.
