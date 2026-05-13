# Story Guide Generator — CLAUDE.md

## What This Project Does

Converts a Power BI dashboard (`.pbix` decomposed into `.Report` + `.SemanticModel` folders) into a structured **Story Guide** — a document that explains every visual on every page in plain business English, including metric definitions, SQL equivalents, directional signals, and drill-down sequences.

---

## The Core Architecture Problem (Read This First)

The previous pipeline had **four compounding failures**. Fixing any single one without the others still produces description, not interpretation.

### Failure 1: No Page Intent Layer (root cause)

The pipeline ran **bottom-up**: visual → L0 → L1 → L2 → L3 → page story.
The template is structured **top-down**: *What question does this page answer?* → *How does each visual contribute?* → *How do visuals connect?*

Without a Page Context Builder establishing the page's intent first, every visual description is written in a vacuum. L1 interprets a DAX formula. L3 writes about that interpretation. But neither knows they are contributing to a page trying to answer *"Where is our risk capture program underperforming and why?"*

### Failure 2: Layer 2 Was a Stub

`visual_parserL2.py` line ~76 → `raise NotImplementedError`

Layer 2 is the **entire cross-visual interpretation layer**. It generates directional rows, drill paths, and cross-read patterns. Without L2, L3 had no interpretation data to write with.

### Failure 3: Wrong Parallelization Model

Current model: `visual → L0 → L1 → L2 → L3` in parallel across all visuals simultaneously.

This is broken for L2. Layer 2 needs all L1 packets for the page first (to reason about peer visuals). The correct model is **phase-based within each page**: all L0s → page context → all L1s → all L2s → all L3s → page assembler.

### Failure 4: Dashboard Overview Is a Dead End

`dashboard_overview.md` is generated and written to disk. Then nothing reads it back. L1/L2/L3 receive no knowledge of the dashboard's purpose, user roles, or key questions. This is why visual narratives read like documentation, not analysis.

---

## Corrected 8-Stage Pipeline

```
Stage 1: EXTRACTION (existing, no change)
  Power BI .tmdl + .Report files
    → tmdl_parser, visual_parser, relationship_parser, measure_resolver
    → output/dashboards/<dash>/stage1/schema_sections/
        measures_resolved.json, visuals.json, relationships.json, filters.json

Stage 2: METRIC DICTIONARY (existing, no change)
  2a: measures_resolved.json → compiler (cleaner→lexer→parser→AST→sql_generator)
      → final_measures.json
  2b: final_measures.json → LLM (VALIDATOR/FIXER/BUILDER/DEFINER)
      → final_measures_with_llm.json
  2c: final_measures_with_llm.json → LLM (metric_catalog)
      → metric_catalog.json [optional]

Stage 3-PRE-A: Visual Enrichment (existing, no change)
  visuals.json + measures_resolved.json + final_measures_with_llm.json
    → visual_enricher.py → visuals_enriched.json
    → visual_enricher_pages.py → output/enriched_pages/<page_name>.json

Stage 3-PRE-B: Filter Guide (existing, no change)
  filters.json → filter_story_maker.py → LLM → filter_guide/

Stage 3B: Dashboard Overview (existing, enhance slightly)
  all enriched_pages/*.json + filters.json
    → dashboard_overview.py → LLM → dashboard_overview.md
    ENHANCEMENT NEEDED: Also produce dashboard_overview.json (machine-readable)
    with: dashboard_question, user_roles, page_purposes dict

Stage 3C: Page Context Builder (NEW — most critical missing component)
  FOR EACH PAGE:
    all L0 packets for this page + dashboard_overview.json
      → page_context_builder.py → LLM (temp=0.2)
      → output/page_contexts/<page_name>_context.json

Stage 3D: L0 Structure Extraction (existing, no change)
  enriched_page.json (one visual at a time)
    → visual_parserL0.py → L0Packet (deterministic Python, no LLM)
    → output/l0_packets/<page>/<visual_id>.json

Stage 3E: L1 Semantic Interpretation (existing, enhance prompt)
  L0Packet + page_context.json + dashboard_overview.json
    → visaul_pareserL1.py → LLM (temp=0.1) → L1Packet
    → output/l1_packets/<page>/<visual_id>.json
  ENHANCEMENT: Pass visual_role from page_context into L1 prompt

Stage 3F: L2 Cross-Visual Patterns (IMPLEMENT — was stub)
  L0Packet + L1Packet + all peer L1Packets + page_context.json
    → visual_parserL2.py → LLM (temp=0.2) → L2Packet
    → output/l2_packets/<page>/<visual_id>.json
  CONSTRAINT: Must run AFTER all L1s for the page are complete

Stage 3G: L3 Visual Narrative (fix + implement)
  L0Packet + L1Packet + L2Packet + page_context.json
    → visual_parserL3_storymaking.py → LLM (temp=0.1) → markdown section
    → output/l3_packets/<page>/<visual_id>.md

Stage 3H: Page Story Assembler (NEW)
  page_context.json + all L3 sections in reading_order
    → page_story_assembler.py → LLM (temp=0.2)
    → output/page_stories/<page_name>_story.md

Stage 4: Word Document Assembly (existing)
  dashboard_overview.md + filter_guide/ + page_stories/*.md
    → document_assembler.py → final.docx
```

---

## Correct Execution Order (Dependency Graph)

```
Stage 1 → Stage 2a → 2b → [2c optional]
  ↓
3-PRE-A → 3-PRE-B → 3B
  ↓
┌──────────────────────────────────────────────────────┐
│              [FOR EACH PAGE, in parallel]            │
│                                                      │
│  3D: All L0s in parallel (across visuals)            │
│         ↓                                            │
│  3C: Page Context Builder (after all L0s done)       │
│         ↓                                            │
│  3E: All L1s in parallel (L0 + page_context each)   │
│         ↓                                            │
│  3F: All L2s in parallel (all L1s now available)     │
│         ↓                                            │
│  3G: All L3s in parallel (L0+L1+L2+page_context)    │
│         ↓                                            │
│  3H: Page Story Assembler (sequential per page)      │
└──────────────────────────────────────────────────────┘
  ↓
Stage 4: Word Doc Assembly
```

---

## Page Context Builder Output Schema (Stage 3C)

```json
{
  "page": "overview_ly",
  "page_question": "What question is this page designed to answer?",
  "visual_reading_order": ["KPI Cards", "Across LOBs", "Payer/plan details", "..."],
  "visual_roles": {
    "Eligible population card": "primary_kpi",
    "Documented risk card": "primary_kpi",
    "Across LOBs": "breakdown_chart",
    "Payer/plan details": "breakdown_table",
    "Members trend": "supporting_trend"
  },
  "page_narrative_arc": "The KPI cards establish the current state...",
  "key_visual_relationships": [
    {
      "from": "Risk recapture rate card",
      "to": "Payer/plan details table",
      "relationship": "card shows aggregate; table breaks it down by payer"
    }
  ]
}
```

---

## Prompt Context Stack (What Each LLM Call Receives)

| Layer | System Role | Context | Input |
|-------|-------------|---------|-------|
| 3C Page Context | Dashboard Page Architect | dashboard_overview.json | all L0 titles/types/measures |
| 3E L1 Semantic | DAX interpreter | page_context (page_question + visual_role) | L0Packet |
| 3F L2 Cross-visual | Dashboard context analyst | page_context (narrative_arc + relationships) + condensed peer L1s | L1Packet |
| 3G L3 Narrative | Template filler | page_context (visual_role) | L0+L1+L2 |
| 3H Page Assembler | Documentation writer | page_context (reading_order + narrative_arc) | all L3 sections |

---

## Packet Data Flow

```
L0Packet (no LLM)
  visual_id, title, visual_type, page
  primary_measure, primary_dax
  all_dax: [DaxEntry(name, dax, columns, deps, role)]
  paired_dax: [...]   ← YoY/MoM/Color siblings
  comparison: "YoY" | "MoM" | "None"
  active_filters: [str]
  page_visuals: [PageVisual(id, title, type, category)]
  peer_cards: [PeerCard(title, measures)]
  glossary: dict
  is_table / is_linechart / is_barchart / is_donut / is_scatter
  table_columns / chart_lines / x_axis_col / category_axis / etc.

L1Packet (LLM, temp=0.1)
  one_line_definition, numerator_meaning, denominator_meaning
  result_meaning, scope_note
  direction: "higher_is_better" | "lower_is_better" | "context_dependent"
  metric_type: "rate" | "count" | "average" | "gap" | "ratio"
  measure_meanings: {measure_name: str}
  column_definitions: {col: {definition, increasing, decreasing}}  ← tables
  directional_rows (for bar/donut/scatter from L1 directly)

L2Packet (LLM, temp=0.2) — NEEDS IMPLEMENTATION
  directional_rows: [{movement, signal, interpretation}]  ← 3 rows, signal=Positive|Negative|Investigate
  drill_steps: [{step, visual_name, question}]            ← 5-6 steps
  cross_read_combined: {primary_kpi, partners, rows}      ← 6 combined-state rows
  key_patterns: [{pattern, meaning}]                      ← tables only

L3 Output: markdown section per visual (template-filled, temp=0.1)
```

---

## Files To Create (Not Yet Existing)

| File | Purpose |
|------|---------|
| `src/stage3/page_context_builder.py` | Stage 3C — page_context.json per page |
| `src/stage3/page_story_assembler.py` | Stage 3H — assembled page_story.md |
| `src/stage3/orchestrator.py` | Phase-based execution engine (replaces visaul_pipeline_runner.py) |
| `prompts/risk-dash/schema_context.txt` | LLM prompt: Snowflake schema for VALIDATOR/BUILDER |
| `prompts/risk-dash/validator_system.txt` | LLM prompt: VALIDATOR role |
| `prompts/risk-dash/validator_checklist.txt` | LLM prompt: validation checklist |
| `prompts/risk-dash/builder_system.txt` | LLM prompt: BUILDER role |
| `prompts/risk-dash/definer_system.txt` | LLM prompt: DEFINER role |

---

## How to Run (Current State)

### Full pipeline — single command (recommended)

```bash
# Run all stages for all dashboards
python main.py

# Run all stages for one dashboard
python main.py --dashboard risk-dash

# Resume from a specific stage (e.g. skip extraction)
python main.py --dashboard risk-dash --from-stage 2

# Full Visual_wise run (disable test mode)
python main.py --no-test

# Skip optional Metric_dictionary steps
python main.py --skip-verifier --skip-catalog

# No LLM / Snowflake calls (dry run)
python main.py --dry-run
```

Pipeline execution order inside `main.py`:
```
Stage 1  →  Extraction                                (sequential)
Stage 2  →  Visual_wise ∥ filter_section ∥ Metric_dict  (parallel, threaded)
Stage 3  →  Page_wise                                 (sequential)
Stage 4  →  Glossary & FAQ                            (sequential)
```

### Per-module runners (for targeted re-runs)

```bash
# Stage 1 — Extraction + measure resolution
python src/Extraction/runner.py --dashboard risk-dash

# Stage 2 — Metric Dictionary (DAX → SQL → LLM)
python src/Metric_dictionary/runner.py --dashboard risk-dash

# Stage 2 — Visual stories (L0→L1→L2→L3)
python src/Visual_wise/runner.py --dashboard risk-dash

# Stage 2 — Filter guide
python src/filter_section/runner.py --dashboard risk-dash

# Stage 2 — Dashboard overview
python src/dashboard_overview/runner.py --dashboard risk-dash

# Stage 3 — Page_wise story assembly
python src/Page_wise/runner.py --dashboard risk-dash

# Stage 4 — Glossary & FAQ
python src/glossary_faq/runner.py --dashboard risk-dash
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
```

**Critical:** All Stage 3 files use `TF_MODEL` / `TF_API_KEY` / `TF_BASE_URL`.
Do NOT use `TRUEFOUNDRY_MODEL` / `TRUEFOUNDRY_API_KEY` / `TRUEFOUNDRY_BASE_URL` — those are wrong.

---

## File Map

```
main.py                        ← TOP-LEVEL PIPELINE RUNNER (stage 1→2→3→4)
│
src/
├── paths.py                   ← Centralized output-path registry (DashboardPaths, get_paths)
│
├── Extraction/
│   ├── runner.py              ← Stage 1 entry point  ← NEW
│   ├── extractor.py           ← Stage 1 orchestrator (called by runner.py)
│   ├── tmdl_parser.py
│   ├── relationship_parser.py
│   ├── visual_parser.py
│   ├── dependency_graph.py
│   ├── measure_resolver_.py
│   └── models.py
│
├── Metric_dictionary/
│   ├── runner.py              ← Stage 2 orchestrator
│   ├── ast_nodes_step0.py
│   ├── cleaner_step1.py
│   ├── lexer_step3.py
│   ├── parser_step4.py
│   ├── dep_resolver_step5.py
│   ├── semantic_resolver_step6.py
│   ├── classifier_step7.py
│   ├── sql_generator_step8.py
│   ├── pipeline_step9.py      ← DAX → SQL compiler
│   ├── llm_fallback_step10.py ← LLM validate/fix/build/define
│   ├── snowflake_verifier_step11.py
│   ├── metric_catalog_step12.py ← tech + business definitions
│   └── scope_classifier.py
│
├── Visual_wise/
│   ├── runner.py              ← Stage 2 entry point  ← NEW
│   ├── visaul_pipeline_runner.py          ← core pipeline (TYPO — do not rename)
│   ├── visual_enricher_with_resolved_dax_adder_L0.py
│   ├── visual_parserL0.py                 ← L0: visual → L0Packet (deterministic)
│   ├── visaul_pareserL1.py                ← L1: L0 → L1Packet (LLM)  [TYPO — do not rename]
│   ├── visual_parserL2.py                 ← L2: L0+L1 → L2Packet (LLM)
│   └── visual_parserL3_storymaking.py     ← L3: L0+L1+L2 → markdown (LLM)
│
├── Page_wise/
│   ├── runner.py              ← Stage 3 page-wise orchestrator
│   ├── funnel_input_builder_step0.py
│   ├── funnel_mapper_step1.py
│   ├── widget_group_writer_step3.py
│   ├── funnel_connector_step4.py
│   ├── document_assembler_step5.py ← assembles final story guide markdown
│   └── Widgets/
│       ├── kpi_card_processor.py
│       ├── trend_lines_processor.py
│       ├── clinical_pair_processor.py
│       ├── detail_table_processor.py
│       ├── entity_scatter_processor.py
│       ├── multi_chart_processor.py
│       ├── action_table_processor.py
│       └── segmentation_processor.py
│
├── dashboard_overview/
│   ├── runner.py              ← Stage 2 entry point  ← NEW
│   ├── dashboard_overview_generator.py
│   └── dashboard_overview_generator_simple.py
│
├── filter_section/
│   ├── runner.py              ← Stage 2 entry point  ← NEW
│   └── filter_story_guidemaker.py
│
├── glossary_faq/
│   ├── runner.py              ← Stage 4 entry point
│   ├── glossary_generator.py
│   └── faq_generator.py
│
└── word_generator/
    ├── generate_word_doc.py   ← Final Word doc generator (Stage 4)
    └── generate_reference_docx.py

output/dashboards/<dashboard>/
├── stage1/
│   ├── extracted_schema.json
│   └── schema_sections/
│       ├── measures_resolved.json
│       ├── visuals.json
│       ├── filters.json
│       ├── relationships.json
│       └── *.json
├── stage2/
│   ├── final_measures.json
│   ├── final_measures_with_llm.json
│   ├── registry.json
│   ├── run_report.json
│   ├── metric_catalog.json
│   ├── metric_catalog.md
│   ├── metric_catalog_registry.json
│   └── scope/
└── stage3/
    ├── enriched_pages/        ← per-page enriched JSON
    ├── l0_packets/            ← per-visual L0 JSON
    ├── l1_packets/            ← per-visual L1 JSON
    ├── l2_packets/            ← per-visual L2 JSON
    ├── widget_content/        ← widget narrative JSON
    ├── story_guide/           ← per-visual markdown files
    │   ├── overview_ly/
    │   ├── risk_capture_potential/
    │   └── data_availability/
    ├── dashboard_overview.md
    ├── global_filters.md
    ├── faq.md
    ├── glossary.md
    ├── page_wise_story.md
    ├── funnel_map.json
    └── funnel_connector.json
```

---

## Known Bugs Fixed in This Session

| Bug | File | Fix Applied |
|-----|------|-------------|
| Self-import `from visual_parserL2 import DirectionalRow, DrillStep` inside `_l2_from_dict()` | visual_parserL2.py | Removed (classes are in same file) |
| Wrong env var `TRUEFOUNDRY_MODEL` | visual_parserL2.py | Changed to `TF_MODEL` |
| L2 packet save commented out | visual_parserL2.py | Enabled |
| Wrong env vars `TRUEFOUNDRY_MODEL/API_KEY/BASE_URL` (3 places) | visaul_pareserL1.py | Changed to `TF_MODEL/API_KEY/BASE_URL` |
| L1 packet save commented out | visaul_pareserL1.py | Enabled |
| No sys.path setup — imports fail unless run from src/Metric_dictionary/ | pipeline.py | Added sys.path.insert at top |
| `load_prompts()` crashes with FileNotFoundError if prompts/ dir missing | llm_fallback.py | Added fallback to inline prompt strings |

---

## Still Needs Implementation

| Component | Status | File |
|-----------|--------|------|
| Stage 3C: Page Context Builder | NOT CREATED | `src/stage3/page_context_builder.py` |
| Stage 3H: Page Story Assembler | NOT CREATED | `src/stage3/page_story_assembler.py` |
| Phase-based orchestrator | NOT CREATED | `src/stage3/orchestrator.py` |
| dashboard_overview.json companion | NOT CREATED | Enhancement to `dashboard_overview_generator.py` |
| prompts/ directory with .txt files | NOT CREATED | `prompts/risk-dash/*.txt` |
| L3 storymaking: partially commented | PARTIAL | `visual_parserL3_storymaking.py` |

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

## LLM Roles in `llm_fallback.py`

| Role | Trigger | Action |
|------|---------|--------|
| VALIDATOR | scope=IN_SCOPE + sql_query exists | Reviews compiler SQL for logic errors |
| FIXER | VALIDATOR returns needs_fix | Applies corrected SQL |
| BUILDER | scope=IN_SCOPE + llm_role=BUILDER (no SQL) | Generates SQL for complex patterns |
| DEFINER | scope != IN_SCOPE + llm_role=DEFINER | Plain-English definition only |

All results cached in `registry.json`. Re-runs skip API calls for cached measures.

---

## Adding a New Dashboard

1. Add Power BI files to `input/`
2. Add BI→SF mapping JSON to `input/`
3. `pipeline.py`: add to `DASHBOARD_INPUTS`, `DASHBOARD_SF_MAPS`, `DASHBOARD_RELS`
4. `llm_fallback.py`: add to `DASHBOARD_LLM_CONFIGS`, `DASHBOARD_SCHEMA_CONTEXT`
5. `metric_catalog.py`: add to `DASHBOARD_CONFIGS`
6. Run stages 1-4 in order
