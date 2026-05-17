# Adding a New Dashboard — Complete Checklist

Replace `<new-dash>` with your dashboard key (e.g. `quality-dash`) everywhere below.

---

## Step 1 — Input files

Place these in `input/`:

| File | Description |
|---|---|
| `<Name>.SemanticModel/` | Power BI Semantic Model folder |
| `<Name>.Report/` | Power BI Report folder |
| `<new-dash>_bi_snowflkes_naming_matching.json` | BI column → Snowflake column mapping |

---

## Step 2 — `src/utils/config.py`

**Lines 17–26** — Add entry to `DASHBOARDS` dict:

```python
DASHBOARDS: dict[str, dict] = {
    "risk-dash": { ... },
    "pac-dash":  { ... },

    # ADD THIS
    "<new-dash>": {
        "semantic_model": ROOT / "input" / "<Name>.SemanticModel",
        "report":         ROOT / "input" / "<Name>.Report",
    },
}
```

---

## Step 3 — `prompt/dashboard_config.json`

**Lines 1–26** — Add entry (used by visual_wise prompts and funnel_input_builder):

```json
{
  "risk-dash": { ... },
  "pac-dash":  { ... },

  "<new-dash>": {
    "display_name": "<Full Dashboard Name>",
    "domain": "<One line: what this dashboard tracks>",
    "users": "<Comma-separated user roles>",
    "common_pain_points": [
      "Numbers differ from colleague",
      "<Any dashboard-specific pain points>"
    ]
  }
}
```

---

## Step 4 — `prompt/system_prompt/base_context_<new-dash>.txt`

**Create new file** (copy from `base_context_pac-dash.txt` and update domain lines):

```
You are a healthcare analytics documentation expert.
Your job is to generate a Story Guide for a single
dashboard visual in a Power BI report focused on
<describe the domain of new dashboard>.

Domain context:
- This dashboard is used by <user roles>
- Metrics relate to <key metric areas>
- Users may not understand DAX — use plain
  business language only
- Never include DAX syntax in your output
- Output in clean markdown only

Shared rules:
- Every high/low/pattern bullet must name a specific
  other visual to cross-check
- Drill order must go summary → breakdown → detail
- Always clarify if a metric is a driver or outcome
- Use sentence case everywhere, never ALL CAPS
```

> **Note:** `visaul_pipeline_runner.py` line 402 loads `base_context.txt` (generic fallback).
> The dashboard-specific file is loaded by `load_prompt()` via `dashboard_config.json`.

---

## Step 5 — `src/Metric_dictionary/pipeline_step9.py`

### 5a. `DASHBOARD_INPUTS` — Lines 107–117

```python
DASHBOARD_INPUTS = {
    "risk-dash": [ ... ],
    "pac-dash":  [ ... ],

    # ADD THIS
    "<new-dash>": [
        _BASE / "output" / "dashboards" / "<new-dash>" / "extraction" / "schema_sections" / "measures_resolved.json",
        _BASE / "output" / "dashboards" / "<new-dash>" / "extraction" / "schema_sections" / "measures.json",
    ],
}
```

### 5b. `DASHBOARD_SF_MAPS` — Lines 119–127

```python
DASHBOARD_SF_MAPS = {
    "risk-dash": [ ... ],
    "pac-dash":  [ ... ],

    # ADD THIS
    "<new-dash>": [
        _BASE / "input" / "<new-dash>_bi_snowflkes_naming_matching.json",
    ],
}
```

### 5c. `DASHBOARD_RELS` — Lines 130–137

```python
DASHBOARD_RELS = {
    "risk-dash": [ ... ],
    "pac-dash":  [ ... ],

    # ADD THIS
    "<new-dash>": [
        _BASE / "output" / "dashboards" / "<new-dash>" / "extraction" / "schema_sections" / "relationships.json",
    ],
}
```

---

## Step 6 — `src/Metric_dictionary/llm_fallback_step10.py`

### 6a. `DASHBOARD_LLM_CONFIGS` — Lines 197–206

```python
DASHBOARD_LLM_CONFIGS = {
    "risk-dash": { ... },
    "pac-dash":  { ... },

    # ADD THIS
    "<new-dash>": {
        "final_json" : BASE_DIR / "output" / "dashboards" / "<new-dash>" / "metric_dictionary" / "final_measures.json",
        "output_dir" : BASE_DIR / "output" / "dashboards" / "<new-dash>" / "metric_dictionary",
    },
}
```

### 6b. `SCHEMA_CONTEXT_<NEW>` — after Line 497

Add a new schema context string describing the Snowflake tables for this dashboard.
Copy the structure from `SCHEMA_CONTEXT_PAC` (lines 451–497) and replace tables/columns:

```python
SCHEMA_CONTEXT_<NEW> = """
Snowflake tables available:
  <TABLE_NAME_1>   — <description>. Key cols: <col1>, <col2>.
                     Date filter col: <date_col>
                     <HAS / NO> max_month_flag column.

  <TABLE_NAME_2>   — <description>. ...

━━━ DATE FILTER RULES — apply exactly as written ━━━

  RULE A — BASE measures:
    <TABLE_NAME_1>: WHERE <date_col> = :selected_month
    !! <TABLE_NAME_1> does NOT have MAX_MONTH_FLAG — never add it !! (if applicable)

  RULE B — TIME-INTEL measures: PY, PM, YoY, MoM
    PY: WHERE <date_col> = DATEADD(year,  -1, :selected_month)
    PM: WHERE <date_col> = DATEADD(month, -1, :selected_month)
    YoY/MoM ratio — use two subqueries, no MAX_MONTH_FLAG anywhere.

  RULE C — CONTEXT_REMOVER (ALL / ALL('DATE')):
    No date filter whatsoever.

━━━ OTHER CONVENTIONS ━━━
  - DIVIDE(a,b)   -> a / NULLIF(b, 0)
  - DIVIDE(a,b,0) -> COALESCE(a / NULLIF(b, 0), 0)
  - Always use SELECT ... FROM ... (no CTEs unless necessary)
"""
```

### 6c. `DASHBOARD_SCHEMA_CONTEXT` — Lines 499–502

```python
DASHBOARD_SCHEMA_CONTEXT = {
    "risk-dash": SCHEMA_CONTEXT_RISK,
    "pac-dash" : SCHEMA_CONTEXT_PAC,

    # ADD THIS
    "<new-dash>": SCHEMA_CONTEXT_<NEW>,
}
```

---

## Step 7 — `src/Metric_dictionary/metric_catalog_step12.py`

**Lines 81–90** — Add to `DASHBOARD_CONFIGS`:

```python
DASHBOARD_CONFIGS = {
    "pac-dash":  { ... },
    "risk-dash": { ... },

    # ADD THIS
    "<new-dash>": {
        "llm_json"  : BASE_DIR / "output" / "dashboards" / "<new-dash>" / "metric_dictionary" / "final_measures_with_llm.json",
        "output_dir": BASE_DIR / "output" / "dashboards" / "<new-dash>" / "metric_dictionary",
    },
}
```

---

## Step 8 — `prompt/<new-dash>/` prompt folder

**Create folder** `prompt/<new-dash>/` with these 8 files.

### 8a. Visual enrichment files (new — required for correct L0/L1 output)

**`fixes.json`** — Used by `visual_parserL0.py` and `visaul_pipeline_runner.py` to fix wrong titles and skip non-content visuals. If no fixes needed, create with empty defaults:

```json
{
  "title_overrides": {
    "<visual_id>": "<correct title for this visual>"
  },
  "generic_titles": [
    "<any stale section-header title that incorrectly appears as a card title>"
  ],
  "skip_types": ["slicer", "advancedSlicerVisual", "textbox", "image",
                 "shape", "actionButton", "basicShape", "multiRowCard", "card"]
}
```

> `title_overrides` keyed by visual ID (from `extraction/schema_sections/visuals.json`).
> `generic_titles` are dashboard-specific strings that `visual_parser` picks up as titles but are really container headings.
> `skip_types` — keep the defaults unless the new dashboard uses `multiRowCard`/`card` as standalone visuals (not as paired YoY/MoM tiles).

**`glossary.json`** — Used by `visual_parserL0.py` to give the LLM domain vocabulary during visual enrichment:

```json
{
  "flags": {
    "<flag_value>": "<plain English meaning>"
  },
  "columns": {
    "<col_name>": "<what this column represents>"
  },
  "domain_terms": {
    "<ACRONYM>": "<full form and meaning>"
  }
}
```

> Only add terms unique to this dashboard. Generic healthcare terms don't need repeating.

### 8b. Metric_dictionary prompt files (copy from `prompt/pac-dash/` and update)

| File | Used by | What to write |
|---|---|---|
| `schema_context.txt` | `llm_fallback_step10.py` → BUILDER role | Full Snowflake schema — all tables, key columns, date filter rules |
| `schema_rules_only.txt` | `llm_fallback_step10.py` → VALIDATOR role | Only date filter rules + SQL conventions (no table descriptions) |
| `validator_system.txt` | `llm_fallback_step10.py` → VALIDATOR role | System prompt: "You are a SQL expert reviewing Snowflake SQL..." |
| `validator_checklist.txt` | `llm_fallback_step10.py` → VALIDATOR role | Checklist: table name correct? date column correct? MAX_MONTH_FLAG used correctly? |
| `builder_system.txt` | `llm_fallback_step10.py` → BUILDER role | System prompt: "You are a Snowflake SQL expert. Generate SQL for this DAX measure..." |
| `definer_system.txt` | `llm_fallback_step10.py` → DEFINER role | System prompt: "You are a healthcare analytics expert. Write a plain English definition..." |

> **Note:** `llm_fallback_step10.py` line 357 looks for these files at `PROMPTS_DIR / dashboard`
> where `PROMPTS_DIR = BASE_DIR / "prompts"` (with an **s**). The actual folder is `prompt/` (no s).
> Fix line 194: `PROMPTS_DIR = BASE_DIR / "prompt"` so dashboard-specific prompt files actually load.

---

## Step 9 — `src/Page_wise/funnel_input_builder_step0.py`

Three hardcoded sections need updating for each new dashboard:

### 9a. `SKIP_PAGES` (~line 73)

Add the new dashboard's utility/tooltip page names (exact `display_name` from `pages.json`):

```python
SKIP_PAGES = {
    "Scatter plot tooltip",
    "Additional dimensions",
    "Data availability",
    "<new-dash utility page name>",   # ADD THIS
}
```

### 9b. `KNOWN_DASHBOARD_NAMES` (~line 357)

Fallback display name used when `dashboard_config.json` is missing:

```python
KNOWN_DASHBOARD_NAMES = {
    "risk-dash": "Risk Management",
    "pac-dash":  "PAC",
    "<new-dash>": "<Full Display Name>",   # ADD THIS
}
```

### 9c. `GENERIC_TITLES` (~line 197)

If `visual_parser` picks up container/section headings as card titles for the new dashboard, add them here:

```python
GENERIC_TITLES = {
    "Pharmacy PMPM YoY",   # risk-dash specific
    "Leakage %",           # risk-dash specific
    "Card", "Visual", "",
    "<new-dash stale title>",   # ADD IF NEEDED
}
```

> Check `funnel_llm_input.json` after step 0 — if any visual has a title that is obviously a section header, add it here and re-run step 0.

---

## Step 10 — Run

```bash
# Full pipeline for new dashboard
python main.py --dashboard <new-dash>

# Or stage by stage
python main.py --dashboard <new-dash> --from-stage 1
python main.py --dashboard <new-dash> --from-stage 2
python main.py --dashboard <new-dash> --from-stage 3
python main.py --dashboard <new-dash> --from-stage 4
python main.py --dashboard <new-dash> --from-stage 5
```

---

## Notes

> **Page ordering** — No config needed. Pages whose names start with `main_page`, `main`, `overview`, or `summary` automatically sort first in both `page_wise_story.md` and the Word document. All other pages follow alphabetically.

> **LM/LY mirror pages** — No config needed. Any `*_LM` page that has a matching `*_LY` page is automatically skipped in both `visual_wise` and `page_wise` pipelines — only the LY version is processed.

> **`PROMPTS_DIR` bug** — `llm_fallback_step10.py` line 194 points to `prompts/` (with s) but folder is `prompt/` (no s). Fix line 194: `PROMPTS_DIR = BASE_DIR / "prompt"` so dashboard-specific prompt files actually load instead of falling back to inline constants.

> **Missing `metric_catalog_registry.json`** — If Stage 2 Metric_dictionary is not run, all measure definitions in `funnel_llm_input.json` will be empty. This significantly degrades funnel categorization quality in Step 1. Always run Stage 2 completely before Stage 3.

---

## Summary Table

| # | File | What to add |
|---|---|---|
| 1 | `input/` | `.SemanticModel`, `.Report`, BI→SF mapping JSON |
| 2 | `src/utils/config.py` | Entry in `DASHBOARDS` dict |
| 3 | `prompt/dashboard_config.json` | Dashboard metadata block |
| 4 | `prompt/system_prompt/base_context_<new-dash>.txt` | Domain-specific base context prompt (new file) |
| 5a | `src/Metric_dictionary/pipeline_step9.py` | `DASHBOARD_INPUTS` entry |
| 5b | `src/Metric_dictionary/pipeline_step9.py` | `DASHBOARD_SF_MAPS` entry |
| 5c | `src/Metric_dictionary/pipeline_step9.py` | `DASHBOARD_RELS` entry |
| 6a | `src/Metric_dictionary/llm_fallback_step10.py` | `DASHBOARD_LLM_CONFIGS` entry |
| 6b | `src/Metric_dictionary/llm_fallback_step10.py` | `SCHEMA_CONTEXT_<NEW>` string (inline) |
| 6c | `src/Metric_dictionary/llm_fallback_step10.py` | `DASHBOARD_SCHEMA_CONTEXT` entry |
| 7 | `src/Metric_dictionary/metric_catalog_step12.py` | `DASHBOARD_CONFIGS` entry |
| 8a | `prompt/<new-dash>/fixes.json` | Title overrides, generic titles, skip types (new file) |
| 8a | `prompt/<new-dash>/glossary.json` | Domain flags, column meanings, acronyms (new file) |
| 8b | `prompt/<new-dash>/` (6 txt files) | Metric_dictionary prompt files: schema_context, schema_rules_only, validator_system, validator_checklist, builder_system, definer_system |
| 9a | `src/Page_wise/funnel_input_builder_step0.py` | `SKIP_PAGES` — utility page names |
| 9b | `src/Page_wise/funnel_input_builder_step0.py` | `KNOWN_DASHBOARD_NAMES` — fallback display name |
| 9c | `src/Page_wise/funnel_input_builder_step0.py` | `GENERIC_TITLES` — if dashboard has stale container titles |
