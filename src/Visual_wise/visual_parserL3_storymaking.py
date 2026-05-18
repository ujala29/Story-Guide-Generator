


"""
Layer 3 — Story Writer
=======================
Input  : L0Packet + L1Packet + L2Packet
Output : story_guide.md — saved to disk

No LLM call — markdown is built directly from structured data.
LLM hallucination on fixed fields (Comparison, DAX, columns)
eliminated completely.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_parserL0 import (
    L0Packet, DaxEntry, ColumnRef, PageVisual, PeerCard
)
from visaul_pareserL1 import L1Packet
from visual_parserL2 import (
    L2Packet, DirectionalRow, DrillStep, CrossReadCombined
)

# ============================================================
# CONFIG
# ============================================================

_HERE = Path(__file__).parent.resolve()

sys.path.insert(0, str(_HERE.parent))  # src/ — for paths.py
from paths import get_paths as _get_paths

_DASHBOARD    = os.environ.get("STORY_DASHBOARD", "risk-dash")
L3_OUTPUT_DIR = str(_get_paths(_DASHBOARD).story_guide_dir)

# ============================================================
# OUTPUT SCHEMA — L3Packet
# ============================================================

@dataclass
class L3Packet:
    """
    Layer 3 output — final markdown story guide.
    """
    visual_id   : str
    title       : str
    page        : str
    visual_type : str
    markdown    : str

    warnings    : list[str] = field(default_factory=list)
    skip        : bool      = False
    skip_reason : str       = ""


# ============================================================
# FORMATTERS — code builds each section, no LLM
# ============================================================
def _get_leaf_deps(measure_name: str, seen: set = None) -> list[str]:
    """
    Recursively get all upstream leaf measures
    that this measure depends on.
    e.g. "% members with open coding gaps"
      -> ["#Members", "Members with open coding gaps"]
    """
    if seen is None:
        seen = set()

    entry = _MEASURES_RESOLVED.get(measure_name, {})
    deps  = entry.get("depends_on", [])
    result = []

    for dep in deps:
        dep_name = dep if isinstance(dep, str) else dep.get("measure_name", "")
        if not dep_name or dep_name in seen:
            continue
        seen.add(dep_name)

        dep_entry = _MEASURES_RESOLVED.get(dep_name, {})
        dep_deps  = dep_entry.get("depends_on", [])

        if not dep_deps:
            # Leaf — no further deps
            result.append(dep_name)
        else:
            # Recurse deeper
            result.extend(_get_leaf_deps(dep_name, seen))

    return result

def _fmt_filters(active_filters: list[str]) -> str:
    if not active_filters:
        return "None — responds to global filters only"
    return "Responds to: " + ", ".join(active_filters)


# ── Load measures_resolved for full DAX lookup ───────────────
_RESOLVED_PATH = _get_paths(_DASHBOARD).measures_resolved
_MEASURES_RESOLVED: dict = {}

try:
    with open(_RESOLVED_PATH, encoding="utf-8") as _f:
        _MEASURES_RESOLVED = json.load(_f)
except FileNotFoundError:
    print(f"  [WARN] measures_resolved.json not found: {_RESOLVED_PATH}")
except json.JSONDecodeError as e:
    print(f"  [WARN] Malformed JSON in measures_resolved.json: {e}")


def _get_related_measures(primary_name: str) -> list[tuple[str, str, str]]:
    """
    measures_resolved.json se primary measure ke saare
    related measures nikalo:
      - YoY Card, MoM Card  ← include
      - Color, PY, PM, YoY, MoM (non-card)  ← exclude
      - Exact name match on prefix

    Returns: [(name, dax, role), ...]
    """
    # Roles to include in DAX section
    INCLUDE_ROLES = {"yoy_card", "mom_card"}

    primary_lower = primary_name.lower()
    results = []

    for measure_name, entry in _MEASURES_RESOLVED.items():
        if measure_name == primary_name:
            continue

        name_lower = measure_name.lower()

        # Must start with primary name (prefix match)
        if not name_lower.startswith(primary_lower):
            continue

        # Suffix after primary name
        suffix = name_lower[len(primary_lower):].strip()

        # Determine role from suffix
        if "yoy card" in suffix or suffix == "yoy card":
            role = "yoy_card"
        elif "mom card" in suffix or suffix == "mom card":
            role = "mom_card"
        elif "yoy color" in suffix or "color" in suffix:
            role = "yoy_color"
        elif "mom color" in suffix:
            role = "mom_color"
        else:
            continue   # PY, PM, YoY, MoM (non-card) — skip

        if role not in INCLUDE_ROLES:
            continue

        dax = entry.get("dax", "").strip()
        if dax:
            results.append((measure_name, dax, role))

    return results


def _clean_dax(dax: str) -> str:
    try:
        from Metric_dictionary.cleaner_step1 import clean as _full_clean
        return _full_clean("_", dax).clean_dax
    except Exception:
        import re
        return re.sub(r'\nlineageTag:\s*[a-f0-9\-]+', '', dax).strip()


def _fmt_dax(all_dax: list[DaxEntry], paired_dax: list[DaxEntry]) -> str:
    """
    All measures verbatim — color measures excluded.

    Strategy:
    1. all_dax + paired_dax se jo milta hai lo
    2. Agar YoY/MoM Card missing hai toh measures_resolved
       se primary name prefix match se dhundho
    """
    seen   = set()
    blocks = []

    # ── Step 1: all_dax + paired_dax ────────────────────────
    primary_name = None
    for entry in all_dax + paired_dax:
        if entry.name in seen:
            continue
        seen.add(entry.name)
        if entry.role in {"yoy_color", "mom_color"}:
            continue
        if entry.role == "primary":
            primary_name = entry.name
        blocks.append((entry.name, entry.dax, entry.role))

    # ── Step 2: measures_resolved se missing ones add karo ───
    if primary_name and _MEASURES_RESOLVED:

        # Step 2a: YoY Card / MoM Card
        related = _get_related_measures(primary_name)
        for name, dax, role in related:
            if name not in seen:
                seen.add(name)
                blocks.append((name, dax, role))

        # Step 2b: Upstream leaf deps ka DAX bhi include karo
        # e.g. "% members" depends on "#Members" and
        # "Members with open coding gaps" — include their DAX
        primary_entry = _MEASURES_RESOLVED.get(primary_name, {})
        leaf_deps = _get_leaf_deps(primary_name)
        for dep_name in leaf_deps:
            if dep_name not in seen:
                dep_entry = _MEASURES_RESOLVED.get(dep_name, {})
                dep_dax   = dep_entry.get("dax", "").strip()
                if dep_dax:
                    seen.add(dep_name)
                    blocks.append((dep_name, dep_dax, "dep"))

    # ── Build output — primary first, then cards ─────────────
    # Sort: primary/dep -> yoy_card -> mom_card -> other
    role_order = {"primary": 0, "yoy_card": 1, "mom_card": 2, "dep": 0, "other": 3}
    blocks.sort(key=lambda x: role_order.get(x[2], 3))

    lines = [f"**{name}** = {_clean_dax(dax)}" for name, dax, _ in blocks]
    return "\n\n".join(lines) if lines else "N/A"


def _fmt_columns(
    all_columns       : list[ColumnRef],
    row_dim_col_names : set = None
) -> str:
    """Column table rows — role from column name pattern."""
    if not all_columns:
        return "| unknown | unknown | No columns resolved |"

    role_map = {
        "risk_value"                    : "HCC risk weight — summed for numerator or denominator",
        "patient_count"                 : "Patient/member count — used as denominator",
        "member_count"                  : "Patient/member count — used as denominator",
        "documentation_flag"            : "Flag filter — restricts rows to specific documentation status",
        "recapture_numerator"           : "Numerator — gaps successfully closed",
        "recapture_denominator"         : "Denominator — total identified gaps",
        "suspect_numerator"             : "Numerator — suspected gaps closed",
        "suspect_denominator"           : "Denominator — total suspected gaps",
        "member_with_open_coding_gap"   : "Numerator — members with at least one open coding gap",
        "ytd_visit_amount"              : "Numerator — total YTD medical cost",
        "ytd_member_count"              : "Denominator — total YTD member count",
        "empi"                          : "Member identifier — distinct count for targeted patients",
        "month_of_date"                 : "Time intelligence — drives YoY/MoM comparison",
        "month_of_year"                 : "X-axis — groups data by calendar month",
        "month_of_year_num"             : "X-axis — groups data by calendar month",
        "x axis"                        : "Slicer table — drives X-axis metric selection",
        "y axis"                        : "Slicer table — drives Y-axis metric selection",
    }

    # rows = []
    # for col in all_columns:
    #     if col.table.strip("'\"") == "date":
    #         role = "Time intelligence — drives YoY/MoM comparison"
    #     else:
    #         col_lower = col.column.lower()
    #         role = next(
    #             (v for k, v in role_map.items() if k in col_lower),
    #             "Source column — contributes to measure calculation"
    #         )
    rows = []
    for col in all_columns:
        if col.table.strip("'\"") == "date":
            role = "Time intelligence — drives YoY/MoM comparison"
        elif row_dim_col_names and col.column in row_dim_col_names:
            role = "Row dimension — groups rows in the matrix"
        else:
            col_lower = col.column.lower()
            role = next(
                (v for k, v in role_map.items() if k in col_lower),
                "Source column — contributes to measure calculation"
            )
        # Clean table name — remove Power BI quotes e.g. "'date'" -> "date"
        clean_table = col.table.strip("'\"")
        rows.append(f"| {clean_table} | {col.column} | {role} |")
    return "\n".join(rows)


def _fmt_directional_rows(rows: list[DirectionalRow]) -> str:
    lines = [
        f"| {r.movement} | {r.signal} | {r.interpretation} |"
        for r in rows
    ]
    return "\n".join(lines) if lines else "| — | — | — |"


def _fmt_secondary(
    all_dax   : list[DaxEntry],
    paired_dax: list[DaxEntry],
    l1        : L1Packet
) -> str:
    """
    Secondary metrics row — measures that are not primary,
    not YoY/MoM cards, not color measures.
    Returns empty string if none exist.
    """
    seen = set()
    rows = []
    for entry in all_dax + paired_dax:
        if entry.name in seen:
            continue
        seen.add(entry.name)
        if entry.role in {"primary", "yoy_card", "mom_card",
                          "yoy_color", "mom_color"}:
            continue
        meaning = l1.measure_meanings.get(entry.name, "")
        if not meaning:
            continue
        rows.append(f"| Secondary metric | {entry.name} — {meaning} |")

    return "\n".join(rows) + "\n" if rows else ""


def _fmt_key_patterns(combined: "CrossReadCombined | None") -> str:
    """
    Single combined multi-KPI table.
    Returns empty string if no cross-read data.
    """
    if not combined or not combined.rows:
        return ""

    primary  = combined.primary_kpi
    partners = combined.partners
    all_cols = [primary] + partners

    header = " | ".join(all_cols + ["What it means"])
    sep    = " | ".join(["---"] * (len(all_cols) + 1))

    lines = [
        "**Key patterns:**",
        "",
        f"| {header} |",
        f"| {sep} |",
    ]

    for row in combined.rows:
        cells = [row.get(col, "—") for col in all_cols]
        cells.append(row.get("meaning", ""))
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)
def _build_table_markdown(
    l0: L0Packet,
    l1: L1Packet,
    l2: L2Packet
) -> str:
    """
    pivotTable story guide — exact template.
    No LLM. Every field code-injected.
    """
    filters_text = _fmt_filters(l1.active_filters)

    # ── Column definitions table ──────────────────────────
    col_def_rows = []
    for col_name in l0.table_columns:
        col_def = l1.column_definitions.get(col_name.strip(), {})
        defn    = col_def.get("definition", "—")
        inc     = col_def.get("increasing", "—")
        dec     = col_def.get("decreasing", "—")
        col_def_rows.append(
            f"| {col_name} | {defn} | {inc} | {dec} |"
        )
    col_def_md = "\n".join(col_def_rows) if col_def_rows \
                 else "| — | — | — | — |"

    # ── Key patterns block ────────────────────────────────
    if l2.key_patterns:
        kp_rows = "\n".join(
            f"| {row.get('pattern','—')} | {row.get('meaning','—')} |"
            for row in l2.key_patterns
        )
        key_patterns_block = (
            "**Key patterns to watch**\n\n"
            "| Pattern | What it means |\n"
            "|---|---|\n"
            f"{kp_rows}"
        )
    else:
        key_patterns_block = ""

    # ── DAX block ─────────────────────────────────────────
    dax_block = _fmt_dax(l0.all_dax, l0.paired_dax)

    # ── Columns table ─────────────────────────────────────
    # base_columns_md = _fmt_columns(l0.all_columns)
    base_columns_md = _fmt_columns(l0.all_columns, l0.row_dim_col_names)
    # pcp dimension rows add karo
    # pcp_rows = "\n".join([
    #     "| pcp | practice_name | Row dimension — groups metrics by practice |",
    #     "| pcp | pcp_name | Row dimension — groups metrics by individual PCP |",
    # ])
    # columns_md = base_columns_md + "\n" + pcp_rows
    columns_md = base_columns_md

    md = f"""**Widget: {l1.title} (Table)**

> 📷 *Insert: Cropped screenshot of the {l1.title} table*

**Definition**

{l1.one_line_definition}

**What it measures**

| Element | Description |
|---|---|
| Visual type | Matrix / table |
| Primary metric | Multiple — one per column |
| Comparison | {"YoY and MoM change columns embedded in the table" if l0.comparison != "None" else "None — current period values only, no time comparison"} |
| Visual-level filters | {filters_text} |

**Column definitions and directional impact**

| Column | Definition | ↑ Increasing | ↓ Decreasing |
|---|---|---|---|
{col_def_md}

{key_patterns_block}

**Technical specification**

**DAX measure(s):**

{dax_block}

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
{columns_md}"""

    return md.strip()

# ============================================================
# SKELETON BUILDER — final markdown, no LLM
# ============================================================

def _build_linechart_markdown(
    l0: L0Packet,
    l1: L1Packet
) -> str:
    filters_text = _fmt_filters(l1.active_filters)

    lines_str = ", ".join(
        l["display_name"] for l in l0.chart_lines
    ) or "Current year, Previous year"

    dax_block  = _fmt_dax(l0.all_dax, l0.paired_dax)
    columns_md = _fmt_columns(l0.all_columns)

    md = f"""**Widget: {l1.title} (lineChart)**

> 📷 *Insert: Cropped screenshot of the {l1.title} lineChart*

**Definition**

{l1.one_line_definition}

**What it measures**

| Element | Description |
|---|---|
| Visual type | Line chart |
| Lines | {lines_str} |
| X-axis | {l0.x_axis_col} |
| Comparison | {l0.comparison} |
| Visual-level filters | {filters_text} |

**How to read it**

{l1.result_meaning}

**Technical specification**

**DAX measure(s):**

{dax_block}

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
{columns_md}"""

    return md.strip()


def _build_barchart_markdown(
    l0: L0Packet,
    l1: L1Packet
) -> str:
    filters_text = _fmt_filters(l1.active_filters)
    dax_block    = _fmt_dax(l0.all_dax, l0.paired_dax)
    columns_md   = _fmt_columns(
        l0.all_columns, l0.row_dim_col_names
    )

    # Category column role override — dashboard-agnostic
    if l0.category_axis:
        cat_col_name = l0.category_axis.lower().replace(" ", "_")
        columns_lines = []
        for line in columns_md.split("\n"):
            if (cat_col_name in line.lower()
                    and "source column" in line.lower()):
                parts = line.split("|")
                if len(parts) >= 4:
                    parts[-2] = f" Category axis — groups bars by {l0.category_axis} "
                    line = "|".join(parts)
            columns_lines.append(line)
        columns_md = "\n".join(columns_lines)

    orientation = l0.bar_orientation.capitalize()

    tooltip_str = ", ".join(
        t["display_name"] for t in l0.tooltip_measures
    ) if l0.tooltip_measures else "None"

    dir_rows_md = "| — | — | — |"
    try:
        rows = json.loads(l1.result_meaning)
        if rows:
            dir_rows_md = "\n".join(
                f"| {r.get('movement','')} "
                f"| {r.get('signal','')} "
                f"| {r.get('interpretation','')} |"
                for r in rows
            )
    except (json.JSONDecodeError, TypeError):
        pass

    md = f"""**Widget: {l1.title} (Bar Chart)**

> 📷 *Insert: Cropped screenshot of the {l1.title} bar chart*

**Definition**

{l1.one_line_definition}

**What it measures**

| Element | Description |
|---|---|
| Visual type | {orientation} bar chart |
| Primary metric | {l0.primary_measure} |
| Category axis | {l0.category_axis} |
| Tooltip | {tooltip_str} |
| Comparison | {l0.comparison} |
| Visual-level filters | {filters_text} |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
{dir_rows_md}

**Technical specification**

**DAX measure(s):**

{dax_block}

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
{columns_md}"""

    return md.strip()


def _build_donut_markdown(l0: L0Packet, l1: L1Packet) -> str:
    filters_text = _fmt_filters(l1.active_filters)
    dax_block    = _fmt_dax(l0.all_dax, l0.paired_dax)
    columns_md   = _fmt_columns(l0.all_columns)

    # Legend column role override — match by non-measure dimension columns
    measure_col_raws = set()
    for dax_entry in l0.all_dax:
        for col in dax_entry.columns:
            measure_col_raws.add(col.raw)

    columns_lines = []
    for line in columns_md.split("\n"):
        for col in l0.all_columns:
            if (col.raw not in measure_col_raws
                    and col.table.strip("'\"") != "date"
                    and f"| {col.table} |" in line
                    and f"| {col.column} |" in line
                    and "source column" in line.lower()):
                parts = line.split("|")
                if len(parts) >= 4:
                    parts[-2] = f" Legend / category — {l0.legend_col} segments "
                    line = "|".join(parts)
                break
        columns_lines.append(line)
    columns_md = "\n".join(columns_lines)

    # Pattern rows from result_meaning
    pattern_rows_md = "| — | — |"
    try:
        rows = json.loads(l1.result_meaning)
        if rows:
            pattern_rows_md = "\n".join(
                f"| {r.get('pattern','')} | {r.get('interpretation','')} |"
                for r in rows
            )
    except (json.JSONDecodeError, TypeError):
        pass

    md = f"""**Widget: {l1.title} (Donut Chart)**

> 📷 *Insert: Cropped screenshot of the {l1.title} donut*

**Definition**

{l1.one_line_definition}

**What it measures**

| Element | Description |
|---|---|
| Visual type | Donut chart |
| Primary metric | {l0.primary_measure} |
| Legend | {l0.legend_col} |
| Comparison | {l0.comparison} |
| Visual-level filters | {filters_text} |

**How to read it**

| Pattern | Interpretation |
|---|---|
{pattern_rows_md}

**Technical specification**

**DAX measure(s):**

{dax_block}

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
{columns_md}"""

    return md.strip()


def _build_scatter_markdown(l0: L0Packet, l1: L1Packet) -> str:
    filters_text = _fmt_filters(l1.active_filters)
    # Clean scatter_category display
    cat_display = (
        l0.scatter_category
        .replace("_", " ")
        .title()
    )
    dax_block    = _fmt_dax(l0.all_dax, l0.paired_dax)
    columns_md   = _fmt_columns(l0.all_columns)

    # Category column role override
    if l0.scatter_category:
        measure_col_raws = set()
        for dax_entry in l0.all_dax:
            for col in dax_entry.columns:
                measure_col_raws.add(col.raw)
        columns_lines = []
        for line in columns_md.split("\n"):
            for col in l0.all_columns:
                if (col.raw not in measure_col_raws
                        and col.table.strip("'\"") != "date"
                        and f"| {col.table} |" in line
                        and f"| {col.column} |" in line
                        and "source column" in line.lower()):
                    parts = line.split("|")
                    if len(parts) >= 4:
                        parts[-2] = f" Data point identity — each bubble is one {cat_display} "
                        line = "|".join(parts)
                    break
            columns_lines.append(line)
        columns_md = "\n".join(columns_lines)

    # Position rows from result_meaning
    position_rows_md = "| — | — |"
    try:
        rows = json.loads(l1.result_meaning)
        if rows:
            position_rows_md = "\n".join(
                f"| {r.get('position','')} | {r.get('interpretation','')} |"
                for r in rows
            )
    except (json.JSONDecodeError, TypeError):
        pass

    md = f"""**Widget: {l1.title} (Scatter Plot)**

> 📷 *Insert: Cropped screenshot of the {l1.title} scatter plot*

**Definition**

{l1.one_line_definition}

**What it measures**

| Element | Description |
|---|---|
| Visual type | Scatter plot with configurable axes |
| Primary metric | Y-axis: {l0.primary_measure} (selectable via dropdown) |
| Secondary metric | X-axis: selectable via dropdown |
| Bubble size | {l0.bubble_size} — panel size |
| Category | {cat_display} — each bubble = one {cat_display} |
| Comparison | {l0.comparison} — point-in-time distribution |
| Visual-level filters | {filters_text} |

**How to read it**

| Position | Interpretation |
|---|---|
{position_rows_md}

**Technical specification**

**DAX measure(s):**

{dax_block}

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
{columns_md}"""

    return md.strip()


def build_markdown(
    l0: L0Packet,
    l1: L1Packet,
    l2: L2Packet
) -> str:
    if l0.is_table:
        return _build_table_markdown(l0, l1, l2)
    if l0.is_linechart:
        return _build_linechart_markdown(l0, l1)
    if l0.is_barchart:
        return _build_barchart_markdown(l0, l1)
    if l0.is_donut:
        return _build_donut_markdown(l0, l1)
    if l0.is_scatter:
        return _build_scatter_markdown(l0, l1)
    """
    Build complete markdown directly from structured data.
    Every field is code-injected — no LLM touch.
    """
    filters_text    = _fmt_filters(l1.active_filters)
    dax_block       = _fmt_dax(l0.all_dax, l0.paired_dax)
    columns_md      = _fmt_columns(l0.all_columns)
    dir_rows_md     = _fmt_directional_rows(l2.directional_rows)
    secondary_rows  = _fmt_secondary(l0.all_dax, l0.paired_dax, l1)
    key_patterns    = _fmt_key_patterns(l2.cross_read_combined)

    md = f"""**Widget: {l1.title} ({l1.visual_type})**

> 📷 *Insert: Cropped screenshot of the {l1.title} {l1.visual_type}*

**Definition**

{l1.one_line_definition}

**What it measures**

| Element | Description |
|---|---|
| Visual type | {l1.visual_type} |
| Primary metric | {l1.result_meaning} |
{secondary_rows}| Comparison | {l1.comparison} |
| Visual-level filters | {filters_text} |

**How to read it**

**Directional impact:**

| Movement | Signal | Interpretation |
|---|---|---|
{dir_rows_md}

**Technical specification**

**DAX measure(s):**

{dax_block}

**Tables and columns used:**

| Table | Column | Role |
|---|---|---|
{columns_md}"""

    if key_patterns:
        md += f"\n\n{key_patterns}"

    return md.strip()


# ============================================================
# VALIDATE
# ============================================================
def _validate(markdown: str, l1: L1Packet,
              is_table: bool = False,
              is_linechart: bool = False,
              is_barchart: bool = False,
              is_donut: bool = False,
              is_scatter: bool = False) -> list[str]:
    warnings = []

    # ── Common sections — both card and table ────────────
    required = [
        f"**Widget: {l1.title}",
        "**Definition**",
        "**What it measures**",
        "**Technical specification**",
        "**DAX measure(s):**",
        "**Tables and columns used:**",
    ]

    # ── How to read it — card + linechart, not table ──────
    if not is_table:
        required += [
            "**How to read it**",
        ]

    # ── Card-only sections (not table, not linechart, not barchart) ─
    if not is_table and not is_linechart and not is_barchart:
        required += [
            f"| Comparison | {l1.comparison} |",
        ]

    for section in required:
        if section not in markdown:
            warnings.append(f"Missing: '{section}'")

    # ── Directional rows count — card path only ───────────
    if not is_table and "**Directional impact:**" in markdown:
        start   = markdown.index("**Directional impact:**")
        chunk   = markdown[start:start + 800]
        dr_rows = [
            ln for ln in chunk.split("\n")
            if ln.strip().startswith("|")
            and "Movement" not in ln
            and "---" not in ln
        ]
        if len(dr_rows) != 3:
            warnings.append(
                f"Directional table has {len(dr_rows)} rows — expected 3"
            )

    return warnings


# ============================================================
# MAIN — call_layer3
# ============================================================

def call_layer3(
    l0: L0Packet,
    l1: L1Packet,
    l2: L2Packet,
    llm_client=None     # Not used — kept for API compatibility
) -> L3Packet:
    """
    Layer 3 entry point. No LLM call.

    Input  : L0Packet + L1Packet + L2Packet
    Output : L3Packet (markdown)
    """
    # ── Skip propagation ────────────────────────────────────
    if l0.skip or l1.skip or l2.skip:
        reason = (
            l0.skip_reason if l0.skip else
            l1.skip_reason if l1.skip else
            l2.skip_reason
        )
        packet = L3Packet(
            visual_id   = l0.visual_id,
            title       = l0.title,
            page        = l0.page,
            visual_type = l0.visual_type,
            markdown    = "",
            skip        = True,
            skip_reason = f"upstream_skipped: {reason}"
        )
        save_l3_packet(packet, l0)
        return packet

    # ── Build markdown directly from data ───────────────────
    markdown = build_markdown(l0, l1, l2)
    warnings = _validate(
        markdown, l1,
        is_table=l0.is_table,
        is_linechart=l0.is_linechart,
        is_barchart=l0.is_barchart,
        is_donut=l0.is_donut,
        is_scatter=l0.is_scatter
    )

    packet = L3Packet(
        visual_id   = l0.visual_id,
        title       = l1.title,
        page        = l0.page,
        visual_type = l0.visual_type,
        markdown    = markdown,
        warnings    = warnings,
        skip        = False,
        skip_reason = ""
    )

    # ── Save ─────────────────────────────────────────────────
    save_l3_packet(packet, l0)
    return packet


# ============================================================
# SAVE
# ============================================================

def save_l3_packet(
    packet     : L3Packet,
    l0         : "L0Packet" = None,
    output_dir : str = L3_OUTPUT_DIR
) -> str:
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

    page_subdir = (
        packet.page
        .lower()
        .replace(" ", "_")
        .strip("_")
    ) if packet.page else "unknown_page"

    page_output_dir = os.path.join(output_dir, page_subdir)
    os.makedirs(page_output_dir, exist_ok=True)

    # Visual type suffix add karo — same title conflicts avoid karo
    type_suffix_map = {
        "cardVisual"        : "card",
        "lineChart"         : "trend",
        "areaChart"         : "trend",
        "clusteredBarChart" : "bar",
        "barChart"          : "bar",
        "columnChart"       : "bar",
        "donutChart"        : "donut",
        "scatterChart"      : "scatter",
        "pivotTable"        : "table",
        "tableEx"           : "table",
    }
    vtype = l0.visual_type if l0 else ""
    type_suffix = type_suffix_map.get(vtype, "")
    if type_suffix:
        filename = f"{safe_title}_{type_suffix}.md"
    else:
        filename = f"{safe_title}.md"
    filepath = os.path.join(page_output_dir, filename)

    content = packet.markdown if not packet.skip else (
        f"# SKIPPED — {packet.title}\nReason: {packet.skip_reason}\n"
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    status = "SKIP" if packet.skip else "OK"
    print(f"  [L3-{status}] Saved: {filepath}")
    return filepath


# ============================================================
# SERIALISER
# ============================================================

def l3_to_dict(packet: L3Packet) -> dict:
    return {
        "visual_id"  : packet.visual_id,
        "title"      : packet.title,
        "page"       : packet.page,
        "markdown"   : packet.markdown,
        "warnings"   : packet.warnings,
        "skip"       : packet.skip,
        "skip_reason": packet.skip_reason
    }


# ============================================================
# DEBUG PRINTER
# ============================================================

def print_l3_packet(packet: L3Packet):
    print("\n" + "=" * 60)
    print(f"  L3 PACKET — {packet.title}")
    print("=" * 60)
    print(f"  visual_id : {packet.visual_id}")
    print(f"  page      : {packet.page}")
    print(f"  skip      : {packet.skip}"
          + (f" ({packet.skip_reason})" if packet.skip else ""))

    if packet.warnings:
        print(f"\n  Warnings ({len(packet.warnings)}):")
        for w in packet.warnings:
            print(f"    ⚠  {w}")

    if packet.skip:
        print("=" * 60 + "\n")
        return

    print(f"\n  Preview (first 500 chars):")
    print("-" * 40)
    print(packet.markdown[:500])
    print("-" * 40)
    print(f"  Total chars : {len(packet.markdown)}")
    print("=" * 60 + "\n")


# ============================================================
# STANDALONE — run from saved L0/L1/L2 packets
# ============================================================

if __name__ == "__main__":

    l0_dir = _get_paths(_DASHBOARD).l0_packets_dir
    l1_dir = _get_paths(_DASHBOARD).l1_packets_dir
    l2_dir = _get_paths(_DASHBOARD).l2_packets_dir

    l0_files = sorted(l0_dir.glob("*.json"))
    l1_files = sorted(l1_dir.glob("*.json"))
    l2_files = sorted(l2_dir.glob("*.json"))

    if not l0_files:
        print(f"No L0 packets: {l0_dir}"); sys.exit(1)
    if not l1_files:
        print(f"No L1 packets: {l1_dir}"); sys.exit(1)
    if not l2_files:
        print(f"No L2 packets: {l2_dir}"); sys.exit(1)

    print("=" * 60)
    print(f"  Layer 3 — Story Writer (no LLM)")
    print(f"  L0: {len(l0_files)}  L1: {len(l1_files)}  L2: {len(l2_files)}")
    print(f"  Output: {L3_OUTPUT_DIR}")
    print("=" * 60)

    # ── Reconstruction helpers ───────────────────────────────

    def _dax(x):
        return DaxEntry(
            name    = x["name"],
            dax     = x["dax"],
            columns = [ColumnRef(table=c["table"],
                                  column=c["column"],
                                  raw=c["raw"])
                       for c in x.get("columns", [])],
            deps    = x.get("deps", []),
            role    = x.get("role", "other"),
        )

    def _l0(d):
        return L0Packet(
            visual_id       = d["visual_id"],
            title           = d["title"],
            visual_type     = d["visual_type"],
            page            = d["page"],
            primary_measure = d["primary_measure"],
            primary_dax     = _dax(d["primary_dax"]) if d.get("primary_dax") else None,
            all_dax         = [_dax(x) for x in d.get("all_dax", [])],
            paired_dax      = [_dax(x) for x in d.get("paired_dax", [])],
            comparison      = d.get("comparison", "None"),
            active_filters  = d.get("active_filters", []),
            all_columns     = [ColumnRef(table=c["table"],
                                          column=c["column"],
                                          raw=c["raw"])
                                for c in d.get("all_columns", [])],
            page_visuals    = [PageVisual(id=p["id"], title=p["title"],
                                           type=p["type"], category=p["category"])
                               for p in d.get("page_visuals", [])],
            peer_cards      = [PeerCard(title=p["title"],
                                         measures=p["measures"])
                               for p in d.get("peer_cards", [])],
            glossary        = d.get("glossary", {}),
            warnings        = d.get("warnings", []),
            skip            = d.get("skip", False),
            skip_reason     = d.get("skip_reason", ""),
            is_table      = d.get("is_table", False),
            table_columns = d.get("table_columns", []),
            row_dimension = d.get("row_dimension", ""),
        )

    def _l1(d):
        return L1Packet(
            visual_id           = d["visual_id"],
            title               = d["title"],
            visual_type         = d["visual_type"],
            page                = d["page"],
            comparison          = d.get("comparison", "None"),
            active_filters      = d.get("active_filters", []),
            one_line_definition = d.get("one_line_definition", ""),
            numerator_meaning   = d.get("numerator_meaning", ""),
            denominator_meaning = d.get("denominator_meaning", ""),
            result_meaning      = d.get("result_meaning", ""),
            scope_note          = d.get("scope_note", ""),
            direction           = d.get("direction", ""),
            metric_type         = d.get("metric_type", ""),
            measure_meanings    = d.get("measure_meanings", {}),
            warnings            = d.get("warnings", []),
            skip                = d.get("skip", False),
            skip_reason         = d.get("skip_reason", ""),
        )

    def _l2(d):
        # cross_read_combined
        crc_raw = d.get("cross_read_combined")
        crc = None
        if crc_raw and isinstance(crc_raw, dict):
            crc = CrossReadCombined(
                primary_kpi = crc_raw.get("primary_kpi", ""),
                partners    = crc_raw.get("partners", []),
                rows        = crc_raw.get("rows", []),
            )
        return L2Packet(
            visual_id           = d["visual_id"],
            title               = d["title"],
            visual_type         = d["visual_type"],
            page                = d["page"],
            comparison          = d.get("comparison", "None"),
            active_filters      = d.get("active_filters", []),
            directional_rows    = [
                DirectionalRow(
                    movement       = r["movement"],
                    signal         = r["signal"],
                    interpretation = r["interpretation"],
                ) for r in d.get("directional_rows", [])
            ],
            drill_steps         = [
                DrillStep(
                    step        = s["step"],
                    visual_name = s["visual_name"],
                    question    = s["question"],
                ) for s in d.get("drill_steps", [])
            ],
            cross_read_combined = crc,
            warnings            = d.get("warnings", []),
            skip                = d.get("skip", False),
            skip_reason         = d.get("skip_reason", ""),
            is_table     = d.get("is_table", False),
            key_patterns = d.get("key_patterns", []),
        )

    # ── Load all packets ─────────────────────────────────────

    def _load(files, fn):
        m = {}
        for fp in files:
            with open(fp, encoding="utf-8") as f:
                d = json.load(f)
            m[d["visual_id"]] = fn(d)
        return m

    l0_map = _load(l0_files, _l0)
    l1_map = _load(l1_files, _l1)
    l2_map = _load(l2_files, _l2)

    matched   = sorted(set(l0_map) & set(l1_map) & set(l2_map))
    unmatched = sorted(set(l0_map) - set(l1_map) - set(l2_map))

    if unmatched:
        print(f"\n  Skipping {len(unmatched)} — missing L1/L2:")
        for vid in unmatched:
            print(f"    - {l0_map[vid].title}")

    print(f"\n  Processing {len(matched)} visuals...\n")

    ok = skip = err = 0

    for vid in matched:
        print(f"-> {l0_map[vid].title}")
        try:
            l3 = call_layer3(l0_map[vid], l1_map[vid], l2_map[vid])
            print_l3_packet(l3)
            if l3.skip: skip += 1
            else:        ok   += 1
        except Exception as e:
            import traceback
            print(f"  [ERROR] {e}")
            traceback.print_exc()
            err += 1

    print("\n" + "=" * 60)
    print(f"  Done — OK: {ok}  Skipped: {skip}  Errors: {err}")
    print(f"  Output -> {L3_OUTPUT_DIR}")
    print("=" * 60)