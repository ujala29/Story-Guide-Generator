# Extraction — Stage 1 README

Stage 1 reads the raw Power BI files (`.SemanticModel` + `.Report` folders) and converts them into a single structured `extracted_schema.json` that every downstream stage depends on.

---

## File Overview

| File | Role |
|---|---|
| [runner.py](runner.md) | CLI entry point — reads config, calls extractor |
| [extractor.py](extractor.md) | **Main orchestrator** — calls all parsers in correct order |
| [tmdl_parser.py](tmdl_parser.md) | Parses `.tmdl` files → tables, columns, measures, relationships |
| [dependency_graph.py](dependency_graph.md) | Builds measure→measure DAG, topological sort |
| [visual_parser.py](visual_parser.md) | Reads report layout → visuals, filters, bookmarks, metadata |
| [measure_resolver_.py](measure_resolver_.md) | Builds recursive DAX dependency chains per measure |
| [relationship_parser.py](relationship_parser.md) | Standalone relationship parser (not used in current pipeline) |
| [models.py](models.md) | All Pydantic data models — imported by every other file |

---

## How Files Are Connected

```
runner.py
  │
  └── extractor.py  (run_extraction)
        │
        ├── tmdl_parser.py          [Step 1]
        │     └── models.py         (ColumnSchema, MeasureSchema, TableSchema, RelationshipSchema)
        │
        ├── dependency_graph.py     [Step 2]
        │     └── models.py         (MeasureSchema, DependencyEdge)
        │
        ├── visual_parser.py        [Steps 3, 4, 5, 6]
        │     │   build_visual_map()         → visual lookup dict
        │     │   ReportLayoutParser         → pages, visuals, filters, interactions
        │     │   BookmarkExtractor          → bookmarks, toggle_groups
        │     │   ReportMetaParser           → report_meta
        │     └── models.py         (VisualSchema, FilterSchema, ReportMeta)
        │
        ├── measure_resolver_.py    [Step 8, inside _write_section_files]
        │     └── (no Extraction imports — pure stdlib)
        │
        └── models.py               (ExtractedSchema, ExtractionSummary)
```

**`models.py` is the shared foundation** — imported by every file. It defines no functions, only data classes.

---

## Full Pipeline Call Flow

```
runner.py
  └── run_extraction(semantic_model_path, report_path, output_path)
        │
        │  ── STEP 1: Semantic Model ───────────────────────────────
        ├── TMDLExtractor(semantic_model_path)
        │     ├── extract_tables()
        │     │     └── for each *.tmdl:
        │     │           _parse_table_file()
        │     │             ├── _get_table_name()
        │     │             ├── _parse_columns()
        │     │             ├── _parse_measures()     ← handles 3 DAX formats
        │     │             ├── _parse_power_query()
        │     │             └── _classify_table()
        │     ├── extract_all_measures(tables)       → flat list
        │     └── extract_relationships()
        │           └── _parse_relationships()
        │
        │  ── STEP 2: Dependency Graph ─────────────────────────────
        ├── MeasureDependencyGraph(all_measures)
        │     ├── _build()                   ← scans DAX for [Ref] tokens
        │     ├── enrich_measures()          ← mutates each MeasureSchema
        │     │     └── get_depth()          ← recursive with cycle guard
        │     ├── build_edges()              → DependencyEdge list
        │     ├── topological_order()        → sorted name list (Kahn's BFS)
        │     └── build_summary()            → stats dict
        │
        │  ── STEP 3: Visual Map (built once, shared) ───────────────
        ├── build_visual_map(pages_dir)      ← reads ALL visual.json in one pass
        │     └── _extract_fields_with_roles()
        │     └── _extract_title()
        │
        │  ── STEP 4: Report Layout ────────────────────────────────
        ├── ReportLayoutParser(report_path)
        │     └── extract(visual_map)
        │           ├── for each page: reads page.json
        │           ├── for each visual: reads visual.json
        │           │     ├── _parse_visual()
        │           │     │     ├── _extract_fields_with_roles()
        │           │     │     └── _parse_filter_config()
        │           │     └── _make_filter()     ← for slicer visuals
        │           │           └── _extract_slicer_meta()
        │           └── _parse_interactions(visual_map)
        │
        │  ── STEP 5: Bookmarks ────────────────────────────────────
        ├── BookmarkExtractor(report_path)
        │     └── extract(visual_map)
        │           ├── _build_enriched()
        │           │     ├── _classify()
        │           │     └── _extract_visibility()
        │           │           └── _charts_in_group()
        │           └── _build_toggle_groups()
        │
        │  ── STEP 6: Report Metadata ──────────────────────────────
        ├── ReportMetaParser(report_path)
        │     └── extract()
        │           ├── _parse_settings()
        │           ├── _parse_slow_settings()
        │           └── _match_custom_visual()
        │
        │  ── STEP 7: Summary ──────────────────────────────────────
        ├── ExtractionSummary(counts...)
        │
        │  ── STEP 8: Assemble + Write ─────────────────────────────
        └── ExtractedSchema(all fields)
              ├── write → extracted_schema.json
              └── _write_section_files()
                    ├── write → schema_sections/*.json
                    └── resolve_all(measures.json)          ← measure_resolver_.py
                          └── build_chain() recursively
                          └── write → measures_resolved.json
```

---

## Data Flow Between Files

```
INPUT FILES (.SemanticModel, .Report)
    │
    ▼
tmdl_parser.py
    │   tables[]           ─────────────────────────────────────────────────────┐
    │   all_measures[]     → dependency_graph.py → enriched measures[]          │
    │   relationships[]                                                          │
    ▼                                                                            │
visual_parser.py                                                                 │
    │   pages[]                                                                  │
    │   visuals[]                                                                │
    │   filters[]                                                                │
    │   interactions{}                                                           │
    │   bookmarks[]                                                              │
    │   toggle_groups[]                                                          │
    │   report_meta{}                                                            │
    ▼                                                                            │
extractor.py (assembles all)                                                     │
    │   extracted_schema.json ←─────────────────────────────────────────────────┘
    │   schema_sections/
    │     measures.json
    │             │
    │             ▼
    │         measure_resolver_.py
    │             └── measures_resolved.json
    ▼
OUTPUT → consumed by Stage 2 (Visual_wise, filter_section, Metric_dictionary)
```

---

## What Each Downstream Stage Reads

| Downstream Stage | Files Read from `schema_sections/` |
|---|---|
| `Visual_wise` | `visuals.json`, `measures_resolved.json`, `pages.json` |
| `filter_section` | `filters.json`, `pages.json` |
| `Metric_dictionary` | `measures.json`, `measures_resolved.json`, `relationships.json` |
| `Page_wise` | `visuals.json`, `measures_resolved.json`, `pages.json` |
| `dashboard_overview` | `extracted_schema.json` (full) |
| `glossary_faq` | `measures.json`, `visuals.json` |

---

## Hardcoded Parts — Summary Across All Files

| File | What's Hardcoded | Impact if Not Changed |
|---|---|---|
| `tmdl_parser.py` | `PARAM_TABLES` — parameter table names | New dashboard's parameter tables classified as `"source"` |
| `tmdl_parser.py` | `MEASURE_CONTAINER_NAMES` — measure table names | Measure prefix shown unnecessarily in field references |
| `tmdl_parser.py` | DB connector keywords in `_classify_table()` | New DB (BigQuery etc.) not detected → static lookup misclassified as source |
| `visual_parser.py` | `_MEASURE_CONTAINER_TABLES` — duplicate of above | Same as above for visual field extraction |
| `visual_parser.py` | `MEANINGFUL_VISUAL_TYPES` — kept visual types | Custom visuals with unknown type strings silently dropped |
| `visual_parser.py` | `CUSTOM_VISUAL_REGISTRY` — known custom visual metadata | Unknown custom visuals get generic warning instead of rich description |
| `extractor.py` | `_DASHBOARD_CONFIGS` in `__main__` block | Only matters when running `extractor.py` directly (not via `runner.py`) |
| `measure_resolver_.py` | `DEFAULT_MEASURES_PATH` — points to `risk-dash` | Only matters when running `measure_resolver_.py` directly for debugging |
| `measure_resolver_.py` | Sample measure names in `__main__` | Only affects CLI sample output — no processing impact |

---

## How to Run Stage 1

```bash
# Via runner (recommended)
python src/Extraction/runner.py --dashboard risk-dash
python src/Extraction/runner.py --dashboard pac-dash
python src/Extraction/runner.py                         # all dashboards

# Via main.py (full pipeline)
python main.py --dashboard risk-dash --from-stage 1
```
