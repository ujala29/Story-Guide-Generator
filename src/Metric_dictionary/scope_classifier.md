# scope_classifier.py — Measure Scope Pre-classifier

## Purpose
Runs before the lexer/parser chain. Reads `measures_resolved.json` and splits all measures into **in-scope** (compiler will attempt SQL) and **out-of-scope** (LLM definition only, no SQL). Writes three output files to the `scope/` folder and exposes a public API used by `pipeline_step9.py`.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `output/dashboards/<dash>/extraction/schema_sections/measures_resolved.json` |
| **Output A** | `output/dashboards/<dash>/metric_dictionary/scope/measures_in_scope.json` |
| **Output B** | `output/dashboards/<dash>/metric_dictionary/scope/measures_out_of_scope.json` |
| **Output C** | `output/dashboards/<dash>/metric_dictionary/scope/scope_summary.json` — counts + reason breakdown |

---

## Scope Decision Rules

Priority order — first match wins:

| Reason code | Trigger | DAX example |
|---|---|---|
| `HARDCODED_STRING` | DAX is empty OR starts with `"` or `'` | `"The cohort is built on..."` |
| `DEMO_MEASURE` | Contains `RANDBETWEEN` | Non-deterministic test metric |
| `DISPLAY_SYMBOL` | Contains `UNICHAR` | Trend arrow symbols `▲▼` |
| `COLOR_CODE` | `SWITCH(TRUE(), x < N, digit` regex | Conditional formatting integer |
| `DISPLAY_FORMAT` | `FORMAT` + `SWITCH` without `KEEPFILTERS` | Display string, not a number |
| `RUNTIME_ROUTER` | Contains `SELECTEDVALUE` | Depends on slicer at runtime |
| `ROW_ITERATOR` | Contains `SUMX`, `AVERAGEX`, `CONCATENATEX`, `MINX`, `MAXX`, `COUNTX`, `RANKX`, `TOPN`, `GENERATE` | Row-context iterators |
| `IN_SCOPE` | Everything else | Compiler attempts parse + SQL |

Out-of-scope measures get `llm_role="DEFINER"` and `sql_applicable=False`.

---

## Function Flow

```
run_scope_classification(measures: dict) → dict
  ├── for each (name, measure):
  │     classify_scope(name, measure) → (scope, reason)
  │     _build_entry(name, measure, scope, reason) → entry dict
  │     append to in_scope or out_of_scope list
  └── return {in_scope, out_of_scope, summary}

write_outputs(result, output_dir) → (in_path, out_path, summary_path)
  ├── write measures_in_scope.json
  ├── write measures_out_of_scope.json
  └── write scope_summary.json
```

---

## Function Details

### `classify_scope(measure_name, measure) → (scope, reason)`
Applies rules in priority order against the `clean_dax` or `dax` field. Returns `(SCOPE_IN, description)` if no out-of-scope rule matched. Never raises.

### `run_scope_classification(measures) → dict`
Classifies all measures. Sorts both lists alphabetically by `measure_name`. Computes `summary` dict with counts, percentages, and per-reason breakdowns.

### `_build_entry(name, measure, scope, reason) → dict`
Builds the standardized entry dict. In-scope entries get `sql_applicable=True`, `parse_status=None`, `verified=False`. Out-of-scope entries get `llm_role="DEFINER"`, `sql_applicable=False`, `sql_query=None`.

### `write_outputs(result, output_dir) → tuple[Path, Path, Path]`
Creates `output_dir` if needed. Writes all three JSON files. Returns paths.

### Public API used by `pipeline_step9.py`

| Function | Purpose |
|---|---|
| `get_in_scope(output_dir)` | Load `measures_in_scope.json` — raises if not found |
| `get_out_of_scope(output_dir)` | Load `measures_out_of_scope.json` — raises if not found |

---

## File Connections

| Imports from | Used by |
|---|---|
| — (stdlib only) | `pipeline_step9.py` — `run_scope_classification()`, `write_outputs()` |

**Called by:** `pipeline_step9.py` as the pre-step before any parsing begins

---

## Hardcoded Parts (Change for New Dashboards)

### `INPUT_PATHS` (line ~49)
```python
INPUT_PATHS = [
    BASE_DIR / "output/dashboards/risk-dash/extraction/.../measures_resolved.json",
    BASE_DIR / "output/dashboards/risk-dash/extraction/.../measures.json",
]
```
Hardcoded to `risk-dash` when run standalone. When called from `pipeline_step9.py`, the input is passed in as a parameter — these paths are only used for the `main()` standalone run.

### `ROW_ITERATORS` list (line ~129)
```python
ROW_ITERATORS = ["SUMX", "AVERAGEX", "CONCATENATEX", "MINX", "MAXX",
                 "COUNTX", "RANKX", "TOPN", "GENERATE"]
```
Add any additional DAX row-context functions that should be classified out-of-scope for a new dashboard.
