# dep_resolver_step5.py — Dependency Resolver (Step 3)

## Purpose
Walks every parsed AST, collects which other measures each measure depends on (`MeasureRef` nodes) and which VAR binding names it defines (`VarDef` nodes). Builds a cross-measure dependency graph and returns a **topological order** (leaves first) so `pipeline_step9.py` processes measures in the correct bottom-up sequence. Also detects circular dependencies.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `dict[str, ParseSuccess]` — all successfully parsed measures keyed by name |
| **Output** | `DepResult` dataclass |

---

## `DepResult` Schema

```python
order:        list[str]              # measure names, leaves first (safe processing order)
deps:         dict[str, list[str]]   # {name: [direct_dep_names]}
var_bindings: dict[str, list[str]]   # {name: [var_binding_names defined in this measure]}
circular:     list[str]              # names involved in cycles (usually empty)
```

---

## Why This Matters

DAX measures build on each other:
```
#Members        → SUM(attribution[member_count])
#Members PY     → CALCULATE([#Members], SAMEPERIODLASTYEAR(...))
#Members YoY    → VAR py = [#Members PY] ... RETURN DIVIDE(...)
```
Processing order must be: `#Members` → `#Members PY` → `#Members YoY`.
Otherwise when SQL is generated for `#Members YoY`, the SQL for its dependencies is not yet in `sql_cache`.

## Why `var_bindings` Are Collected

Parser emits `ColumnRef("py","*")` for bare variable names like `py` (it looks like a table reference with no column). `semantic_resolver_step6` needs to know: *"is `py` a VAR binding in this measure, or is it a real table name?"*

```
var_bindings["#Members YoY"] = ["py"]
→ semantic_resolver sees ColumnRef("py","*")
→ "py" is in var_bindings → upgrade to VarRef("py")
```

---

## Function Flow

```
resolve(parse_successes: dict) → DepResult
  ├── for each (name, ParseSuccess):
  │     collect_measure_refs(ast)   → set of MeasureRef.name strings
  │     collect_var_bindings(ast)   → list of VarDef.name strings
  │
  ├── build adjacency dict: {name: [deps]}
  │
  └── topological_sort(adjacency)   → (order, circular)
        Kahn's BFS algorithm — same as stage1/dependency_graph.py
        leaves (no deps) → in-degree 0 → processed first
```

---

## Function Details

### `collect_measure_refs(ast, found=None) → set[str]`
Recursive AST walk. Visits every node type. Collects `MeasureRef.name` values. Returns set of measure name strings.

### `collect_var_bindings(ast) → list[str]`
Walks `VarBlock.bindings` to collect `VarDef.name` values. Returns list of variable names defined in this measure's VAR block.

### `resolve(parse_successes) → DepResult`
Main entry point. Builds the full dependency graph, runs Kahn's BFS topological sort, returns `DepResult`.

### `_norm_name(name) → str`
Normalizes spaces around operators so `"Cost / Admit"` (parser adds spaces) matches `"Cost/Admit"` (model key). Prevents missed dependency lookups due to spacing differences.

---

## File Connections

| Imports from | Used by |
|---|---|
| `ast_nodes_step0` | `MeasureRef`, `VarBlock`, `VarDef`, `FunctionCall`, `DivideNode`, `BinaryOp`, `InSetExpr`, `CompoundAnd`, `InlineFilter`, `ScalarMultiplier`, `ParseSuccess` |
| `dataclasses`, `collections` (stdlib) | — |

**Called by:** `pipeline_step9.py` — `dep_resolve(parse_successes)` after all measures are parsed

The `DepResult` is also consumed by `semantic_resolver_step6.py` to look up `var_bindings` during VarRef upgrade.

---

## Hardcoded Parts

> **None.** Dependency resolution is purely structural — no dashboard-specific logic.
