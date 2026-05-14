# visaul_pipeline_runner.py — Core Pipeline Orchestrator

## Purpose
The main execution engine for the Visual_wise pipeline. Runs the enricher, discovers pages, preprocesses and deduplicates visuals, then executes 4 parallel phases (L0→L1→L2→L3) per page. Pages run sequentially; visuals within each page run in parallel via `ThreadPoolExecutor`.

**NOTE: filename has a typo (`visaul_pipeline_runner`) — do not rename.**

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `output/dashboards/<dash>/visual_wise/enriched_pages/*.json` — per-page enriched visuals |
| **Input B** | `output/dashboards/<dash>/extraction/schema_sections/measures_resolved.json` |
| **Input C** | `config/fixes.json` — `title_overrides`, `generic_titles`, `skip_types` |
| **Input D** | `prompt/system_prompt/*.txt` + `prompt/dashboard_config.json` |
| **Env vars** | `STORY_DASHBOARD`, `STORY_TEST_MODE`, `STORY_TEST_VISUAL_TYPE`, `STORY_TEST_LIMIT` |
| **Output** | `story_guide/<page>/<id>_<title>.md` — one markdown file per processed visual |

---

## Pipeline Steps

```
Step 0  enrich_and_split()       → enriched_pages/*.json
Step 1  discover_pages()         → page list with skip flags
Step 2  print_page_plan()        → show what will run / skip
Step 3  [per page, sequential] process_page()
          Phase 1  build_l0_packet()  × all visuals  (parallel, L0_WORKERS=8)
          Phase 2  call_layer1()      × active L0s   (parallel, MAX_WORKERS=3)
          Phase 3  call_layer2()      × active L1s   (parallel, MAX_WORKERS=3)
          Phase 4  call_layer3()      × active L2s   (parallel, MAX_WORKERS=3)
Step 4  print final summary
```

---

## Function Flow

```
main()
  ├── enrich_and_split(visuals_path, measures_resolved, enriched_pages_dir)
  ├── discover_pages()
  │     ├── glob enriched_pages/*.json
  │     ├── build duplicate_page_pairs: *_lm.json → skip if *_ly.json exists
  │     ├── skip SKIP_FILES (hardcoded utility pages)
  │     └── load page JSON + attach PAGE_COMPARISON_CONTEXT
  ├── print_page_plan(pages)
  └── [per non-skipped page] process_page(page, llm_client)
        ├── preprocess(all_visuals) → (fixed_visuals, report)
        │     ├── fix_title(visual)     — override / generic / blank
        │     └── detect_issues(visual) — log title problems
        ├── deduplicate(fixed_visuals)
        │     ├── TABLE_LIKE types     → dedupe by visual.id
        │     └── card types          → dedupe by primary measure name
        ├── apply_test_filter(deduplicated)
        │     └── if TEST_MODE: return cards[limit] + tables + lines + charts + donuts + scatters
        ├── build_page_context(all_visuals)  [L0 pre-computation]
        │
        ├── PHASE 1: ThreadPoolExecutor(L0_WORKERS=8)
        │     └── [per visual] build_l0_packet(v, page_context) → save_l0_packet()
        │
        ├── PHASE 2: ThreadPoolExecutor(MAX_WORKERS=3)  [after ALL L0s done]
        │     └── [per active L0] call_layer1(l0, llm_client)
        │
        ├── PHASE 3: ThreadPoolExecutor(MAX_WORKERS=3)  [after ALL L1s done]
        │     └── [per active L1] call_layer2(l0, l1, llm_client)
        │
        └── PHASE 4: ThreadPoolExecutor(MAX_WORKERS=3)  [after ALL L2s done]
              └── [per active L2] call_layer3(l0, l1, l2, llm_client)
```

---

## Key Functions

### `discover_pages() → list[dict]`
Returns a list of page dicts, each with:
```python
{
  'file'       : "overview_ly.json",
  'path'       : Path(...),
  'data'       : {...},         # None if skipped
  'skip'       : False,
  'skip_reason': '',
  'context'    : PAGE_COMPARISON_CONTEXT entry or {}
}
```
Skip reasons: `"explicitly excluded"` (SKIP_FILES) or `"mirror of '<ly_file>' — same visuals, different comparison period (LM)"` (auto-detected `*_lm` mirrors).

### `preprocess(all_visuals) → (list, dict)`
Strips SKIP_TYPES visuals, fixes titles, logs issues. Returns `(fixed_visuals, report)`.

### `deduplicate(fixed_visuals) → list`
- `TABLE_LIKE` types (`pivotTable`, `tableEx`, `lineChart`, etc.): dedupe by `visual.id`
- Card types: dedupe by primary measure name (first `measures_used` entry, table prefix stripped)

### `apply_test_filter(visuals) → list`
If `TEST_MODE=True`: returns `cards[:TEST_LIMIT] + tables + lines + charts + donuts + scatters`. `TEST_LIMIT=0` = all cards. Allows limiting which card types run during development.

### `fix_title(visual) → str`
1. Check `TITLE_OVERRIDES[visual.id]` (hardcoded fixes)
2. If title in `GENERIC_TITLES` → use `measures_used[0]`
3. If blank → use `measures_used[0]` or `visual.type`

### `lookup_all_measures_dax(measures_used) → str`
Formats a DAX block string for all measures in the list. Used in `build_prompt()` (legacy path — not used by the 4-phase pipeline, only by the old single-visual `generate_story_guide()` function).

### `build_prompt(visual, all_visuals, system_prompt, page_context_meta) → (str, str)`
Legacy prompt builder. Used by the old single-pass approach. Not called in the current 4-phase pipeline (which uses per-layer prompts inside L1/L2/L3 files). Kept for reference.

### `load_prompt(visual_type) → str | None`
Loads `base_context.txt` + domain block from `dashboard_config.json` + visual-type prompt file. Returns `None` if visual type has no prompt (→ skipped). Used by legacy `generate_story_guide()`.

---

## Configuration Constants

| Constant | Value | Purpose |
|---|---|---|
| `MAX_WORKERS` | 3 | Parallel threads for L1/L2/L3 phases |
| `L0_WORKERS` | 8 | Parallel threads for L0 phase (no LLM, CPU-only) |
| `LLM_CALL_DELAY` | 0.5s | Sleep between LLM calls in old single-pass path |
| `TEST_MODE` | `STORY_TEST_MODE` env | Whether to restrict visual types |
| `TEST_VISUAL_TYPE` | `STORY_TEST_VISUAL_TYPE` env | Which type to run (default `cardVisual`) |
| `TEST_LIMIT` | `STORY_TEST_LIMIT` env | Max cards to process (0 = unlimited) |

---

## Visual Type Map

| Power BI type | Prompt file | Processed? |
|---|---|---|
| `cardVisual` | `card.txt` | Yes |
| `lineChart` | `lineChart.txt` | Yes |
| `areaChart` | `lineChart.txt` | Yes |
| `donutChart` | `donutChart.txt` | Yes |
| `clusteredBarChart` | `clusteredBarChart.txt` | Yes |
| `barChart` | `clusteredBarChart.txt` | Yes |
| `columnChart` | `clusteredBarChart.txt` | Yes |
| `pivotTable` | `pivotTable.txt` | Yes |
| `tableEx` | `pivotTable.txt` | Yes |
| `scatterChart` | `scatterChart.txt` | Yes |
| `card` | None | Skipped |
| `multiRowCard` | None | Skipped |
| `slicer` | None | Skipped |

---

## File Connections

| Imports from | Used for |
|---|---|
| `visual_enricher_with_resolved_dax_adder_L0` | `enrich_and_split()` |
| `visual_parserL0` | `build_page_context()`, `build_l0_packet()`, `save_l0_packet()` |
| `visaul_pareserL1` | `call_layer1()` |
| `visual_parserL2` | `call_layer2()` |
| `visual_parserL3_storymaking` | `call_layer3()` |
| `utils/llm_client.py` | `llm_chat()` (legacy path only) |
| `utils/paths.py` | `get_paths()`, `get_config()` |
| `prompt/system_prompt/*.txt` | Per-type system prompts (legacy path) |
| `prompt/dashboard_config.json` | Domain + users per dashboard |
| `config/fixes.json` | `TITLE_OVERRIDES`, `GENERIC_TITLES`, `SKIP_TYPES` |

**Called by:** `runner.py` (as subprocess)

---

## Hardcoded Parts (Change for New Dashboards)

### `SKIP_FILES` (line ~82)
```python
SKIP_FILES = {
    "additional_dimensions.json",
    "scatter_plot_tooltip.json",
    "pages_summary.json",
}
```
Add new dashboard's utility/tooltip page filenames here.

### `PAGE_COMPARISON_CONTEXT` (line ~94)
```python
PAGE_COMPARISON_CONTEXT = {
    "overview_ly.json": {
        "label"  : "Overview",
        "periods": ["YoY (Year-over-Year)", "MoM (Month-over-Month)"],
    },
    ...
}
```
Maps page filename → comparison method label. Add new dashboard pages here. Missing entries are silently ignored (processed without comparison note).

### `VISUAL_TYPE_MAP` (line ~136)
Maps visual type → prompt filename. Add new visual types here with a corresponding `.txt` prompt file in `prompt/system_prompt/`.

### `deduplicate()` dedup key (line ~708)
Cards deduplicated by primary measure name. If a new dashboard has two cards with the same primary measure but different purposes, they will collapse to one. Ensure unique measure names or adjust dedup logic.

### `_lm` mirror detection (line ~206)
```python
fname.endswith("_lm.json") and fname[:-8] + "_ly.json" in all_fnames
```
Auto-skips `*_lm.json` when a `*_ly.json` counterpart exists. Update the `_lm` / `_ly` suffix pattern if a new dashboard uses different mirror page naming.
