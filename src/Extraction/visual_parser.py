# pipeline/stage1_extraction/visual_parser.py
#
# PURPOSE:
#   Reads the Report folder and extracts:
#     - Pages (name, display name, canvas dimensions)
#     - Visuals (type, title, position, measures/columns used)
#     - Filters (slicers reinterpreted as filter descriptors)
#     - Cross-filter Interactions (which visuals filter which)
#     - Bookmarks (toggle states, filter snapshots)
#     - Toggle Groups (bookmark pairs that share visual group IDs)
#     - Report Metadata (theme, export settings, custom visuals)
#
# FILE STRUCTURE THIS MODULE READS:
#   <Report>/definition/
#     report.json         ← theme, settings, custom visuals, resources
#     version.json        ← PBIP version string
#     pages/
#       <PageFolder>/
#         page.json       ← display name, canvas dimensions, cross-filter rules
#         visuals/
#           <VisualFolder>/
#             visual.json ← visual type, position, query bindings, title
#     bookmarks/
#       *.json            ← bookmark states and target visual names
#
# WHAT'S KEPT vs DROPPED:
#   KEPT:
#     - width, height (size matters for layout understanding)
#     - axis_bindings with role-aware keys (x_axis, y_axis, legend, rows, columns…)
#     - display_name per field (user-facing label)
#     - drill_order for HierarchyLevel fields
#     - drill_filter_other_visuals
#     - filter_config — only entries with an actual field OR conditions
#     - FilterSchema: slicer_mode, single_select, select_all_enabled, sync_group,
#       visual_filter_conditions
#
#   DROPPED (cosmetic / non-semantic / always-default):
#     - x, y, z, tab_order    — canvas position / keyboard nav
#     - sort                  — display ordering only
#     - objects / container   — formatting/styling
#     - datapoint_colors      — cosmetic color overrides
#     - slicer_meta on VisualSchema — moved into FilterSchema only
#     - query_ref, native_query_ref — redundant next to display_name
#     - active: true          — only written when False
#     - filter_config entries with no field AND no conditions
#     - filter_config "name"  — hash string, meaningless for LLM
#
# MODULE LAYOUT:
#   Section 1: Module-level helpers (shared by all classes — built ONCE)
#   Section 2: ReportMetaParser   ← reads report.json + version.json
#   Section 3: ReportLayoutParser ← reads pages + visuals + filters + interactions
#   Section 4: BookmarkExtractor  ← reads bookmarks + builds toggle groups
#
# CALLED BY:
#   pipeline/stage1_extraction/extractor.py -> run_extraction()

import json
from pathlib import Path
from typing import Optional

from models import VisualSchema, FilterSchema, ReportMeta


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — MODULE-LEVEL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

# Maps Power BI queryState role names -> semantic axis keys.
ROLE_TO_AXIS = {
    "Category":        "x_axis",
    "Axis":            "x_axis",
    "X":               "x_axis",
    "Y":               "y_axis",
    "Values":          "y_axis",
    "Value":           "y_axis",
    "Series":          "legend",
    "Legend":          "legend",
    "Details":         "legend",
    "Tooltips":        "tooltip",
    "Size":            "size",
    "Rows":            "rows",
    "Columns":         "columns",
    "Field":           "x_axis",
    "Small multiples": "small_multiples",
}


def build_visual_map(pages_dir: Path) -> dict:
    """
    Reads ALL visual.json files across all pages in one pass.
    Returns a dict: visual_id (folder name) -> info dict.

    WHY ONCE:
      Both ReportLayoutParser and BookmarkExtractor need visual metadata.
      Building this map once avoids reading the same files twice.

    WHAT IT RETURNS FOR EACH VISUAL:
      - kind:          "visual" or "group"
      - title:         display title string
      - type:          Power BI visual type string
      - page:          parent page display name
      - parent_group:  parent group folder name (if nested)
      - is_hidden:     True if visual is hidden by default
      - measures_used / columns_used: flat field lists (for bookmark extractor)
      - axis_bindings: role-aware field map {x_axis, y_axis, legend, …}
      - width, height: canvas dimensions
    """
    visual_map = {}

    for page_dir in sorted(pages_dir.iterdir()):
        if not page_dir.is_dir():
            continue

        display_name = page_dir.name
        page_meta    = page_dir / "page.json"
        if page_meta.exists():
            try:
                meta         = json.loads(page_meta.read_text(encoding="utf-8", errors="ignore"))
                display_name = meta.get("displayName", page_dir.name)
            except Exception:
                pass

        visuals_dir = page_dir / "visuals"
        if not visuals_dir.exists():
            continue

        for vdir in sorted(visuals_dir.iterdir()):
            if not vdir.is_dir():
                continue
            vfile = vdir / "visual.json"
            if not vfile.exists():
                continue

            try:
                data = json.loads(vfile.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue

            vid      = vdir.name
            position = data.get("position", {})

            # group containers — no visual node
            if "visualGroup" in data and "visual" not in data:
                visual_map[vid] = {
                    "id":           vid,
                    "kind":         "group",
                    "group_name":   data["visualGroup"].get("displayName", ""),
                    "group_mode":   data["visualGroup"].get("groupMode", ""),
                    "parent_group": data.get("parentGroupName", None),
                    "is_hidden":    data.get("isHidden", False),
                    "page":         display_name,
                    "width":        float(position.get("width", 0)),
                    "height":       float(position.get("height", 0)),
                }
                continue

            if "visual" not in data:
                continue

            visual_node               = data["visual"]
            axis_bindings, measures, columns = _extract_fields_with_roles(visual_node)

            visual_map[vid] = {
                "id":            vid,
                "kind":          "visual",
                "title":         _extract_title(visual_node),
                "type":          visual_node.get("visualType", "unknown"),
                "page":          display_name,
                "parent_group":  data.get("parentGroupName", None),
                "is_hidden":     data.get("isHidden", False),
                "measures_used": measures,
                "columns_used":  columns,
                "axis_bindings": axis_bindings,
                "width":         float(position.get("width", 0)),
                "height":        float(position.get("height", 0)),
            }

    return visual_map


def _extract_title(visual_node: dict) -> str:
    """
    Extracts visual title from two possible storage locations.
    Priority: visualContainerObjects.title -> objects.title
    Returns empty string on any failure.
    """
    try:
        return (visual_node["visualContainerObjects"]["title"][0]
                ["properties"]["text"]["expr"]["Literal"]["Value"].strip("'"))
    except Exception:
        pass
    try:
        return (visual_node["objects"]["title"][0]
                ["properties"]["text"]["expr"]["Literal"]["Value"].strip("'"))
    except Exception:
        pass
    return ""


def _extract_fields_with_roles(visual_node: dict) -> tuple[dict, list, list]:
    """
    Role-aware field extraction.

    Reads queryState and maps each role -> semantic axis key using ROLE_TO_AXIS.

    Returns:
        axis_bindings  -> { "x_axis": [...], "y_axis": [...], "legend": [...], … }
                          (empty keys omitted)
        measures_used  -> flat deduplicated list (for bookmark extractor compat)
        columns_used   -> flat deduplicated list (for bookmark extractor compat)

    Each field entry in axis_bindings:
        {
            "field_type":   "Measure" | "Column" | "HierarchyLevel",
            "table":        str,
            "property":     str,
            "display_name": str,
            # "active": False   ← only present when active=False; omitted when True
            # "drill_order": int ← HierarchyLevel only
        }

    DROPPED vs previous version:
        - query_ref        — internal PBI ref, redundant next to display_name
        - native_query_ref — same as display_name in most cases
        - active: true     — default; only written when False to save tokens
    """
    axis_bindings = {k: [] for k in set(ROLE_TO_AXIS.values())}
    axis_bindings["other"] = []
    measures, columns = [], []

    query_state = visual_node.get("query", {}).get("queryState", {})

    for role_name, role_data in query_state.items():
        axis_key    = ROLE_TO_AXIS.get(role_name, "other")
        projections = role_data.get("projections", [])

        for drill_order, proj in enumerate(projections):
            field        = proj.get("field", {})
            native_ref   = proj.get("nativeQueryRef", "")
            display_name = proj.get("displayName", native_ref)
            active       = proj.get("active", True)

            entry = None

            if "Measure" in field:
                prop  = field["Measure"].get("Property", "")
                table = _extract_entity(field["Measure"])
                k     = f"{table}.{prop}" if table else prop
                entry = {
                    "field_type":   "Measure",
                    "table":        table,
                    "property":     prop,
                    "display_name": display_name,
                }
                if k and k not in measures:
                    measures.append(k)

            elif "Column" in field:
                prop  = field["Column"].get("Property", "")
                table = _extract_entity(field["Column"])
                k     = f"{table}.{prop}" if table else prop
                entry = {
                    "field_type":   "Column",
                    "table":        table,
                    "property":     prop,
                    "display_name": display_name,
                }
                if k and k not in columns:
                    columns.append(k)

            elif "HierarchyLevel" in field:
                try:
                    level = field["HierarchyLevel"]["Level"]
                    table = (field["HierarchyLevel"]["Expression"]
                             ["Hierarchy"]["Expression"]["SourceRef"]["Entity"])
                    k     = f"{table}.{level}"
                    entry = {
                        "field_type":   "HierarchyLevel",
                        "table":        table,
                        "property":     level,
                        "display_name": display_name,
                        "drill_order":  drill_order,
                    }
                    if k not in columns:
                        columns.append(k)
                except Exception:
                    pass

            if entry:
                # only write active key when it deviates from default (True)
                if not active:
                    entry["active"] = False
                axis_bindings[axis_key].append(entry)

    # drop empty axis keys
    axis_bindings = {k: v for k, v in axis_bindings.items() if v}
    return axis_bindings, measures, columns


def _extract_entity(field_node: dict) -> str:
    """Extracts the source entity (table name) from a field reference node."""
    try:
        return field_node["Expression"]["SourceRef"]["Entity"]
    except Exception:
        return ""


def _parse_filter_config(data: dict) -> list:
    """
    Extracts top-level filterConfig from visual.json.

    filterConfig is at the TOP LEVEL of visual.json — NOT inside visual node.
    This is a visual-level pre-applied filter (e.g. org_name IS NOT NULL).

    DROPPED vs previous version:
        - "name" key (hash string — meaningless for LLM)
        - entries where field is empty AND conditions is empty
          (these are unconfigured placeholder filters — zero LLM value)

    Returns list of:
        {
            "field_type":  "Column" | "Measure",
            "table":       str,
            "property":    str,
            "filter_type": "Advanced" | "Basic" | "Categorical" | …,
            "how_created": "User" | "" | …,
            "conditions":  [str]   ← human-readable condition strings
        }
    """
    filters = []
    for f in data.get("filterConfig", {}).get("filters", []):
        field      = f.get("field", {})
        table, prop, field_type = "", "", ""

        if "Column" in field:
            table      = _extract_entity(field["Column"])
            prop       = field["Column"].get("Property", "")
            field_type = "Column"
        elif "Measure" in field:
            table      = _extract_entity(field["Measure"])
            prop       = field["Measure"].get("Property", "")
            field_type = "Measure"

        conditions = []
        for where in f.get("filter", {}).get("Where", []):
            conditions.append(_describe_condition(where.get("Condition", {})))

        # drop entries that carry zero information
        has_field      = bool(table and prop)
        has_conditions = bool(conditions)
        if not has_field and not has_conditions:
            continue

        filters.append({
            "field_type":  field_type,
            "table":       table,
            "property":    prop,
            "filter_type": f.get("type", ""),
            "how_created": f.get("howCreated", ""),
            "conditions":  conditions,
        })
    return filters


def _describe_condition(cond: dict) -> str:
    """Converts a filter condition dict into a human-readable string."""
    if "Not" in cond:
        return f"NOT ({_describe_condition(cond['Not']['Expression'])})"
    if "Comparison" in cond:
        c    = cond["Comparison"]
        kind = {0: "==", 1: ">", 2: ">=", 3: "<", 4: "<=", 5: "!="}.get(
            c.get("ComparisonKind", 0), "?")
        left  = _field_ref_str(c.get("Left",  {}))
        right = _literal_str(c.get("Right", {}))
        return f"{left} {kind} {right}"
    if "In" in cond:
        left   = _field_ref_str(cond["In"].get("Expressions", [{}])[0])
        values = [_literal_str(v) for v in cond["In"].get("Values", [])]
        return f"{left} IN ({', '.join(values)})"
    return str(cond)[:80]


def _field_ref_str(expr: dict) -> str:
    """Returns 'Table.Property' string from a field expression."""
    try:
        if "Column" in expr:
            t = _extract_entity(expr["Column"])
            p = expr["Column"].get("Property", "")
            return f"{t}.{p}"
        if "Measure" in expr:
            t = _extract_entity(expr["Measure"])
            p = expr["Measure"].get("Property", "")
            return f"{t}.{p}"
    except Exception:
        pass
    return str(expr)[:40]


def _literal_str(expr: dict) -> str:
    """Returns the literal value string from an expression dict."""
    try:
        return expr.get("Literal", {}).get("Value", str(expr)).strip("'")
    except Exception:
        return str(expr)[:40]


def _extract_slicer_meta(visual_node: dict) -> dict:
    """
    Reads slicer-specific display properties directly from the raw visual node.
    Called only by _make_filter() — not stored on VisualSchema.

    Reads from raw objects dict (not a parsed block) because these keys
    (data, header, selection, general) are intentionally excluded from
    VisualSchema to avoid cosmetic bloat.

    Returns:
        {
            "mode":               str   ("Dropdown" | "List" | "Tile" | "Between")
            "header_text":        str
            "single_select":      str   ("true" | "false")
            "select_all_enabled": str   ("true" | "false")
        }
    """
    raw_objects = visual_node.get("objects", {})

    def _first(obj_key, prop_name):
        for item in raw_objects.get(obj_key, []):
            val = item.get("properties", {}).get(prop_name)
            if val is not None:
                # resolve simple Literal scalar inline — no _resolve_scalar dependency
                if isinstance(val, dict):
                    expr = val.get("expr", val)
                    if "Literal" in expr:
                        return expr["Literal"].get("Value", "").strip("'")
                    if "Boolean" in expr:
                        return str(expr["Boolean"].get("Value", ""))
                return str(val)
        return ""

    return {
        "mode":               _first("data",      "mode"),
        "header_text":        _first("header",    "text"),
        "single_select":      _first("selection", "singleSelect"),
        "select_all_enabled": _first("selection", "selectAllCheckboxEnabled"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — REPORT META PARSER
# ══════════════════════════════════════════════════════════════════════════════

CUSTOM_VISUAL_REGISTRY = {
    "ChicletSlicer": {
        "name":            "Chiclet Slicer",
        "publisher":       "Microsoft",
        "visual_behavior": "button_slicer",
        "description":     "Button-style slicer — each option is a clickable tile. Allows single or multi-select.",
        "user_warning":    "If you see a 'Custom visual needs to be saved' warning, this visual is the cause. Data is not affected.",
        "filter_behavior": "Acts like a standard slicer but with button UI instead of dropdown.",
    },
}

EXPORT_MODE_DESCRIPTIONS = {
    "AllowSummarized": "Only summarized/aggregated data can be exported — raw row-level data is restricted.",
    "AllowAll":        "Both summarized and raw row-level data can be exported.",
    "Disabled":        "Data export is completely disabled for this dashboard.",
}


class ReportMetaParser:
    def __init__(self, report_path: str):
        self.report_path = Path(report_path)

    def extract(self) -> ReportMeta:
        report_json  = self.report_path / "definition" / "report.json"
        version_json = self.report_path / "definition" / "version.json"
        data         = json.loads(report_json.read_text(encoding="utf-8", errors="ignore"))

        pbip_version = ""
        if version_json.exists():
            try:
                pbip_version = json.loads(
                    version_json.read_text(encoding="utf-8", errors="ignore")
                ).get("version", "")
            except Exception:
                pass

        tc     = data.get("themeCollection", {})
        custom = tc.get("customTheme", {})
        theme  = {
            "base_theme_name":   tc.get("baseTheme", {}).get("name", ""),
            "custom_theme_name": custom.get("name", ""),
            "has_custom_theme":  bool(custom),
            "llm_note": (
                f"Dashboard uses custom theme '{custom.get('name','')}'. "
                "All colors follow this theme, not Power BI defaults."
                if custom else "Dashboard uses Power BI default theme."
            ),
        }

        custom_visuals = [
            self._match_custom_visual(v)
            for v in data.get("publicCustomVisuals", [])
        ]

        settings      = self._parse_settings(data.get("settings", {}))
        slow_settings = self._parse_slow_settings(data.get("slowDataSourceSettings", {}))

        filter_sort   = data.get("filterConfig", {}).get("filterSortOrder", "")
        filter_config = {
            "filter_sort_order": filter_sort,
            "llm_note": (
                "Filters are in custom order — reflects developer's intended priority."
                if filter_sort == "Custom" else f"Filter sort order: {filter_sort}"
            ),
        }

        resources = [
            {
                "name":         item.get("name", ""),
                "path":         item.get("path", ""),
                "type":         item.get("type", ""),
                "package_type": pkg.get("type", ""),
                "description":  self._describe_resource(item),
            }
            for pkg in data.get("resourcePackages", [])
            for item in pkg.get("items", [])
        ]

        llm_context = {
            "all_descriptions": (
                [theme["llm_note"]]
                + settings.get("descriptions", [])
                + slow_settings.get("descriptions", [])
                + [filter_config["llm_note"]]
                + [v["description"] for v in custom_visuals]
            ),
            "user_warnings":             [v["user_warning"] for v in custom_visuals if v.get("user_warning")],
            "custom_visuals_present":    len(custom_visuals) > 0,
            "has_custom_theme":          theme["has_custom_theme"],
            "export_restricted":         settings.get("export_mode") == "AllowSummarized",
            "filters_apply_immediately": not slow_settings["apply_all_button"],
        }

        return ReportMeta(
            pbip_version=pbip_version,
            theme=theme,
            custom_visuals=custom_visuals,
            settings=settings,
            slow_settings=slow_settings,
            filter_config=filter_config,
            resources=resources,
            llm_context=llm_context,
        )

    def _match_custom_visual(self, vid: str) -> dict:
        for prefix, info in CUSTOM_VISUAL_REGISTRY.items():
            if vid.startswith(prefix):
                return {"visual_id": vid, "matched_name": prefix, **info}
        return {
            "visual_id":       vid,
            "matched_name":    vid,
            "name":            vid,
            "visual_behavior": "unknown",
            "description":     f"Unknown custom visual '{vid}'.",
            "user_warning":    "Custom visual present — verify it loads correctly.",
            "filter_behavior": "Unknown — verify cross-filter behavior manually.",
        }

    def _describe_resource(self, item: dict) -> str:
        ext = Path(item.get("name", "")).suffix.lower()
        if ext == ".json" and item.get("type") == "Image":
            return "Custom color theme file."
        if ext in (".png", ".jpg", ".jpeg", ".svg", ".gif"):
            return "Embedded image (logo, banner, or background graphic)."
        return f"Resource file of type '{item.get('type', '')}'."

    def _parse_settings(self, raw: dict) -> dict:
        known = {
            "defaultDrillFilterOtherVisuals": (
                "drill_filters_other_visuals",
                "Drill-through filtering ON — drilling down filters other visuals.",
                "Drill-through filtering OFF.",
            ),
            "useEnhancedTooltips": (
                "enhanced_tooltips",
                "Enhanced tooltips ON — hover for additional detail.",
                "Standard tooltips only.",
            ),
            "allowChangeFilterTypes": (
                "allow_change_filter_types",
                "Users can switch filters between Basic and Advanced mode.",
                "Filter type is fixed.",
            ),
            "useStylableVisualContainerHeader": (
                "stylable_visual_header",
                "Visual headers are stylable.",
                "Standard visual headers.",
            ),
            "useDefaultAggregateDisplayName": (
                "default_aggregate_display_name",
                "Default aggregate names shown.",
                "Custom aggregate display names used.",
            ),
        }
        structured, descriptions = {}, []
        for raw_key, raw_val in raw.items():
            if raw_key == "exportDataMode":
                structured["export_mode"] = raw_val
                descriptions.append(EXPORT_MODE_DESCRIPTIONS.get(raw_val, f"Export mode: '{raw_val}'."))
            elif raw_key in known:
                dest, t_desc, f_desc = known[raw_key]
                structured[dest] = raw_val
                descriptions.append(t_desc if raw_val else f_desc)
            else:
                structured[f"unknown_{raw_key}"] = raw_val
        structured["descriptions"] = descriptions
        return structured

    def _parse_slow_settings(self, raw: dict) -> dict:
        cross = not raw.get("isCrossHighlightingDisabled", False)
        apply = raw.get("isApplyAllButtonEnabled", False)
        return {
            "cross_highlighting_enabled": cross,
            "apply_all_button":           apply,
            "slicer_selections_button":   raw.get("isSlicerSelectionsButtonEnabled", False),
            "filter_selections_button":   raw.get("isFilterSelectionsButtonEnabled", False),
            "descriptions": [
                "Cross-highlighting is ON — clicking a visual highlights related data elsewhere."
                if cross else "Cross-highlighting is OFF.",
                "Filters apply immediately — no Apply button needed."
                if not apply else "'Apply All' button is present.",
            ],
        }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — REPORT LAYOUT PARSER
# ══════════════════════════════════════════════════════════════════════════════

MEANINGFUL_VISUAL_TYPES = {
    "card", "multiRowCard", "cardVisual", "kpiVisual", "gauge",
    "lineChart", "areaChart",
    "barChart", "clusteredBarChart", "stackedBarChart",
    "columnChart", "clusteredColumnChart", "stackedColumnChart",
    "donutChart", "pieChart",
    "tableEx", "pivotTable", "matrix",
    "scatterChart", "waterfallChart", "funnelChart",
    "slicer", "filtersVisual",
}


class ReportLayoutParser:
    def __init__(self, report_path: str):
        self.pages_dir = Path(report_path) / "definition" / "pages"

    def extract(self, visual_map: dict):
        """
        Main entry point. Reads all pages and their visuals.

        Returns: (pages, visuals, filters, interactions)
          pages        -> list of page metadata dicts
          visuals      -> list of VisualSchema (only MEANINGFUL_VISUAL_TYPES)
          filters      -> list of FilterSchema (slicers only)
          interactions -> dict keyed by page name -> cross-filter rules
        """
        pages   = []
        visuals = []
        filters = []

        if not self.pages_dir.exists():
            return pages, visuals, filters, {}

        for page_order, page_dir in enumerate(sorted(self.pages_dir.iterdir())):
            if not page_dir.is_dir():
                continue

            display_name = page_dir.name
            bi_width     = 1440
            bi_height    = 2000

            page_meta = page_dir / "page.json"
            if page_meta.exists():
                try:
                    meta         = json.loads(page_meta.read_text(encoding="utf-8", errors="ignore"))
                    display_name = meta.get("displayName", page_dir.name)
                    bi_width     = meta.get("width",  bi_width)
                    bi_height    = meta.get("height", bi_height)
                except Exception:
                    pass

            pages.append({
                "name":         page_dir.name,
                "display_name": display_name,
                "order":        page_order + 1,
                "width":        bi_width,
                "height":       bi_height,
            })

            visuals_dir = page_dir / "visuals"
            if not visuals_dir.exists():
                continue

            for vdir in sorted(visuals_dir.iterdir()):
                if not vdir.is_dir():
                    continue
                vfile = vdir / "visual.json"
                if not vfile.exists():
                    continue

                try:
                    data = json.loads(vfile.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    continue

                if "visual" not in data:
                    continue

                v_type = data["visual"].get("visualType", "")
                if v_type not in MEANINGFUL_VISUAL_TYPES:
                    continue

                v = self._parse_visual(data, vdir.name, display_name)
                if not v:
                    continue

                visuals.append(v)

                if v.type == "slicer":
                    f = self._make_filter(data, v, display_name)
                    if f:
                        filters.append(f)

        interactions = self._parse_interactions(visual_map)
        return pages, visuals, filters, interactions

    def _parse_visual(self, data: dict, vid: str, page_name: str) -> Optional[VisualSchema]:
        """
        Parses one visual.json into a VisualSchema.

        IMPORTANT: position is at TOP LEVEL of visual.json — NOT inside visual node.
        IMPORTANT: filterConfig is at TOP LEVEL of visual.json — NOT inside visual node.

        Fields intentionally NOT extracted here (dropped):
          x, y, z, tab_order  — canvas position / keyboard nav
          sort                 — display ordering only
          objects / container  — formatting/styling
          datapoint_colors     — cosmetic color overrides
        """
        visual_node = data["visual"]
        v_type      = visual_node.get("visualType", "unknown")

        pos    = data.get("position", {})
        width  = float(pos.get("width",  0))
        height = float(pos.get("height", 0))

        title                    = self._get_title(visual_node)
        axis_bindings, measures, columns = _extract_fields_with_roles(visual_node)
        filter_config            = _parse_filter_config(data)
        drill_filter             = visual_node.get("drillFilterOtherVisuals", True)

        return VisualSchema(
            id=vid,
            title=title,
            type=v_type,
            page=page_name,
            width=width,
            height=height,
            measures_used=measures,
            columns_used=columns,
            axis_bindings=axis_bindings,
            drill_filter_other_visuals=drill_filter,
            filter_config=filter_config,
        )

    def _get_title(self, visual_node: dict) -> str:
        try:
            return (visual_node["visualContainerObjects"]["title"][0]
                    ["properties"]["text"]["expr"]["Literal"]["Value"].strip("'"))
        except Exception:
            pass
        try:
            return (visual_node["objects"]["title"][0]
                    ["properties"]["text"]["expr"]["Literal"]["Value"].strip("'"))
        except Exception:
            pass
        return ""

    def _make_filter(self, data: dict, v: VisualSchema, page_name: str) -> Optional[FilterSchema]:
        """
        Builds a FilterSchema from a slicer visual's queryState.
        Tries role names in priority order: Values -> Field -> Category -> Y.
        Reads slicer_meta and sync_group directly from raw data — these are
        NOT stored on VisualSchema (cosmetic/behavioral, belong only in FilterSchema).
        Returns None if no bound column/measure is found.
        """
        vn     = data["visual"]
        qs     = vn.get("query", {}).get("queryState", {})
        table  = ""
        column = ""

        for role in ["Values", "Field", "Category", "Y"]:
            projs = qs.get(role, {}).get("projections", [])
            if not projs:
                continue
            field = projs[0].get("field", {})
            if "Column" in field:
                column = field["Column"].get("Property", "")
                table  = _extract_entity(field["Column"])
                break
            elif "Measure" in field:
                column = field["Measure"].get("Property", "")
                table  = _extract_entity(field["Measure"])
                break

        if not column:
            return None

        slicer_meta = _extract_slicer_meta(vn)
        sync_group  = data.get("syncGroup", {})
        name        = slicer_meta.get("header_text") or v.title or f"Slicer_{v.id}"

        return FilterSchema(
            name=name,
            type="slicer",
            table=table,
            column=column,
            page=page_name,
            slicer_mode=slicer_meta.get("mode", ""),
            single_select=slicer_meta.get("single_select", ""),
            select_all_enabled=slicer_meta.get("select_all_enabled", ""),
            sync_group=sync_group.get("groupName", ""),
            visual_filter_conditions=[
                c for fc in v.filter_config for c in fc.get("conditions", [])
            ],
        )

    def _parse_interactions(self, visual_map: dict) -> dict:
        """
        Reads visualInteractions from each page.json.
        Maps source/target visual IDs -> titles using visual_map.
        Returns per-page cross-filter rules with LLM-ready descriptions.
        """
        all_pages  = {}
        skip_types = {"shape", "textbox", "image", "actionButton", "basicShape"}

        for page_dir in sorted(self.pages_dir.iterdir()):
            if not page_dir.is_dir():
                continue
            page_json = page_dir / "page.json"
            if not page_json.exists():
                continue

            data         = json.loads(page_json.read_text(encoding="utf-8", errors="ignore"))
            display_name = data.get("displayName", page_dir.name)
            interactions = data.get("visualInteractions", [])

            if not interactions or not isinstance(interactions, list):
                continue

            by_source = {}
            for rule in interactions:
                src_id = rule.get("source", "")
                tgt_id = rule.get("target", "")
                itype  = rule.get("type",   "")
                if not src_id or not tgt_id:
                    continue

                src_info = visual_map.get(src_id, {})
                tgt_info = visual_map.get(tgt_id, {})

                if src_id not in by_source:
                    by_source[src_id] = {
                        "source_id":    src_id,
                        "source_title": src_info.get("title", "untitled"),
                        "source_type":  src_info.get("type",  "unknown"),
                        "filters":      [],
                        "no_filters":   [],
                    }

                entry = {
                    "target_id":    tgt_id,
                    "target_title": tgt_info.get("title", "untitled"),
                    "target_type":  tgt_info.get("type",  "unknown"),
                }

                if itype == "DataFilter":
                    by_source[src_id]["filters"].append(entry)
                else:
                    by_source[src_id]["no_filters"].append(entry)

            summary = []
            for s in by_source.values():
                if s["source_type"] in skip_types:
                    continue
                if not s["filters"] and not s["no_filters"]:
                    continue
                f_names  = [x["target_title"] for x in s["filters"]   if x["target_title"] != "untitled"]
                nf_names = [x["target_title"] for x in s["no_filters"] if x["target_title"] != "untitled"]
                desc     = f"When '{s['source_title']}' ({s['source_type']}) is clicked"
                if f_names:  desc += f", it filters: {', '.join(f_names)}"
                if nf_names: desc += f". It does NOT filter: {', '.join(nf_names)}"
                summary.append({**s, "llm_description": desc})

            all_pages[display_name] = {
                "page":                   display_name,
                "total_rules":            len(interactions),
                "interaction_types":      list(set(r.get("type", "") for r in interactions)),
                "interactions_by_source": summary,
            }

        return all_pages


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — BOOKMARK EXTRACTOR
# ══════════════════════════════════════════════════════════════════════════════

class BookmarkExtractor:
    def __init__(self, report_path: str):
        self.bookmarks_dir = Path(report_path) / "definition" / "bookmarks"

    def extract(self, visual_map: dict) -> tuple[list, list]:
        enriched      = self._build_enriched(visual_map)
        toggle_groups = self._build_toggle_groups(enriched)
        return enriched, toggle_groups

    def _build_enriched(self, visual_map: dict) -> list:
        enriched = []
        if not self.bookmarks_dir.exists():
            return enriched

        for f in sorted(self.bookmarks_dir.glob("*.json")):
            data    = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
            name    = data.get("displayName", "unnamed")
            targets = data.get("options", {}).get("targetVisualNames", [])
            bm_type = self._classify(targets, visual_map)

            if bm_type == "page_default":
                enriched.append({
                    "bookmark_name": name,
                    "bookmark_type": "page_default",
                    "purpose":       "Restores page to default state",
                    "targets_count": 0,
                })
                continue

            page = next(
                (visual_map[v]["page"] for v in targets
                 if v in visual_map and visual_map[v].get("page")),
                ""
            )

            vis           = self._extract_visibility(data, visual_map)
            shown_charts  = [c for g in vis["shown"]  for c in g.get("charts", [])]
            hidden_charts = [c for g in vis["hidden"] for c in g.get("charts", [])]

            enriched.append({
                "bookmark_name": name,
                "bookmark_type": bm_type,
                "page":          page,
                "targets_count": len(targets),
                "when_active": {
                    "groups_shown":   vis["shown"],
                    "groups_hidden":  vis["hidden"],
                    "charts_visible": shown_charts,
                    "charts_hidden":  hidden_charts,
                },
            })

        return enriched

    def _classify(self, targets: list, visual_map: dict) -> str:
        if not targets:
            return "page_default"
        return (
            "toggle"
            if any(visual_map.get(v, {}).get("kind") == "group" for v in targets)
            else "filter_state"
        )

    def _extract_visibility(self, data: dict, visual_map: dict) -> dict:
        shown, hidden = [], []
        try:
            for section_data in data.get("explorationState", {}).get("sections", {}).values():
                for parent_id, parent_data in section_data.get("visualContainerGroups", {}).items():
                    for child_id, child_data in parent_data.get("children", {}).items():
                        is_hid     = child_data.get("isHidden", False)
                        group_name = visual_map.get(child_id, {}).get("group_name", child_id)
                        entry      = {
                            "group_id":   child_id,
                            "group_name": group_name,
                            "charts":     self._charts_in_group(child_id, visual_map),
                        }
                        (hidden if is_hid else shown).append(entry)
        except Exception:
            pass
        return {"shown": shown, "hidden": hidden}

    def _charts_in_group(self, group_id: str, visual_map: dict) -> list:
        skip   = {"", "unknown", "actionButton", "textbox", "shape", "image", "basicShape"}
        charts = []
        for vid, info in visual_map.items():
            if info.get("parent_group") != group_id:
                continue
            if info.get("kind") == "visual" and info.get("type") not in skip:
                charts.append({
                    "visual_id":     vid,
                    "title":         info.get("title", ""),
                    "type":          info.get("type",  ""),
                    "measures_used": info.get("measures_used", []),
                    "columns_used":  info.get("columns_used",  []),
                })
            elif info.get("kind") == "group":
                charts.extend(self._charts_in_group(vid, visual_map))
        return charts

    def _build_toggle_groups(self, enriched: list) -> list:
        sig_map = {}
        for bm in enriched:
            if bm.get("bookmark_type") != "toggle":
                continue
            all_ids = frozenset(
                g["group_id"]
                for key in ["groups_shown", "groups_hidden"]
                for g in bm.get("when_active", {}).get(key, [])
            )
            if not all_ids:
                continue
            sig_map.setdefault(all_ids, []).append(bm)

        groups = []
        for group_ids, bookmarks in sig_map.items():
            if len(bookmarks) < 2:
                continue
            page         = bookmarks[0].get("page", "")
            chart_titles = list(set(
                c["title"]
                for bm in bookmarks
                for c in bm["when_active"]["charts_visible"] + bm["when_active"]["charts_hidden"]
                if c.get("title")
            ))
            all_measures = list(set(
                m
                for bm in bookmarks
                for c in bm["when_active"]["charts_visible"] + bm["when_active"]["charts_hidden"]
                for m in c.get("measures_used", [])
            ))
            states = [
                {
                    "bookmark_name":   bm["bookmark_name"],
                    "charts_shown":    bm["when_active"]["charts_visible"],
                    "measures_shown":  list(set(m for c in bm["when_active"]["charts_visible"]
                                               for m in c.get("measures_used", []))),
                    "charts_hidden":   bm["when_active"]["charts_hidden"],
                    "measures_hidden": list(set(m for c in bm["when_active"]["charts_hidden"]
                                               for m in c.get("measures_used", []))),
                }
                for bm in bookmarks
            ]
            groups.append({
                "page":          page,
                "chart_titles":  chart_titles,
                "total_states":  len(bookmarks),
                "states":        states,
                "all_measures":  all_measures,
                "llm_description": (
                    f"On '{page}', chart(s) '{', '.join(chart_titles)}' "
                    f"have {len(bookmarks)} toggle states. "
                    f"Only one state is visible at a time. "
                    f"Measures: {', '.join(all_measures)}. "
                    f"States: {', '.join(b['bookmark_name'] for b in bookmarks)}."
                ),
            })
        return groups