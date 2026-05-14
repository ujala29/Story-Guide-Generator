# widget_group_writer_step3.py — Step 3: Widget Content Generator

## Purpose
For each page, reads widgets from `funnel_map.json`, detects what type each widget is (KPI cards, trend lines, entity table, etc.), dispatches to the appropriate processor in `Widgets/`, runs all widgets for a page **in parallel**, and writes the filled story content to `page_wise/widget_content/<page_slug>.json`.

One LLM call per widget. All widget processors are called concurrently via `ThreadPoolExecutor`.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `page_wise/funnel_map.json` — widget definitions |
| **Input** | `page_wise/funnel_llm_input.json` — visual lookup (enriched data) |
| **Output** | `page_wise/widget_content/<page_slug>.json` — one file per page |
| **Cache** | Checks `content_hash` per page file. Use `--force` to re-run |

---

## Widget Types and Processors

| Type string | Detected when | Processor |
|---|---|---|
| `KPI_CARD_ROW` | All visuals are card / cardVisual / multiRowCard | `process_kpi_card_row()` (in this file) |
| `TREND_LINES` | All visuals are `lineChart` | `Widgets/trend_lines_processor.py` |
| `DETAIL_TABLE` | Has table, no scatter or disease columns | `Widgets/detail_table_processor.py` |
| `CLINICAL_PAIR` | Table + bar chart + disease/risk_factor column | `Widgets/clinical_pair_processor.py` |
| `ENTITY_SCATTER` | Table + scatter chart | `Widgets/entity_scatter_processor.py` |
| `MULTI_CHART` | Bar or donut charts, no table | `Widgets/multi_chart_processor.py` |
| `ACTION_TABLE` | funnel_position=ACTION + has table | `Widgets/action_table_processor.py` |
| `SEGMENTATION` | funnel_position=ACTION, no table | `Widgets/segmentation_processor.py` |

---

## Function Flow

```
main()
  ├── load funnel_map.json + funnel_llm_input.json
  ├── build visual_lookup: {visual_id → visual dict}
  ├── determine pages to process (overview pages first)
  └── for each page:
        process_page(page_name, funnel_map, visual_lookup, out_dir, force, max_workers)
          ├── get widgets for this page from funnel_map
          ├── cache check — skip if content_hash matches
          ├── build funnel_context dict (dashboard_name, funnel questions)
          ├── ThreadPoolExecutor(max_workers)
          │     └── for each widget → run_widget(widget)
          │           └── process_widget(widget, visual_lookup, funnel_context)
          │                 ├── get_widget_visuals()        → enriched visual list
          │                 ├── detect_widget_type()        → type string
          │                 └── dispatch to processor
          │                       KPI_CARD_ROW → process_kpi_card_row()
          │                       TREND_LINES  → process_trend_lines()
          │                       ...
          ├── restore reading_order from funnel_map
          └── write widget_content/<page_slug>.json
```

---

## Function Details

### `detect_widget_type(widget, visuals) → str`
Inspects visual types in the widget and the widget's `funnel_position`. Detection priority:
1. All card types → `KPI_CARD_ROW`
2. All line charts → `TREND_LINES`
3. ACTION + table → `ACTION_TABLE`; ACTION without table → `SEGMENTATION`
4. Table + scatter → `ENTITY_SCATTER`
5. Table + bar + disease/risk_factor column → `CLINICAL_PAIR`; else `BREAKDOWN_WIDGET` (routes to `DETAIL_TABLE`)
6. Table only → `DETAIL_TABLE`
7. Bar or donut → `MULTI_CHART`

### `process_kpi_card_row(widget, visuals, funnel_context, max_retries=3) → dict`
KPI card processor lives in this file (not a separate Widgets/ file). Uses `KPI_SYSTEM` prompt. Calls `call_llm()` with `max_tokens=6000`. Validates: `metrics` array non-empty + `reading_together` present. Retries up to 3 times.

### `build_kpi_prompt(widget, visuals, funnel_context) → str`
Assembles user prompt from `get_unique_measures()`. Each measure line: `metric:`, `definition:`, `dax:` (first 100 chars). Returns expected JSON schema inline.

### `get_unique_measures(visuals) → list`
Deduplicates measures across all visuals. Skips `multiRowCard` visuals (they are YoY/MoM indicator cards — their base metrics come from card visuals). Strips `"Formatted "` prefix from measure names (display wrapper around the same underlying metric).

### `get_widget_visuals(widget, visual_lookup) → list`
Returns enriched visual dicts for all `visual_ids` in the widget. Skips IDs not found in lookup silently.

### `process_widget(widget, visual_lookup, funnel_context) → dict`
Dispatcher. Detects type, gets client, calls the right processor. Returns a `NOT_IMPLEMENTED` placeholder for unknown types.

### `process_page(page_name, funnel_map, visual_lookup, out_dir, force, max_workers)`
Orchestrates one page. Runs all widgets concurrently via `ThreadPoolExecutor`. Uses a `print_lock` so concurrent print statements don't interleave. Restores reading order from `funnel_map` after parallel execution (results come back in completion order, not submission order).

### `page_to_slug(page_name) → str`
`"Overview LY"` → `"overview_ly"` — used for output filenames.

---

## File Connections

| Imports from | Used for |
|---|---|
| `Widgets/trend_lines_processor.py` | `process_trend_lines()` |
| `Widgets/detail_table_processor.py` | `process_detail_table()` |
| `Widgets/clinical_pair_processor.py` | `process_clinical_pair()` |
| `Widgets/entity_scatter_processor.py` | `process_entity_scatter()` |
| `Widgets/multi_chart_processor.py` | `process_multi_chart()` |
| `Widgets/action_table_processor.py` | `process_action_table()` |
| `Widgets/segmentation_processor.py` | `process_segmentation()` |
| `utils/llm_client.py` | `llm_chat()`, `get_client()` |

**Called by:** `runner.py` (Step 3, as subprocess)

**Input from:** `funnel_mapper_step1.py` → `funnel_map.json`, `funnel_input_builder_step0.py` → `funnel_llm_input.json`

**Output consumed by:** `document_assembler_step5.py`

---

## Hardcoded Parts (Change for New Dashboards)

### `CARD_TYPES` (line ~116)
```python
CARD_TYPES = {"card", "cardVisual", "multiRowCard"}
```
Power BI card visual type strings. Standard — unlikely to change.

### `detect_widget_type()` — disease column detection (line ~153)
```python
if any("disease" in c or "risk_factor" in c or "risk_group" in c for c in cols):
    return "CLINICAL_PAIR"
```
Column name keywords used to detect clinical pair widgets. These are **risk-dash specific** column names. For a new dashboard, add its disease/clinical dimension column name patterns here.

### `KPI_SYSTEM` prompt (line ~212)
```python
KPI_SYSTEM = """You are a technical documentation writer...
Your audience is a healthcare analyst or quality leader...
"""
```
References healthcare audience. For a non-healthcare dashboard, update the audience description.

### Overview page detection (line ~563)
```python
overview_pages = [p for p in all_page_names if "overview" in p.lower()]
```
Overview pages are run first. If a new dashboard's main page has a different name (e.g. `"summary"`, `"home"`), add it to this check or remove the ordering entirely.

### `max_tokens=6000` for KPI cards (line ~322)
```python
raw = call_llm(KPI_SYSTEM, prompt, max_tokens=6000)
```
Raised from original 3000 after `finish_reason=length` errors. If a new dashboard has KPI sections with many more metrics, increase further.
