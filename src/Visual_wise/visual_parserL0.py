"""
Layer 0 — Pre-processor
=======================
Input  : visual (dict) + PageContext (pre-computed)
Output : L0Packet (dataclass) — structured, validated, ready for Layer 1/2/3

No LLM calls here. Pure code.

Two-step usage:
  Step 1 — call build_page_context(all_visuals) ONCE
  Step 2 — call build_l0_packet(visual, page_context) per visual

What this layer does:
  1. Title fix        — override / generic / blank
  2. Type routing     — cardVisual -> card path | pivotTable/tableEx -> table path
  3. Primary measure  — from axis_bindings
  4. DAX fetch        — all measures_used + paired cards (card path only)
  5. Comparison       — YoY / MoM from paired multiRowCard (card) or column names (table)
  6. Filters          — active filter_config entries
  7. Columns          — parse referenced_columns -> Table + Column
  8. Page visuals     — O(1) from page_context.page_map
  9. Peer cards       — O(1) from page_context.peer_cache (card path only)
  10. Validation      — missing fields warn, skip if unrecoverable
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import re

# ============================================================
# CONFIG PATHS
# ============================================================

_HERE         = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent

sys.path.insert(0, str(_HERE.parent))  # src/ — for paths.py
from paths import get_paths as _get_paths, get_config as _get_config

_DASHBOARD             = os.environ.get("STORY_DASHBOARD", "risk-dash")
_cfg                   = _get_config()
MEASURES_RESOLVED_PATH = str(_get_paths(_DASHBOARD).measures_resolved)

# ============================================================
# LOAD CONFIG  (dashboard-specific — no cross-dashboard fallback)
# ============================================================

_dash_fixes_path    = _cfg.dashboard_prompt_dir(_DASHBOARD) / "fixes.json"
_dash_glossary_path = _cfg.dashboard_prompt_dir(_DASHBOARD) / "glossary.json"

if _dash_fixes_path.exists():
    with open(_dash_fixes_path, encoding="utf-8") as f:
        _FIXES = json.load(f)
else:
    _FIXES = {"title_overrides": {}, "generic_titles": [], "skip_types": ["slicer", "multiRowCard", "card"]}

TITLE_OVERRIDES : dict = _FIXES["title_overrides"]
GENERIC_TITLES  : set  = set(_FIXES["generic_titles"])
SKIP_TYPES      : set  = set(_FIXES["skip_types"])

with open(MEASURES_RESOLVED_PATH, encoding="utf-8") as f:
    MEASURES_RESOLVED: dict = json.load(f)

GLOSSARY: dict = {}
if _dash_glossary_path.exists():
    with open(_dash_glossary_path, encoding="utf-8") as f:
        GLOSSARY = json.load(f)

# ============================================================
# CONSTANTS
# ============================================================

TREND_TYPES    = {"lineChart", "areaChart"}
KPI_CARD_TYPES = {"cardVisual"}
TABLE_TYPES    = {"pivotTable", "tableEx"}
CHART_TYPES    = {"clusteredBarChart", "barChart",
                  "columnChart", "donutChart", "scatterChart"}

# ============================================================
# OUTPUT SCHEMA  (L0Packet)
# ============================================================

@dataclass
class ColumnRef:
    """One parsed referenced_column entry."""
    table : str
    column: str
    raw   : str   # original string e.g. "risk_core[risk_value]"


@dataclass
class DaxEntry:
    """One measure's full resolved data."""
    name   : str
    dax    : str
    columns: list[ColumnRef]
    deps   : list[str]       # direct depends_on measure names
    role   : str             # "primary" | "yoy_card" | "mom_card" |
                             # "yoy_color" | "mom_color" | "other"


@dataclass
class PageVisual:
    """Another visual on the same page."""
    id      : str
    title   : str
    type    : str
    category: str   # "kpi_card" | "trend" | "table" | "chart" | "other"


@dataclass
class PeerCard:
    """Cross-read candidate — another cardVisual on same page."""
    title   : str
    measures: list[str]   # primary measure names (cleaned)


@dataclass
class PageContext:
    """
    Pre-computed page-level lookups — build ONCE, reuse per visual.
    Eliminates O(N×M) repeated all_visuals scans.
    """
    # page_name -> all visuals on that page (excl. SKIP_TYPES)
    page_map      : dict

    # visual_id -> (multiRowCard_visual, card_visual) tuple
    # cardVisuals only
    pairing_cache : dict

    # visual_id -> list[PeerCard]
    # cardVisuals only
    peer_cache    : dict


@dataclass
class L0Packet:
    """
    Full Layer 0 output.
    Every field consumed by at least one downstream layer.
    """
    # ── Identity ──────────────────────────────────────────
    visual_id   : str
    title       : str
    visual_type : str
    page        : str

    # ── Primary measure ───────────────────────────────────
    primary_measure : str          # "RAF recapture rate"
    primary_dax     : DaxEntry     # full resolved entry

    # ── All DAX on this visual (primary + paired) ─────────
    all_dax     : list[DaxEntry]   # visual's own measures
    paired_dax  : list[DaxEntry]   # multiRowCard + card measures (card path)

    # ── Comparison baseline ───────────────────────────────
    comparison  : str   # "YoY % change" | "MoM % change" | "None"

    # ── Filters ───────────────────────────────────────────
    active_filters: list[str]   # ["year", "month", "payer"]

    # ── Columns (deduplicated across all measures) ────────
    all_columns : list[ColumnRef]

    # ── Page context ─────────────────────────────────────
    page_visuals: list[PageVisual]   # all other visuals, categorised
    peer_cards  : list[PeerCard]     # cross-read candidates (card path)

    # ── Glossary (pass-through for Layer 1) ───────────────
    glossary    : dict

    # ── Table-specific fields ─────────────────────────────
    is_table      : bool      = False
    table_columns : list      = field(default_factory=list)
    # display_names from y_axis axis_bindings e.g.
    # ["Members", "Documented risk", "Gap to potential risk", ...]
    row_dimension : str       = ""
    row_dim_col_names : set = field(default_factory=set)
    # "practice_name / pcp_name" — from rows axis_bindings

    # ── LineChart-specific fields ─────────────────────────────
    is_linechart  : bool = False
    chart_lines   : list = field(default_factory=list)
    # [{"measure": "RAF recapture rate", "display_name": "RAF recapture rate"}, ...]
    x_axis_col    : str  = ""
    # display_name of the x-axis Column field (e.g. "Month")

    # ── BarChart-specific fields ──────────────────────────────
    is_barchart      : bool = False
    bar_orientation  : str  = ""
    # "vertical" or "horizontal"
    category_axis    : str  = ""
    # dimension column display_name e.g. "Disease" / "LOB"
    tooltip_measures : list = field(default_factory=list)
    # [{"measure": "...", "display_name": "..."}]
    # ── DonutChart-specific fields ────────────────────────────
    is_donut   : bool = False
    legend_col : str  = ""
    # category dimension display_name e.g. "Type of visit"
    # ── ScatterChart-specific fields ──────────────────────────
    is_scatter       : bool = False
    bubble_size      : str  = ""
    # measure used for bubble size e.g. "#Members"
    scatter_category : str  = ""
    # dimension column e.g. "pcp_name"

    # ── Validation flags ──────────────────────────────────
    warnings    : list[str] = field(default_factory=list)
    skip        : bool      = False
    skip_reason : str       = ""


# ============================================================
# HELPERS
# ============================================================

def _fix_title(visual: dict) -> str:
    """Return corrected display title."""
    vid   = visual.get("id", "")
    title = visual.get("title", "").strip()

    if vid in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[vid]
    if title in GENERIC_TITLES:
        measures = visual.get("measures_used", [])
        if measures:
            return measures[0].split(".", 1)[-1].strip()
    if not title:
        measures = visual.get("measures_used", [])
        if measures:
            return measures[0].split(".", 1)[-1].strip()
        return visual.get("type", "unknown")
    return title


def _parse_column_ref(raw: str) -> ColumnRef:
    """
    "risk_core[risk_value]"
       -> ColumnRef(table="risk_core", column="risk_value", raw=...)

    "'date'[month_of_date]"
       -> ColumnRef(table="date", column="month_of_date", raw=...)
    """
    raw = raw.strip()
    if "[" in raw and raw.endswith("]"):
        table_part, col_part = raw.split("[", 1)
        table  = table_part.strip().strip("'\"")
        column = col_part.rstrip("]").strip()
    else:
        table  = "unknown"
        column = raw
    return ColumnRef(table=table, column=column, raw=raw)


def _resolve_measure(raw_name: str) -> Optional[DaxEntry]:
    """
    Lookup one measure in MEASURES_RESOLVED.
    raw_name can be "ALL DAX.RAF recapture rate" or just
    "RAF recapture rate".
    """
    name = raw_name.split(".", 1)[-1].strip()

    entry = MEASURES_RESOLVED.get(name)
    if not entry:
        return None

    cols = [
        _parse_column_ref(c)
        for c in entry.get("referenced_columns", [])
    ]
    deps = [
        d["measure_name"]
        for d in entry.get("depends_on", [])
    ]

    return DaxEntry(
        name    = name,
        dax     = entry.get("dax", "").strip(),
        columns = cols,
        deps    = deps,
        role    = "other"   # caller sets correct role
    )


def _get_all_dep_names(measure_name: str, seen: set = None) -> set:
    """Recursively collect all upstream dependency names."""
    if seen is None:
        seen = set()
    entry = MEASURES_RESOLVED.get(measure_name)
    if not entry:
        return seen
    for d in entry.get("depends_on", []):
        dep = d["measure_name"]
        if dep not in seen:
            seen.add(dep)
            _get_all_dep_names(dep, seen)
    return seen


def _get_all_referenced_cols(measure_name: str) -> set[str]:
    """Collect all referenced columns recursively through dep tree."""
    all_deps = _get_all_dep_names(measure_name) | {measure_name}
    all_cols = set()
    for dep in all_deps:
        entry = MEASURES_RESOLVED.get(dep, {})
        for col in entry.get("referenced_columns", []):
            all_cols.add(col)
    return all_cols


def _categorise_visual(visual: dict) -> str:
    vtype = visual.get("type", "")
    if vtype in KPI_CARD_TYPES:
        return "kpi_card"
    if vtype in TREND_TYPES:
        return "trend"
    if vtype in TABLE_TYPES:
        return "table"
    if vtype in CHART_TYPES:
        return "chart"
    return "other"


def _assign_dax_role(name: str, page: str) -> str:
    """
    Assign role to a measure based on name pattern + page.
    """
    n = name.lower()
    if "yoy card" in n or ("yoy" in n and "card" in n):
        return "yoy_card"
    if "mom card" in n or ("mom" in n and "card" in n):
        return "mom_card"
    if "yoy color" in n or ("yoy" in n and "color" in n):
        return "yoy_color"
    if "mom color" in n or ("mom" in n and "color" in n):
        return "mom_color"
    return "primary"


def _detect_comparison(
    paired_dax      : list[DaxEntry],
    page            : str,
    primary_measure : str = ""
) -> str:
    """
    Determine comparison baseline.

    Strategy:
    1. paired_dax roles se detect karo (multiRowCard mila)
    2. Agar paired_dax empty — measures_resolved mein
       primary_measure + "YoY Card" / "MoM Card" check karo
    3. Page name se prefer karo — LY->YoY, LM->MoM
    """
    page_lower = page.lower()

    if "ly" in page_lower:
        preferred = "yoy"
    elif "lm" in page_lower:
        preferred = "mom"
    else:
        preferred = None

    # ── Step 1: paired_dax se detect ────────────────────────
    roles_found = {d.role for d in paired_dax}

    if preferred:
        preferred_role = f"{preferred}_card"
        if preferred_role in roles_found:
            return "YoY % change" if preferred == "yoy" else "MoM % change"

    if "yoy_card" in roles_found:
        return "YoY % change"
    if "mom_card" in roles_found:
        return "MoM % change"

    # ── Step 2: measures_resolved fallback ──────────────────
    if primary_measure and MEASURES_RESOLVED:
        has_yoy = f"{primary_measure} YoY Card" in MEASURES_RESOLVED
        has_mom = f"{primary_measure} MoM Card" in MEASURES_RESOLVED

        if preferred == "yoy" and has_yoy:
            return "YoY % change"
        if preferred == "mom" and has_mom:
            return "MoM % change"

        if has_yoy:
            return "YoY % change"
        if has_mom:
            return "MoM % change"

    return "None"


# ============================================================
# PAIRING LOGIC  (card path only)
# ============================================================

def _find_paired_visuals(
    visual      : dict,
    all_visuals : list,
    page        : str
) -> tuple[Optional[dict], Optional[dict]]:
    """
    Find paired multiRowCard (change tile) and card (subtitle)
    for a cardVisual.

    Returns: (multiRowCard_visual, card_visual)
    """
    measures = visual.get("measures_used", [])
    if not measures:
        return None, None

    # primary_measure = measures[0].split(".", 1)[-1].strip().lower()
    override = visual.get("_pairing_measure_override", "")
    if override:
        primary_measure = override.lower()
    else:
        primary_measure = measures[0].split(".", 1)[-1].strip().lower()
    page_lower      = page.lower()

    if "ly" in page_lower:
        preferred_comparison = "yoy"
    elif "lm" in page_lower:
        preferred_comparison = "mom"
    else:
        preferred_comparison = None

    best_multirow  = None
    best_score     = 0
    fallback_multi = None
    best_card      = None
    #   # ── DEBUG ────────────────────────────────────────────────
    # print(f"\n  [PAIR-DEBUG] primary_measure: '{primary_measure}'")
    # multirow_visuals = [v for v in all_visuals if v.get("type") == "multiRowCard"]
    # print(f"  [PAIR-DEBUG] total multiRowCards: {len(multirow_visuals)}")
    # for v in multirow_visuals:
    #     vm = v.get("measures_used", [])
    #     if vm:
    #         vp = vm[0].split(".", 1)[-1].strip().lower()
    #         print(f"    -> '{vp}' | match: {primary_measure in vp}")
    # # ── END DEBUG ─────────────────────────────────────────────

    for v in all_visuals:
        if v["id"] == visual["id"]:
            continue

        v_measures = v.get("measures_used", [])
        if not v_measures:
            continue

        v_primary = v_measures[0].split(".", 1)[-1].strip().lower()

        if v["type"] == "multiRowCard":
            if primary_measure in v_primary:
                is_preferred = (
                    preferred_comparison is not None
                    and preferred_comparison in v_primary
                )
                if is_preferred and best_score < 999:
                    best_multirow = v
                    best_score    = 999
                elif best_score < 999:
                    score = len(primary_measure)
                    if score > best_score:
                        best_score     = score
                        fallback_multi = v

        if v["type"] == "card":
            if primary_measure in v_primary:
                best_card = v

    if best_multirow is None:
        best_multirow = fallback_multi

    return best_multirow, best_card


# ============================================================
# PEER CARD DETECTION  (card path only)
# ============================================================

def _find_peer_cards(
    visual         : dict,
    all_visuals    : list,
    primary_measure: str
) -> list[PeerCard]:
    """
    Find other cardVisuals whose measures are business-linked
    to primary_measure via shared columns or dep tree.
    """
    primary_deps = _get_all_dep_names(primary_measure)
    primary_cols = _get_all_referenced_cols(primary_measure)

    peer_cards = []

    for v in all_visuals:
        if v["id"] == visual["id"]:
            continue
        if v["type"] not in KPI_CARD_TYPES:
            continue

        v_measures = v.get("measures_used", [])
        if not v_measures:
            continue

        v_primary_name = v_measures[0].split(".", 1)[-1].strip()

        if v_primary_name == primary_measure:
            continue

        matched = False
        for raw in v_measures:
            m_name    = raw.split(".", 1)[-1].strip()
            peer_deps = _get_all_dep_names(m_name)
            peer_cols = _get_all_referenced_cols(m_name)

            case1 = primary_measure in peer_deps
            case2 = m_name in primary_deps
            case3 = bool(primary_cols & peer_cols)

            if case1 or case2 or case3:
                matched = True
                break

        if matched:
            title = _fix_title(v)
            peer_measure_names = [
                r.split(".", 1)[-1].strip()
                for r in v_measures
            ]
            peer_cards.append(PeerCard(
                title    = title,
                measures = peer_measure_names
            ))

    # Deduplicate by title
    seen   = set()
    unique = []
    for p in peer_cards:
        if p.title not in seen:
            seen.add(p.title)
            unique.append(p)

    return unique


# ============================================================
# TABLE PATH  — dedicated L0 builder for pivotTable / tableEx
# ============================================================

# def _build_table_l0_packet(
#     visual      : dict,
#     page_context: PageContext,
#     vid         : str,
#     vtype       : str,
#     page        : str,
#     title       : str,
#     warnings    : list
# ) -> "L0Packet":
#     """
#     pivotTable / tableEx ke liye dedicated L0 builder.

#     Differences from card path:
#     - No paired visuals (no multiRowCard)
#     - No peer_cards (tables don't cross-read cards)
#     - table_columns  = y_axis measure display_names
#     - row_dimension  = rows axis_bindings property names
#     - comparison     = detected from column names (YoY/MoM)
#     - columns_used   = pcp dimension columns added directly
#     """
#     axis = visual.get("axis_bindings", {})

#     # ── Table columns — y_axis Measure fields ────────────────
#     # display_name preferred; fallback to property
#     # table_columns = [
#     #     f.get("display_name") or f.get("property", "")
#     #     for f in axis.get("y_axis", [])
#     #     if f.get("field_type") == "Measure"
#     # ]
    

#     seen_cols = set()
#     table_columns = []
#     for f in axis.get("y_axis", []):
#         if f.get("field_type") != "Measure":
#            continue
#     # property preferred over display_name — clean name without suffix
#         name = f.get("property", "") or f.get("display_name", "")
#     # Trailing digits strip karo — "Eligible population1" -> "Eligible population"
#         name = re.sub(r'\d+\s*$', '', name).strip()
#         if name not in seen_cols:
#           seen_cols.add(name)
#           table_columns.append(name)

#     # ── Row dimension — rows axis_bindings ───────────────────
#     row_parts = [
#         f.get("property", "")
#         for f in axis.get("rows", [])
#     ]
#     row_dimension = " / ".join(row_parts)
#     row_dim_col_names = {
#     col_raw.split(".", 1)[-1]
#     for col_raw in visual.get("columns_used", [])
#     if "." in col_raw
#      }

#     # ── Primary measure — first y_axis Measure ───────────────
#     primary_measure = ""
#     primary_dax     = None
#     for f in axis.get("y_axis", []):
#         if f.get("field_type") == "Measure":
#             primary_measure = f.get("property", "").strip()
#             break

#     # ── Resolve all_dax from measures_used ───────────────────
#     all_dax   = []
#     missing_m = []

#     for raw in visual.get("measures_used", []):
#         entry = _resolve_measure(raw)
#         if entry is None:
#             missing_m.append(raw.split(".", 1)[-1].strip())
#             continue
#         entry.role = "primary" if entry.name == primary_measure else "other"
#         all_dax.append(entry)

#     if missing_m:
#         warnings.append(
#             f"table measures not in MEASURES_RESOLVED: {missing_m}"
#         )

#     primary_dax = next(
#         (d for d in all_dax if d.name == primary_measure), None
#     )
#     if primary_dax is None and primary_measure:
#         warnings.append(
#             f"primary measure '{primary_measure}' not resolved"
#         )

#     # ── All columns — deduplicated across all measures ────────
#     seen_cols   = set()
#     all_columns = []

#     for dax_entry in all_dax:
#         # Direct columns from this measure
#         for col in dax_entry.columns:
#             if col.raw not in seen_cols:
#                 seen_cols.add(col.raw)
#                 all_columns.append(col)
#         # Upstream dep columns (e.g. date[month_of_date] via YoY)
#         for dep_col_raw in _get_all_referenced_cols(dax_entry.name):
#             if dep_col_raw not in seen_cols:
#                 seen_cols.add(dep_col_raw)
#                 all_columns.append(_parse_column_ref(dep_col_raw))

#     # ── Row dimension columns — pcp table ────────────────────
#     # columns_used = ["pcp.practice_name", "pcp.pcp_name"]
#     for col_raw in visual.get("columns_used", []):
#         if "." in col_raw:
#             tbl, col = col_raw.split(".", 1)
#             fake_raw = f"{tbl}[{col}]"
#             if fake_raw not in seen_cols:
#                 seen_cols.add(fake_raw)
#                 all_columns.append(ColumnRef(
#                     table  = tbl,
#                     column = col,
#                     raw    = fake_raw
#                 ))

#     # ── Comparison — detect from column names ─────────────────
#     # If any column is a YoY or MoM change column -> note it
#     has_yoy = any("YoY" in c or "yoy" in c for c in table_columns)
#     has_mom = any("MoM" in c or "mom" in c for c in table_columns)

#     if has_yoy:
#         comparison = "YoY % change"
#     elif has_mom:
#         comparison = "MoM % change"
#     else:
#         comparison = "None"
    

#     # DEBUG — temporarily add karo
#     # print(f"\n  [DEBUG] {title} — filter_config with conditions:")
#     # for f in visual.get("filter_config", []):
#     #     if f.get("conditions"):
#     #       print(f"    field_type={f.get('field_type')} | property={f.get('property')}")
#     # ── Active filters ────────────────────────────────────────
#     # active_filters = [
#     #     f["property"]
#     #     for f in visual.get("filter_config", [])
#     #     if f.get("conditions")
#     # ]
#     active_filters = [
#         f["property"]
#         for f in visual.get("filter_config", [])
#         if f.get("conditions")
#         and f.get("field_type") == "Column"
#            ]

#     # ── Page visuals ──────────────────────────────────────────
#     page_visuals = [
#         PageVisual(
#             id       = v.get("id", ""),
#             title    = _fix_title(v),
#             type     = v.get("type", ""),
#             category = _categorise_visual(v)
#         )
#         for v in page_context.page_map.get(page, [])
#         if v.get("id") != vid
#     ]

#     return L0Packet(
#         visual_id       = vid,
#         title           = title,
#         visual_type     = vtype,
#         page            = page,
#         primary_measure = primary_measure,
#         primary_dax     = primary_dax,
#         all_dax         = all_dax,
#         paired_dax      = [],          # tables have no paired cards
#         comparison      = comparison,
#         active_filters  = active_filters,
#         all_columns     = all_columns,
#         page_visuals    = page_visuals,
#         peer_cards      = [],          # tables don't cross-read cards
#         glossary        = GLOSSARY,
#         warnings        = warnings,
#         is_table        = True,
#         table_columns   = table_columns,
#         row_dimension   = row_dimension,
#         row_dim_col_names = row_dim_col_names,
#         skip            = False,
#         skip_reason     = ""
#     )

def _build_scatter_l0_packet(
    visual      : dict,
    page_context: PageContext,
    vid         : str,
    vtype       : str,
    page        : str,
    title       : str,
    warnings    : list
) -> "L0Packet":
    axis = visual.get("axis_bindings", {})

    # ── Scatter category — Column field in x_axis ─────────────
    scatter_category = ""
    for f in axis.get("x_axis", []):
        if f.get("field_type") == "Column":
            scatter_category = f.get("display_name", "") or f.get("property", "")
            break

    # ── Bubble size — Measure field in size ───────────────────
    bubble_size = ""
    for f in axis.get("size", []):
        if f.get("field_type") == "Measure":
            bubble_size = f.get("property", "").strip()
            break

    # ── Primary measure — y_axis Measure ─────────────────────
    primary_measure = ""
    for f in axis.get("y_axis", []):
        if f.get("field_type") == "Measure":
            primary_measure = f.get("property", "").strip()
            break
    if not primary_measure:
        measures_used = visual.get("measures_used", [])
        primary_measure = (
            measures_used[0].split(".", 1)[-1].strip()
            if measures_used else ""
        )

    # ── Resolve all_dax ───────────────────────────────────────
    all_dax   = []
    missing_m = []
    for raw in visual.get("measures_used", []):
        entry = _resolve_measure(raw)
        if entry is None:
            missing_m.append(raw.split(".", 1)[-1].strip())
            continue
        entry.role = "primary" if entry.name == primary_measure else "other"
        all_dax.append(entry)

    if missing_m:
        warnings.append(f"scatter measures not in MEASURES_RESOLVED: {missing_m}")

    primary_dax = next(
        (d for d in all_dax if d.name == primary_measure), None
    )

    # ── All columns — deduplicated ────────────────────────────
    seen_cols   = set()
    all_columns = []
    for dax_entry in all_dax:
        for col in dax_entry.columns:
            if col.raw not in seen_cols:
                seen_cols.add(col.raw)
                all_columns.append(col)
        for dep_col_raw in _get_all_referenced_cols(dax_entry.name):
            if dep_col_raw not in seen_cols:
                seen_cols.add(dep_col_raw)
                all_columns.append(_parse_column_ref(dep_col_raw))

    for col_raw in visual.get("columns_used", []):
        if "." in col_raw:
            tbl, col = col_raw.split(".", 1)
            fake_raw = f"{tbl}[{col}]"
            if fake_raw not in seen_cols:
                seen_cols.add(fake_raw)
                all_columns.append(ColumnRef(table=tbl, column=col, raw=fake_raw))

    # ── Active filters — Column type with conditions only ─────
    active_filters = [
        f["property"]
        for f in visual.get("filter_config", [])
        if f.get("conditions") and f.get("field_type") == "Column"
    ]

    # ── Page visuals ──────────────────────────────────────────
    page_visuals = [
        PageVisual(
            id       = v.get("id", ""),
            title    = _fix_title(v),
            type     = v.get("type", ""),
            category = _categorise_visual(v)
        )
        for v in page_context.page_map.get(page, [])
        if v.get("id") != vid
    ]

    return L0Packet(
        visual_id         = vid,
        title             = title,
        visual_type       = vtype,
        page              = page,
        primary_measure   = primary_measure,
        primary_dax       = primary_dax,
        all_dax           = all_dax,
        paired_dax        = [],
        comparison        = "None",
        active_filters    = active_filters,
        all_columns       = all_columns,
        page_visuals      = page_visuals,
        peer_cards        = [],
        glossary          = GLOSSARY,
        warnings          = warnings,
        is_table          = False,
        table_columns     = [],
        row_dimension     = "",
        row_dim_col_names = set(),
        is_linechart      = False,
        chart_lines       = [],
        x_axis_col        = "",
        is_barchart       = False,
        bar_orientation   = "",
        category_axis     = "",
        tooltip_measures  = [],
        is_donut          = False,
        legend_col        = "",
        is_scatter        = True,
        bubble_size       = bubble_size,
        scatter_category  = scatter_category,
        skip              = False,
        skip_reason       = ""
    )


def _build_donut_l0_packet(
    visual      : dict,
    page_context: PageContext,
    vid         : str,
    vtype       : str,
    page        : str,
    title       : str,
    warnings    : list
) -> "L0Packet":
    axis = visual.get("axis_bindings", {})

    # ── Primary measure — y_axis Measure ─────────────────────
    primary_measure = ""
    for f in axis.get("y_axis", []):
        if f.get("field_type") == "Measure":
            primary_measure = f.get("property", "").strip()
            break

    # ── Legend column — x_axis Column ────────────────────────
    legend_col = ""
    for f in axis.get("x_axis", []):
        if f.get("field_type") == "Column":
            legend_col = f.get("display_name", "") or f.get("property", "")
            break

    # ── Resolve all_dax ───────────────────────────────────────
    all_dax   = []
    missing_m = []
    for raw in visual.get("measures_used", []):
        entry = _resolve_measure(raw)
        if entry is None:
            missing_m.append(raw.split(".", 1)[-1].strip())
            continue
        entry.role = "primary" if entry.name == primary_measure else "other"
        all_dax.append(entry)

    if missing_m:
        warnings.append(f"donut measures not in MEASURES_RESOLVED: {missing_m}")

    primary_dax = next(
        (d for d in all_dax if d.name == primary_measure), None
    )

    # ── All columns — deduplicated ────────────────────────────
    seen_cols   = set()
    all_columns = []
    for dax_entry in all_dax:
        for col in dax_entry.columns:
            if col.raw not in seen_cols:
                seen_cols.add(col.raw)
                all_columns.append(col)
        for dep_col_raw in _get_all_referenced_cols(dax_entry.name):
            if dep_col_raw not in seen_cols:
                seen_cols.add(dep_col_raw)
                all_columns.append(_parse_column_ref(dep_col_raw))

    for col_raw in visual.get("columns_used", []):
        if "." in col_raw:
            tbl, col = col_raw.split(".", 1)
            fake_raw = f"{tbl}[{col}]"
            if fake_raw not in seen_cols:
                seen_cols.add(fake_raw)
                all_columns.append(ColumnRef(table=tbl, column=col, raw=fake_raw))

    # ── Active filters — Column type with conditions only ─────
    active_filters = [
        f["property"]
        for f in visual.get("filter_config", [])
        if f.get("conditions") and f.get("field_type") == "Column"
    ]

    # ── Page visuals ──────────────────────────────────────────
    page_visuals = [
        PageVisual(
            id       = v.get("id", ""),
            title    = _fix_title(v),
            type     = v.get("type", ""),
            category = _categorise_visual(v)
        )
        for v in page_context.page_map.get(page, [])
        if v.get("id") != vid
    ]

    return L0Packet(
        visual_id         = vid,
        title             = title,
        visual_type       = vtype,
        page              = page,
        primary_measure   = primary_measure,
        primary_dax       = primary_dax,
        all_dax           = all_dax,
        paired_dax        = [],
        comparison        = "None",
        active_filters    = active_filters,
        all_columns       = all_columns,
        page_visuals      = page_visuals,
        peer_cards        = [],
        glossary          = GLOSSARY,
        warnings          = warnings,
        is_table          = False,
        table_columns     = [],
        row_dimension     = "",
        row_dim_col_names = set(),
        is_linechart      = False,
        chart_lines       = [],
        x_axis_col        = "",
        is_barchart       = False,
        bar_orientation   = "",
        category_axis     = "",
        tooltip_measures  = [],
        is_donut          = True,
        legend_col        = legend_col,
        is_scatter        = False,
        bubble_size       = "",
        scatter_category  = "",
        skip              = False,
        skip_reason       = ""
    )


def _build_barchart_l0_packet(
    visual      : dict,
    page_context: PageContext,
    vid         : str,
    vtype       : str,
    page        : str,
    title       : str,
    warnings    : list
) -> "L0Packet":
    axis = visual.get("axis_bindings", {})

    # ── Orientation — x_axis Column -> vertical, y_axis Column -> horizontal ──
    x_axis = axis.get("x_axis", [])
    y_axis = axis.get("y_axis", [])

    if any(f.get("field_type") == "Column" for f in x_axis):
        orientation = "vertical"
    elif any(f.get("field_type") == "Column" for f in y_axis):
        orientation = "horizontal"
    else:
        orientation = "vertical"

    # ── Category axis — display_name of the Column field ─────
    if orientation == "vertical":
        category_axis = next(
            (f.get("display_name", "") or f.get("property", "")
             for f in x_axis if f.get("field_type") == "Column"),
            ""
        )
    else:
        category_axis = next(
            (f.get("display_name", "") or f.get("property", "")
             for f in y_axis if f.get("field_type") == "Column"),
            ""
        )

    # ── Primary measure ───────────────────────────────────────
    if orientation == "vertical":
        primary_measure = next(
            (f.get("property", "") for f in y_axis
             if f.get("field_type") == "Measure"),
            ""
        )
    else:
        primary_measure = next(
            (f.get("property", "") for f in x_axis
             if f.get("field_type") == "Measure"),
            ""
        )
    if not primary_measure:
        measures_used = visual.get("measures_used", [])
        primary_measure = (
            measures_used[0].split(".", 1)[-1].strip()
            if measures_used else ""
        )

    # ── Tooltip measures ──────────────────────────────────────
    tooltip_measures = [
        {
            "measure":      f.get("property", ""),
            "display_name": f.get("display_name", "") or f.get("property", ""),
        }
        for f in axis.get("tooltip", [])
        if f.get("field_type") == "Measure"
    ]

    # ── Resolve all_dax from measures_used ───────────────────
    all_dax   = []
    missing_m = []

    for raw in visual.get("measures_used", []):
        entry = _resolve_measure(raw)
        if entry is None:
            missing_m.append(raw.split(".", 1)[-1].strip())
            continue
        entry.role = "primary" if entry.name == primary_measure else "other"
        all_dax.append(entry)

    if missing_m:
        warnings.append(
            f"barchart measures not in MEASURES_RESOLVED: {missing_m}"
        )

    primary_dax = next(
        (d for d in all_dax if d.name == primary_measure), None
    )

    # ── All columns — deduplicated ────────────────────────────
    seen_cols   = set()
    all_columns = []

    for dax_entry in all_dax:
        for col in dax_entry.columns:
            if col.raw not in seen_cols:
                seen_cols.add(col.raw)
                all_columns.append(col)
        for dep_col_raw in _get_all_referenced_cols(dax_entry.name):
            if dep_col_raw not in seen_cols:
                seen_cols.add(dep_col_raw)
                all_columns.append(_parse_column_ref(dep_col_raw))

    for col_raw in visual.get("columns_used", []):
        if "." in col_raw:
            tbl, col = col_raw.split(".", 1)
            fake_raw = f"{tbl}[{col}]"
            if fake_raw not in seen_cols:
                seen_cols.add(fake_raw)
                all_columns.append(ColumnRef(table=tbl, column=col, raw=fake_raw))

    # ── Comparison ────────────────────────────────────────────
    page_lower = page.lower()
    if "ly" in page_lower:
        comparison = "YoY % change"
    elif "lm" in page_lower:
        comparison = "MoM % change"
    else:
        comparison = "None"

    # ── Active filters — Column type with conditions only ─────
    active_filters = [
        f["property"]
        for f in visual.get("filter_config", [])
        if f.get("conditions") and f.get("field_type") == "Column"
    ]

    # ── Page visuals ──────────────────────────────────────────
    page_visuals = [
        PageVisual(
            id       = v.get("id", ""),
            title    = _fix_title(v),
            type     = v.get("type", ""),
            category = _categorise_visual(v)
        )
        for v in page_context.page_map.get(page, [])
        if v.get("id") != vid
    ]

    return L0Packet(
        visual_id         = vid,
        title             = title,
        visual_type       = vtype,
        page              = page,
        primary_measure   = primary_measure,
        primary_dax       = primary_dax,
        all_dax           = all_dax,
        paired_dax        = [],
        comparison        = comparison,
        active_filters    = active_filters,
        all_columns       = all_columns,
        page_visuals      = page_visuals,
        peer_cards        = [],
        glossary          = GLOSSARY,
        warnings          = warnings,
        is_table          = False,
        table_columns     = [],
        row_dimension     = "",
        row_dim_col_names = set(),
        is_linechart      = False,
        chart_lines       = [],
        x_axis_col        = "",
        is_barchart       = True,
        bar_orientation   = orientation,
        category_axis     = category_axis,
        tooltip_measures  = tooltip_measures,
        is_donut          = False,
        legend_col        = "",
        is_scatter        = False,
        bubble_size       = "",
        scatter_category  = "",
        skip              = False,
        skip_reason       = ""
    )


def _build_linechart_l0_packet(
    visual      : dict,
    page_context: PageContext,
    vid         : str,
    vtype       : str,
    page        : str,
    title       : str,
    warnings    : list
) -> "L0Packet":
    axis = visual.get("axis_bindings", {})

    # ── chart_lines — y_axis Measure fields ──────────────────
    chart_lines = []
    for f in axis.get("y_axis", []):
        if f.get("field_type") != "Measure":
            continue
        chart_lines.append({
            "measure":      f.get("property", ""),
            "display_name": f.get("display_name", "") or f.get("property", ""),
        })

    # ── x_axis_col — first x_axis Column field ───────────────
    x_axis_col = ""
    for f in axis.get("x_axis", []):
        if f.get("field_type") == "Column":
            x_axis_col = f.get("display_name", "") or f.get("property", "")
            break

    # ── Primary measure — first chart_line ───────────────────
    primary_measure = chart_lines[0]["measure"] if chart_lines else ""

    # ── Resolve all_dax from measures_used ───────────────────
    all_dax   = []
    missing_m = []

    for raw in visual.get("measures_used", []):
        entry = _resolve_measure(raw)
        if entry is None:
            missing_m.append(raw.split(".", 1)[-1].strip())
            continue
        entry.role = "primary" if entry.name == primary_measure else "other"
        all_dax.append(entry)

    if missing_m:
        warnings.append(
            f"linechart measures not in MEASURES_RESOLVED: {missing_m}"
        )

    primary_dax = next(
        (d for d in all_dax if d.name == primary_measure), None
    )

    # ── All columns — deduplicated across all measures ────────
    seen_cols   = set()
    all_columns = []

    for dax_entry in all_dax:
        for col in dax_entry.columns:
            if col.raw not in seen_cols:
                seen_cols.add(col.raw)
                all_columns.append(col)
        for dep_col_raw in _get_all_referenced_cols(dax_entry.name):
            if dep_col_raw not in seen_cols:
                seen_cols.add(dep_col_raw)
                all_columns.append(_parse_column_ref(dep_col_raw))

    for col_raw in visual.get("columns_used", []):
        if "." in col_raw:
            tbl, col = col_raw.split(".", 1)
            fake_raw = f"{tbl}[{col}]"
            if fake_raw not in seen_cols:
                seen_cols.add(fake_raw)
                all_columns.append(ColumnRef(table=tbl, column=col, raw=fake_raw))

    # ── Comparison — from page name ───────────────────────────
    page_lower = page.lower()
    if "ly" in page_lower:
        comparison = "YoY % change"
    elif "lm" in page_lower:
        comparison = "MoM % change"
    else:
        comparison = "None"

    # ── Active filters — Column type with conditions only ─────
    active_filters = [
        f["property"]
        for f in visual.get("filter_config", [])
        if f.get("conditions") and f.get("field_type") == "Column"
    ]

    # ── Page visuals ──────────────────────────────────────────
    page_visuals = [
        PageVisual(
            id       = v.get("id", ""),
            title    = _fix_title(v),
            type     = v.get("type", ""),
            category = _categorise_visual(v)
        )
        for v in page_context.page_map.get(page, [])
        if v.get("id") != vid
    ]

    return L0Packet(
        visual_id         = vid,
        title             = title,
        visual_type       = vtype,
        page              = page,
        primary_measure   = primary_measure,
        primary_dax       = primary_dax,
        all_dax           = all_dax,
        paired_dax        = [],
        comparison        = comparison,
        active_filters    = active_filters,
        all_columns       = all_columns,
        page_visuals      = page_visuals,
        peer_cards        = [],
        glossary          = GLOSSARY,
        warnings          = warnings,
        is_table          = False,
        table_columns     = [],
        row_dimension     = "",
        row_dim_col_names = set(),
        is_linechart      = True,
        chart_lines       = chart_lines,
        x_axis_col        = x_axis_col,
        is_barchart       = False,
        bar_orientation   = "",
        category_axis     = "",
        tooltip_measures  = [],
        is_donut          = False,
        legend_col        = "",
        is_scatter        = False,
        bubble_size       = "",
        scatter_category  = "",
        skip              = False,
        skip_reason       = ""
    )


def _build_table_l0_packet(
    visual      : dict,
    page_context: PageContext,
    vid         : str,
    vtype       : str,
    page        : str,
    title       : str,
    warnings    : list
) -> "L0Packet":
    axis = visual.get("axis_bindings", {})

    # ── Table columns — y_axis Measure fields ────────────────
    seen_cols = set()
    table_columns = []
    for f in axis.get("y_axis", []):
        if f.get("field_type") != "Measure":
            continue
        name = f.get("property", "") or f.get("display_name", "")
        name = re.sub(r'\d+\s*$', '', name).strip()
        if name not in seen_cols:
            seen_cols.add(name)
            table_columns.append(name)

    # ── Fallback — measures_used mein jo hain lekin y_axis mein nahi aaye ──
    y_axis_properties = {
        f.get("property", "")
        for f in axis.get("y_axis", [])
        if f.get("field_type") == "Measure"
    }
    seen_table_cols = set(table_columns)
    for raw in visual.get("measures_used", []):
        name = raw.split(".", 1)[-1].strip()
        name = re.sub(r'\d+\s*$', '', name).strip()
        if name not in seen_table_cols and name not in y_axis_properties:
            seen_table_cols.add(name)
            table_columns.append(name)

    # ── Row dimension — rows axis_bindings ───────────────────
    row_parts = [
        f.get("property", "")
        for f in axis.get("rows", [])
    ]
    row_dimension = " / ".join(row_parts)

    # ── Row dimension col names — dashboard-agnostic ─────────
    row_dim_col_names = {
        col_raw.split(".", 1)[-1]
        for col_raw in visual.get("columns_used", [])
        if "." in col_raw
    }

    # ── Primary measure — first y_axis Measure ───────────────
    primary_measure = ""
    primary_dax     = None
    for f in axis.get("y_axis", []):
        if f.get("field_type") == "Measure":
            primary_measure = f.get("property", "").strip()
            break

    # ── Resolve all_dax from measures_used ───────────────────
    all_dax   = []
    missing_m = []

    for raw in visual.get("measures_used", []):
        entry = _resolve_measure(raw)
        if entry is None:
            missing_m.append(raw.split(".", 1)[-1].strip())
            continue
        entry.role = "primary" if entry.name == primary_measure else "other"
        all_dax.append(entry)

    if missing_m:
        warnings.append(
            f"table measures not in MEASURES_RESOLVED: {missing_m}"
        )

    primary_dax = next(
        (d for d in all_dax if d.name == primary_measure), None
    )
    if primary_dax is None and primary_measure:
        warnings.append(
            f"primary measure '{primary_measure}' not resolved"
        )

    # ── All columns — deduplicated across all measures ────────
    seen_cols   = set()
    all_columns = []

    for dax_entry in all_dax:
        for col in dax_entry.columns:
            if col.raw not in seen_cols:
                seen_cols.add(col.raw)
                all_columns.append(col)
        for dep_col_raw in _get_all_referenced_cols(dax_entry.name):
            if dep_col_raw not in seen_cols:
                seen_cols.add(dep_col_raw)
                all_columns.append(_parse_column_ref(dep_col_raw))

    # ── Row dimension columns — from columns_used ────────────
    for col_raw in visual.get("columns_used", []):
        if "." in col_raw:
            tbl, col = col_raw.split(".", 1)
            fake_raw = f"{tbl}[{col}]"
            if fake_raw not in seen_cols:
                seen_cols.add(fake_raw)
                all_columns.append(ColumnRef(
                    table  = tbl,
                    column = col,
                    raw    = fake_raw
                ))

    # ── Comparison — detect from column names ─────────────────
    has_yoy = any("YoY" in c or "yoy" in c for c in table_columns)
    has_mom = any("MoM" in c or "mom" in c for c in table_columns)

    if has_yoy:
        comparison = "YoY % change"
    elif has_mom:
        comparison = "MoM % change"
    else:
        comparison = "None"

    # ── Active filters — Column type only ────────────────────
    active_filters = [
        f["property"]
        for f in visual.get("filter_config", [])
        if f.get("conditions")
        and f.get("field_type") == "Column"
    ]

    # ── Page visuals ──────────────────────────────────────────
    page_visuals = [
        PageVisual(
            id       = v.get("id", ""),
            title    = _fix_title(v),
            type     = v.get("type", ""),
            category = _categorise_visual(v)
        )
        for v in page_context.page_map.get(page, [])
        if v.get("id") != vid
    ]

    return L0Packet(
        visual_id         = vid,
        title             = title,
        visual_type       = vtype,
        page              = page,
        primary_measure   = primary_measure,
        primary_dax       = primary_dax,
        all_dax           = all_dax,
        paired_dax        = [],
        comparison        = comparison,
        active_filters    = active_filters,
        all_columns       = all_columns,
        page_visuals      = page_visuals,
        peer_cards        = [],
        glossary          = GLOSSARY,
        warnings          = warnings,
        is_table          = True,
        table_columns     = table_columns,
        row_dimension     = row_dimension,
        row_dim_col_names = row_dim_col_names,
        is_linechart      = False,
        chart_lines       = [],
        x_axis_col        = "",
        is_barchart       = False,
        bar_orientation   = "",
        category_axis     = "",
        tooltip_measures  = [],
        is_donut          = False,
        legend_col        = "",
        is_scatter        = False,
        bubble_size       = "",
        scatter_category  = "",
        skip              = False,
        skip_reason       = ""
    )
# ============================================================
# PRE-COMPUTE  — call ONCE before processing all visuals
# ============================================================

def build_page_context(all_visuals: list) -> PageContext:
    """
    Pre-compute all expensive lookups ONCE.

    Call this before the visual processing loop:
        ctx = build_page_context(all_visuals)
        for visual in visuals:
            l0 = build_l0_packet(visual, ctx)

    Complexity:
        build_page_context : O(N*M) — runs once
        build_l0_packet    : O(1)  lookups per visual
    """

    # ── 1. page_map ─────────────────────────────────────────
    # page_name -> list of visuals on that page (excl. SKIP_TYPES)
    page_map: dict = {}
    for v in all_visuals:
        if v.get("type") in SKIP_TYPES:
            continue
        page = v.get("page", "")
        if page not in page_map:
            page_map[page] = []
        page_map[page].append(v)

    # ── 2. pairing_cache — cardVisuals only ──────────────────
    pairing_cache: dict = {}
    # for v in all_visuals:
    #     if v.get("type") != "cardVisual":
    #         continue
    #     page  = v.get("page", "")
    #     multi, card = _find_paired_visuals(v, all_visuals, page)
    #     pairing_cache[v["id"]] = (multi, card)
    for v in all_visuals:
        if v.get("type") != "cardVisual":
            continue
        page     = v.get("page", "")
        measures = v.get("measures_used", [])
        pm       = measures[0].split(".", 1)[-1].strip() if measures else ""
        # Formatted wrapper strip karo pairing ke liye
        if pm.lower().startswith("formatted "):
            base = pm[len("formatted "):].strip()
            if base in MEASURES_RESOLVED:
                pm = base
        # print(f"    [pair-debug] id={v['id']} "
        #       f"| title={v.get('title', '?')} "
        #       f"| pairing_measure={pm}")
        multi, card = _find_paired_visuals(
            {**v, "_pairing_measure_override": pm},
            all_visuals, page
        )
        pairing_cache[v["id"]] = (multi, card)
    # ── 3. peer_cache — cardVisuals only ─────────────────────
    peer_cache: dict = {}
    for v in all_visuals:
        if v.get("type") != "cardVisual":
            continue
        measures = v.get("measures_used", [])
        if not measures:
            peer_cache[v["id"]] = []
            continue
        # primary = measures[0].split(".", 1)[-1].strip()
        # peer_cache[v["id"]] = _find_peer_cards(
        #     v, all_visuals, primary
        # )
        primary = measures[0].split(".", 1)[-1].strip()
        # Formatted wrapper strip karo
        if primary.lower().startswith("formatted "):
            base = primary[len("formatted "):].strip()
            if base in MEASURES_RESOLVED:
                primary = base
        peer_cache[v["id"]] = _find_peer_cards(
            v, all_visuals, primary
        )

    print(f"  [PageContext] pages={len(page_map)} "
          f"| paired={len(pairing_cache)} "
          f"| peers={len(peer_cache)}")

    return PageContext(
        page_map      = page_map,
        pairing_cache = pairing_cache,
        peer_cache    = peer_cache,
    )


# ============================================================
# MAIN — build_l0_packet
# ============================================================

def build_l0_packet(
    visual       : dict,
    page_context : PageContext
) -> L0Packet:
    """
    Entry point for Layer 0.
    Uses pre-computed PageContext — O(1) lookups only.

    Routing:
      TABLE_TYPES  -> _build_table_l0_packet()
      KPI_CARD_TYPES -> card path (existing logic)
    """
    warnings   = []
    vid        = visual.get("id", "unknown")
    vtype      = visual.get("type", "unknown")
    page       = visual.get("page", "")

    # ── 1. Title ────────────────────────────────────────────
    title = _fix_title(visual)

    # ── 2. Table routing — dedicated path ───────────────────
    if vtype in TABLE_TYPES:
        return _build_table_l0_packet(
            visual, page_context, vid, vtype, page, title, warnings
        )

    # ── 2b. LineChart routing — dedicated path ───────────────
    if vtype in TREND_TYPES:
        return _build_linechart_l0_packet(
            visual, page_context, vid, vtype, page, title, warnings
        )

    # ── 2c. DonutChart routing — dedicated path ──────────────
    if vtype in {"donutChart"}:
        return _build_donut_l0_packet(
            visual, page_context, vid, vtype, page, title, warnings
        )

    # ── 2e. ScatterChart routing — dedicated path ─────────────
    if vtype in {"scatterChart"}:
        return _build_scatter_l0_packet(
            visual, page_context, vid, vtype, page, title, warnings
        )

    # ── 2d. BarChart routing — dedicated path ────────────────
    if vtype in CHART_TYPES - {"donutChart"}:
        return _build_barchart_l0_packet(
            visual, page_context, vid, vtype, page, title, warnings
        )

    # ── 3. Primary measure from axis_bindings (card path) ───
    axis = visual.get("axis_bindings", {})
    primary_list = (
        axis.get("y_axis")   or
        axis.get("other")    or
        axis.get("x_axis")   or
        axis.get("rows")     or
        axis.get("columns")  or
        []
    )

    if not primary_list:
        return L0Packet(
            visual_id=vid, title=title, visual_type=vtype,
            page=page, primary_measure="", primary_dax=None,
            all_dax=[], paired_dax=[], comparison="None",
            active_filters=[], all_columns=[], page_visuals=[],
            peer_cards=[], glossary=GLOSSARY,
            warnings=["no axis_bindings found"],
            skip=True, skip_reason="no axis_bindings"
        )

    primary_field = primary_list[0]

    # Handle Column field_type — not a measure
    if primary_field.get("field_type") == "Column":
        measures_used = visual.get("measures_used", [])
        if measures_used:
            primary_field = {
                "property":   measures_used[0].split(".", 1)[-1].strip(),
                "field_type": "Measure",
                "table":      "unknown"
            }
            warnings.append(
                "primary field was Column — switched to first measures_used"
            )
        else:
            return L0Packet(
                visual_id=vid, title=title, visual_type=vtype,
                page=page, primary_measure="", primary_dax=None,
                all_dax=[], paired_dax=[], comparison="None",
                active_filters=[], all_columns=[], page_visuals=[],
                peer_cards=[], glossary=GLOSSARY,
                warnings=["only Column fields, no measures"],
                skip=True, skip_reason="no measures found"
            )

    # primary_measure = primary_field.get("property", "").strip()
    primary_measure = primary_field.get("property", "").strip()

# ── Formatted wrapper detect karo — base measure use karo pairing ke liye ──
# "Formatted Eligible population" -> "Eligible population"
    pairing_measure = primary_measure
    if primary_measure.lower().startswith("formatted "):
        base_name = primary_measure[len("formatted "):].strip()
    # base measure exists in MEASURES_RESOLVED?
        if base_name in MEASURES_RESOLVED:
           pairing_measure = base_name

    if not primary_measure:
        return L0Packet(
            visual_id=vid, title=title, visual_type=vtype,
            page=page, primary_measure="", primary_dax=None,
            all_dax=[], paired_dax=[], comparison="None",
            active_filters=[], all_columns=[], page_visuals=[],
            peer_cards=[], glossary=GLOSSARY,
            warnings=["empty primary measure name"],
            skip=True, skip_reason="empty primary measure"
        )

    # ── 4. Resolve all_dax (visual's own measures_used) ─────
    all_dax   = []
    missing_m = []

    for raw in visual.get("measures_used", []):
        entry = _resolve_measure(raw)
        if entry is None:
            missing_m.append(raw.split(".", 1)[-1].strip())
            continue
        entry.role = (
            "primary"
            if entry.name == primary_measure
            else _assign_dax_role(entry.name, page)
        )
        all_dax.append(entry)

    if missing_m:
        warnings.append(
            f"measures not found in MEASURES_RESOLVED: {missing_m}"
        )

    # Primary DaxEntry
    primary_dax = next(
        (d for d in all_dax if d.name == primary_measure),
        None
    )
    if primary_dax is None:
        warnings.append(
            f"primary measure '{primary_measure}' not resolved"
        )

    # ── 5. Paired visuals (multiRowCard + card) — O(1) ──────
    multi_visual, card_visual = page_context.pairing_cache.get(
        vid, (None, None)
    )

    paired_dax = []

    for pv in [multi_visual, card_visual]:
        if pv is None:
            continue
        for raw in pv.get("measures_used", []):
            entry = _resolve_measure(raw)
            if entry is None:
                warnings.append(
                    f"paired measure not found: "
                    f"{raw.split('.', 1)[-1].strip()}"
                )
                continue
            entry.role = _assign_dax_role(entry.name, page)
            paired_dax.append(entry)

    # ── 6. Comparison baseline ───────────────────────────────
    comparison = _detect_comparison(paired_dax, page, primary_measure)

    # ── 7. Active filters ────────────────────────────────────
    active_filters = [
        f["property"]
        for f in visual.get("filter_config", [])
        if f.get("conditions")
    ]

    # ── 8. All columns (deduplicated) ────────────────────────
    seen_cols   = set()
    all_columns = []

    for dax_entry in all_dax + paired_dax:
        for col in dax_entry.columns:
            if col.raw not in seen_cols:
                seen_cols.add(col.raw)
                all_columns.append(col)
        for dep_col_raw in _get_all_referenced_cols(dax_entry.name):
            if dep_col_raw not in seen_cols:
                seen_cols.add(dep_col_raw)
                all_columns.append(_parse_column_ref(dep_col_raw))

    # paired_dax empty — YoY/MoM Card columns add karo
    if primary_measure and MEASURES_RESOLVED:
        for suffix in ["YoY Card", "MoM Card"]:
            card_name  = f"{primary_measure} {suffix}"
            card_entry = MEASURES_RESOLVED.get(card_name)
            if not card_entry:
                continue
            for raw_col in card_entry.get("referenced_columns", []):
                if raw_col not in seen_cols:
                    seen_cols.add(raw_col)
                    all_columns.append(_parse_column_ref(raw_col))

    # ── 9. Page visuals — O(1) ───────────────────────────────
    page_visuals = []
    for v in page_context.page_map.get(page, []):
        if v.get("id") == vid:
            continue
        page_visuals.append(PageVisual(
            id       = v.get("id", ""),
            title    = _fix_title(v),
            type     = v.get("type", ""),
            category = _categorise_visual(v)
        ))

    # ── 10. Peer cards — O(1) ────────────────────────────────
    peer_cards = page_context.peer_cache.get(vid, [])

    # ── 11. Build packet ─────────────────────────────────────
    return L0Packet(
        visual_id       = vid,
        title           = title,
        visual_type     = vtype,
        page            = page,
        primary_measure = primary_measure,
        primary_dax     = primary_dax,
        all_dax         = all_dax,
        paired_dax      = paired_dax,
        comparison      = comparison,
        active_filters  = active_filters,
        all_columns     = all_columns,
        page_visuals    = page_visuals,
        peer_cards      = peer_cards,
        glossary        = GLOSSARY,
        warnings        = warnings,
        is_table        = False,
        table_columns   = [],
        row_dimension   = "",
        row_dim_col_names = set(),
        is_linechart    = False,
        chart_lines     = [],
        x_axis_col      = "",
        is_barchart      = False,
        bar_orientation  = "",
        category_axis    = "",
        tooltip_measures = [],
        is_donut         = False,
        legend_col       = "",
        is_scatter       = False,
        bubble_size      = "",
        scatter_category = "",
        skip            = False,
        skip_reason     = ""
    )


# ============================================================
# SERIALISER  (L0Packet -> plain dict for logging / Layer 1)
# ============================================================

def l0_to_dict(packet: L0Packet) -> dict:
    """Convert L0Packet dataclass to a plain JSON-serialisable dict."""

    def dax_to_dict(d: DaxEntry) -> dict:
        return {
            "name"   : d.name,
            "dax"    : d.dax,
            "columns": [{"table": c.table, "column": c.column,
                          "raw": c.raw} for c in d.columns],
            "deps"   : d.deps,
            "role"   : d.role
        }

    return {
        "visual_id"      : packet.visual_id,
        "title"          : packet.title,
        "visual_type"    : packet.visual_type,
        "page"           : packet.page,
        "primary_measure": packet.primary_measure,
        "primary_dax"    : dax_to_dict(packet.primary_dax)
                           if packet.primary_dax else None,
        "all_dax"        : [dax_to_dict(d) for d in packet.all_dax],
        "paired_dax"     : [dax_to_dict(d) for d in packet.paired_dax],
        "comparison"     : packet.comparison,
        "active_filters" : packet.active_filters,
        "all_columns"    : [{"table": c.table, "column": c.column,
                              "raw": c.raw}
                             for c in packet.all_columns],
        "page_visuals"   : [{"id": p.id, "title": p.title,
                              "type": p.type, "category": p.category}
                             for p in packet.page_visuals],
        "peer_cards"     : [{"title": p.title, "measures": p.measures}
                             for p in packet.peer_cards],
        "glossary"       : packet.glossary,
        # ── Table-specific ────────────────────────────────
        "is_table"       : packet.is_table,
        "table_columns"  : packet.table_columns,
        "row_dimension"  : packet.row_dimension,
        "row_dim_col_names" : list(packet.row_dim_col_names),
        # ── LineChart-specific ────────────────────────────
        "is_linechart"   : packet.is_linechart,
        "chart_lines"    : packet.chart_lines,
        "x_axis_col"     : packet.x_axis_col,
        # ── BarChart-specific ─────────────────────────────
        "is_barchart"      : packet.is_barchart,
        "bar_orientation"  : packet.bar_orientation,
        "category_axis"    : packet.category_axis,
        "tooltip_measures" : packet.tooltip_measures,
        # ── DonutChart-specific ───────────────────────────
        "is_donut"   : packet.is_donut,
        "legend_col" : packet.legend_col,
        # ── ScatterChart-specific ─────────────────────────
        "is_scatter"       : packet.is_scatter,
        "bubble_size"      : packet.bubble_size,
        "scatter_category" : packet.scatter_category,
        # ── Validation ────────────────────────────────────
        "warnings"       : packet.warnings,
        "skip"           : packet.skip,
        "skip_reason"    : packet.skip_reason
    }


# ============================================================
# SAVE  (L0Packet -> disk)
# ============================================================

L0_OUTPUT_DIR = str(_get_paths(_DASHBOARD).l0_packets_dir)


def save_l0_packet(packet: L0Packet, output_dir: str = L0_OUTPUT_DIR):
    """
    L0Packet ko JSON file mein save karo.
    Path: output/l0_packets/{visual_id}_{safe_title}.json
    Skip packets bhi save hote hain — debug ke liye.
    """
    import os
    os.makedirs(output_dir, exist_ok=True)

    safe_title = (
        packet.title
        .replace(" ", "_")
        .replace("%", "pct")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(":", "")
        .strip("_")
    )

    filename = f"{packet.visual_id}_{safe_title}.json"
    filepath = os.path.join(output_dir, filename)

    out = l0_to_dict(packet)

    # L0 JSON save disabled — uncomment to enable
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    status = "SKIP" if packet.skip else "OK"
    # print(f"  [L0-{status}] Saved: {filepath}")
    print(f"  [L0-{status}] {packet.title}")

    return filepath


# ============================================================
# DEBUG PRINTER
# ============================================================

def print_l0_packet(packet: L0Packet):
    print("\n" + "=" * 60)
    print(f"  L0 PACKET — {packet.title}")
    print("=" * 60)
    print(f"  id            : {packet.visual_id}")
    print(f"  type          : {packet.visual_type}")
    print(f"  page          : {packet.page}")
    print(f"  is_table      : {packet.is_table}")
    print(f"  skip          : {packet.skip}"
          + (f" ({packet.skip_reason})" if packet.skip else ""))

    if packet.warnings:
        print(f"\n  Warnings:")
        for w in packet.warnings:
            print(f"    ⚠ {w}")

    print(f"\n  primary_measure : {packet.primary_measure}")
    print(f"  comparison      : {packet.comparison}")
    print(f"  active_filters  : {packet.active_filters}")

    if packet.is_table:
        print(f"\n  table_columns ({len(packet.table_columns)}):")
        for c in packet.table_columns:
            print(f"    {c}")
        print(f"\n  row_dimension   : {packet.row_dimension}")
    else:
        print(f"\n  all_dax ({len(packet.all_dax)} measures):")
        for d in packet.all_dax:
            print(f"    [{d.role}] {d.name}")
            print(f"      DAX  : {d.dax[:80]}"
                  f"{'...' if len(d.dax) > 80 else ''}")
            print(f"      cols : {[c.raw for c in d.columns]}")
            print(f"      deps : {d.deps}")

        print(f"\n  paired_dax ({len(packet.paired_dax)} measures):")
        for d in packet.paired_dax:
            print(f"    [{d.role}] {d.name}")

    print(f"\n  all_columns ({len(packet.all_columns)}):")
    for c in packet.all_columns:
        print(f"    {c.table}.{c.column}")

    print(f"\n  page_visuals ({len(packet.page_visuals)}):")
    for p in packet.page_visuals:
        print(f"    [{p.category}] {p.title} ({p.type})")

    if not packet.is_table:
        print(f"\n  peer_cards ({len(packet.peer_cards)}):")
        for p in packet.peer_cards:
            print(f"    {p.title} -> {p.measures}")

    print("=" * 60 + "\n")


# ============================================================
# STANDALONE TEST
# ============================================================
 
if __name__ == "__main__":
    import sys
 
    json_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "../../output/visaul_enricher_pages/overview_ly.json"
    )
 
    print(f"Loading: {json_path}")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
 
    all_visuals = data["visuals"]
    print(f"Total visuals: {len(all_visuals)}")
 
    # ── Pre-compute ONCE ────────────────────────────────────
    print("\nBuilding page context...")
    ctx = build_page_context(all_visuals)
 
    # ── Test: first pivotTable only ─────────────────────────
    table_visuals = [
        v for v in all_visuals
        if v.get("type") in TABLE_TYPES
    ]
 
    if not table_visuals:
        print("No pivotTable / tableEx found in this JSON.")
        sys.exit(1)
 
    visual = table_visuals[0]
    print(f"\nTesting single pivotTable: [{visual['id']}] {visual.get('title','')}\n")
 
    packet = build_l0_packet(visual, ctx)
    print_l0_packet(packet)
    save_l0_packet(packet)
 