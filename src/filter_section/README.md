# filter_section — Stage 2 README

Stage 2 filter section (runs in parallel with `Visual_wise` and `Metric_dictionary`) reads the slicer list extracted in Stage 1, classifies filters as global or page-specific, and uses an LLM to produce a markdown filter reference guide.

---

## File Overview

| File | Role |
|---|---|
| [runner.py](runner.md) | CLI entry point — orchestrates per-dashboard filter guide generation |
| [filter_story_guidemaker.py](filter_story_guidemaker.md) | All filter processing logic — group, classify, prompt, LLM call, save |

---

## How Files Are Connected

```
runner.py
  │
  ├── imports directly from filter_story_guidemaker.py (not subprocess)
  │     ├── extract_filters_by_page()
  │     ├── get_global_filters()
  │     ├── print_filter_summary()
  │     ├── generate_filter_guide()
  │     └── save_filter_guide()
  │
  ├── utils/env_check.py   → assert_env(), assert_prompts()
  └── utils/config.py      → ALL_DASHBOARDS

filter_story_guidemaker.py
  ├── utils/llm_client.py  → llm_chat()
  └── prompt/
        ├── system_prompt/prompt_for_filter.txt  (required)
        ├── system_prompt/base_context.txt
        └── dashboard_config.json
```

---

## Full Pipeline Call Flow

```
runner.py
  │
  └── run_dashboard(dashboard, llm_client)
        │
        ├── [1] read extraction/schema_sections/filters.json
        │
        ├── [2] extract_filters_by_page(filters)
        │         ├── skip SKIP_PAGES (utility pages)
        │         └── group by page → {page: [filter_dicts]}
        │
        ├── [3] get_global_filters(page_filters)
        │         ├── intersect column sets across all pages
        │         └── return filters common to ALL pages
        │
        ├── [4] print_filter_summary(page_filters, global_filters)
        │         └── console output (dev feedback only)
        │
        └── [5] generate_filter_guide(global_filters, page_filters, llm_client)
                  │
                  ├── load_filter_prompt(dashboard)
                  │     ├── prompt/dashboard_config.json → domain_block
                  │     ├── prompt/system_prompt/base_context.txt
                  │     └── prompt/system_prompt/prompt_for_filter.txt  ← required
                  │
                  ├── build_filter_prompt(global_filters, page_filters, ...)
                  │     ├── _translate_default()   → PERIOD_MODE_MAP translation
                  │     ├── build global_list string
                  │     ├── build page_specific dict (removes global filters)
                  │     └── assemble user_prompt (with mirror-page collapse rule)
                  │
                  ├── llm_chat([system, user], temperature=0.3)
                  │
                  └── save_filter_guide(result, dashboard)
                        └── write → filter_section/global_filters.md
```

---

## Data Flow

```
Stage 1 output:
  extraction/schema_sections/filters.json
          │
          ▼
  filter_story_guidemaker.py
          │
          ├── extract_filters_by_page()   → {page: [filters]}
          ├── get_global_filters()        → [global_filters]
          ├── build_filter_prompt()       → user_prompt string
          ├── llm_chat()                  → markdown string
          │
          ▼
  filter_section/global_filters.md
          │
          ▼
  Consumed by: word_generator (Stage 5) → inserted into final .docx
```

---

## Global vs Page-Specific Filters Explained

```
filters.json (all slicers across all pages)
        │
        ▼ extract_filters_by_page()
{
  "Overview LY": [Year, Month, LOB, PCP Attribution],
  "Overview LM": [Year, Month, LOB, PCP Attribution],
  "Detail LY":   [Year, Month, LOB],
}
        │
        ▼ get_global_filters()
Global (on ALL pages): [Year, Month, LOB]

Page-specific (only on some pages):
  Overview LY/LM: [PCP Attribution]
```

The LLM receives both lists and is instructed to:
1. Collapse mirror pages (LY/LM) into one combined table
2. Never repeat global filters in page-specific tables

---

## Prompt Files Required

| File | Required? | What happens if missing |
|---|---|---|
| `prompt/system_prompt/prompt_for_filter.txt` | **Required** | Script exits with error |
| `prompt/system_prompt/base_context.txt` | Optional | Skipped silently |
| `prompt/dashboard_config.json` | Optional | Uses fallback domain/users |

**Unlike glossary/FAQ** (which have inline fallbacks), the filter prompt **has no fallback** — it hard-exits if `prompt_for_filter.txt` is missing.

---

## How to Run

```bash
# Via runner (recommended)
python src/filter_section/runner.py --dashboard risk-dash
python src/filter_section/runner.py                         # all dashboards

# Direct run (uses main() inside filter_story_guidemaker)
python src/filter_section/filter_story_guidemaker.py --dashboard risk-dash

# Via main.py (full pipeline — Stage 2)
python main.py --dashboard risk-dash --from-stage 2
```

---

## Hardcoded Parts — Summary Across All Files

| File | What's Hardcoded | Impact if Not Changed |
|---|---|---|
| `filter_story_guidemaker.py` | `SKIP_PAGES` | Utility pages included as real dashboard pages |
| `filter_story_guidemaker.py` | `PERIOD_MODE_MAP` | Period mode defaults shown as raw `"Last Year"` instead of `"YTD"` |
| `filter_story_guidemaker.py` | Period column name check (`"period"`, `"period_mode"`, `"periodmode"`) | Period translation not triggered for differently-named columns |
| `filter_story_guidemaker.py` | Mirror page collapse instruction in user prompt (`LY`, `LM`, `YTD`, `MTD`, `Q1-Q4` suffixes) | Mirror pages not collapsed — separate tables generated for each |
| `filter_story_guidemaker.py` | Output filename `global_filters.md` | Fixed — not configurable |
| `runner.py` | Default `--dashboard all` | Only affects direct CLI; `main.py` always passes `--dashboard` |

**Best practice for a new dashboard**:
1. Add the dashboard to `prompt/dashboard_config.json` with `domain` and `users`
2. Update `SKIP_PAGES` if the new dashboard has utility pages with different names
3. Update `PERIOD_MODE_MAP` if the period slicer uses different default values
4. Use the same `prompt_for_filter.txt` or create a dashboard-specific one
