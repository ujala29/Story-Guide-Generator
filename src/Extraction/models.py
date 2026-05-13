# pipeline/stage1_extraction/models.py
#
# PURPOSE:
#   Central place for ALL Pydantic data models used across Stage 1.
#   Every other Stage 1 file imports from here — never define models elsewhere.
#
# WHY PYDANTIC:
#   Pydantic gives us free JSON serialization (.model_dump_json()),
#   type validation at runtime, and clean IDE autocomplete.
#
# MODEL HIERARCHY (read top to bottom — each builds on the previous):
#   ColumnSchema         ← one column inside a table
#   MeasureSchema        ← one DAX measure (enriched later by dependency graph)
#   TableSchema          ← one table = columns + measures + optional Power Query
#   RelationshipSchema   ← one foreign-key link between two tables
#   VisualSchema         ← one meaningful chart/card/slicer on a report page
#   FilterSchema         ← one slicer parsed as a filter
#   DependencyEdge       ← one node in the measure->measure DAG
#   ReportMeta           ← report-level settings, theme, custom visuals
#   ExtractionSummary    ← aggregate stats for the whole report
#   ExtractedSchema      ← ROOT: the final JSON written to extracted_schema.json

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────
# COLUMN
# Represents one physical or calculated column in a table.
# ──────────────────────────────────────────────────────────

class ColumnSchema(BaseModel):
    name: str                        # column display name from TMDL
    data_type: str                   # e.g. "int64", "string", "dateTime"
    is_calculated: bool              # True if DAX calculated column
    expression: Optional[str] = None # DAX expression (only if is_calculated)


# ──────────────────────────────────────────────────────────
# MEASURE
# Represents one DAX measure.
# Fields like depends_on / depth / is_leaf start empty and are
# filled in by MeasureDependencyGraph.enrich_measures() later.
# ──────────────────────────────────────────────────────────

class MeasureSchema(BaseModel):
    name: str                          # measure display name
    table: str                         # parent table name
    dax: str                           # full DAX expression string
    is_visible: bool                   # False if isHidden = true in TMDL
    referenced_tables: list[str]       # table names found in the DAX text
    referenced_columns: list[str]      # "Table[Column]" refs found in DAX
    depends_on: list[str] = []         # other measure names this measure calls
    depth: int = 0                     # 0 = leaf, higher = more nested chain
    is_leaf: bool = True               # True when depends_on is empty


# ──────────────────────────────────────────────────────────
# TABLE
# One full table from the SemanticModel.
# table_type is classified by TMDLExtractor._classify_table().
# ──────────────────────────────────────────────────────────

class TableSchema(BaseModel):
    name: str
    table_type: str                    # "source" | "measure_container" | "parameter" | "static_lookup"
    columns: list[ColumnSchema]
    measures: list[MeasureSchema]
    power_query: Optional[str] = None  # M expression if present, else None


# ──────────────────────────────────────────────────────────
# RELATIONSHIP
# One foreign-key link between two tables.
# "from" = many side, "to" = one side (standard star-schema convention).
# ──────────────────────────────────────────────────────────

class RelationshipSchema(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    direction: str      # "singleDirection" | "bothDirections"
    is_active: bool     # False if isActive: false in relationships.tmdl


# ──────────────────────────────────────────────────────────
# VISUAL
# One meaningful chart, card, table, or slicer on a report page.
# Only types in MEANINGFUL_VISUAL_TYPES (visual_parser.py) are included.
# ──────────────────────────────────────────────────────────
class VisualSchema(BaseModel):
    id:    str
    title: str
    type:  str
    page:  str
    width:  float
    height: float
    measures_used: list[str]
    columns_used:  list[str]
    axis_bindings: Dict[str, List] = Field(default_factory=dict)
    drill_filter_other_visuals: bool = True
    filter_config: List[Dict] = Field(default_factory=list)
   
# ──────────────────────────────────────────────────────────
# FILTER
# A slicer visual reinterpreted as a filter descriptor.
# Used in Chapter 06 (Filter Guide) of the story guide.
# ──────────────────────────────────────────────────────────

class FilterSchema(BaseModel):
    name: str                         # slicer title or "Slicer_<id>"
    type: str                         # always "slicer" for now
    table: str                        # source table of the slicer field
    column: str                       # source column or measure name
    default_value: Optional[str] = None  # default selection (currently unused)
    page: str                         # parent page display name
    slicer_mode:                str       = ""
    single_select:              str       = ""
    select_all_enabled:         str       = ""
    sync_group:                 str       = ""
    visual_filter_conditions:   List[str] = Field(default_factory=list)
# ──────────────────────────────────────────────────────────
# DEPENDENCY EDGE
# One node in the measure->measure directed acyclic graph (DAG).
# Built by MeasureDependencyGraph.build_edges().
# ──────────────────────────────────────────────────────────

class DependencyEdge(BaseModel):
    measure: str            # the measure this edge describes
    depends_on: list[str]   # direct measure dependencies (names only)
    depth: int              # recursive chain depth from leaves
    is_leaf: bool           # True when depends_on is empty


# ──────────────────────────────────────────────────────────
# REPORT META
# Report-level metadata extracted from report.json + version.json.
# Covers theme, custom visuals, export settings, filter config.
# ──────────────────────────────────────────────────────────

class ReportMeta(BaseModel):
    pbip_version: str          # from version.json
    theme: dict                # base_theme_name, custom_theme_name, llm_note
    custom_visuals: list[dict] # matched against CUSTOM_VISUAL_REGISTRY
    settings: dict             # export_mode, drill behavior, tooltip flags
    slow_settings: dict        # cross-highlighting, apply-all button
    filter_config: dict        # filter sort order + llm_note
    resources: list[dict]      # embedded images, theme files, etc.
    llm_context: dict          # pre-assembled descriptions ready for LLM prompts


# ──────────────────────────────────────────────────────────
# EXTRACTION SUMMARY
# Aggregate counts and stats for the whole report.
# Written into the "summary" block of extracted_schema.json.
# ──────────────────────────────────────────────────────────

class ExtractionSummary(BaseModel):
    total_tables: int
    total_measures: int
    total_relationships: int
    total_pages: int
    total_visuals: int
    total_filters: int
    total_bookmarks: int
    total_toggle_groups: int
    table_classification: dict           # {type_string: [table_names]}
    most_referenced_measures: list[dict] # top-10 [{name, dependent_count}]
    max_dependency_depth: int            # deepest DAX dependency chain
    measures_with_dependencies: int      # count of measures calling other measures


# ──────────────────────────────────────────────────────────
# EXTRACTED SCHEMA  ← ROOT OUTPUT MODEL
# The complete output written to extracted_schema.json.
# Every field maps to one section of the final JSON file.
# ──────────────────────────────────────────────────────────

class ExtractedSchema(BaseModel):
    file_meta: dict                          # file_name + extracted_at timestamp
    summary: ExtractionSummary
    report_meta: ReportMeta
    pages: list[dict]                        # [{name, display_name, order, width, height}]
    measures: list[MeasureSchema]            # all measures, enriched with dependency data
    tables: list[TableSchema]
    relationships: list[RelationshipSchema]
    visuals: list[VisualSchema]
    filters: list[FilterSchema]
    interactions: dict                       # per-page cross-filter interaction rules
    bookmarks: list[dict]                    # enriched bookmark list
    toggle_groups: list[dict]                # grouped toggle bookmark pairs
    dependency_graph: list[DependencyEdge]   # full DAG edge list
    topological_order: list[str]             # measure names, leaf-first safe order