# semantic_resolver_step6.py — Semantic Resolver (Step 4)

## Purpose
Walks every AST node and annotates it with Snowflake information: maps BI table/column names to their Snowflake equivalents, upgrades `ColumnRef("varname","*")` to `VarRef("varname")` for VAR binding references, and identifies static/parameter table references. Returns an `AnnotatedAST` with all resolution metadata attached.

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `ParseSuccess` — AST from `parser_step4` |
| **Input B** | `DepResult` — from `dep_resolver_step5` (provides `var_bindings`) |
| **Input C** | `sf_map` — dict from `bi_snowflakes_naming_matching.json` |
| **Input D** | `relationships` — list from `relationships.json` |
| **Output** | `AnnotatedAST` dataclass |

---

## `SFRef` Schema

```python
bi_table  : str             # BI table name  e.g. "attribution"
bi_column : str             # BI column name e.g. "member_count"  ("*" for table-only)
sf_object : Optional[str]   # Snowflake object e.g. "PCP_VISITS_V4_VIEW"
sf_column : Optional[str]   # Snowflake column  e.g. "MEMBER_COUNT"  (uppercase)
ref_type  : str             # "source" | "static" | "parameter" | "measure_container" | "var_ref" | "unresolved"
cte_name  : Optional[str]   # set for static tables — the CTE block name
```

## `AnnotatedAST` Schema

```python
measure_name  : str
ast           : Any            # original AST (not mutated)
sf_refs       : list[SFRef]    # all column references resolved
join_paths    : list[str]      # SQL join conditions between source tables
static_tables : list[str]      # static_ table names referenced
unresolved    : list[str]      # BI table names not found in sf_map
warnings      : list[str]      # non-fatal issues (parameter tables, etc.)
```

---

## Function Flow

```
resolve_one(parse_success, dep_result, sf_map, relationships) → AnnotatedAST
  ├── build_snowflake_lookup(sf_map)      → flat {bi_table: {sf_object, type}} dict
  ├── build_rel_graph(relationships)      → join condition lookup
  │
  ├── walk AST recursively (_walk_node)
  │     for each ColumnRef:
  │       check var_bindings[measure_name] — if match → upgrade to VarRef
  │       else → lookup bi_table in sf_lookup
  │         "source"            → SFRef(ref_type="source", sf_object=VIEW_NAME)
  │         "static"            → SFRef(ref_type="static", cte_name=...)
  │         "parameter"         → SFRef(ref_type="parameter") + warning added
  │         "measure_container" → SFRef(ref_type="measure_container") — skip
  │         not found           → SFRef(ref_type="unresolved") + unresolved list
  │
  ├── collect all source sf_objects used
  ├── get_join_paths(source_objects, rel_graph) → join_paths list
  └── return AnnotatedAST(measure_name, ast, sf_refs, join_paths, ...)
```

---

## Function Details

### `build_snowflake_lookup(sf_map) → dict`
Builds flat `{bi_table_name: {sf_object, type}}` lookup. Handles:
- Regular source tables: `{"snowflake_object": "VIEW_NAME", "type": "source"}`
- Dual-DB tables: `{"snowflake_object": {"snowflake": "X", "postgres": "Y"}}` — picks `"snowflake"` value
- Measure containers: `{"type": "measure_container", "snowflake_object": null}` — `sf_object=None`
- Static tables: nested under `"static_tables"` key
- Parameter tables: `{"type": "parameter"}`

### `build_rel_graph(relationships) → dict`
Builds lookup of join conditions from `relationships.json`. Used by `get_join_paths()` when a measure spans multiple tables.

### `resolve_one(parse_success, dep_result, sf_map, relationships) → AnnotatedAST`
Main entry point per measure. Walks AST, resolves all `ColumnRef` nodes, upgrades VAR references, collects join paths.

### VarRef Upgrade Logic
```python
if bi_table in dep_result.var_bindings.get(measure_name, []):
    # ColumnRef("py","*") → VarRef("py")
```
Parser emits `ColumnRef("varname","*")` because bare identifiers look like table names with no column. This step corrects that.

---

## Special Table Handling

| Table type | `_NO_SQL_TABLES` / `_PARAMETER_TABLES` | Outcome |
|---|---|---|
| `ALL_DAX`, `ALL DAX` | `_NO_SQL_TABLES` | Skipped entirely — measure container |
| `X Axis scatter plot`, `Y Axis scatter plot` | `_PARAMETER_TABLES` | `ref_type="parameter"` + warning |

---

## File Connections

| Imports from | Used by |
|---|---|
| `ast_nodes_step0` | all node types for AST walking |
| `dep_resolver_step5` | `DepResult` — for `var_bindings` |
| `dataclasses`, `collections` (stdlib) | — |

**Called by:** `pipeline_step9.py` — `resolve_one()` per measure after dep resolution

---

## Hardcoded Parts (Change for New Dashboards)

### `_NO_SQL_TABLES` (line ~111)
```python
_NO_SQL_TABLES = {"ALL_DAX", "ALL DAX"}
```
Measure container table names that have no Snowflake object. Add new dashboard's measure container names if different.

### `_PARAMETER_TABLES` (line ~114)
```python
_PARAMETER_TABLES = {"X Axis scatter plot", "Y Axis scatter plot"}
```
Parameter/slicer tables to skip. Add new dashboard's parameter table names here.
