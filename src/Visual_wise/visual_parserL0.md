# visual_parserL0.py — L0 Pre-processor (No LLM)

## Purpose
Deterministic, no-LLM layer. Takes one enriched visual dict + a pre-computed `PageContext` and produces a fully structured `L0Packet` — the single input object consumed by L1, L2, and L3. Resolves primary measure, pairs YoY/MoM companion cards, detects comparison type, categorises page visuals, and finds peer cards for cross-read analysis.

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `visual` dict — one enriched visual from `enriched_pages/<page>.json` |
| **Input B** | `PageContext` — pre-computed page-level lookup built ONCE via `build_page_context()` |
| **Input C** | `measures_resolved.json` — loaded at module level as `MEASURES_RESOLVED` |
| **Input D** | `config/fixes.json` — `title_overrides`, `generic_titles`, `skip_types` |
| **Output** | `L0Packet` dataclass — structured, validated, ready for L1/L2/L3 |
| **Side effect** | `save_l0_packet()` writes `l0_packets/<page>/<id>.json` |

---

## Pipeline Steps

```
Step 1  build_page_context(all_visuals)    → PageContext  [called ONCE per page]
Step 2  [per visual] build_l0_packet(visual, page_context)
          a. fix_title
          b. resolve primary measure from axis_bindings
          c. find paired multiRowCard + card (YoY/MoM companions)
          d. resolve all_dax + paired_dax from MEASURES_RESOLVED
          e. detect comparison (YoY / MoM / None)
          f. parse active_filters
          g. parse all_columns → ColumnRef list
          h. build page_visuals + peer_cards from PageContext
          i. set visual-type-specific flags
          j. validate — skip if no primary measure
Step 3  save_l0_packet(l0)                → l0_packets/<page>/<id>.json
```

---

## Function Flow

```
build_page_context(all_visuals) → PageContext
  ├── page_map    : page_name → list of visual dicts (excl. SKIP_TYPES)
  ├── pairing_cache: visual_id → (multiRowCard_visual, card_visual)
  └── peer_cache  : visual_id → list[PeerCard]  (other cardVisuals, business-linked)

build_l0_packet(visual, page_context) → L0Packet
  ├── _fix_title(visual)
  │     ├── TITLE_OVERRIDES lookup
  │     ├── GENERIC_TITLES → fallback to measures_used[0]
  │     └── blank title → measures_used[0] or visual type
  ├── resolve primary measure
  │     ├── axis_bindings: y_axis → x_axis → other → rows → columns
  │     └── skip if no Measure field found
  ├── _find_paired_visuals(visual, all_visuals, page)
  │     ├── match multiRowCard by primary measure name substring
  │     ├── prefer YoY (LY page) or MoM (LM page) match
  │     └── match card by primary measure name
  ├── _resolve_measure(raw_name) [per measure in measures_used + paired]
  │     ├── strip table prefix
  │     ├── MEASURES_RESOLVED.get(name)
  │     └── parse ColumnRef list + deps list
  ├── _assign_dax_role(name, page)
  │     ├── "yoy card" in name → "yoy_card"
  │     ├── "mom card" in name → "mom_card"
  │     ├── "yoy color" in name → "yoy_color"
  │     ├── "mom color" in name → "mom_color"
  │     └── else → "primary"
  ├── _detect_comparison(paired_dax, page, primary_measure)
  │     ├── prefer LY/LM page suffix → YoY/MoM
  │     ├── check paired_dax roles for yoy_card / mom_card
  │     └── fallback: measures_resolved prefix match for "<primary> YoY Card"
  ├── parse active_filters from filter_config[].conditions
  ├── deduplicate all_columns from all_dax + paired_dax
  ├── set type-specific flags (is_table, is_linechart, is_barchart, is_donut, is_scatter)
  │     ├── table: parse table_columns from y_axis/rows display_names
  │     │          parse row_dimension from rows axis_binding
  │     ├── linechart: parse chart_lines, x_axis_col
  │     ├── barchart: detect orientation, category_axis, tooltip_measures
  │     ├── donut: parse legend_col
  │     └── scatter: parse bubble_size, scatter_category
  └── validate → skip if primary_measure empty

save_l0_packet(l0) → writes l0_packets/<page>/<id>.json
```

---

## Output Schema — `L0Packet`

```python
# Identity
visual_id       : str
title           : str
visual_type     : str          # "cardVisual" | "lineChart" | etc.
page            : str

# Primary measure
primary_measure : str
primary_dax     : DaxEntry     # name, dax, columns, deps, role

# All DAX (visual's own + companion cards)
all_dax         : list[DaxEntry]
paired_dax      : list[DaxEntry]   # multiRowCard + card measures

# Comparison
comparison      : str   # "YoY % change" | "MoM % change" | "None"

# Filters
active_filters  : list[str]

# Columns
all_columns     : list[ColumnRef]  # deduplicated across all measures

# Page context
page_visuals    : list[PageVisual]   # other visuals, categorised
peer_cards      : list[PeerCard]     # cross-read candidates
glossary        : dict

# Type-specific (False by default)
is_table / is_linechart / is_barchart / is_donut / is_scatter : bool
table_columns / row_dimension / chart_lines / x_axis_col
bar_orientation / category_axis / tooltip_measures
legend_col / bubble_size / scatter_category

# Validation
warnings        : list[str]
skip            : bool
skip_reason     : str
```

---

## Helper Functions

| Function | What it does |
|---|---|
| `_fix_title(visual)` | Override / generic / blank title resolution |
| `_parse_column_ref(raw)` | `"table[col]"` → `ColumnRef(table, column, raw)` |
| `_resolve_measure(raw_name)` | Look up one measure in `MEASURES_RESOLVED`, return `DaxEntry` |
| `_get_all_dep_names(name)` | Recursive upstream dependency name collector |
| `_get_all_referenced_cols(name)` | All columns through full dep tree |
| `_categorise_visual(visual)` | `"kpi_card"` \| `"trend"` \| `"table"` \| `"chart"` \| `"other"` |
| `_assign_dax_role(name, page)` | Name pattern → `"yoy_card"` / `"mom_card"` / etc. |
| `_detect_comparison(paired_dax, page, primary)` | Detect YoY/MoM baseline from paired measures + page name |
| `_find_paired_visuals(visual, all_visuals, page)` | Find companion multiRowCard + card by measure name match |
| `_find_peer_cards(visual, all_visuals, primary)` | Find other cardVisuals linked by shared columns or dep tree |

---

## File Connections

| Imports from | Used for |
|---|---|
| `utils/paths.py` | `get_paths(dashboard)` — output dir for l0_packets |
| `config/fixes.json` | `TITLE_OVERRIDES`, `GENERIC_TITLES`, `SKIP_TYPES` |
| `measures_resolved.json` | Loaded at module level as `MEASURES_RESOLVED` |

**Called by:** `visaul_pipeline_runner.py` Phase 1 (parallel, `L0_WORKERS=8`)

---

## Hardcoded Parts (Change for New Dashboards)

### `TITLE_OVERRIDES` / `GENERIC_TITLES` / `SKIP_TYPES` — from `fixes.json`
Not hardcoded in this file — loaded from `config/fixes.json`. Add new dashboard-specific title overrides and generic title strings there.

### `_assign_dax_role()` name patterns (line ~2214)
```python
if "yoy card" in n or ("yoy" in n and "card" in n):
    return "yoy_card"
if "mom card" in n or ("mom" in n and "card" in n):
    return "mom_card"
```
Matches measure names by substring. If a new dashboard uses different naming for YoY/MoM companion measures (e.g. `"YTD Change"` instead of `"YoY Card"`), add detection logic here.

### `_detect_comparison()` page suffix check (line ~2246)
```python
if "ly" in page_lower:
    preferred = "yoy"
elif "lm" in page_lower:
    preferred = "mom"
```
Assumes `*_ly` pages = YoY and `*_lm` pages = MoM. Update if new dashboard uses different page naming conventions.

### NOTE — file has large commented-out block (lines 1–2000)
The top ~2000 lines of this file are commented-out old implementation. The active code starts around line 2030. Do not confuse the two sections.
