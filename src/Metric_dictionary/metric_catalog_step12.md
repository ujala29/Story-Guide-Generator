# metric_catalog_step12.py — Metric Catalog Generator (Step 12)

## Purpose
For every in-scope measure, calls the LLM to generate a `technical_definition` (SQL/DAX-level explanation for engineers) and a `business_definition` (plain-English meaning for analysts). Outputs a structured `metric_catalog.json` and a readable `metric_catalog.md` markdown table. Runs after Step 10 so the enriched SQL from `final_measures_with_llm.json` is available. Optional — skipped unless `runner.py` is called without `--skip-catalog`.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `output/dashboards/<dash>/metric_dictionary/final_measures_with_llm.json` |
| **Output A** | `output/dashboards/<dash>/metric_dictionary/metric_catalog.json` — structured catalog |
| **Output B** | `output/dashboards/<dash>/metric_dictionary/metric_catalog.md` — markdown table |

---

## How to Run

```bash
python src/Metric_dictionary/metric_catalog_step12.py --dashboard risk-dash
python src/Metric_dictionary/metric_catalog_step12.py --dashboard pac-dash --skip-registry
python src/Metric_dictionary/metric_catalog_step12.py --measure "PAC PMPM"
python src/Metric_dictionary/metric_catalog_step12.py --dry-run
```

---

## LLM Call Details

| Property | Value |
|---|---|
| Temperature | not specified (default) |
| Concurrency | `WORKERS = 5` parallel threads |
| System prompt | Hardcoded in file — instructs LLM to write two definitions |
| User prompt | Measure name, DAX pattern, DAX expression, SQL, tables, columns, relationships, dependencies |
| Returns | JSON `{"technical": "...", "business": "..."}` |

### System Prompt
```
You are a healthcare analytics expert who writes concise metric definitions.
- Technical: 2-3 sentences. Mention key columns, filters, aggregation type.
- Business: 1-2 sentences. Plain English. No column names, no SQL.
- Respond ONLY in exact JSON format: {"technical": "...", "business": "..."}
```

---

## Function Flow

```
main()
  ├── get_client()           → OpenAI(base_url, api_key)
  ├── load final_measures_with_llm.json
  ├── load registry (or empty dict if --skip-registry)
  │
  ├── [parallel, WORKERS=5] ThreadPoolExecutor
  │     for each in-scope measure:
  │       ├── registry hit? → use cached definitions
  │       └── _build_prompt(entry)  → user prompt string
  │             (measure_name, dax_pattern, DAX, SQL, tables, columns, rels, deps)
  │           LLM call → JSON string
  │           parse JSON → technical + business definitions
  │           update registry
  │
  ├── _extract_catalog_entries(measures, registry) → list[CatalogEntry]
  │     extracts: measure_name, dax_pattern, sql, tables, columns, deps,
  │               technical_definition, business_definition
  │
  ├── write metric_catalog.json
  └── write metric_catalog.md   (markdown table)
        columns: Measure | Pattern | Tables | SQL | Technical | Business
```

---

## Function Details

### `get_client() → OpenAI`
Reads `TF_BASE_URL`, `TF_API_KEY`, `TF_MODEL` from env. Exits with clear error if any missing.

### `_build_prompt(entry) → str`
Builds the user message for the LLM. Includes all available context: measure name, DAX pattern label, clean DAX expression, SQL query, Snowflake tables used, columns used, join relationships, upstream measure dependencies.

### `_extract_catalog_entries(measures, registry) → list[dict]`
Merges `final_measures_with_llm.json` data with LLM definitions from registry. Produces one dict per measure for JSON/MD output.

---

## `DASHBOARD_CONFIGS`

```python
DASHBOARD_CONFIGS = {
    "pac-dash": {
        "llm_json":   BASE_DIR / "output/dashboards/pac-dash/metric_dictionary/final_measures_with_llm.json",
        "output_dir": BASE_DIR / "output/dashboards/pac-dash/metric_dictionary",
    },
    "risk-dash": {
        "llm_json":   BASE_DIR / "output/dashboards/risk-dash/metric_dictionary/final_measures_with_llm.json",
        "output_dir": BASE_DIR / "output/dashboards/risk-dash/metric_dictionary",
    },
}
```

---

## File Connections

| Imports from | Used by |
|---|---|
| `openai.OpenAI` | LLM API calls |
| `pandas` (optional) | markdown table formatting — graceful ImportError if not installed |

**Called by:** `runner.py` as Step 12 (unless `--skip-catalog` is passed)

The `metric_catalog.md` output is consumed by `word_generator/generate_word_doc.py` — it reads the first 10 rows for the Metric Dictionary section of the Story Guide Word doc.

---

## Hardcoded Parts (Change for New Dashboards)

### `DASHBOARD_CONFIGS` (line ~81)
Add a new key for each new dashboard with paths to its `final_measures_with_llm.json` and output directory.

### `SYSTEM_PROMPT` (line ~110)
Currently generic (healthcare analytics expert). If a new dashboard has a very different domain, update the system prompt to reflect the correct domain expertise.

### `WORKERS = 5` (line ~73)
Parallel LLM thread count. Reduce if hitting API rate limits; increase if quota allows.
