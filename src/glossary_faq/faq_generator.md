# faq_generator.py — FAQ Builder

## Purpose
Collects 4 types of signals from earlier pipeline outputs (watch-out callouts, cross-page patterns, filter metadata, analytical sub-questions), then sends them to an LLM to produce 10–15 Frequently Asked Questions that answer real user anxieties when reading the dashboard.

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `output/dashboards/<dash>/page_wise/widget_content/*.json` — `italic_callout` per metric (watch-outs → FAQ seeds) |
| **Input B** | `output/dashboards/<dash>/page_wise/funnel_connector.json` — `cross_page_patterns` |
| **Input C** | `output/dashboards/<dash>/extraction/schema_sections/filters.json` — slicer metadata |
| **Input D** | `output/dashboards/<dash>/page_wise/funnel_map.json` — `sub_questions` + `domain_context` |
| **System prompt** | `prompt/system_prompt/faq.txt` (if exists) else inline fallback |
| **Config** | `prompt/dashboard_config.json` — domain, users per dashboard |
| **Output** | `output/dashboards/<dashboard>/glossary_faq/faq.md` |

---

## Pipeline Steps

```
Step 1  collect_faq_signals()    → gather 4 signal types
Step 2  load_faq_prompt()        → load system prompt (file or inline)
Step 3  build_faq_prompt()       → assemble user prompt with all signals
Step 4  generate_faq()           → LLM call → markdown string
Step 5  save_faq()               → write faq.md
```

---

## Function Flow

```
main()
  ├── parse --dashboard arg
  ├── OpenAI client (TF_API_KEY + TF_BASE_URL)
  ├── collect_faq_signals(dashboard, _ROOT)
  │     ├── Source A: widget_content/*.json
  │     │     └── skip SKIP_PAGES, extract metric.italic_callout → callouts[]
  │     ├── Source B: funnel_connector.json
  │     │     └── connector.cross_page_patterns[] → cross_page_patterns[]
  │     ├── Source C: filters.json
  │     │     ├── skip SKIP_TABLES, skip Slicer_ prefix names
  │     │     ├── deduplicate by column
  │     │     ├── translate PERIOD_MAP defaults
  │     │     └── → filter_summaries[]
  │     └── Source D: funnel_map.json
  │           └── domain_context string + sub_questions[]
  │
  ├── generate_faq(data, llm_client, dashboard)
  │     ├── load_faq_prompt(dashboard)
  │     │     ├── try: load prompt/system_prompt/faq.txt
  │     │     │     + prepend domain_block + base_context.txt
  │     │     └── fallback: FAQ_SYSTEM_INLINE
  │     ├── build_faq_prompt(data, system_prompt)
  │     │     ├── _format_callouts()         → [page -> widget -> metric] + watch-out text
  │     │     ├── _format_cross_page()       → pattern + interpretation
  │     │     ├── _format_filters()          → name | column | single/multi | default
  │     │     ├── _format_sub_questions()    → [page] question (deduplicated)
  │     │     └── returns (system_prompt, user_prompt)
  │     └── llm_chat([system, user], temperature=0.3)
  │
  └── save_faq(result, dashboard, _ROOT)
        └── write → glossary_faq/faq.md
```

---

## Function Details

### `collect_faq_signals(dashboard, root) → dict`
Reads from 4 sources and returns:
```python
{
  "callouts":             [{page, widget, metric, callout}],
  "cross_page_patterns":  [{pattern, interpretation}],
  "filter_summaries":     [{name, column, slicer_mode, single_select, default}],
  "sub_questions":        [{page, widget, question}],
  "domain_context":       str,
}
```
- Skips pages in `SKIP_PAGES` (utility/tooltip pages)
- Skips filter tables in `SKIP_TABLES` (scatter axis parameter tables)
- Skips filters with names starting with `"Slicer_"` (unnamed slicers)
- Deduplicates filter_summaries by `column` (same filter on multiple pages counted once)
- Translates `"Last Year"` / `"Last Month"` defaults using `PERIOD_MAP`
- Prints warnings for missing files, continues with empty values

### `load_faq_prompt(dashboard) → str`
Tries `prompt/system_prompt/faq.txt`. If found:
- Prepends domain block from `dashboard_config.json`
- Prepends `base_context.txt`

Falls back to `FAQ_SYSTEM_INLINE` if `faq.txt` doesn't exist.

### `build_faq_prompt(data, system_prompt) → tuple[str, str]`
Assembles user prompt with 4 sections (watch-outs, cross-page patterns, filter metadata, sub-questions). LLM is instructed to generate 10–15 FAQ entries covering all signal types.

### `generate_faq(data, llm_client, dashboard) → str`
Calls `llm_chat()` with `temperature=0.3`. Returns raw markdown.

### `save_faq(content, dashboard, root) → Path`
Writes to `output/dashboards/<dashboard>/glossary_faq/faq.md`.

### `_format_callouts(callouts) → str`
Formats each callout as `[page -> widget -> metric]` + watch-out text blocks.

### `_format_cross_page(patterns) → str`
Formats as `Pattern: ...` / `Interpretation: ...` pairs.

### `_format_filters(filters) → str`
Formats as `- Name | column: X | single/multi-select | default: Y`.

### `_format_sub_questions(questions) → str`
Formats as `[page] question text` — deduplicates repeated questions.

---

## LLM Output Structure
The LLM is instructed to produce:
```
## 8.1 Frequently Asked Questions

**[Question in bold?]**
Answer in 1–3 sentences. Prescriptive. Plain English.

[10–15 entries total]
```

6 question categories: filter questions, number mismatch, interpretation, data freshness, navigation, definitions.

---

## File Connections

| Imports from | Used for |
|---|---|
| `utils/llm_client.py` | `llm_chat()` — LLM call with tenacity retry |
| `prompt/system_prompt/faq.txt` | System prompt (optional — falls back to inline) |
| `prompt/system_prompt/base_context.txt` | Shared base rules |
| `prompt/dashboard_config.json` | `users` + `domain` per dashboard |

**Called by:** `runner.py` (as subprocess)

---

## Hardcoded Parts (Change for New Dashboards)

### `SKIP_PAGES` (line ~37)
```python
SKIP_PAGES = {"additional dimensions", "additional_dimensions",
              "scatter plot tooltip", "scatter_plot_tooltip"}
```
Utility page names specific to risk-dash / pac-dash. Add new dashboard's utility pages here.

### `SKIP_TABLES` (line ~39)
```python
SKIP_TABLES = {"X Axis scatter plot", "Y Axis scatter plot"}
```
Parameter table names used by the scatter plot slicer. These are risk-dash / pac-dash specific. If a new dashboard has different scatter axis parameter tables, add their names here, otherwise those slicers show up as filter FAQs.

### `PERIOD_MAP` (line ~40)
```python
PERIOD_MAP = {
    "Last Year" : "YTD (year-to-date: Jan 1 of current year to selected month)",
    "Last Month": "Rolling (last year's date to current date)",
}
```
Maps raw Power BI slicer default values to human-readable period mode descriptions. These names (`"Last Year"`, `"Last Month"`) come from the actual slicer values in the dashboard. If a new dashboard uses different period mode values (e.g. `"YTD"`, `"MTD"`), update this map accordingly.

### `FAQ_SYSTEM_INLINE` (line ~166)
```python
FAQ_SYSTEM_INLINE = """\
You are a documentation writer for a healthcare risk adjustment dashboard.
...
1. Filter questions: wrong numbers, filter order, what does X filter do
...
For Period mode: ALWAYS say "YTD" or "Rolling", never "Last Year" or "Last Month"
"""
```
Inline fallback system prompt is **healthcare risk adjustment specific**. The period mode rule (`"ALWAYS say YTD or Rolling"`) is hardcoded for risk-dash vocabulary. For a different domain:
- Create `prompt/system_prompt/faq.txt` (preferred), OR
- Update the inline fallback

### User prompt hardcoded text (line ~265)
```python
user_prompt = f"""Generate a FAQ section for the Risk Management Dashboard.
...
─── USERS ───────────────────────────────────────────────────
Medical Director, Care Manager, Payer Analyst, Practice Manager
"""
```
"Risk Management Dashboard" title and the user list are hardcoded in the user prompt. Update for new dashboards.

### `build_filter_prompt` column check (line ~152)
```python
if f["column"].lower() in ("period", "period_mode", "periodmode"):
    return PERIOD_MAP.get(raw, raw)
```
Period mode column names are hardcoded. If a new dashboard names its period slicer column differently, add the column name to this check.
