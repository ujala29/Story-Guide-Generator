# filter_story_guidemaker.py — Filter Guide Generator

## Purpose
Reads the raw slicer list from `filters.json`, classifies each filter as global (present on all pages) or page-specific, builds a structured prompt, and calls an LLM to produce a markdown reference table explaining every filter's behavior and default value.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `filters.json` — list of `FilterSchema` objects from Stage 1 extraction |
| **System prompt** | `prompt/system_prompt/prompt_for_filter.txt` (required — exits if missing) |
| **Base prompt** | `prompt/system_prompt/base_context.txt` |
| **Config** | `prompt/dashboard_config.json` — domain, users per dashboard |
| **Output** | `output/dashboards/<dashboard>/filter_section/global_filters.md` |

---

## Pipeline Steps

```
Step 1  extract_filters_by_page()  → group filters by page, skip utility pages
Step 2  get_global_filters()       → find filters common across all pages
Step 3  print_filter_summary()     → console summary (dev feedback)
Step 4  load_filter_prompt()       → load + compose system prompt
Step 5  build_filter_prompt()      → build user prompt with global + page-specific lists
Step 6  generate_filter_guide()    → LLM call → markdown string
Step 7  save_filter_guide()        → write global_filters.md
```

---

## Function Flow

```
runner.py calls:
  extract_filters_by_page(filters)        [Step 1]
  get_global_filters(page_filters)        [Step 2]
  print_filter_summary(...)               [Step 3]
  generate_filter_guide(global_filters, page_filters, llm_client)   [Steps 4–6]
    ├── load_filter_prompt(dashboard)      [Step 4]
    │     ├── PROMPT_DIR/base_context.txt
    │     ├── dashboard_config.json → domain_block
    │     └── PROMPT_DIR/prompt_for_filter.txt   ← required, exits if missing
    ├── build_filter_prompt(global_filters, page_filters, system_prompt, domain, users)  [Step 5]
    │     ├── _translate_default(f)        ← translates "Last Year"/"Last Month"
    │     ├── builds global_list string
    │     ├── builds page_specific dict   ← removes global filters from per-page lists
    │     └── assembles user_prompt with collapsing rule for mirror pages
    └── llm_chat([system, user], temperature=0.3)   [Step 6]
  save_filter_guide(result, dashboard)    [Step 7]
```

---

## Function Details

### `extract_filters_by_page(filters) → dict`
Groups all `FilterSchema` entries by page name. Returns `{page_name: [filter_dicts]}`.

- Skips pages in `SKIP_PAGES` (utility/tooltip pages)
- Each filter entry keeps: `name`, `table`, `column`, `slicer_mode`, `single_select`, `select_all_enabled`, `default_value`, `conditions`
- Does NOT deduplicate — same filter appearing on multiple pages is kept in each page's list

### `get_global_filters(page_filters) → list`
Finds filters common to **all pages** by intersecting column sets.

Algorithm:
1. Start with the column set from the first page
2. Intersect with column sets from all other pages
3. Return filter entries (from page 1) whose columns are in the intersection

**Why from page 1**: all pages are assumed to have the same global filter metadata — only one copy is needed.

### `print_filter_summary(page_filters, global_filters)`
Console output showing total pages, total global filters, and per-page filter list with GLOBAL / page-only labels. Developer feedback only — no effect on output.

### `load_filter_prompt(dashboard) → str`
Builds the system prompt by combining 3 parts:
1. Domain block from `dashboard_config.json` (users + domain)
2. `base_context.txt` (shared base rules)
3. `prompt_for_filter.txt` (filter-specific instructions — **required, hard exits if missing**)

### `build_filter_prompt(global_filters, page_filters, system_prompt, domain, users) → tuple[str, str]`
Assembles the user prompt. Key logic:

- **Global list**: one line per global filter — `Name | column: X | default: Y`
- **Page-specific**: removes global filters from each page's list, then formats remaining
- **`_translate_default(f)`**: translates period mode defaults using `PERIOD_MODE_MAP` — looks at column name to decide if translation applies
- **Mirror page rule**: hardcoded instruction in the user prompt text tells the LLM to collapse mirror pages (e.g. `Overview LY` + `Overview LM`) into one table

### `generate_filter_guide(global_filters, page_filters, llm_client, ...) → str`
Calls `llm_chat()` with `temperature=0.3`. Returns raw markdown string.

### `save_filter_guide(content, dashboard) → Path`
Creates `output/dashboards/<dashboard>/filter_section/` and writes `global_filters.md`.

### `load_dashboard_config(dashboard) → dict`
Reads `prompt/dashboard_config.json` and returns the config dict for the given dashboard. Used in `main()` to get domain + users for the user prompt.

---

## LLM Output Structure
The LLM is instructed to produce **only** this (no intro, no bullets outside tables):
```
## Global Filters

| Filter Name | What it does | Default |
|---|---|---|
[one row per global filter]

## Page-specific Filters

[one table per unique page or mirror group that has page-specific filters]
| Filter Name | What it does | Default |
```

The user prompt contains explicit instructions:
- Mirror pages must be collapsed into one table
- Global filters must not be repeated in page-specific tables

---

## File Connections

| Imports from | Used for |
|---|---|
| `utils/llm_client.py` | `llm_chat()` — LLM call with tenacity retry |
| `prompt/system_prompt/prompt_for_filter.txt` | Filter-specific system prompt (required) |
| `prompt/system_prompt/base_context.txt` | Shared base rules |
| `prompt/dashboard_config.json` | `users` + `domain` per dashboard |

**Called by:** `runner.py` (functions imported directly, not subprocess)

---

## Hardcoded Parts (Change for New Dashboards)

### `SKIP_PAGES` in `extract_filters_by_page()` (line ~46)
```python
SKIP_PAGES = {"additional dimensions", "additional_dimensions",
              "scatter plot tooltip", "scatter_plot_tooltip"}
```
Utility page names for risk-dash / pac-dash. Add new dashboard's utility pages here (both space and underscore versions).

### `PERIOD_MODE_MAP` in `build_filter_prompt()` (line ~146)
```python
PERIOD_MODE_MAP = {
    "Last Year":  "YTD (year-to-date: Jan 1 of current year to selected month)",
    "Last Month": "Rolling (last year's date to current date)",
}
```
Raw slicer default values → human-readable period descriptions. These values (`"Last Year"`, `"Last Month"`) are the actual default values set in the Power BI slicer for risk-dash. If a new dashboard uses different period mode defaults (e.g. `"YTD"`, `"MTD"`, `"Monthly"`), update this map.

### Period column name check (line ~152)
```python
if f["column"].lower() in ("period", "period_mode", "periodmode"):
    return PERIOD_MAP.get(raw, raw)
```
Column names that trigger period translation are hardcoded. If a new dashboard's period slicer uses a different column name (e.g. `"time_period"`, `"selected_period"`), add it to this tuple.

### Default domain + users in `generate_filter_guide()` signature (line ~204)
```python
def generate_filter_guide(
    global_filters, page_filters, llm_client,
    domain: str = "Healthcare dashboard",
    users: str = "Analyst, Executive",
    dashboard: str = "risk-dash",
) -> str:
```
Default values for `domain` and `users` are generic fallbacks. When called from `runner.py`, these are passed from `dashboard_config.json`. When called from `main()` (direct run), `load_dashboard_config()` provides the values.

### Mirror page collapsing instruction (line ~192)
```python
"Mirror pages (pages that share the same base name but differ only by a time-period suffix like LY, LM, YTD, MTD, Q1-Q4) must be collapsed into ONE table..."
```
This instruction is hardcoded in the user prompt string. It references `LY`, `LM`, `YTD`, `MTD`, `Q1-Q4` suffixes — which are specific to the current dashboards' naming convention. If a new dashboard uses different page naming suffixes, update this instruction.

### Output filename (line ~232)
```python
out_path = out_dir / "global_filters.md"
```
Fixed filename. Not configurable. All dashboards write to the same filename within their own folder.

### Prompt file requirement
```python
except FileNotFoundError:
    print(f"ERROR: Prompt file not found: {PROMPT_DIR / 'prompt_for_filter.txt'}")
    sys.exit(1)
```
`prompt_for_filter.txt` is **required** — the script hard-exits if missing. Unlike glossary/FAQ which have inline fallbacks, the filter prompt has no fallback. Each new dashboard can customize `prompt_for_filter.txt`, or it can share the existing one.
