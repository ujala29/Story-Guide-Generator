"""
funnel_input_builder.py
=======================
Stage 3A — Step 1

Reads existing Stage 1 and Stage 2 output files and produces a single
clean JSON file that is the complete LLM input for funnel mapping.

REAL DATA SOURCES (verified against actual files):

  output/dashboards/<dashboard>/stage3/enriched_pages/<page_name>.json
    One file per page. Structure:
      {
        "page": "Overview LM",
        "visual_count": 44,
        "visuals": [ {id, title, type, page, measures_used, columns_used,
                       axis_bindings, measure_chains, ...}, ... ]
      }

  stage1/schema_sections/pages.json
    [{name (hex id), display_name, order, width, height}, ...]
    Used only for page ordering — visuals come from stage3/enriched_pages/

  stage2/metric_catalog_registry.json        ← definitions live HERE
    {"<measure_name>": {
        "technical_definition": "...",
        "business_definition":  "...",
        "updated_at": "..."
    }, ...}

  config/fixes.json
    {"title_overrides": {"<visual_id>": "Display Title"}}

  config/dashboard_config.json
    {"risk-dash": {"display_name": "Risk Management", ...}, ...}

OUTPUT:
  output/dashboards/<dash>/stage3/funnel_llm_input.json

WHAT THE OUTPUT CONTAINS PER VISUAL:
  visual_id, title, type, page
  measures  -> [{name, dax (leaf formula only), definition, display_name_in_visual}]
  columns_used
  row_dimensions  (for tables — what the rows are broken down by)

Run:
  python -m app.story.funnel_input_builder --dashboard risk-dash
  python -m app.story.funnel_input_builder --dashboard pac-dash
  python -m app.story.funnel_input_builder --dashboard risk-dash --print
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import json
import argparse
import hashlib
from pathlib import Path


# ── visual types that are filters/slicers/decoration — never content ──────────
SKIP_TYPES = {
    "slicer",
    "advancedSlicerVisual",
    "textbox",
    "image",
    "shape",
    "actionButton",
    "basicShape",
}

# ── pages that are utility/tooltip — not part of the story ───────────────────
SKIP_PAGES = {
    "Scatter plot tooltip",
    "Additional dimensions",
    "Data availability",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_json(path: Path):
    """Load JSON. Return None if file does not exist."""
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "output").exists() and (parent / "config").exists():
            return parent
    for parent in Path(__file__).resolve().parents:
        if (parent / "run.py").exists():
            return parent
    return Path(__file__).resolve().parent.parent.parent


def strip_table_prefix(raw: str) -> str:
    """
    "ALL DAX.Risk recapture rate PY"  ->  "Risk recapture rate PY"
    "date.month_of_year"              ->  "date.month_of_year"   (kept, it's a column)

    Rule: strip prefix only when prefix is "ALL DAX" (the measure container).
    Column references like "date.month_of_year" keep their prefix because the
    table name is meaningful there.
    """
    if raw.startswith("ALL DAX."):
        return raw[len("ALL DAX."):]
    return raw.strip()


def get_leaf_dax(measure_chain: dict) -> str:
    """
    measure_chains entries have a full dependency tree via 'depends_on'.
    The leaf measure (is_leaf=True, depth=0) has the actual formula.
    We want the leaf DAX — it's concise and reveals what columns/tables
    the measure reads from, which is the signal the LLM uses to understand
    the measure's analytical intent.

    If no leaf found, fall back to the top-level DAX.
    """
    queue = [measure_chain]
    while queue:
        node = queue.pop(0)
        if node.get("is_leaf", False):
            return _clean_dax(node.get("dax", ""))
        for dep in node.get("depends_on", []):
            queue.append(dep)
    return _clean_dax(measure_chain.get("dax", ""))


def _clean_dax(dax: str) -> str:
    """
    Remove Power BI metadata annotations appended after the DAX formula:
      formatString: 0.0%;-0.0%;0.0%
      lineageTag: 1fc47f63-...
      annotation PBI_FormatHint = {...}
    These lines appear after a newline and are not part of the formula.
    """
    if not dax:
        return ""
    lines = dax.split("\n")
    clean = []
    for line in lines:
        stripped = line.strip()
        if (
            stripped.startswith("formatString:")
            or stripped.startswith("lineageTag:")
            or stripped.startswith("annotation ")
        ):
            break
        clean.append(line)
    return "\n".join(clean).strip()


def get_display_name_for_measure(measure_name: str, axis_bindings: dict) -> str:
    """
    axis_bindings contains the display_name used in the visual for each measure.
    E.g. "Risk recapture rate PY" might display as "Previous year" in the chart.
    This tells the LLM how the visual labels this measure to the user.
    Returns "" if the display name is trivially the same as the measure name.
    """
    for axis_list in axis_bindings.values():
        for entry in axis_list:
            if (
                entry.get("field_type") == "Measure"
                and entry.get("property") == measure_name
            ):
                dn = entry.get("display_name", "").strip()
                if dn and dn != measure_name:
                    return dn
    return ""


def get_row_dimensions(axis_bindings: dict) -> list:
    """
    For pivotTable / matrix visuals, 'rows' shows what dimension the table
    is broken down by. E.g. risk_model_name -> "Model/sub-model".
    This tells the LLM what entity this table segments by — crucial for
    correctly classifying it in the funnel (MIDDLE diagnostic vs BOTTOM entity).
    """
    dims = []
    for entry in axis_bindings.get("rows", []):
        dn = entry.get("display_name") or entry.get("property", "")
        if dn:
            dims.append(dn)
    return dims


# ── titles that are clearly wrong/stale for card-type visuals ────────────────
# When a multiRowCard or cardVisual has one of these titles, we override
# it with the measure name / display_name instead
GENERIC_TITLES = {
    "Pharmacy PMPM YoY",
    "Leakage %",
    "Card",
    "Visual",
    "",
}

# visual types where the title often doesn't reflect the actual content
CARD_TYPES = {"multiRowCard", "cardVisual", "card"}


def resolve_title(visual: dict, title_overrides: dict) -> str:
    """
    Priority:
      1. Manual override from fixes.json (by visual id)
      2. visual["title"] if non-empty AND not a known generic/wrong title
         (for card types, also reject if title is in GENERIC_TITLES)
      3. For card/multiRowCard types: use measure's display_name_in_visual
         or measure name — whichever is more descriptive
      4. First non-trivial display_name from axis_bindings
      5. visual type as last resort
    """
    vid   = visual.get("id", "")
    vtype = visual.get("type", "")

    # 1. manual override always wins
    if vid in title_overrides:
        return title_overrides[vid]

    title = visual.get("title", "").strip()

    # 2. for non-card visuals: trust the title if it exists and isn't generic
    if vtype not in CARD_TYPES:
        if title and title not in GENERIC_TITLES:
            return title

    # 3. for card types (or if title is generic): derive from measure
    if vtype in CARD_TYPES or title in GENERIC_TITLES or not title:
        # try axis_bindings display_name first — it's what the visual shows
        for axis_list in visual.get("axis_bindings", {}).values():
            for entry in axis_list:
                if entry.get("field_type") == "Measure":
                    dn = entry.get("display_name", "").strip()
                    if dn and dn not in GENERIC_TITLES:
                        return dn

        measures_used = visual.get("measures_used", [])
        if measures_used:
            return strip_table_prefix(measures_used[0])

    # 4. non-generic title from field 2
    if title and title not in GENERIC_TITLES:
        return title

    # 5. last resort
    return vtype or "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Core builders
# ─────────────────────────────────────────────────────────────────────────────

def build_measure_entries(visual: dict, definitions: dict, measures_resolved: dict) -> list:
    """
    Build the measures array for one visual.

    Uses measures_resolved for DAX (loaded once in build_funnel_llm_input).
    Uses metric_catalog_registry for business/technical definitions.

    Returns:
      [{name, dax, definition, display_name_in_visual}, ...]
    """
    axis_bindings = visual.get("axis_bindings", {})
    seen = set()
    result = []

    for raw in visual.get("measures_used", []):
        name = strip_table_prefix(raw)
        if name in seen:
            continue
        seen.add(name)

        chain = measures_resolved.get(name, {})
        dax = get_leaf_dax(chain) if chain else ""

        def_entry = definitions.get(name, {})
        definition = (
            def_entry.get("business_definition")
            or def_entry.get("technical_definition")
            or ""
        )

        display_name_in_visual = get_display_name_for_measure(name, axis_bindings) or name

        result.append({
            "name":                  name,
            "dax":                   dax,
            "definition":            definition,
            "display_name_in_visual": display_name_in_visual,
        })

    return result


def build_visual_entry(visual: dict, title: str, definitions: dict, measures_resolved: dict) -> dict:
    """Build one clean visual entry for the LLM input JSON."""
    axis_bindings = visual.get("axis_bindings", {})

    entry = {
        "visual_id":    visual["id"],
        "title":        title,
        "type":         visual.get("type", ""),
        "page":         visual.get("page", ""),
        "measures":     build_measure_entries(visual, definitions, measures_resolved),
        "columns_used": visual.get("columns_used", []),
    }

    row_dims = get_row_dimensions(axis_bindings)
    if row_dims:
        entry["row_dimensions"] = row_dims

    return entry


def build_funnel_llm_input(dashboard: str, project_root: Path) -> dict:
    """
    Read all source files and assemble the complete LLM input dict.

    Visuals come from output/dashboards/<dashboard>/stage3/enriched_pages/<page>.json (one file per page).
    """
    # ── paths ──────────────────────────────────────────────────────────────
    # NOTE: "visaul" is the actual folder name (typo in original codebase)
    enricher_pages_dir = project_root / "output" / "dashboards" / dashboard / "visual_wise" / "enriched_pages"
    stage1             = project_root / "output" / "dashboards" / dashboard / "extraction" / "schema_sections"
    stage2             = project_root / "output" / "dashboards" / dashboard / "metric_dictionary"
    config             = project_root / "config"

    # ── load ───────────────────────────────────────────────────────────────
    pages_raw        = load_json(stage1 / "pages.json") or []
    definitions      = load_json(stage2 / "metric_catalog_registry.json") or {}
    measures_resolved = load_json(stage1 / "measures_resolved.json") or {}
    fixes            = load_json(config / "fixes.json") or {}
    dash_cfg         = load_json(config / "dashboard_config.json") or {}

    # ── dashboard display name ─────────────────────────────────────────────
    # Fallback map for known dashboards when dashboard_config.json is missing
    # or doesn't have a display_name for this dashboard key
    KNOWN_DASHBOARD_NAMES = {
        "risk-dash": "Risk Management",
        "pac-dash":  "PAC",
    }
    meta = dash_cfg.get(dashboard, dash_cfg) if isinstance(dash_cfg, dict) else {}
    dashboard_name = (
        meta.get("dashboard_name")
        or meta.get("display_name")
        or meta.get("name")
        or KNOWN_DASHBOARD_NAMES.get(dashboard)
        or dashboard
    )
    if dashboard_name == dashboard:
        print(f"[funnel_input_builder] WARNING: dashboard_name fell back to key '{dashboard}'")
        print(f"[funnel_input_builder]          dashboard_config keys: {list(dash_cfg.keys()) if isinstance(dash_cfg, dict) else 'not a dict'}")

    # ── title overrides ────────────────────────────────────────────────────
    title_overrides = fixes.get("title_overrides", {})

    # ── pages — sorted by order from pages.json, skip utility pages ────────
    pages = []
    valid_page_display_names = set()
    _all_display_names_upper = {
        p.get("display_name", "").strip().upper()
        for p in pages_raw
    }
    for p in sorted(pages_raw, key=lambda x: x.get("order", 99)):
        dn = p.get("display_name", "").strip()
        if not dn or dn in SKIP_PAGES:
            continue
        # Skip *_LM pages that have a mirror *_LY page — same visuals, different
        # time comparison label. Process only the LY version.
        if dn.upper().endswith(" LM"):
            ly_counterpart = dn[:-3].rstrip() + " LY"
            if ly_counterpart.upper() in _all_display_names_upper:
                print(f"[funnel_input_builder] SKIP mirror page: '{dn}' (LY counterpart exists)")
                continue
        pages.append({
            "page_id":      p["name"],
            "display_name": dn,
            "order":        p.get("order", 0),
        })
        valid_page_display_names.add(dn)

    # ── load visuals from per-page enricher files ──────────────────────────
    # Each file: output/dashboards/<dashboard>/stage3/enriched_pages/<page_name>.json
    # The filename stem is the page display_name with spaces replaced by
    # underscores and lowercased (e.g. "Overview LM" -> "overview_lm.json")
    # We match by reading the "page" field inside each file rather than
    # relying on filename conventions — more robust.

    if not enricher_pages_dir.exists():
        raise FileNotFoundError(
            f"enriched_pages folder not found: {enricher_pages_dir}\n"
            f"Run stage 3-PRE (visual_enricher_pages.py) first."
        )

    all_page_files = list(enricher_pages_dir.glob("*.json"))
    if not all_page_files:
        raise FileNotFoundError(
            f"No JSON files found in {enricher_pages_dir}\n"
            f"Run stage 3-PRE (visual_enricher_pages_wise.py) first."
        )

    visuals_out   = []
    skipped_type  = 0
    skipped_page  = 0
    skipped_empty = 0
    pages_loaded  = []

    for page_file in sorted(all_page_files):
        page_data = load_json(page_file)
        if not page_data:
            continue

        page_display_name = page_data.get("page", "").strip()

        # skip utility pages
        if page_display_name in SKIP_PAGES:
            skipped_page += len(page_data.get("visuals", []))
            continue

        # skip pages not in our valid page list from pages.json
        # (this also catches *_LM mirror pages filtered out above)
        if page_display_name not in valid_page_display_names:
            skipped_page += len(page_data.get("visuals", []))
            continue

        pages_loaded.append(page_display_name)

        for v in page_data.get("visuals", []):
            vtype = v.get("type", "")

            if vtype in SKIP_TYPES:
                skipped_type += 1
                continue

            title = resolve_title(v, title_overrides)

            # skip visuals with no title AND no measures AND no columns
            if not title and not v.get("measures_used") and not v.get("columns_used"):
                skipped_empty += 1
                continue

            visuals_out.append(build_visual_entry(v, title, definitions, measures_resolved))

    # ── content hash for downstream cache invalidation ────────────────────
    hash_src = json.dumps(
        [{"id": v["visual_id"], "m": [m["name"] for m in v["measures"]]}
         for v in visuals_out],
        sort_keys=True,
    )
    content_hash = hashlib.md5(hash_src.encode()).hexdigest()[:12]

    total_measures  = sum(len(v["measures"]) for v in visuals_out)
    with_definition = sum(1 for v in visuals_out for m in v["measures"] if m["definition"])

    return {
        "dashboard":      dashboard,
        "dashboard_name": dashboard_name,
        "content_hash":   content_hash,
        "pages":          pages,
        "total_visuals":  len(visuals_out),
        "visuals":        visuals_out,
        "_meta": {
            "pages_loaded":         pages_loaded,
            "skipped_type":         skipped_type,
            "skipped_page":         skipped_page,
            "skipped_empty":        skipped_empty,
            "total_measures":       total_measures,
            "measures_with_def":    with_definition,
            "definition_coverage":  f"{with_definition}/{total_measures}",
            "has_definitions_file": bool(definitions),
            "enricher_pages_dir":   str(enricher_pages_dir),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build funnel LLM input JSON from Stage 1 + Stage 2 outputs"
    )
    parser.add_argument("--dashboard", default="risk-dash",
                        help="e.g. risk-dash or pac-dash (default: risk-dash)")
    parser.add_argument("--output", default=None,
                        help="Override output path")
    parser.add_argument("--print", dest="print_output", action="store_true",
                        help="Print JSON to stdout instead of writing file")
    args = parser.parse_args()

    root = get_project_root()

    print(f"[funnel_input_builder] dashboard    : {args.dashboard}")
    print(f"[funnel_input_builder] project root : {root}")

    result = build_funnel_llm_input(args.dashboard, root)

    m = result["_meta"]
    print(f"[funnel_input_builder] pages loaded : {m['pages_loaded']}")
    print(f"[funnel_input_builder] visuals kept : {result['total_visuals']}")
    print(f"[funnel_input_builder] skipped type : {m['skipped_type']}")
    print(f"[funnel_input_builder] skipped page : {m['skipped_page']}")
    print(f"[funnel_input_builder] definitions  : {m['definition_coverage']}")
    print(f"[funnel_input_builder] content_hash : {result['content_hash']}")

    if args.print_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = root / "output" / "dashboards" / args.dashboard / "page_wise"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "funnel_llm_input.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[funnel_input_builder] written to   : {out_path}")


if __name__ == "__main__":
    main()
