# llm_fallback_step10.py — LLM Fallback (Step 10)

## Purpose
Four LLM roles using the TrueFoundry API (OpenAI-compatible): **VALIDATOR** (review compiler SQL), **FIXER** (correct flagged SQL), **BUILDER** (generate SQL for patterns the compiler couldn't handle), **DEFINER** (plain-English definitions for out-of-scope measures). All results are cached in `registry.json` — re-runs skip API calls for already-processed measures.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `output/dashboards/<dash>/metric_dictionary/final_measures.json` |
| **Output A** | `output/dashboards/<dash>/metric_dictionary/final_measures_with_llm.json` — enriched with LLM results |
| **Output B** | `output/dashboards/<dash>/metric_dictionary/registry.json` — LLM result cache |

---

## How to Run

```bash
python src/Metric_dictionary/llm_fallback_step10.py --dashboard risk-dash
python src/Metric_dictionary/llm_fallback_step10.py --validate-only
python src/Metric_dictionary/llm_fallback_step10.py --build-only
python src/Metric_dictionary/llm_fallback_step10.py --define-only
python src/Metric_dictionary/llm_fallback_step10.py --measure "#Members YoY"
python src/Metric_dictionary/llm_fallback_step10.py --dry-run
```

---

## LLM Roles

| Role | Trigger | LLM does |
|---|---|---|
| `VALIDATOR` | `scope=IN_SCOPE` + `sql_query` exists | Reviews compiler SQL for logic errors; returns `ok` / `needs_fix` / `unsure` |
| `FIXER` | VALIDATOR returns `needs_fix` | Rewrites SQL to fix the identified error |
| `BUILDER` | `scope=IN_SCOPE` + `llm_role=BUILDER` (compiler produced no SQL) | Generates SQL from scratch for `COMPLEX` patterns |
| `DEFINER` | `scope != IN_SCOPE` + `llm_role=DEFINER` | Plain-English business definition only — no SQL |

---

## Registry Cache

`registry.json` is a flat dict keyed by measure name. Stores:
- `sql` (validated/fixed/built)
- `definition` (plain English)
- `validation_verdict` (`ok` / `needs_fix` / `unsure`)
- `fix_history` list
- `timestamps` per operation

On re-run: registry hit → skip API call → use cached result.

---

## Function Flow

```
main()
  ├── load final_measures.json
  ├── load registry.json (or start fresh)
  │
  ├── [parallel, WORKERS=5] ThreadPoolExecutor
  │     for each measure:
  │       ├── registry hit? → skip (return cached)
  │       │
  │       ├── VALIDATOR role (scope=IN_SCOPE, has sql_query)
  │       │     trim_schema_to_tables(schema, sql, dax)  ← reduce prompt tokens
  │       │     llm_chat([system, user], temperature=0.1)
  │       │     parse verdict → "ok" | "needs_fix" | "unsure"
  │       │     if needs_fix → FIXER role (second LLM call)
  │       │         clean_llm_sql(response)
  │       │         resolve_placeholders(sql)
  │       │
  │       ├── BUILDER role (IN_SCOPE, no sql_query)
  │       │     build prompt with DAX + schema context
  │       │     llm_chat([system, user])
  │       │     clean_llm_sql(response)   ← strip markdown fences + placeholders
  │       │
  │       └── DEFINER role (out-of-scope)
  │             build prompt with DAX description
  │             llm_chat([system, user])
  │             store plain English definition
  │
  ├── write registry.json (after each measure — thread-safe via _registry_lock)
  └── write final_measures_with_llm.json
```

---

## Key Helper Functions

### `strip_markdown_fences(sql) → str`
Removes ` ```sql ... ``` ` or ` ``` ... ``` ` wrapping from LLM-generated SQL. LLMs often wrap SQL in markdown code blocks even when instructed not to.

### `clean_llm_sql(sql) → str`
Calls `strip_markdown_fences()` then `resolve_placeholders()`.

### `resolve_placeholders(sql) → (str, list[str])`
Strips angle-bracket placeholders left by LLM (e.g. `<PAC_TABLE>` → `PAC_TABLE`). Only strips tokens matching `[\w.]+` (valid SQL identifiers). Returns `(cleaned_sql, unresolved_tokens)`.

### `trim_schema_to_tables(schema, sql, dax) → str`
Returns only the table blocks from the schema context that are actually referenced in the SQL or DAX, plus the `DATE FILTER RULES` and `SQL CONVENTIONS` sections. Reduces VALIDATOR prompt size by ~600 tokens for single-table measures.

---

## Concurrency

`WORKERS = 5` parallel threads via `ThreadPoolExecutor`. Registry writes are serialized with `_registry_lock` (threading.Lock). Reduce `WORKERS` if hitting API rate limits.

---

## File Connections

| Imports from | Used by |
|---|---|
| `utils/llm_client.py` | `llm_chat()` with tenacity retry (5 attempts, exponential backoff) |

**Called by:** `runner.py` as Step 10 (after `pipeline_step9.py` completes)

---

## Hardcoded Parts (Change for New Dashboards)

### `DASHBOARD_LLM_CONFIGS` (in file, look for the dict)
```python
DASHBOARD_LLM_CONFIGS = {
    "risk-dash": {
        "final_measures_path": ...,
        "registry_path": ...,
        "output_path": ...,
    },
    "pac-dash": {...},
}
```
Add a config block for each new dashboard so step 10 knows where to read `final_measures.json` and write `registry.json` + `final_measures_with_llm.json`.

### `SKIP_OUT_OF_SCOPE = False` (line ~53)
Set to `True` to skip the DEFINER role entirely and save API calls on out-of-scope measures when definitions aren't needed.

### `TABLE_NAMES` in `trim_schema_to_tables()` (line ~144)
```python
TABLE_NAMES = [
    "RISK_CORE_V4_VIEW", "RISK_GROUP_V4_VIEW", "RISK_COHORT_V4_VIEW",
    "PCP_VISITS_V4_VIEW", "PAC_TABLE", "INPATIENT_PAC_V4_VIEW", ...
]
```
All Snowflake table/view names used across dashboards. Add new dashboard's table names here so the schema trimmer can reduce prompt size for those tables.
