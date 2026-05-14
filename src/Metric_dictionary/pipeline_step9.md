# pipeline_step9.py — DAX → SQL Compiler Orchestrator

## Purpose
Runs the full deterministic compiler chain (steps 0–8) for every DAX measure in a dashboard and produces `final_measures.json` + `run_report.json`. Internally it calls scope_classifier → cleaner → lexer → parser → dep_resolver → semantic_resolver → classifier → sql_generator in topological order (leaves first) so dependency SQL is always available before it is needed.

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `output/dashboards/<dash>/extraction/schema_sections/measures_resolved.json` |
| **Input B** | `input/<dash>/bi_snowflakes_naming_matching.json` — BI → Snowflake name mapping |
| **Input C** | `input/<dash>/relationships.json` — table join paths |
| **Output A** | `output/dashboards/<dash>/metric_dictionary/final_measures.json` — all measures with SQL + metadata |
| **Output B** | `output/dashboards/<dash>/metric_dictionary/run_report.json` — pipeline stats + errors |
| **Output C** | `output/dashboards/<dash>/metric_dictionary/scope/` — scope split files (via scope_classifier) |

---

## How to Run

```bash
python src/Metric_dictionary/pipeline_step9.py --dashboard risk-dash
python src/Metric_dictionary/pipeline_step9.py --dashboard pac-dash
python src/Metric_dictionary/pipeline_step9.py --dry-run   # parse + classify only, no SQL
```

---

## Function Flow

```
main()
  ├── _find_file(DASHBOARD_INPUTS[dash])    → measures_resolved.json path
  ├── _find_file(DASHBOARD_SF_MAPS[dash])   → sf_map JSON path
  ├── _find_file(DASHBOARD_RELS[dash])      → relationships JSON path
  ├── _load_measures(path)                  → dict of {measure_name: measure}
  │
  ├── run_scope_classification(measures)    → {in_scope, out_of_scope, summary}
  │     └── write_scope_outputs(result, scope_dir)
  │
  ├── build_snowflake_lookup(sf_map)        → flat BI→SF lookup dict
  ├── build_rel_graph(relationships)        → join path lookup dict
  │
  ├── [collect all ParseSuccess ASTs]
  │     for each in-scope measure:
  │       clean(raw_dax)                    → CleanResult
  │       tokenize(clean_dax)               → LexResult
  │       parse_dax(tokens)                 → ParseSuccess | ParseFailure
  │
  ├── dep_resolve(parse_successes)          → DepResult (topological order)
  │
  ├── [per measure in topological order]
  │     resolve_one(parse_result, dep_result, sf_lookup, rel_graph) → AnnotatedAST
  │     do_classify(annotated_ast)          → ClassifyResult
  │     generate(annotated_ast, clf, sql_cache) → GenerateResult
  │     sql_cache[name] = generated_sql     ← cached for downstream measure deps
  │     _make_record(...)                   → final measure dict entry
  │
  ├── [out-of-scope measures]
  │     add to records with sql_applicable=False, llm_role="DEFINER"
  │
  ├── write final_measures.json
  └── write run_report.json
```

---

## Function Details

### `_find_file(candidates) → Path`
Tries each path in the candidates list in order; returns first that exists. Raises `FileNotFoundError` with all tried paths if none found.

### `_load_measures(path) → dict`
Loads JSON — handles both list format `[{name, ...}]` and dict format `{name: {...}}`.

### `_make_record(name, measure, clean_result, parse_result, ann, clf, gen, scope, scope_reason, duration_ms) → dict`
Builds the final JSON entry for one measure. Includes: `measure_name`, `raw_dax`, `clean_dax`, `scope`, `dax_pattern`, `sql_applicable`, `sql_query`, `llm_role`, `sf_refs`, `join_paths`, `parse_status`, `duration_ms`, `warnings`.

---

## File Connections

| Imports from | Used for |
|---|---|
| `scope_classifier` | `run_scope_classification()`, `write_outputs()` |
| `cleaner_step1` | `clean()` → `CleanResult` |
| `lexer_step3` | `tokenize()` → `LexResult` |
| `parser_step4` | `parse_dax()` → `ParseResult` |
| `dep_resolver_step5` | `dep_resolve()` → `DepResult` |
| `semantic_resolver_step6` | `build_snowflake_lookup()`, `build_rel_graph()`, `resolve_one()` → `AnnotatedAST` |
| `classifier_step7` | `do_classify()` → `ClassifyResult` |
| `sql_generator_step8` | `generate()` → `GenerateResult` |
| `ast_nodes_step0` | `ParseSuccess`, `ParseFailure` type checks |

**Called by:** `runner.py` as Step 9

---

## Hardcoded Parts (Change for New Dashboards)

### `DASHBOARD_INPUTS` (line ~107)
```python
DASHBOARD_INPUTS = {
    "risk-dash": [path1, path2, ...],
    "pac-dash":  [path1, path2, ...],
}
```
Candidate paths for `measures_resolved.json` per dashboard. Add new dashboard key + paths.

### `DASHBOARD_SF_MAPS` (line ~119)
```python
DASHBOARD_SF_MAPS = {
    "risk-dash": [_BASE / "input" / "bi_snowflakes_naming_matching.json"],
    "pac-dash":  [_BASE / "input" / "pac_dashboard_bi_snowflkes_naming_matching.json"],
}
```
BI→SF name mapping JSON per dashboard.

### `DASHBOARD_RELS` (line ~130)
```python
DASHBOARD_RELS = {
    "risk-dash": [path_to_relationships.json],
    "pac-dash":  [path_to_relationships.json],
}
```
Join path JSON per dashboard.
