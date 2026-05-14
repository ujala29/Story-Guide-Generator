# models.py — Pydantic Data Models

## Purpose
Central definitions for **all Pydantic data models** used across the entire Stage 1 extraction pipeline. Every other file in `Extraction/` imports from here. Models are never defined elsewhere.

**Why Pydantic**: free JSON serialization via `.model_dump_json()`, runtime type validation, and clean IDE autocomplete.

---

## Input / Output

This file defines **no functions** — only data model classes. It is imported by every other Stage 1 file.

---

## Model Hierarchy (read top to bottom — each builds on previous)

```
ColumnSchema              ← one column inside a table
MeasureSchema             ← one DAX measure (enriched later by dependency_graph.py)
TableSchema               ← one table = columns + measures + optional Power Query
RelationshipSchema        ← one foreign-key link between two tables
VisualSchema              ← one meaningful chart/card/slicer on a page
FilterSchema              ← one slicer reinterpreted as a filter descriptor
DependencyEdge            ← one node in the measure→measure DAG
ReportMeta                ← report-level settings, theme, custom visuals
ExtractionSummary         ← aggregate counts for the whole report
ExtractedSchema           ← ROOT: the final JSON written to extracted_schema.json
```

---

## Model Details

### `ColumnSchema`
Represents one physical or calculated column in a table.

| Field | Type | Description |
|---|---|---|
| `name` | str | Column display name from TMDL |
| `data_type` | str | e.g. `"int64"`, `"string"`, `"dateTime"` |
| `is_calculated` | bool | True if DAX calculated column |
| `expression` | Optional[str] | DAX expression — only if `is_calculated` |

---

### `MeasureSchema`
Represents one DAX measure. Fields `depends_on`, `depth`, `is_leaf` start empty and are filled in by `MeasureDependencyGraph.enrich_measures()` later.

| Field | Type | Description |
|---|---|---|
| `name` | str | Measure display name |
| `table` | str | Parent table name |
| `dax` | str | Full DAX expression string |
| `is_visible` | bool | False if `isHidden = true` in TMDL |
| `referenced_tables` | list[str] | Table names found in DAX text |
| `referenced_columns` | list[str] | `"Table[Column]"` refs found in DAX |
| `depends_on` | list[str] | Other measure names this measure calls (filled by dependency_graph.py) |
| `depth` | int | 0 = leaf, higher = more nested chain (filled by dependency_graph.py) |
| `is_leaf` | bool | True when `depends_on` is empty (filled by dependency_graph.py) |

---

### `TableSchema`
One full table from the SemanticModel. `table_type` is classified by `TMDLExtractor._classify_table()`.

| Field | Type | Description |
|---|---|---|
| `name` | str | Table name |
| `table_type` | str | `"source"` / `"measure_container"` / `"parameter"` / `"static_lookup"` |
| `columns` | list[ColumnSchema] | All columns |
| `measures` | list[MeasureSchema] | All DAX measures |
| `power_query` | Optional[str] | M expression if present, else None |

---

### `RelationshipSchema`
One foreign-key link. `from` = many side, `to` = one side (standard star-schema convention).

| Field | Type | Description |
|---|---|---|
| `from_table` | str | Many-side table |
| `from_column` | str | Many-side column |
| `to_table` | str | One-side table |
| `to_column` | str | One-side column |
| `direction` | str | `"singleDirection"` / `"bothDirections"` |
| `is_active` | bool | False if `isActive: false` in `relationships.tmdl` |

---

### `VisualSchema`
One meaningful chart, card, table, or slicer on a report page. Only types in `MEANINGFUL_VISUAL_TYPES` (defined in `visual_parser.py`) are included.

| Field | Type | Description |
|---|---|---|
| `id` | str | Visual folder name (unique per page) |
| `title` | str | Display title |
| `type` | str | Power BI visual type string |
| `page` | str | Parent page display name |
| `width`, `height` | float | Canvas dimensions |
| `measures_used` | list[str] | Flat list of measure names used |
| `columns_used` | list[str] | Flat list of column refs used |
| `axis_bindings` | Dict[str, List] | Role-aware field map: `{x_axis, y_axis, legend, …}` |
| `drill_filter_other_visuals` | bool | Whether clicking this visual filters others |
| `filter_config` | List[Dict] | Pre-applied visual-level filters |

---

### `FilterSchema`
A slicer visual reinterpreted as a filter descriptor. Used in the Filter Guide chapter of the story guide.

| Field | Type | Description |
|---|---|---|
| `name` | str | Slicer title or `"Slicer_<id>"` |
| `type` | str | Always `"slicer"` for now |
| `table` | str | Source table of the slicer field |
| `column` | str | Source column or measure name |
| `default_value` | Optional[str] | Default selection (currently unused) |
| `page` | str | Parent page display name |
| `slicer_mode` | str | `"Dropdown"` / `"List"` / `"Tile"` / `"Between"` |
| `single_select` | str | `"true"` / `"false"` |
| `select_all_enabled` | str | `"true"` / `"false"` |
| `sync_group` | str | Sync group name if slicer is synced across pages |
| `visual_filter_conditions` | List[str] | Human-readable condition strings |

---

### `DependencyEdge`
One node in the measure→measure DAG. Built by `MeasureDependencyGraph.build_edges()`.

| Field | Type | Description |
|---|---|---|
| `measure` | str | The measure this edge describes |
| `depends_on` | list[str] | Direct measure dependencies |
| `depth` | int | Recursive chain depth from leaves |
| `is_leaf` | bool | True when `depends_on` is empty |

---

### `ReportMeta`
Report-level metadata extracted from `report.json` + `version.json`.

| Field | Type | Description |
|---|---|---|
| `pbip_version` | str | From `version.json` |
| `theme` | dict | `base_theme_name`, `custom_theme_name`, `llm_note` |
| `custom_visuals` | list[dict] | Matched against `CUSTOM_VISUAL_REGISTRY` |
| `settings` | dict | Export mode, drill behavior, tooltip flags |
| `slow_settings` | dict | Cross-highlighting, apply-all button |
| `filter_config` | dict | Filter sort order + `llm_note` |
| `resources` | list[dict] | Embedded images, theme files, etc. |
| `llm_context` | dict | Pre-assembled descriptions ready for LLM prompts |

---

### `ExtractionSummary`
Aggregate counts and stats for the whole report. Written into the `"summary"` block of `extracted_schema.json`.

| Field | Type | Description |
|---|---|---|
| `total_tables` | int | |
| `total_measures` | int | |
| `total_relationships` | int | |
| `total_pages` | int | |
| `total_visuals` | int | |
| `total_filters` | int | |
| `total_bookmarks` | int | |
| `total_toggle_groups` | int | |
| `table_classification` | dict | `{type_string: [table_names]}` |
| `most_referenced_measures` | list[dict] | Top-10 `[{name, dependent_count}]` |
| `max_dependency_depth` | int | Deepest DAX dependency chain |
| `measures_with_dependencies` | int | Count of measures calling other measures |

---

### `ExtractedSchema` (ROOT)
The complete output written to `extracted_schema.json`. Every field maps to one section.

| Field | Source |
|---|---|
| `file_meta` | Assembled in `extractor.py` |
| `summary` | `ExtractionSummary` |
| `report_meta` | `ReportMetaParser.extract()` |
| `pages` | `ReportLayoutParser.extract()` |
| `measures` | `TMDLExtractor` → enriched by `MeasureDependencyGraph` |
| `tables` | `TMDLExtractor.extract_tables()` |
| `relationships` | `TMDLExtractor.extract_relationships()` |
| `visuals` | `ReportLayoutParser.extract()` |
| `filters` | `ReportLayoutParser.extract()` |
| `interactions` | `ReportLayoutParser.extract()` |
| `bookmarks` | `BookmarkExtractor.extract()` |
| `toggle_groups` | `BookmarkExtractor.extract()` |
| `dependency_graph` | `MeasureDependencyGraph.build_edges()` |
| `topological_order` | `MeasureDependencyGraph.topological_order()` |

---

## File Connections

**Imported by:** Every other file in `Extraction/` — `tmdl_parser.py`, `dependency_graph.py`, `visual_parser.py`, `extractor.py`, `relationship_parser.py`

---

## Hardcoded Parts (Change for New Dashboards)

> **None.** All models are generic and dashboard-agnostic. The `table_type` values (`"source"`, `"measure_container"`, `"parameter"`, `"static_lookup"`) are classifier outputs set by `tmdl_parser.py`, not hardcoded here.
