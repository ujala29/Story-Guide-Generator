# Visual_wise — Pipeline Documentation

## Purpose
Converts per-page enriched visual JSON into individual Story Guide markdown files using a 4-layer pipeline. Each visual is processed through L0 (deterministic structuring) → L1 (DAX interpretation via LLM) → L2 (directional signals + drill order via LLM) → L3 (markdown assembly from structured data). All layers within a page run in parallel.

---

## Files in This Folder

| File | Role |
|---|---|
| `runner.py` | Entry point — parses CLI args, spawns `visaul_pipeline_runner.py` as subprocess |
| `visaul_pipeline_runner.py` | Core orchestrator — page discovery, preprocessing, parallel 4-phase execution (TYPO in filename — do not rename) |
| `visual_enricher_with_resolved_dax_adder_L0.py` | Pre-processor — adds `measure_chains` to each visual, splits into per-page files |
| `visual_parserL0.py` | L0 — deterministic structuring, no LLM, builds `L0Packet` |
| `visaul_pareserL1.py` | L1 — LLM DAX interpreter, builds `L1Packet` (TYPO in filename — do not rename) |
| `visual_parserL2.py` | L2 — LLM context builder, builds `L2Packet` |
| `visual_parserL3_storymaking.py` | L3 — markdown assembler from structured data, builds `L3Packet` |

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `output/dashboards/<dash>/extraction/schema_sections/visuals.json` — all visuals from extraction |
| **Input B** | `output/dashboards/<dash>/extraction/schema_sections/measures_resolved.json` — resolved DAX chains |
| **Input C** | `prompt/system_prompt/base_context.txt` + `card.txt` / `lineChart.txt` / etc. — LLM system prompts |
| **Input D** | `prompt/dashboard_config.json` — domain and users per dashboard |
| **Input E** | `config/fixes.json` — `title_overrides`, `generic_titles`, `skip_types` |
| **Output A** | `output/dashboards/<dash>/visual_wise/visuals_enriched.json` — all visuals with `measure_chains` |
| **Output B** | `output/dashboards/<dash>/visual_wise/enriched_pages/<page>.json` — one file per page |
| **Output C** | `output/dashboards/<dash>/visual_wise/l0_packets/<page>/<id>.json` — per-visual L0 |
| **Output D** | `output/dashboards/<dash>/visual_wise/l1_packets/<page>/<id>.json` — per-visual L1 |
| **Output E** | `output/dashboards/<dash>/visual_wise/l2_packets/<page>/<id>.json` — per-visual L2 |
| **Output F** | `output/dashboards/<dash>/visual_wise/story_guide/<page>/<id>_<title>.md` — final narrative |

---

## Pipeline Steps

```
Pre-Step  enrich_and_split()       → adds measure_chains, saves enriched_pages/*.json
Step 1    discover_pages()         → find all non-skipped page JSON files
Step 2    preprocess()             → fix titles, skip SKIP_TYPES
Step 3    deduplicate()            → remove duplicate primary measures
Step 4    apply_test_filter()      → TEST_MODE: limit visual types
Phase 1   build_l0_packet()        → parallel L0 (no LLM)
Phase 2   call_layer1()            → parallel L1 (LLM: DAX interpretation)
Phase 3   call_layer2()            → parallel L2 (LLM: directional + drill + cross-read)
Phase 4   call_layer3()            → parallel L3 (markdown assembly, no LLM)
```

---

## Function Flow

```
runner.py  main()
  └── subprocess: visaul_pipeline_runner.py  main()
        ├── enrich_and_split(visuals, measures_resolved, enriched_pages_dir)
        │     ├── add measure_chains per visual
        │     ├── save visuals_enriched.json
        │     └── save enriched_pages/<page>.json (one per page)
        │
        ├── discover_pages()
        │     ├── skip SKIP_FILES (utility/tooltip pages)
        │     └── skip *_lm.json that have a *_ly.json counterpart
        │
        ├── [per page] process_page()
        │     ├── preprocess(all_visuals)
        │     │     ├── fix_title()   — override / generic / blank → measure name
        │     │     └── detect_issues()
        │     ├── deduplicate(fixed_visuals)
        │     │     ├── TABLE_LIKE types → dedupe by visual id
        │     │     └── KPI card types  → dedupe by primary measure name
        │     ├── apply_test_filter()  → if TEST_MODE, restrict visual types
        │     │
        │     ├── PHASE 1 (parallel, L0_WORKERS=8)
        │     │     └── build_l0_packet(visual, page_context) → L0Packet
        │     │           ├── build_page_context(all_visuals)  ← called ONCE before loop
        │     │           ├── resolve primary measure from axis_bindings
        │     │           ├── lookup all_dax + paired_dax via MEASURES_RESOLVED
        │     │           ├── detect YoY / MoM comparison from paired card measures
        │     │           ├── parse active_filters from filter_config
        │     │           ├── parse all_columns → ColumnRef list
        │     │           └── skip if no primary measure found
        │     │
        │     ├── PHASE 2 (parallel, MAX_WORKERS=3)
        │     │     └── call_layer1(l0, llm_client) → L1Packet
        │     │           ├── load system prompt (base_context + visual-type prompt)
        │     │           ├── build user prompt with DAX + columns + glossary
        │     │           └── LLM → one_line_definition, numerator_meaning,
        │     │                     denominator_meaning, result_meaning,
        │     │                     direction, metric_type, sql_equivalent,
        │     │                     watch_out, italic_callout
        │     │
        │     ├── PHASE 3 (parallel, MAX_WORKERS=3)  ← starts AFTER all L1s complete
        │     │     └── call_layer2(l0, l1, llm_client) → L2Packet
        │     │           ├── build user prompt with page_visuals + peer_cards + L1 profile
        │     │           └── LLM → directional_impact (3 rows), drill_steps (5-6),
        │     │                     cross_read_patterns (per peer card)
        │     │
        │     └── PHASE 4 (parallel, MAX_WORKERS=3)
        │           └── call_layer3(l0, l1, l2, llm_client) → L3Packet
        │                 ├── assemble markdown from structured L0+L1+L2 data
        │                 └── save story_guide/<page>/<id>_<title>.md
        │
        └── print final summary (per-page + overall counts)
```

---

## Packet Schemas

### `L0Packet` — Deterministic pre-processing output
```python
visual_id        : str
title            : str
visual_type      : str          # "cardVisual" | "lineChart" | etc.
page             : str
primary_measure  : str          # e.g. "RAF recapture rate"
primary_dax      : DaxEntry     # full resolved DAX + columns + deps
all_dax          : list[DaxEntry]   # visual's own measures
paired_dax       : list[DaxEntry]   # companion multiRowCard / card measures
comparison       : str          # "YoY % change" | "MoM % change" | "None"
active_filters   : list[str]    # ["year", "month", "payer"]
all_columns      : list[ColumnRef]
page_visuals     : list[PageVisual]   # all other visuals on page, categorised
peer_cards       : list[PeerCard]     # cross-read candidates
glossary         : dict
# type-specific flags:
is_table / is_linechart / is_barchart / is_donut / is_scatter : bool
table_columns / chart_lines / bar_orientation / legend_col / etc.
skip             : bool
skip_reason      : str
```

### `L1Packet` — LLM DAX interpretation output
```python
visual_id            : str
one_line_definition  : str    # plain English definition
numerator_meaning    : str    # what numerator represents
denominator_meaning  : str    # what denominator represents (empty if not ratio)
result_meaning       : str    # what the output value means
direction            : str    # "higher = better" | "lower = better" | "neutral"
metric_type          : str    # "rate" | "count" | "cost" | "index"
sql_equivalent       : str    # SQL translation of the DAX
watch_out            : str    # known gotchas / edge cases
italic_callout       : str    # callout text for story guide
```

### `L2Packet` — LLM context builder output
```python
visual_id           : str
directional_impact  : list[DirectionalRow]   # exactly 3 rows
    # DirectionalRow: movement, signal ("Positive/Negative/Investigate"), interpretation
drill_steps         : list[DrillStep]        # 5-6 steps
    # DrillStep: step (int), visual_name, action
cross_read_patterns : list[CrossReadCombined]  # one per peer card
    # CrossReadCombined: partner_title, rows (list of 4 pattern/signal/action)
```

### `L3Packet` — Final markdown output
```python
visual_id   : str
title       : str
page        : str
visual_type : str
markdown    : str   # full Story Guide section in markdown
skip        : bool
skip_reason : str
```

---

## LLM Calls Per Layer

| Layer | Temperature | What LLM receives | What LLM returns |
|---|---|---|---|
| **L1** | 0.1 (factual) | DAX formula, referenced columns, glossary, visual type | `one_line_definition`, `numerator_meaning`, `denominator_meaning`, `result_meaning`, `direction`, `metric_type`, `sql_equivalent`, `watch_out`, `italic_callout` |
| **L2** | 0.2 (structured) | L1 profile + page_visuals + peer_cards + active_filters | `directional_impact` (3 rows), `drill_steps` (5-6), `cross_read_patterns` (per peer) |
| **L3** | no LLM | L0 + L1 + L2 structured data | markdown assembled directly in code |

---

## File Connections

| Imports from | Used by | Purpose |
|---|---|---|
| `visual_enricher_with_resolved_dax_adder_L0` | `visaul_pipeline_runner.py` | `enrich_and_split()` — adds measure_chains |
| `visual_parserL0` | `visaul_pipeline_runner.py` | `build_page_context()`, `build_l0_packet()`, `save_l0_packet()` |
| `visaul_pareserL1` | `visaul_pipeline_runner.py` | `call_layer1()` |
| `visual_parserL2` | `visaul_pipeline_runner.py` | `call_layer2()` |
| `visual_parserL3_storymaking` | `visaul_pipeline_runner.py` | `call_layer3()` |
| `utils/llm_client.py` | L1, L2 | `llm_chat()` with tenacity retry |
| `utils/paths.py` | all layers | `get_paths(dashboard)` — output dir resolution |
| `prompt/system_prompt/*.txt` | `visaul_pipeline_runner.py` | per-visual-type system prompts |
| `prompt/dashboard_config.json` | `visaul_pipeline_runner.py` | domain + users for prompt prefix |
| `config/fixes.json` | `visual_parserL0.py` | `title_overrides`, `generic_titles`, `skip_types` |

**Called by:** `main.py` Stage 2 (parallel with `filter_section` and `Metric_dictionary`)

---

## Hardcoded Parts (Change for New Dashboards)

### `SKIP_FILES` — `visaul_pipeline_runner.py` (line ~82)
```python
SKIP_FILES = {
    "additional_dimensions.json",
    "scatter_plot_tooltip.json",
    "pages_summary.json",
}
```
Utility/tooltip pages specific to risk-dash / pac-dash. Add any new dashboard's non-analytical pages here.

### `PAGE_COMPARISON_CONTEXT` — `visaul_pipeline_runner.py` (line ~94)
```python
PAGE_COMPARISON_CONTEXT = {
    "overview_ly.json": {
        "label"          : "Overview",
        "periods"        : ["YoY", "MoM"],
        "canonical_note" : "...",
    },
    ...
}
```
Maps page filenames to their comparison method labels. Add new dashboard's page names here to get correct comparison notes in the story guide. If a page isn't in this dict it still processes — just without a comparison label.

### `VISUAL_TYPE_MAP` — `visaul_pipeline_runner.py` (line ~136)
```python
VISUAL_TYPE_MAP = {
    "cardVisual"        : "card.txt",
    "lineChart"         : "lineChart.txt",
    "areaChart"         : "lineChart.txt",
    "donutChart"        : "donutChart.txt",
    "clusteredBarChart" : "clusteredBarChart.txt",
    "pivotTable"        : "pivotTable.txt",
    "tableEx"           : "pivotTable.txt",
    "scatterChart"      : "scatterChart.txt",
    "card"              : None,    # ← skipped (no prompt)
    "multiRowCard"      : None,    # ← skipped
    "slicer"            : None,    # ← skipped
}
```
Maps Power BI visual type → system prompt filename. `None` = visual is skipped (no story guide generated). Add new visual types here with a matching prompt file in `prompt/system_prompt/`.

### `TEST_MODE` env vars — `visaul_pipeline_runner.py` (line ~73)
```python
TEST_MODE        = os.environ.get("STORY_TEST_MODE",   "1") == "1"
TEST_VISUAL_TYPE = os.environ.get("STORY_TEST_VISUAL_TYPE", "cardVisual")
TEST_LIMIT       = int(os.environ.get("STORY_TEST_LIMIT", "0"))
```
Default is test mode ON (processes only 1 `cardVisual` + all tables/lines/charts/donuts/scatters). Pass `--no-test` via runner.py or set `STORY_TEST_MODE=0` for a full run.

### `_lm` / `_ly` mirror page detection — `visaul_pipeline_runner.py` (line ~206)
```python
duplicate_page_pairs = {
    fname: fname[:-8] + "_ly.json"
    for fname in all_fnames
    if fname.endswith("_lm.json") and fname[:-8] + "_ly.json" in all_fnames
}
```
Automatically skips `*_lm.json` pages that have a `*_ly.json` counterpart. Works dynamically — no per-dashboard hardcoding needed. If a new dashboard uses different suffixes for mirror pages, update this pattern.

### `deduplicate()` dedup logic — `visaul_pipeline_runner.py` (line ~708)
KPI cards deduplicated by **primary measure name** (first `measures_used` entry). TABLE_LIKE types deduplicated by **visual id**. If a new dashboard has multiple cards showing the same measure for different purposes (different pages or contexts), this dedup will collapse them — handle by ensuring different titles or ids.
