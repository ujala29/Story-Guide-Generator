# visual_parser.py — Report Layout, Visuals, Filters, Bookmarks, Metadata

## Purpose
Reads the `.Report` folder and extracts all visual-related data: pages, visuals, filters (slicers), cross-filter interactions, bookmarks, toggle groups, and report-level metadata (theme, export settings, custom visuals).

This is the largest file in Stage 1 — split into 4 sections.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | Path to `.Report` folder |
| **Reads** | `definition/report.json` — theme, settings, resources, custom visuals |
| **Reads** | `definition/version.json` — PBIP version string |
| **Reads** | `definition/pages/<PageFolder>/page.json` — display name, canvas size, interactions |
| **Reads** | `definition/pages/<PageFolder>/visuals/<VisualFolder>/visual.json` — visual type, bindings, title |
| **Reads** | `definition/bookmarks/*.json` — bookmark states |
| **Output (ReportLayoutParser)** | `pages[]`, `visuals[]`, `filters[]`, `interactions{}` |
| **Output (BookmarkExtractor)** | `bookmarks[]`, `toggle_groups[]` |
| **Output (ReportMetaParser)** | `ReportMeta` object |

---

## Module Layout (4 sections)

```
Section 1: Module-level helpers    ← shared functions used by all classes
Section 2: ReportMetaParser        ← reads report.json + version.json
Section 3: ReportLayoutParser      ← reads pages + visuals + filters + interactions
Section 4: BookmarkExtractor       ← reads bookmarks + builds toggle groups
```

---

## Section 1: Module-Level Helpers

These functions are **called by both** `ReportLayoutParser` and `BookmarkExtractor` (shared logic, not duplicated).

### `build_visual_map(pages_dir) → dict`
Reads **all** `visual.json` files across all pages in one pass. Built once in `extractor.py` Step 3 and passed to both `ReportLayoutParser.extract()` and `BookmarkExtractor.extract()`.

Returns: `{visual_id: info_dict}` where each entry has:
- `kind` — `"visual"` or `"group"` (layout group container)
- `title`, `type`, `page`, `parent_group`, `is_hidden`
- `measures_used`, `columns_used`, `axis_bindings`
- `width`, `height`

### `_extract_title(visual_node) → str`
Extracts the visual's display title. Two special cases:
- **cardVisual / card**: uses `displayName` from the first measure projection (not the container title, which is a section header shared across all cards)
- **All others**: reads `visualContainerObjects.title` → then falls back to `objects.title`

### `_extract_fields_with_roles(visual_node) → (axis_bindings, measures, columns)`
Role-aware field extraction. Maps Power BI `queryState` role names to semantic axis keys using `ROLE_TO_AXIS`:

| Power BI Role | Semantic Key |
|---|---|
| `Category`, `Axis`, `X` | `x_axis` |
| `Values`, `Value`, `Y` | `y_axis` |
| `Series`, `Legend`, `Details` | `legend` |
| `Tooltips` | `tooltip` |
| `Size` | `size` |
| `Rows` | `rows` |
| `Columns` | `columns` |
| `Field` | `x_axis` |
| `Small multiples` | `small_multiples` |

For each field: extracts `field_type` (`Measure` / `Column` / `HierarchyLevel`), `table`, `property`, `display_name`. Omits `active: true` (default) — only writes `active: false` when different.

Also returns flat `measures_used` and `columns_used` lists for backward compatibility with `BookmarkExtractor`.

### `_parse_filter_config(data) → list`
Extracts `filterConfig` from top level of `visual.json` (NOT inside the visual node). Returns human-readable filter entries. Drops entries with no field AND no conditions (zero LLM value). Drops the `"name"` hash key (meaningless).

### `_describe_condition(cond) → str`
Converts a Power BI filter condition dict into a human-readable string: handles `Not`, `Comparison`, `In` condition types.

### `_extract_entity(field_node) → str`
Extracts table name from a field reference node via `field_node["Expression"]["SourceRef"]["Entity"]`.

### `_extract_slicer_meta(visual_node) → dict`
Reads slicer display properties (`mode`, `header_text`, `single_select`, `select_all_enabled`) directly from raw `objects` dict. Called only by `_make_filter()` — not stored on `VisualSchema` (cosmetic props).

---

## Section 2: ReportMetaParser

### `ReportMetaParser(report_path)`
Reads `report.json` and `version.json`.

**`extract() → ReportMeta`**
Extracts:
- `theme` — base theme + custom theme name + `llm_note`
- `custom_visuals` — matched against `CUSTOM_VISUAL_REGISTRY` (currently only `ChicletSlicer`)
- `settings` — export mode, drill behavior, tooltip flags (via `_parse_settings()`)
- `slow_settings` — cross-highlighting, apply-all button (via `_parse_slow_settings()`)
- `filter_config` — filter sort order + `llm_note`
- `resources` — embedded images, theme files
- `llm_context` — pre-assembled descriptions for LLM use

**`_match_custom_visual(vid) → dict`**
Looks up the visual ID prefix against `CUSTOM_VISUAL_REGISTRY`. If not found, returns a generic "unknown custom visual" warning entry.

**`_parse_settings(raw) → dict`**
Maps known Power BI setting keys to human descriptions. Handles: `exportDataMode`, `defaultDrillFilterOtherVisuals`, `useEnhancedTooltips`, `allowChangeFilterTypes`, `useStylableVisualContainerHeader`, `useDefaultAggregateDisplayName`.

**`_parse_slow_settings(raw) → dict`**
Reads `isCrossHighlightingDisabled` and `isApplyAllButtonEnabled` and flips to positive flags.

---

## Section 3: ReportLayoutParser

### `ReportLayoutParser(report_path)`
Reads pages, visuals, slicers, and interactions.

**`extract(visual_map) → (pages, visuals, filters, interactions)`**
Main loop: iterates all page folders alphabetically. For each page:
1. Reads `page.json` → page metadata (display name, canvas size)
2. Iterates visual folders → reads `visual.json`
3. Skips visuals not in `MEANINGFUL_VISUAL_TYPES`
4. Calls `_parse_visual()` for each kept visual
5. Calls `_make_filter()` for slicer visuals

Finally calls `_parse_interactions(visual_map)`.

**`_parse_visual(data, vid, page_name) → Optional[VisualSchema]`**
Parses one `visual.json` into a `VisualSchema`. Reads:
- `position` from **top level** (not inside `visual` node)
- `filterConfig` from **top level** via `_parse_filter_config()`
- `visualType`, `drillFilterOtherVisuals` from inside `visual` node
- Fields via `_extract_fields_with_roles()`

Intentionally drops: `x, y, z, tab_order` (canvas position), `sort`, `objects/container` (formatting).

**`_make_filter(data, v, page_name) → Optional[FilterSchema]`**
Builds a `FilterSchema` from a slicer visual. Role priority for field lookup: `Values` → `Field` → `Category` → `Y`. Reads `syncGroup` from top-level data. Returns `None` if no bound column/measure found.

**`_parse_interactions(visual_map) → dict`**
Reads `visualInteractions` array from each `page.json`. Groups by source visual, categorizes as `"DataFilter"` (filters) vs other (`no_filters`). Skips decorative types (`shape`, `textbox`, `image`, `actionButton`, `basicShape`). Returns per-page interaction summary with `llm_description`.

---

## Section 4: BookmarkExtractor

### `BookmarkExtractor(report_path)`
Reads bookmarks and builds toggle groups.

**`extract(visual_map) → (enriched, toggle_groups)`**
Entry point. Calls `_build_enriched()` then `_build_toggle_groups()`.

**`_build_enriched(visual_map) → list`**
Reads all `bookmarks/*.json` files. For each bookmark:
- Extracts `displayName` and `targetVisualNames`
- Classifies via `_classify()`:
  - `"page_default"` — no targets → restores page to default
  - `"toggle"` — targets include group containers
  - `"filter_state"` — targets are non-group visuals
- Extracts visibility changes via `_extract_visibility()`

**`_classify(targets, visual_map) → str`**
If no targets → `"page_default"`. If any target is a `"group"` kind visual → `"toggle"`. Otherwise → `"filter_state"`.

**`_extract_visibility(data, visual_map) → dict`**
Reads `explorationState.sections[].visualContainerGroups[].children` to determine which groups are `isHidden=True` vs shown. Returns `{shown: [...], hidden: [...]}`.

**`_charts_in_group(group_id, visual_map) → list`**
Finds all visuals whose `parent_group` matches `group_id`. Skips decorative types. Recursively handles nested groups.

**`_build_toggle_groups(enriched) → list`**
Groups toggle bookmarks by their shared group IDs signature (`frozenset` of group IDs). Bookmark pairs that share the same set of groups are one toggle group. Builds `llm_description` summarizing the toggle behavior.

---

## File Connections

| Imports from | Used for |
|---|---|
| `models.py` | `VisualSchema`, `FilterSchema`, `ReportMeta` |

**Called by:** `extractor.py` → `run_extraction()` (Steps 3–6)

---

## Hardcoded Parts (Change for New Dashboards)

### `MEANINGFUL_VISUAL_TYPES` (line ~669)
```python
MEANINGFUL_VISUAL_TYPES = {
    "card", "multiRowCard", "cardVisual", "kpiVisual", "gauge",
    "lineChart", "areaChart",
    "barChart", "clusteredBarChart", "stackedBarChart",
    ...
    "slicer", "filtersVisual",
}
```
If a new dashboard uses a **custom visual type** (non-standard Power BI type string) that should be included in the story guide, add its type string here. Unknown types are silently dropped.

### `_MEASURE_CONTAINER_TABLES` (line ~89)
```python
_MEASURE_CONTAINER_TABLES = {
    "all_dax_pac", "all_dax", "measures", "_measures",
    "key measures", "dax measures", "dax",
}
```
Same list as in `tmdl_parser.py`. If a new dashboard has a different measure container table name, add it here too. Otherwise measure references will include the table prefix unnecessarily (e.g. `"MyMeasures.Revenue"` instead of `"Revenue"`).

### `CUSTOM_VISUAL_REGISTRY` (line ~480)
```python
CUSTOM_VISUAL_REGISTRY = {
    "ChicletSlicer": {
        "name":            "Chiclet Slicer",
        "publisher":       "Microsoft",
        "visual_behavior": "button_slicer",
        ...
    },
}
```
Currently only `ChicletSlicer` is registered. If a new dashboard uses other third-party custom visuals (e.g., Zebra BI, Charticulator), add their visual ID prefix here with a description. Unknown custom visuals get a generic warning entry.

### `EXPORT_MODE_DESCRIPTIONS` (line ~491)
```python
EXPORT_MODE_DESCRIPTIONS = {
    "AllowSummarized": "Only summarized/aggregated data can be exported...",
    "AllowAll":        "Both summarized and raw row-level data can be exported.",
    "Disabled":        "Data export is completely disabled for this dashboard.",
}
```
These are standard Power BI export mode strings — unlikely to change across dashboards.

### `_parse_settings()` known keys (line ~607)
The `known` dict maps specific Power BI setting keys to description strings. If Power BI adds new setting keys in a future report version, they land in `structured[f"unknown_{raw_key}"]` — no breaking change, but the description won't be human-friendly.

### Default canvas size (line ~710)
```python
bi_width  = 1440
bi_height = 2000
```
Fallback canvas dimensions used when `page.json` doesn't specify width/height. These match the current dashboards' canvas size. If a new dashboard uses a very different canvas size and `page.json` is missing, these defaults may cause layout misinterpretation.
