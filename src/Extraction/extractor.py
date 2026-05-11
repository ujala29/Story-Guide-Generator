# pipeline/stage1_extraction/extractor.py
#
# PURPOSE:
#   Single orchestrator for the entire Stage 1 extraction pipeline.
#   Calls all parsers in the correct order and writes extracted_schema.json.
#
# THIS IS THE ONLY FILE A NEW DEVELOPER NEEDS TO CALL FROM OUTSIDE STAGE 1.
# All other Stage 1 files are internal implementation details.
#
# PIPELINE ORDER (must not be reordered — each step feeds the next):
#   Step 1: TMDLExtractor        → tables, measures, relationships
#   Step 2: MeasureDependencyGraph → enrich measures with dep metadata
#   Step 3: build_visual_map()   → shared visual lookup (built ONCE, reused)
#   Step 4: ReportLayoutParser   → pages, visuals, filters, interactions
#   Step 5: BookmarkExtractor    → bookmarks, toggle groups
#   Step 6: ReportMetaParser     → theme, settings, custom visuals
#   Step 7: ExtractionSummary    → aggregate counts
#   Step 8: ExtractedSchema      → assemble + write JSON
#
# CALLED BY:
#   run.py (top-level entry point)
#   OR directly: from pipeline.stage1_extraction.extractor import run_extraction

from pathlib import Path
from datetime import datetime
from collections import defaultdict
import json
import sys
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
_stage1_dir = str(Path(__file__).resolve().parent)          # src/stage1
_stage2_dir = str(Path(__file__).resolve().parent.parent / "stage2")  # src/stage2
for _p in (_stage1_dir, _stage2_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from models import (
    ExtractionSummary, ExtractedSchema
)
from tmdl_parser import TMDLExtractor
from dependency_graph import MeasureDependencyGraph
from visual_parser import (
    build_visual_map,
    ReportLayoutParser,
    BookmarkExtractor,
    ReportMetaParser,
)
from measure_resolver_ import resolve_all


def run_extraction(
    semantic_model_path: str,
    report_path:         str,
    output_path:         str = "output/extracted_schema.json"
) -> ExtractedSchema:
    """
    Runs the full Stage 1 extraction pipeline.

    Args:
        semantic_model_path: Path to the .SemanticModel folder
                             (contains definition/tables/*.tmdl)
        report_path:         Path to the .Report folder
                             (contains definition/pages/ and report.json)
        output_path:         Where to write extracted_schema.json

    Returns:
        ExtractedSchema — the fully populated root model.
        Also writes the same data to output_path as formatted JSON.

    Raises:
        AssertionError if the semantic model tables folder is missing.
        FileNotFoundError if report.json is not found.
    """

    # ── Step 1: Semantic Model — tables, measures, relationships ───────────────
    # TMDLExtractor reads all *.tmdl files and produces structured objects.
    # extract_all_measures() flattens measures from all tables into one list.
    tmdl          = TMDLExtractor(semantic_model_path)
    tables        = tmdl.extract_tables()
    all_measures  = tmdl.extract_all_measures(tables)
    relationships = tmdl.extract_relationships()

    # ── Step 2: Measure Dependency Graph ──────────────────────────────────────
    # Scans DAX expressions for [MeasureName] references to build a DAG.
    # enrich_measures() mutates each MeasureSchema with depends_on/depth/is_leaf.
    graph        = MeasureDependencyGraph(all_measures)
    all_measures = graph.enrich_measures(all_measures)
    edges        = graph.build_edges()
    topo_order   = graph.topological_order()
    dep_summary  = graph.build_summary()

    # ── Step 3: Build Visual Map (shared, built ONCE) ──────────────────────────
    # visual_map is a dict of visual_id → info for ALL visuals across all pages.
    # It is passed into both ReportLayoutParser and BookmarkExtractor
    # to avoid reading the same files multiple times.
    pages_dir  = Path(report_path) / "definition" / "pages"
    visual_map = build_visual_map(pages_dir)

    # ── Step 4: Report Layout — pages, visuals, filters, interactions ──────────
    # ReportLayoutParser reads page.json + visual.json files.
    # Only visuals in MEANINGFUL_VISUAL_TYPES are included.
    # Slicers are also extracted as FilterSchema objects.
    layout                                = ReportLayoutParser(report_path)
    pages, visuals, filters, interactions = layout.extract(visual_map)

    # ── Step 5: Bookmarks & Toggle Groups ─────────────────────────────────────
    # BookmarkExtractor reads definition/bookmarks/*.json.
    # toggle_groups are bookmark pairs that control the same chart area.
    bm_extractor             = BookmarkExtractor(report_path)
    bookmarks, toggle_groups = bm_extractor.extract(visual_map)

    # ── Step 6: Report Metadata ────────────────────────────────────────────────
    # Reads report.json + version.json for theme, settings, custom visuals.
    report_meta = ReportMetaParser(report_path).extract()

    # ── Step 7: Aggregate Summary ──────────────────────────────────────────────
    # Groups table names by their classified type for the summary block.
    type_counts: dict[str, list] = defaultdict(list)
    for t in tables:
        type_counts[t.table_type].append(t.name)

    summary = ExtractionSummary(
        total_tables=len(tables),
        total_measures=len(all_measures),
        total_relationships=len(relationships),
        total_pages=len(pages),
        total_visuals=len(visuals),
        total_filters=len(filters),
        total_bookmarks=len(bookmarks),
        total_toggle_groups=len(toggle_groups),
        table_classification={k: v for k, v in type_counts.items()},
        most_referenced_measures=dep_summary["most_referenced_measures"],
        max_dependency_depth=dep_summary["max_dependency_depth"],
        measures_with_dependencies=dep_summary["measures_with_dependencies"],
    )

    # ── Step 8: Assemble and Write ─────────────────────────────────────────────
    schema = ExtractedSchema(
        file_meta={
            "file_name":    Path(semantic_model_path).name.replace(".SemanticModel", ""),
            "extracted_at": datetime.utcnow().isoformat(),
        },
        summary=summary,
        report_meta=report_meta,
        pages=pages,
        measures=all_measures,
        tables=tables,
        relationships=relationships,
        visuals=visuals,
        filters=filters,
        interactions=interactions,
        bookmarks=bookmarks,
        toggle_groups=toggle_groups,
        dependency_graph=edges,
        topological_order=topo_order,
    )

    # ensure output directory exists before writing
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(
        schema.model_dump_json(indent=2),
        encoding="utf-8"
    )

    # write section-wise files alongside extracted_schema.json
    _write_section_files(schema, output_path)

    # print summary for developer confirmation
    print(f"\n✅ Stage 1 Extraction complete → {output_path}")
    print(f"   Tables:        {summary.total_tables}")
    print(f"   Measures:      {summary.total_measures}")
    print(f"   Relationships: {summary.total_relationships}")
    print(f"   Pages:         {summary.total_pages}")
    print(f"   Visuals:       {summary.total_visuals}")
    print(f"   Filters:       {summary.total_filters}")
    print(f"   Bookmarks:     {summary.total_bookmarks}")
    print(f"   Toggle groups: {summary.total_toggle_groups}")

    return schema



# ─────────────────────────────────────────────────────────────────
# SECTION FILE WRITER
# ─────────────────────────────────────────────────────────────────

def _write_section_files(schema: "ExtractedSchema", output_path: str) -> None:
    """
    Saves each section of extracted_schema.json as its own file
    inside output/schema_sections/ for easy human inspection.

    Files written:
      summary.json         — counts + table classification
      tables.json          — all tables with columns
      measures.json        — all DAX measures
      relationships.json   — all model relationships
      pages.json           — report pages
      visuals.json         — all visual definitions
      filters.json         — slicer / filter definitions
      bookmarks.json       — bookmarks
      dependency_graph.json— measure dependency edges + topological order
    """
    sections_dir = Path(output_path).parent / "schema_sections"
    sections_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(schema.model_dump_json())

    section_map = {
        "summary.json":          data.get("summary",           {}),
        "tables.json":           data.get("tables",            []),
        "measures.json":         data.get("measures",          []),
        "relationships.json":    data.get("relationships",     []),
        "pages.json":            data.get("pages",             []),
        "visuals.json":          data.get("visuals",           []),
        "filters.json":          data.get("filters",           []),
        "bookmarks.json":        data.get("bookmarks",         []),
        "dependency_graph.json": {
            "edges":             data.get("dependency_graph",  []),
            "topological_order": data.get("topological_order", []),
        },
    }

    for filename, content in section_map.items():
        file_path = sections_dir / filename
        file_path.write_text(
            json.dumps(content, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    # generate measures_resolved.json alongside measures.json
    measures_json_path = sections_dir / "measures.json"
    resolved = resolve_all(str(measures_json_path))
    measures_resolved_path = sections_dir / "measures_resolved.json"
    measures_resolved_path.write_text(
        json.dumps({k: v["chain"] for k, v in resolved.items()}, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"   Sections saved → {sections_dir}/")
    print(f"   {', '.join(section_map.keys())}")
    print(f"   measures_resolved.json → {measures_resolved_path}")


# ─────────────────────────────────────────────────────────────────
# MAIN — direct run ke liye
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse as _ap

    _BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root

    # Known dashboard configs — add new dashboards here
    _DASHBOARD_CONFIGS = {
        "risk-dash": {
            "semantic_model": _BASE_DIR / "input" / "Risk-Management-v4_Insights_v1.SemanticModel",
            "report":         _BASE_DIR / "input" / "Risk-Management-v4_Insights_v1.Report",
            "output":         _BASE_DIR / "output" / "dashboards" / "risk-dash" / "stage1" / "extracted_schema.json",
        },
        "pac-dash": {
            "semantic_model": _BASE_DIR / "input" / "PAC-v4_Insights_v1.SemanticModel",
            "report":         _BASE_DIR / "input" / "PAC-v4_Insights_v1.Report",
            "output":         _BASE_DIR / "output" / "dashboards" / "pac-dash" / "stage1" / "extracted_schema.json",
        },
    }

    _parser = _ap.ArgumentParser(description="Stage 1 — Extraction")
    _parser.add_argument(
        "--dashboard", type=str, default="all",
        help="Dashboard to extract: risk-dash | pac-dash | all (default: all)"
    )
    _parser.add_argument("--semantic-model", type=str, default=None)
    _parser.add_argument("--report",         type=str, default=None)
    _parser.add_argument("--output",         type=str, default=None)
    _args = _parser.parse_args()

    # Decide which dashboards to run
    if _args.dashboard == "all":
        _to_run = list(_DASHBOARD_CONFIGS.keys())
    else:
        _to_run = [_args.dashboard]

    for _dash in _to_run:
        _cfg = _DASHBOARD_CONFIGS.get(_dash, {})
        SEMANTIC_MODEL_PATH = str(_args.semantic_model or _cfg.get("semantic_model", ""))
        REPORT_PATH         = str(_args.report         or _cfg.get("report",         ""))
        OUTPUT_PATH         = str(_args.output         or _cfg.get("output",         ""))

        if not SEMANTIC_MODEL_PATH or not REPORT_PATH or not OUTPUT_PATH:
            print(f"ERROR: Unknown dashboard '{_dash}'. Use --semantic-model, --report, --output to specify paths.")
            import sys as _sys; _sys.exit(1)

        print("=" * 55)
        print(f"  Stage 1 — Extraction ({_dash})")
        print("=" * 55)

        run_extraction(
            semantic_model_path = SEMANTIC_MODEL_PATH,
            report_path         = REPORT_PATH,
            output_path         = OUTPUT_PATH,
        )