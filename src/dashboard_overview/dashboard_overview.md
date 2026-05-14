# dashboard_overview — Pipeline Documentation

## Purpose
Generates the "Dashboard at a Glance" section of the Story Guide — a plain-English executive summary that explains what the dashboard does, what key questions it answers, how the funnel connects across pages, and how to navigate it. Runs as Stage 4 (parallel with `glossary_faq`). Two versions exist: the enhanced generator (uses Page_wise outputs for richer context) and a simple baseline generator (uses raw visual type lists).

---

## Files in This Folder

| File | Role |
|---|---|
| `runner.py` | Entry point — parses CLI args, initialises LLM client, loops over dashboards |
| `dashboard_overview_generator.py` | Enhanced version — reads `funnel_map.json`, `funnel_connector.json`, `widget_content/*.json`; builds rich LLM context |
| `dashboard_overview_generator_simple.py` | Baseline version — reads raw `enriched_pages/*.json`; sends flat visual-type lists to LLM; kept for output quality comparison |

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `output/dashboards/<dash>/page_wise/funnel_map.json` — funnel questions, domain context, widget-to-page mapping |
| **Input B** | `output/dashboards/<dash>/page_wise/funnel_connector.json` — `funnel_table`, `cross_page_patterns`, `closing_paragraph` (Step 4 output) |
| **Input C** | `output/dashboards/<dash>/page_wise/widget_content/*.json` — widget group intros and metric names per page |
| **Input D** | `output/dashboards/<dash>/extraction/schema_sections/filters.json` — global filter names |
| **Input E** | `prompt/system_prompt/base_context.txt` + `prompt/system_prompt/dashboard_overview.txt` — LLM system prompts |
| **Input F** | `prompt/dashboard_config.json` — domain and users per dashboard |
| **Output** | `output/dashboards/<dash>/dashboard_overview/dashboard_overview.md` — executive summary in markdown |
| **Output (simple)** | `output/dashboards/<dash>/dashboard_overview/dashboard_overview_simple.md` — baseline version for comparison |

---

## Pipeline Steps

```
Step 1   gather_dashboard_info()   → read funnel_map, funnel_connector, widget_content, filters
Step 2   load_overview_prompt()    → build system prompt (domain block + base_context + dashboard_overview.txt)
Step 3   build_overview_prompt()   → build user prompt (domain, funnel questions, pages, widgets, metrics, cross-page patterns, filters)
Step 4   generate_dashboard_overview()  → single LLM call (temperature=0.3)
Step 5   save_overview()           → write dashboard_overview.md
```

---

## Function Flow

```
runner.py  main()
  ├── load .env, assert_env(), assert_prompts()
  ├── parse --dashboard arg (default: all)
  └── for each dashboard:
        run_dashboard(dashboard, llm_client)
          ├── read filters.json
          ├── gather_dashboard_info(dashboard, root, filters)
          │     ├── read page_wise/funnel_map.json → domain_context, funnel_questions, widget list
          │     ├── read page_wise/funnel_connector.json → funnel_table, cross_page_patterns, closing_paragraph
          │     ├── read page_wise/widget_content/*.json → page_widget_intros, all_metrics
          │     ├── dedupe filter names (skip Slicer_*, skip scatter axis tables)
          │     └── return assembled info dict
          ├── generate_dashboard_overview(info, llm_client)
          │     ├── load_overview_prompt()  → system prompt string
          │     ├── build_overview_prompt() → (system_prompt, user_prompt)
          │     │     ├── _format_widgets_by_page()      → funnel position + question per widget
          │     │     ├── _format_page_intros()          → group intro + metrics per page
          │     │     ├── _format_funnel_table()         → layer / section / question table
          │     │     └── _format_cross_page_patterns()  → pattern + interpretation bullets
          │     └── llm_chat([system, user], temperature=0.3, client=llm_client)
          └── save_overview(result, dashboard, root)
                └── write output/dashboards/<dash>/dashboard_overview/dashboard_overview.md
```

---

## `info` Dict Schema (output of `gather_dashboard_info`)

```python
domain_context         : str           # from funnel_map["domain_context"]
funnel_question_top    : str           # "What is the current state?" layer
funnel_question_middle : str           # "Why / trend" layer
funnel_question_bottom : str           # "Who / what" layer
funnel_question_action : str           # "What to do" layer
pages_processed        : list[str]     # page names from funnel_map._meta
pages_mirrored         : list[str]     # _LM pages mirrored from _LY
widgets_by_page        : dict[str, list]   # {page: [{name, question, funnel_position, reading_order}]}
page_widget_intros     : dict[str, list]   # {page: [{widget_name, group_intro, metrics}]}
key_metrics            : list[str]     # all metric names across all widget_content, deduped
filters                : list[str]     # global filter names from filters.json
funnel_table           : list[dict]    # from funnel_connector: [{layer, section, question_it_answers}]
cross_page_patterns    : list[dict]    # from funnel_connector: [{pattern, interpretation}]
closing_paragraph      : str           # from funnel_connector
```

---

## LLM Call

| Property | Value |
|---|---|
| Temperature | 0.3 |
| System prompt | `domain block` + `base_context.txt` + `dashboard_overview.txt` |
| User prompt | Domain context, funnel questions (TOP/MIDDLE/BOTTOM/ACTION), pages, widget structure, widget intros, key metrics, funnel table, cross-page patterns, closing arc, global filters, users |
| Returns | Full "Dashboard at a Glance" markdown section |
| Retry | Via `llm_chat()` in `utils/llm_client.py` (tenacity, 5 attempts, exponential backoff) |

---

## Simple Baseline vs Enhanced Generator

| Aspect | `dashboard_overview_generator_simple.py` | `dashboard_overview_generator.py` |
|---|---|---|
| Context source | Raw `enriched_pages/*.json` | `funnel_map.json` + `funnel_connector.json` + `widget_content/*.json` |
| What LLM receives | Flat lists: KPI cards, tables, charts, metrics, filters | Funnel questions, widget reading order, group intros, cross-page patterns, closing arc |
| Output file | `dashboard_overview_simple.md` | `dashboard_overview.md` |
| Used by pipeline | No (comparison only) | Yes — assembled into final Word doc |
| LLM client | Direct `client.chat.completions.create()` | `llm_chat()` with tenacity retry |

---

## File Connections

| Imports from | Used by | Purpose |
|---|---|---|
| `utils/llm_client.py` | `dashboard_overview_generator.py` | `llm_chat()` with tenacity retry |
| `utils/paths.py` | runner.py (via `_ROOT`) | output path resolution |
| `utils/env_check.py` | `runner.py` | `assert_env()`, `assert_prompts()` |
| `utils/config.py` | `runner.py` | `ALL_DASHBOARDS` list |
| `prompt/system_prompt/dashboard_overview.txt` | `dashboard_overview_generator.py` | LLM instruction template |
| `prompt/dashboard_config.json` | both generators | domain + users per dashboard |

**Called by:** `main.py` Stage 4 (parallel with `glossary_faq`)

---

## Hardcoded Parts (Change for New Dashboards)

### `SKIP_TABLES` — `dashboard_overview_generator.py` (line ~71)
```python
SKIP_TABLES = {"X Axis scatter plot", "Y Axis scatter plot"}
```
Filter table names that are scatter plot axis slicers, not real filters. Add any new dashboard's technical slicer tables here so they don't appear in the "Global Filters" section of the overview.

### `build_overview_prompt()` — LY/LM mirror page note — `dashboard_overview_generator.py` (line ~204)
```python
if page.upper().endswith(" LY"):
    base = page[:-3].rstrip()
    if (base + " LM").upper() in mirrored_set:
        lines.append(
            f"  - {base}: has two comparison views — "
            f"Last Year / LY (year-over-year) and "
            f"Last Month / LM (month-over-month, in-period monitoring). ..."
        )
```
Automatically merges `*_LY` / `*_LM` mirror pages into one bullet in the overview. Works dynamically from `pages_mirrored`. If a new dashboard uses different mirror suffixes, update this check.

### `users` in `build_overview_prompt()` — `dashboard_overview_generator.py` (line ~262)
```python
─── USERS ───────────────────────────────────────────
- Medical Director
- Care Manager
- Payer Analyst
- Practice Manager
```
Currently hardcoded in the user prompt string. For a new dashboard, update this block or source it from `prompt/dashboard_config.json` instead.
