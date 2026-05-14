# visual_parserL3_storymaking.py — L3 Story Writer (No LLM)

## Purpose
Final layer — assembles the full Story Guide markdown from structured L0 + L1 + L2 data. No LLM calls. Every field is code-injected from the packet dataclasses. Eliminates hallucination risk on fixed fields (DAX, comparison type, column names, drill steps). Handles all visual types: `cardVisual`, `lineChart`, `clusteredBarChart`, `donutChart`, `scatterChart`, `pivotTable`/`tableEx`.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `L0Packet` + `L1Packet` + `L2Packet` |
| **Output** | `L3Packet` with `markdown` field — full Story Guide section |
| **Side effect** | saves `story_guide/<page>/<id>_<title>.md` |

---

## Pipeline Steps

```
Step 1  call_layer3(l0, l1, l2, llm_client)
Step 2  branch on visual type → select builder function
Step 3  [builder] assemble markdown from structured data
          a. _fmt_dax()            → DAX block (color measures excluded)
          b. _fmt_columns()        → columns table with role annotations
          c. _fmt_filters()        → filter text
          d. _fmt_directional_rows() → directional impact table (cards/charts)
          e. _fmt_secondary()      → secondary metrics rows (if any)
          f. _fmt_key_patterns()   → combined cross-read table (cards/charts)
Step 4  save markdown to story_guide/<page>/<id>_<title>.md
```

---

## Function Flow

```
call_layer3(l0, l1, l2, llm_client) → L3Packet
  ├── if is_table:          _build_table_markdown(l0, l1, l2)
  ├── if is_linechart:      _build_linechart_markdown(l0, l1)
  ├── if is_barchart:       _build_barchart_markdown(l0, l1, l2)
  ├── if is_donut:          _build_donut_markdown(l0, l1, l2)
  ├── if is_scatter:        _build_scatter_markdown(l0, l1, l2)
  └── else (cardVisual):    _build_card_markdown(l0, l1, l2)

All builders call these formatters:
  _fmt_dax(all_dax, paired_dax)
    ├── exclude yoy_color / mom_color roles
    ├── include primary + yoy_card + mom_card from all_dax/paired_dax
    ├── fallback: measures_resolved prefix match for missing YoY/MoM Cards
    ├── include upstream leaf dep DAX
    └── sort: primary/dep → yoy_card → mom_card

  _fmt_columns(all_columns, row_dim_col_names=None)
    ├── role_map: column name → semantic role description
    ├── date table columns → "Time intelligence" role
    └── row_dim columns → "Row dimension" role

  _fmt_filters(active_filters)
    → "Responds to: year, month, payer" or "None — responds to global filters only"

  _fmt_directional_rows(rows)   → markdown table rows
  _fmt_secondary(all_dax, paired_dax, l1)  → secondary metric rows
  _fmt_key_patterns(cross_read_combined)   → combined multi-KPI table block
```

---

## Output Schema — `L3Packet`

```python
visual_id   : str
title       : str
page        : str
visual_type : str
markdown    : str   # full Story Guide section in markdown

warnings    : list[str]
skip        : bool
skip_reason : str
```

---

## Markdown Templates Per Visual Type

| Visual type | Builder | Key sections |
|---|---|---|
| `cardVisual` | `_build_card_markdown` | Definition, What it measures (primary metric, comparison, filters), Directional impact (3 rows), Drill order (5–6 steps), Technical spec (DAX, columns), Key patterns (cross-read table) |
| `pivotTable` / `tableEx` | `_build_table_markdown` | Definition, What it measures (multi-column), Column definitions + directional impact (per column), Key patterns to watch (4 rows), Technical spec (DAX, columns) |
| `lineChart` / `areaChart` | `_build_linechart_markdown` | Definition, What it measures (lines, x-axis, filters), How to read, Directional impact, Drill order, Technical spec |
| `clusteredBarChart` | `_build_barchart_markdown` | Definition, What it measures (orientation, category axis, tooltip measures), Directional impact, Drill order, Technical spec |
| `donutChart` | `_build_donut_markdown` | Definition, What it measures (legend/category, filters), Directional impact, Drill order, Technical spec |
| `scatterChart` | `_build_scatter_markdown` | Definition, What it measures (axes, bubble size, category), Directional impact, Drill order, Technical spec |

---

## Key Formatter Details

### `_fmt_dax()` — DAX fallback logic
If a visual's `all_dax` doesn't include a YoY/MoM Card measure (because the paired card was on a different page or not enriched), `_get_related_measures()` does a prefix match in `measures_resolved.json` to find `"<primary> YoY Card"` / `"<primary> MoM Card"` and adds them. Also includes upstream leaf dependency DAX blocks.

### `_fmt_columns()` — role annotation
Uses a `role_map` dict of column name substrings → semantic roles. Unknown columns get `"Source column — contributes to measure calculation"`. Date table columns auto-assigned `"Time intelligence"`.

### `_fmt_key_patterns()` — cross-read table
Builds a dynamic markdown table with `primary_kpi + partners` as column headers and `meaning` as the last column. Partners come from `L2Packet.cross_read_combined.partners` (max 3 selected by LLM).

---

## File Connections

| Imports from | Used for |
|---|---|
| `visual_parserL0` | `L0Packet`, `DaxEntry`, `ColumnRef`, `PageVisual`, `PeerCard` |
| `visaul_pareserL1` | `L1Packet` |
| `visual_parserL2` | `L2Packet`, `DirectionalRow`, `DrillStep`, `CrossReadCombined` |
| `utils/paths.py` | `get_paths(dashboard)` — story_guide output dir |
| `measures_resolved.json` | Loaded as `_MEASURES_RESOLVED` for DAX fallback lookup |

**Called by:** `visaul_pipeline_runner.py` Phase 4 (parallel, `MAX_WORKERS=3`)

---

## Hardcoded Parts (Change for New Dashboards)

### `role_map` in `_fmt_columns()` (line ~232)
```python
role_map = {
    "risk_value"         : "HCC risk weight — summed for numerator or denominator",
    "patient_count"      : "Patient/member count — used as denominator",
    "documentation_flag" : "Flag filter — restricts rows to specific documentation status",
    "month_of_date"      : "Time intelligence — drives YoY/MoM comparison",
    ...
}
```
Column name substring → semantic role. Specific to risk-dash column naming. Add new dashboard's column names here, otherwise those columns fall through to the generic `"Source column"` label.

### Screenshot placeholder text (in every builder)
```
> 📷 *Insert: Cropped screenshot of the {title} cardVisual*
```
Static placeholder text in every template. This is intentional — screenshots are inserted manually after generation.

### Drill-down end text (in `LAYER2_SYSTEM` — influences L3 output)
The last drill step text "For member-level detail — go to Patient List on the Risk Capture Potential page" is set by L2's system prompt, not L3. L3 just renders whatever L2 returned. To change this wording, update `LAYER2_SYSTEM` in `visual_parserL2.py`.

### `_get_related_measures()` prefix match (line ~133)
```python
if not name_lower.startswith(primary_lower):
    continue
suffix = name_lower[len(primary_lower):].strip()
if "yoy card" in suffix: role = "yoy_card"
elif "mom card" in suffix: role = "mom_card"
```
Finds companion measures by name prefix. If a new dashboard names companions differently (e.g. `"PAC PMPM — YoY"` instead of `"PAC PMPM YoY Card"`), update the suffix detection logic here.
