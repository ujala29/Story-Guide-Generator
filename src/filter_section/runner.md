# runner.py — Filter Section Entry Point

## Purpose
CLI entry point for Stage 2 filter guide generation. Reads `filters.json` (Stage 1 output), runs the full filter processing pipeline, and calls the LLM to produce `global_filters.md`.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `--dashboard` CLI arg (`risk-dash` / `pac-dash` / `all`, default: `all`) |
| **Reads** | `output/dashboards/<dash>/extraction/schema_sections/filters.json` |
| **Config** | `prompt/dashboard_config.json` — domain, users |
| **Output** | `output/dashboards/<dashboard>/filter_section/global_filters.md` |

---

## How to Run

```bash
python src/filter_section/runner.py                       # all dashboards
python src/filter_section/runner.py --dashboard risk-dash
python src/filter_section/runner.py --dashboard pac-dash
```

---

## Function Flow

```
main()
  ├── parse --dashboard arg
  ├── assert_env()            ← validates TF_API_KEY, TF_BASE_URL, TF_MODEL
  ├── assert_prompts()        ← checks prompt/system_prompt/ exists
  ├── OpenAI client init
  └── for each dashboard:
        run_dashboard(dash, llm_client)

run_dashboard(dashboard, llm_client)
  ├── build filters_path → extraction/schema_sections/filters.json
  ├── check file exists (prints error + returns if missing)
  ├── load filters (json.load)
  ├── extract_filters_by_page(filters) → page_filters{}
  ├── get_global_filters(page_filters) → global_filters[]
  ├── print_filter_summary(page_filters, global_filters)
  ├── generate_filter_guide(global_filters, page_filters, llm_client)
  └── save_filter_guide(result, dashboard)
```

---

## Function Details

### `run_dashboard(dashboard, llm_client)`
Orchestrates one dashboard's filter guide generation. Reads `filters.json`, calls processing functions from `filter_story_guidemaker.py`, prints summary, and triggers the LLM call + save.

### `main()`
Parses args, validates env + prompts, creates the OpenAI client once and reuses it across all dashboards. Loops over `ALL_DASHBOARDS` (from `utils/config.py`) when `--dashboard all` is passed.

---

## File Connections

| Imports from | Used for |
|---|---|
| `filter_story_guidemaker.py` | `extract_filters_by_page`, `get_global_filters`, `print_filter_summary`, `generate_filter_guide`, `save_filter_guide` |
| `utils/env_check.py` | `assert_env()`, `assert_prompts()` |
| `utils/config.py` | `ALL_DASHBOARDS` list |

**Called by:** `main.py` Stage 2 (in parallel with `Visual_wise` and `Metric_dictionary`)

---

## Hardcoded Parts (Change for New Dashboards)

### Default dashboard (line ~83)
```python
parser.add_argument("--dashboard", ..., default="all", ...)
```
Default is `"all"`. When called from `main.py`, `--dashboard` is always passed explicitly.

> **No dashboard-specific config in this file.** Dashboard paths come from `utils/config.py`. Domain and users come from `prompt/dashboard_config.json`. Adding a new dashboard here requires no changes to this file.
