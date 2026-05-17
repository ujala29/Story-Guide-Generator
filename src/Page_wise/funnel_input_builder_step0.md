# funnel_input_builder_step0.py — Step 0: Build LLM Input

## Purpose
Reads Stage 1 and Stage 2 output files and assembles a single clean JSON (`funnel_llm_input.json`) that is the complete input for all downstream LLM calls in the Page_wise pipeline. No LLM calls are made here — this is purely a data aggregation and cleaning step.

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `output/dashboards/<dash>/visual_wise/enriched_pages/*.json` — one file per page, contains visuals |
| **Input B** | `output/dashboards/<dash>/extraction/schema_sections/pages.json` — page ordering |
| **Input C** | `output/dashboards/<dash>/extraction/schema_sections/measures_resolved.json` — DAX + dependency tree per measure |
| **Input D** | `output/dashboards/<dash>/metric_dictionary/metric_catalog_registry.json` — business + technical definitions |
| **Input E** | `config/fixes.json` — `title_overrides` for wrong/stale visual titles |
| **Input F** | `config/dashboard_config.json` — dashboard display name |
| **Output** | `output/dashboards/<dashboard>/page_wise/funnel_llm_input.json` |

---

## What the Output Contains (per visual)

```json
{
  "visual_id": "...",
  "title": "...",
  "type": "cardVisual",
  "page": "Main page LY",
  "measures": [
    {
      "name": "Overall Readmission %",
      "dax": "DIVIDE(...)",
      "definition": "Business definition from metric_catalog_registry",
      "display_name_in_visual": "Overall Readmission %",
      "role": "primary"
    },
    {
      "name": "Overall Readmission % YoY Card",
      "dax": "VAR py = CALCULATE(...) RETURN ...",
      "definition": "",
      "display_name_in_visual": "Overall Readmission % YoY Card",
      "role": "yoy_comparison"
    }
  ],
  "columns_used": ["date.month_of_year"],
  "row_dimensions": ["risk_model_name"]   // pivotTable only
}
```

`role` values: `"primary"` (visual's own measure) | `"yoy_comparison"` | `"mom_comparison"` | `"comparison"` (paired multiRowCard measures folded in).

---

## Function Flow

```
main()
  └── build_funnel_llm_input(dashboard, root)
        ├── load: enriched_pages/*.json, pages.json, measures_resolved.json
        │         metric_catalog_registry.json, fixes.json, dashboard_config.json
        │
        ├── resolve dashboard_name (4-level fallback chain)
        │
        ├── build pages[] — sorted by order, skip SKIP_PAGES, skip *_LM mirrors
        │
        ├── for each enriched_pages/*.json file:
        │     skip SKIP_PAGES + LM mirror pages
        │     _build_pairing_map(page_visuals)  → cv_to_supports, paired_ids
        │     for each visual:
        │       skip SKIP_TYPES (slicers, decorations)
        │       skip multiRowCard/card if id in paired_ids (folded into parent cardVisual)
        │       resolve_title(v, title_overrides)
        │       skip if empty (no title, no measures, no columns)
        │       paired = cv_to_supports[v.id] if cardVisual else None
        │       build_visual_entry(v, title, definitions, measures_resolved, paired)
        │         ├── build_measure_entries(visual, definitions, measures_resolved, paired)
        │         │     ├── primary measures → role="primary"
        │         │     ├── paired multiRowCard measures → role="yoy_comparison"|"mom_comparison"
        │         │     ├── strip_table_prefix(raw)        → remove "ALL DAX." prefix
        │         │     ├── measures_resolved.get(name)    → full dep tree for this measure
        │         │     ├── get_leaf_dax(chain)             → deepest leaf formula
        │         │     ├── definitions.get(name)           → business_definition
        │         │     └── get_display_name_for_measure()  → axis label shown in visual
        │         └── get_row_dimensions(axis_bindings)   → pivot table row labels
        │
        ├── build content_hash (MD5 of visual IDs + measure names)
        └── return complete funnel_llm_input dict
```

---

## Function Details

### `build_funnel_llm_input(dashboard, root) → dict`
Main aggregator. Reads all source files and assembles the complete LLM input. Handles missing files gracefully (returns empty fallbacks). Skips LM mirror pages by checking if a `*_LY` counterpart exists.

### `resolve_title(visual, title_overrides) → str`
5-level title resolution priority:
1. Manual override from `fixes.json` (by visual ID) — always wins
2. For non-card visuals: `visual["title"]` if non-empty and not in `GENERIC_TITLES`
3. For card types or generic titles: `axis_bindings` display_name for first Measure
4. First `measures_used` name (after stripping table prefix)
5. Visual type as last resort

### `_build_pairing_map(page_visuals) → (cv_to_supports, paired_ids)`
Pre-computes per-page pairing between `cardVisual` and its supporting `multiRowCard`/`card` tiles.
- Matching rule: `cv_primary in sc_primary` (substring, case-insensitive) — same logic as `visual_parserL0._find_paired_visuals`
- Strips `"formatted "` wrapper before matching (e.g. "Formatted Avg LOS" → "avg los")
- Returns `cv_to_supports` (cardVisual id → list of support visuals) and `paired_ids` (set of claimed support card IDs)
- Works for all dashboards — no hardcoded measure names

### `build_measure_entries(visual, definitions, measures_resolved, paired_visuals=None) → list`
For each measure in `measures_used` (role = `"primary"`):
- Strips `"ALL DAX."` table prefix (risk-dash measure container name)
- Looks up the measure in `measures_resolved` to get its full dependency tree
- Gets leaf DAX via `get_leaf_dax()` — LLM only needs the bottom-most formula
- Looks up `business_definition` → fallback to `technical_definition` from `metric_catalog_registry`
- Gets `display_name_in_visual` — the axis label shown to users, not the internal measure name

Then for each measure in `paired_visuals` (role = `"yoy_comparison"` / `"mom_comparison"` / `"comparison"`):
- Same resolution as primary measures
- Role detected from measure name: contains "yoy" → `yoy_comparison`, "mom" → `mom_comparison`
- Deduped via `seen` set — no measure appears twice

### `get_leaf_dax(measure_chain) → str`
BFS traversal of the `depends_on` tree. Finds the first node with `is_leaf=True` — this is the deepest measure with a real column formula. The leaf DAX is concise and reveals what data the measure reads. Calls `_clean_dax()` to strip metadata lines appended by Power BI.

### `_clean_dax(dax) → str`
Removes Power BI metadata annotations that appear after the formula: `formatString:`, `lineageTag:`, `annotation PBI_FormatHint`. These are storage metadata, not part of the formula.

### `strip_table_prefix(raw) → str`
Strips `"ALL DAX."` prefix from measure names. Column references (e.g. `"date.month_of_year"`) keep their prefix because the table name is meaningful. Only the `"ALL DAX"` measure container is stripped.

### `get_display_name_for_measure(measure_name, axis_bindings) → str`
Searches `axis_bindings` for a Measure entry matching `measure_name`. Returns the `display_name` shown in the visual if it differs from the internal name. E.g. `"Risk recapture rate PY"` might display as `"Previous year"`.

### `get_row_dimensions(axis_bindings) → list`
Extracts `rows` from axis_bindings for pivotTable/matrix visuals. These dimension names tell the LLM what entity/category the table is broken down by — critical for funnel position classification.

### `get_project_root() → Path`
Walks up the file tree looking for a folder containing both `output/` and `config/`. Fallback: looks for `run.py`. Final fallback: 3 levels up from this file.

---

## File Connections

**No imports from other Page_wise files.** Pure stdlib + json.

**Called by:** `runner.py` (Step 0, as subprocess)

**Output consumed by:** `funnel_mapper_step1.py` (Step 1)

---

## Hardcoded Parts (Change for New Dashboards)

### `SKIP_TYPES` (line ~63)
```python
SKIP_TYPES = {
    "slicer", "advancedSlicerVisual", "textbox", "image",
    "shape", "actionButton", "basicShape",
}
```
Visual types that are never content — always skipped. Standard across all Power BI dashboards; unlikely to need changes.

### `SKIP_PAGES` (line ~73)
```python
SKIP_PAGES = {
    "Scatter plot tooltip",
    "Additional dimensions",
    "Data availability",
}
```
Utility page names for risk-dash / pac-dash. Add new dashboard's utility pages here (exact display names from `pages.json`).

### `GENERIC_TITLES` (line ~197)
```python
GENERIC_TITLES = {
    "Pharmacy PMPM YoY",
    "Leakage %",
    "Card",
    "Visual",
    "",
}
```
`"Pharmacy PMPM YoY"` and `"Leakage %"` are **risk-dash specific** stale section-header titles that incorrectly appear as card titles. Add new dashboard's bad titles here if `visual_parser.py`'s title extraction picks up wrong container headings.

### `strip_table_prefix` — `"ALL DAX."` (line ~111)
```python
if raw.startswith("ALL DAX."):
    return raw[len("ALL DAX."):]
```
Hardcoded for the risk-dash measure container name `"ALL DAX"`. PAC-dash uses `"all_dax_pac"` but measures are stored differently there. If a new dashboard has a different measure container name that appears as a prefix in `measures_used`, add it here or generalize the logic.

### `KNOWN_DASHBOARD_NAMES` (line ~357)
```python
KNOWN_DASHBOARD_NAMES = {
    "risk-dash": "Risk Management",
    "pac-dash":  "PAC",
}
```
Fallback display names used when `dashboard_config.json` is missing or doesn't have `display_name`. Add new dashboards here as a safety net.
