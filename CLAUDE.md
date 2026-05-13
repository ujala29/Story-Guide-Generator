# Story Guide Generator — CLAUDE.md

## What This Project Does

Converts a Power BI dashboard (`.pbix` decomposed into `.Report` + `.SemanticModel` folders) into a structured **Story Guide** — a document that explains every visual on every page in plain business English, including metric definitions, SQL equivalents, directional signals, and drill-down sequences.

---

## Pipeline Execution Order

```
Stage 1  [sequential]  Extraction
Stage 2  [parallel]    Visual_wise | filter_section | Metric_dictionary
Stage 3  [sequential]  Page_wise
Stage 4  [parallel]    dashboard_overview | glossary_faq
```

### How to Run

```bash
# Full pipeline — all dashboards
python main.py

# Single dashboard
python main.py --dashboard risk-dash

# Resume from a specific stage
python main.py --dashboard risk-dash --from-stage 3

# Re-run with cache bypass (Page_wise steps 1/3/4)
python main.py --dashboard risk-dash --from-stage 3 --force

# Visual_wise full run (disable test mode)
python main.py --no-test

# Skip optional Metric_dictionary steps
python main.py --skip-verifier --skip-catalog

# No LLM / Snowflake calls
python main.py --dry-run
```

### Resume from failure — quick reference

| Failed at | Restart command |
|---|---|
| Stage 1 | `python main.py --dashboard risk-dash --from-stage 1` |
| Stage 2 | `python main.py --dashboard risk-dash --from-stage 2` |
| Stage 3 step 0 | `python src/Page_wise/runner.py --dashboard risk-dash --from-step 0` |
| Stage 3 step 3 (widget writer) | `python src/Page_wise/runner.py --dashboard risk-dash --from-step 3 --force` |
| Stage 3 step 4 | `python src/Page_wise/runner.py --dashboard risk-dash --from-step 4` |
| Stage 3 step 5 | `python src/Page_wise/runner.py --dashboard risk-dash --from-step 5` |
| Stage 4 | `python main.py --dashboard risk-dash --from-stage 4` |

### Per-module runners

```bash
python src/Extraction/runner.py --dashboard risk-dash
python src/Metric_dictionary/runner.py --dashboard risk-dash
python src/Visual_wise/runner.py --dashboard risk-dash
python src/filter_section/runner.py --dashboard risk-dash
python src/dashboard_overview/runner.py --dashboard risk-dash
python src/Page_wise/runner.py --dashboard risk-dash
python src/glossary_faq/runner.py --dashboard risk-dash
python src/word_generator/runner.py --dashboard risk-dash
```

---

## Output Folder Structure (module-based, not stage-based)

```
output/dashboards/<dashboard>/
├── extraction/
│   ├── extracted_schema.json
│   └── schema_sections/
│       ├── measures_resolved.json
│       ├── visuals.json
│       ├── filters.json
│       ├── relationships.json
│       └── *.json
├── metric_dictionary/
│   ├── final_measures.json
│   ├── final_measures_with_llm.json
│   ├── registry.json
│   ├── run_report.json
│   ├── metric_catalog.json
│   ├── metric_catalog.md
│   ├── metric_catalog_registry.json
│   └── scope/
├── visual_wise/
│   ├── visuals_enriched.json
│   ├── enriched_pages/        <- per-page enriched JSON
│   ├── l0_packets/
│   ├── l1_packets/
│   ├── l2_packets/
│   └── story_guide/
├── filter_section/
│   └── global_filters.md
├── dashboard_overview/
│   └── dashboard_overview.md
├── page_wise/
│   ├── widget_content/        <- widget narrative JSON (one file per page)
│   ├── funnel_map.json
│   ├── funnel_connector.json
│   ├── funnel_llm_input.json
│   ├── page_wise_story.md
│   └── final_story_guide.md
└── glossary_faq/
    ├── glossary.md
    └── faq.md

output/
├── reference.docx             <- Word style template
└── <dashboard>_story_guide.docx
```

---

## File Map

```
main.py                        <- TOP-LEVEL PIPELINE RUNNER (stages 1->2->3->4)

src/
├── utils/
│   ├── config.py              <- Single source of truth: ALL_DASHBOARDS, DASHBOARDS dict
│   ├── paths.py               <- DashboardPaths, get_paths() — module-based output paths
│   ├── env_check.py           <- assert_env(), assert_prompts() startup validators
│   └── llm_client.py          <- llm_chat() with tenacity retry (5 attempts, exponential backoff)
│
├── paths.py                   <- Backward-compat shim — re-exports from utils.paths
│
├── Extraction/
│   ├── runner.py              <- Stage 1 entry point
│   ├── extractor.py           <- Stage 1 orchestrator
│   ├── tmdl_parser.py
│   ├── relationship_parser.py
│   ├── visual_parser.py
│   ├── dependency_graph.py
│   ├── measure_resolver_.py
│   └── models.py
│
├── Metric_dictionary/
│   ├── runner.py              <- Stage 2 orchestrator (steps 9->10->12, skip-verifier default=True)
│   ├── pipeline_step9.py      <- DAX -> SQL compiler
│   ├── llm_fallback_step10.py <- LLM validate/fix/build/define
│   ├── snowflake_verifier_step11.py  <- optional, skipped by default
│   ├── metric_catalog_step12.py      <- tech + business definitions
│   ├── scope_classifier.py
│   ├── ast_nodes_step0.py
│   ├── cleaner_step1.py
│   ├── lexer_step3.py
│   ├── parser_step4.py
│   ├── dep_resolver_step5.py
│   ├── semantic_resolver_step6.py
│   ├── classifier_step7.py
│   └── sql_generator_step8.py
│
├── Visual_wise/
│   ├── runner.py              <- Stage 2 entry point
│   ├── visaul_pipeline_runner.py          <- core pipeline (TYPO in filename — do not rename)
│   ├── visual_enricher_with_resolved_dax_adder_L0.py
│   ├── visual_parserL0.py                 <- L0: deterministic, no LLM
│   ├── visaul_pareserL1.py                <- L1: LLM (TYPO in filename — do not rename)
│   ├── visual_parserL2.py                 <- L2: LLM cross-visual
│   └── visual_parserL3_storymaking.py     <- L3: LLM narrative
│
├── Page_wise/
│   ├── runner.py              <- Stage 3 orchestrator (steps 0->1->3->4->5)
│   ├── funnel_input_builder_step0.py
│   ├── funnel_mapper_step1.py
│   ├── widget_group_writer_step3.py   <- cached; use --force to regenerate
│   ├── funnel_connector_step4.py
│   ├── document_assembler_step5.py
│   └── Widgets/
│       ├── kpi_card_processor.py       max_tokens=6000
│       ├── trend_lines_processor.py    max_tokens=6000
│       ├── clinical_pair_processor.py  max_tokens=6000
│       ├── detail_table_processor.py   max_tokens=6000
│       ├── entity_scatter_processor.py max_tokens=6000
│       ├── multi_chart_processor.py    max_tokens=6000
│       ├── action_table_processor.py   max_tokens=6000
│       └── segmentation_processor.py   max_tokens=8000 (large — 9 visuals)
│
├── dashboard_overview/
│   ├── runner.py              <- Stage 4 entry point (parallel with glossary_faq)
│   ├── dashboard_overview_generator.py
│   └── dashboard_overview_generator_simple.py
│
├── filter_section/
│   ├── runner.py              <- Stage 2 entry point (parallel)
│   └── filter_story_guidemaker.py
│
├── glossary_faq/
│   ├── runner.py              <- Stage 4 entry point (parallel with dashboard_overview)
│   ├── glossary_generator.py
│   └── faq_generator.py
│
└── word_generator/
    ├── runner.py              <- Runs reference_docx then word_doc sequentially
    ├── generate_reference_docx.py  <- Step 1: output/reference.docx (style template)
    └── generate_word_doc.py        <- Step 2: output/<dashboard>_story_guide.docx
```

---

## Environment Variables (`.env` at project root)

```
TF_BASE_URL=https://truefoundry...
TF_API_KEY=eyJhbG...
TF_MODEL=internal-bedrock/sonnet-46

SNOWFLAKE_ACCOUNT=...
SNOWFLAKE_USER=...
SNOWFLAKE_PASSWORD=...
SNOWFLAKE_WAREHOUSE=...
SNOWFLAKE_DATABASE=...
SNOWFLAKE_SCHEMA=...

# Pipeline test mode (Stage 2 Visual_wise)
STORY_TEST_MODE=1
STORY_TEST_VISUAL_TYPE=cardVisual
STORY_TEST_LIMIT=0
```

**Critical:** All LLM files use `TF_MODEL` / `TF_API_KEY` / `TF_BASE_URL`.
Do NOT use `TRUEFOUNDRY_MODEL` / `TRUEFOUNDRY_API_KEY` / `TRUEFOUNDRY_BASE_URL` — those are wrong.

---

## Adding a New Dashboard

1. Add Power BI files to `input/`
2. Add BI->SF mapping JSON to `input/`
3. `src/utils/config.py`: add to `DASHBOARDS` dict
4. `src/Metric_dictionary/pipeline_step9.py`: add to `DASHBOARD_INPUTS`, `DASHBOARD_SF_MAPS`, `DASHBOARD_RELS`
5. `src/Metric_dictionary/llm_fallback_step10.py`: add to `DASHBOARD_LLM_CONFIGS`
6. `src/Metric_dictionary/metric_catalog_step12.py`: add to `DASHBOARD_CONFIGS`
7. Run: `python main.py --dashboard <new-dash>`

---

## Known Bugs Fixed

| Bug | File | Fix |
|-----|------|-----|
| `from __future__` after injected reconfigure block | pipeline_step9.py, metric_catalog_step12.py | Moved `from __future__` back to top |
| UnicodeEncodeError on Windows cp1252 for emoji/arrows | All entry points | `sys.stdout.reconfigure(encoding="utf-8")` at top of every script |
| UnicodeDecodeError in parallel stream thread | main.py `_run_parallel` | `encoding="utf-8", errors="replace"` on Popen |
| Silent hang after stream thread crash | main.py `_stream` | try/except with pipe drain so subprocess never blocks |
| Ctrl+C leaves child processes running | main.py | `proc.terminate()` on KeyboardInterrupt in `_run` and `_run_parallel` |
| Hardcoded `stage1/stage2/stage3` paths across 19 files | Multiple | Updated to module-based: `extraction/`, `metric_dictionary/`, `visual_wise/`, `page_wise/`, etc. |
| `stage3` variable renamed but one reference missed | faq_generator.py line 136 | `stage3` -> `page_wise` |
| SEGMENTATION widget JSON truncated at 4000 tokens | segmentation_processor.py | Raised to `max_tokens=8000` |
| All other widget processors truncating at 3000 tokens | Widgets/*.py | Raised to `max_tokens=6000` |
| Duplicate `import sys` after injection | snowflake_verifier_step11.py | Removed duplicate |
| `visaul_pipeline_runner.py` missing UTF-8 reconfigure | visaul_pipeline_runner.py | Added at top (it runs as subprocess) |
| Self-import in `_l2_from_dict()` | visual_parserL2.py | Removed |
| Wrong env var `TRUEFOUNDRY_MODEL` | visual_parserL2.py, visaul_pareserL1.py | Changed to `TF_MODEL` |
| `load_prompts()` crashes if prompts/ dir missing | llm_fallback.py | Fallback to inline prompt strings |

---

## Snowflake Date Filter Rules (Critical for SQL Correctness)

| Table | Date Column | MAX_MONTH_FLAG |
|-------|-------------|----------------|
| RISK_CORE_V4_VIEW | MONTH_OF_MEASUREMENT | YES |
| RISK_GROUP_V4_VIEW | MONTH_OF_MEASUREMENT | YES |
| RISK_COHORT_V4_VIEW | MONTH_OF_MEASUREMENT | NO — never add it |
| PCP_VISITS_V4_VIEW | MONTH_OF_DATE | NO |

- BASE measures: `WHERE MAX_MONTH_FLAG = TRUE AND MONTH_OF_MEASUREMENT = :selected_month`
- Time-intel (PY/PM/YoY/MoM): **NEVER** use MAX_MONTH_FLAG (returns 0 rows for prior periods)
- CONTEXT_REMOVER (ALL): no date filter at all

---

## DAX Patterns

| Category | Patterns | Handler |
|----------|----------|---------|
| Compiler handles | SIMPLE_AGG, SIMPLE_DIVIDE, ARITHMETIC, FILTERED_AGG, VAR_FILTERED_DIVIDE, TIME_INTEL_YOY, TIME_INTEL_MOM, MEASURE_RATIO, COMPLEX_VAR_DIVIDE, CONTEXT_REMOVER, STATIC_FILTERED | `sql_generator.py` |
| LLM BUILDER | COMPLEX | `llm_fallback.py` |
| LLM DEFINER only | DISPLAY, INFO_TEXT, UNSUPPORTED | `llm_fallback.py` |

---

## LLM Roles in `llm_fallback_step10.py`

| Role | Trigger | Action |
|------|---------|--------|
| VALIDATOR | scope=IN_SCOPE + sql_query exists | Reviews compiler SQL for logic errors |
| FIXER | VALIDATOR returns needs_fix | Applies corrected SQL |
| BUILDER | scope=IN_SCOPE + llm_role=BUILDER (no SQL) | Generates SQL for complex patterns |
| DEFINER | scope != IN_SCOPE + llm_role=DEFINER | Plain-English definition only |

All results cached in `registry.json`. Re-runs skip API calls for cached measures.

---

## Still Needs Implementation

| Component | Status | File |
|-----------|--------|------|
| Stage 3C: Page Context Builder | NOT CREATED | `src/stage3/page_context_builder.py` |
| Stage 3H: Page Story Assembler | NOT CREATED | `src/stage3/page_story_assembler.py` |
| Phase-based orchestrator | NOT CREATED | `src/stage3/orchestrator.py` |
| dashboard_overview.json companion | NOT CREATED | Enhancement to `dashboard_overview_generator.py` |
| L3 storymaking: partially commented | PARTIAL | `visual_parserL3_storymaking.py` |
