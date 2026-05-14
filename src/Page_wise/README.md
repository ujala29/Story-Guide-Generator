# Page_wise — Stage 3 README

Stage 3 converts the visual-level enriched data into a structured, narrative Story Guide for each dashboard page. It runs 5 sequential steps, making multiple LLM calls to classify visuals, group them into widgets, generate interpretive content for each widget, and assemble everything into a final markdown document.

---

## File Overview

| File | Step | Role |
|---|---|---|
| [runner.py](runner.md) | — | CLI entry point — orchestrates steps 0→1→3→4→5 |
| [funnel_input_builder_step0.py](funnel_input_builder_step0.md) | 0 | Aggregates Stage 1+2 data → `funnel_llm_input.json` (no LLM) |
| [funnel_mapper_step1.py](funnel_mapper_step1.md) | 1 | 3-call LLM: classify visuals + group into widgets → `funnel_map.json` |
| [widget_group_writer_step3.py](widget_group_writer_step3.md) | 3 | 1 LLM call per widget → `widget_content/<page>.json` (parallel) |
| [funnel_connector_step4.py](funnel_connector_step4.md) | 4 | 1 LLM call → funnel table + cross-page patterns → `funnel_connector.json` |
| [document_assembler_step5.py](document_assembler_step5.md) | 5 | No LLM — renders all JSONs → `page_wise_story.md` |
| [Widgets/README.md](Widgets/README.md) | — | All 7 widget processors (same pattern, different prompts) |

---

## How Files Are Connected

```
runner.py
  │  (subprocess for each step)
  │
  ├── Step 0: funnel_input_builder_step0.py
  │     reads: visual_wise/enriched_pages/*.json
  │             extraction/schema_sections/pages.json
  │             metric_dictionary/metric_catalog_registry.json
  │             config/fixes.json
  │             config/dashboard_config.json
  │     writes: page_wise/funnel_llm_input.json
  │
  ├── Step 1: funnel_mapper_step1.py
  │     reads: page_wise/funnel_llm_input.json
  │     LLM calls: Call1(funnel questions) + Call2(classify) + Call3(group) per page
  │     writes: page_wise/funnel_map.json
  │
  ├── Step 3: widget_group_writer_step3.py
  │     reads: page_wise/funnel_map.json
  │             page_wise/funnel_llm_input.json
  │     imports: Widgets/*.py (7 processors)
  │     LLM calls: 1 per widget (parallel within page)
  │     writes: page_wise/widget_content/<page_slug>.json (one per page)
  │
  ├── Step 4: funnel_connector_step4.py
  │     reads: page_wise/funnel_map.json
  │     LLM calls: 1 total
  │     writes: page_wise/funnel_connector.json
  │
  └── Step 5: document_assembler_step5.py
        reads: page_wise/funnel_map.json
                page_wise/widget_content/*.json
                page_wise/funnel_connector.json
        writes: page_wise/page_wise_story.md
                (also feeds into word_generator as final_story_guide.md)
```

---

## Full Data Flow

```
Stage 2 outputs (visual_wise/enriched_pages/)   ─────┐
Stage 1 outputs (extraction/schema_sections/)   ──── ▼
Stage 2 outputs (metric_dictionary/)            ── funnel_input_builder_step0.py
                                                       │
                                                       ▼
                                            page_wise/funnel_llm_input.json
                                                       │
                                         ┌─────────────┤
                                         │             │
                                         ▼             ▼
                               funnel_mapper_step1.py  widget_group_writer_step3.py
                               (3 LLM calls/page)      (1 LLM call/widget, parallel)
                                         │             │
                                         ▼             ▼
                               page_wise/funnel_map.json   widget_content/*.json
                                         │
                                         ▼
                               funnel_connector_step4.py  (1 LLM call)
                                         │
                                         ▼
                               page_wise/funnel_connector.json
                                         │
                               ┌─────────┼──────────────────┐
                               │         │                  │
                               ▼         ▼                  ▼
                         funnel_map  widget_content  funnel_connector
                               │         │                  │
                               └─────────┴──────────────────┘
                                         │
                                         ▼
                              document_assembler_step5.py  (no LLM)
                                         │
                                         ▼
                              page_wise/page_wise_story.md
                                         │
                                         ▼
                              word_generator (Stage 5) → <dashboard>_story_guide.docx
```

---

## LLM Calls Summary

| Step | File | Calls | Per |
|---|---|---|---|
| 1 | `funnel_mapper_step1.py` | Call 1 (funnel questions) — once per dashboard | — |
| 1 | `funnel_mapper_step1.py` | Call 2 (classify) + Call 3×N (group buckets) | per page |
| 3 | `widget_group_writer_step3.py` + `Widgets/*.py` | 1 call | per widget (parallel) |
| 4 | `funnel_connector_step4.py` | 1 call | per dashboard |

**Total LLM calls** (typical risk-dash with 4 pages, ~15 widgets):
- Step 1: 1 + (2×4 pages) + (3-4 bucket calls × 4 pages) ≈ 25 calls
- Step 3: ~15 calls (one per widget)
- Step 4: 1 call
- **Total: ~40 LLM calls for a full pipeline run**

---

## Caching Behavior

| Step | Cache mechanism | Override |
|---|---|---|
| Step 1 (`funnel_mapper`) | `content_hash` in `funnel_map.json` matches input | `--force` |
| Step 3 (`widget_writer`) | `content_hash` per page file in `widget_content/` | `--force` |
| Step 4 (`funnel_connector`) | `content_hash` in `funnel_connector.json` | `--force` |
| Step 0 (`input_builder`) | No cache — always re-runs | — |
| Step 5 (`assembler`) | No cache — always re-renders | — |

`content_hash` = MD5 of visual IDs + measure names. Changing measures or visuals in the dashboard invalidates the cache automatically.

---

## Widget Processing Architecture

```
widget_group_writer_step3.py
  │
  ├── detect_widget_type(widget, visuals) → "KPI_CARD_ROW" | "TREND_LINES" | ...
  │
  └── dispatch to processor:
        KPI_CARD_ROW    → process_kpi_card_row()     (in widget_group_writer_step3.py)
        TREND_LINES     → Widgets/trend_lines_processor.py
        DETAIL_TABLE    → Widgets/detail_table_processor.py
        CLINICAL_PAIR   → Widgets/clinical_pair_processor.py
        ENTITY_SCATTER  → Widgets/entity_scatter_processor.py
        MULTI_CHART     → Widgets/multi_chart_processor.py
        ACTION_TABLE    → Widgets/action_table_processor.py
        SEGMENTATION    → Widgets/segmentation_processor.py
```

---

## How to Run

```bash
# Full pipeline
python src/Page_wise/runner.py --dashboard risk-dash

# Resume from step
python src/Page_wise/runner.py --dashboard risk-dash --from-step 3

# Force re-run (bypass caches)
python src/Page_wise/runner.py --dashboard risk-dash --force

# More parallel workers in step 3
python src/Page_wise/runner.py --dashboard risk-dash --workers 5

# Individual steps
python src/Page_wise/funnel_input_builder_step0.py --dashboard risk-dash
python src/Page_wise/funnel_mapper_step1.py --dashboard risk-dash
python src/Page_wise/widget_group_writer_step3.py --dashboard risk-dash --all
python src/Page_wise/funnel_connector_step4.py --dashboard risk-dash
python src/Page_wise/document_assembler_step5.py --dashboard risk-dash
```

---

## Hardcoded Parts — Summary Across All Files

| File | What's Hardcoded | Impact if Not Changed |
|---|---|---|
| `funnel_input_builder_step0.py` | `SKIP_PAGES` | Utility pages included in funnel input |
| `funnel_input_builder_step0.py` | `GENERIC_TITLES` — `"Pharmacy PMPM YoY"`, `"Leakage %"` | Stale risk-dash section headers used as visual titles |
| `funnel_input_builder_step0.py` | `strip_table_prefix` — `"ALL DAX."` | Measure names include table container prefix |
| `funnel_input_builder_step0.py` | `KNOWN_DASHBOARD_NAMES` | Falls back to dashboard key if config missing |
| `funnel_mapper_step1.py` | `TIME_PERIOD_SUFFIXES` | New time suffixes not recognized as mirror pages |
| `funnel_mapper_step1.py` | `ACTION_PAGE_KEYWORDS` | Action pages not detected → classified as regular pages |
| `funnel_mapper_step1.py` | `SYSTEM_PROMPT` grouping rules | Healthcare dimension taxonomy; wrong for other domains |
| `widget_group_writer_step3.py` | Disease column detection (`"disease"`, `"risk_factor"`) | Clinical pair detection fails for new column naming |
| `widget_group_writer_step3.py` | `KPI_SYSTEM` audience | References healthcare analyst |
| `document_assembler_step5.py` | `LAYER_LABELS` — `"The risk position"`, `"The diagnosis"` | Domain-specific layer names in output document |
| `document_assembler_step5.py` | Footer `"L5 Knowledge Base"` | Innovaccer-specific reference |
| `Widgets/*.py` | System prompts — healthcare audience + vocabulary | Wrong domain context in generated content |
| `Widgets/segmentation_processor.py` | `outreach_action` field + AWV/telehealth examples | Healthcare-specific outreach actions |
