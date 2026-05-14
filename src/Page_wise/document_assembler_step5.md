# document_assembler_step5.py — Step 5: Document Assembler

## Purpose
**No LLM calls.** Pure Python markdown rendering. Reads all Stage 3 JSON outputs and assembles `page_wise_story.md` following the exact PDF template structure: title, about-this-guide, per-page layers, funnel connection table, cross-page patterns, closing paragraph, and footer.

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `page_wise/funnel_map.json` — page/widget structure + funnel questions |
| **Input B** | `page_wise/widget_content/*.json` — LLM-generated widget content |
| **Input C** | `page_wise/funnel_connector.json` — funnel table + closing paragraph |
| **Output** | `page_wise/page_wise_story.md` |

---

## Document Structure Produced

```
# [Dashboard Name] — Story Guide
Dashboard | Pages | Last updated

## About this guide
  [domain_context]
  The funnel: • Top → ... • Middle → ... • Bottom → ... • Action → ...

## Page 1: Overview
  ## Layer 1: The risk position
    ### [Widget name]
      📷 Insert: Screenshot of ...
      [group_intro]
      ### [Metric]
      [definition]
      | Direction | Interpretation |
      *italic callout*
    ### Reading the cards together
      | Pattern | Interpretation |

  ## Layer 2: The diagnosis
    ...

  ## Layer 3: The action
    ...

## Page 2: Risk capture potential
  [action_q intro]
  ### [Widget name]
  ...

## Page N: Overview  (mirror page — one-line note)
  > *This page shows same metrics with different comparison period...*

## How the funnel connects
  | Layer | Section | Question it answers |
  ### Reading across pages
  | Pattern | Interpretation |
  [closing_paragraph]

footer
```

---

## Function Flow

```
main()
  └── assemble(dashboard, root)
        ├── load: funnel_map.json, funnel_connector.json
        ├── load all widget_content/*.json → widget_lookup: {widget_id → content}
        ├── build pages list from funnel_map._meta.pages_processed + pages_mirrored
        │
        ├── render title block + About this guide
        │
        ├── for each page in pages_processed:
        │     for each widget (sorted by reading_order):
        │       if first widget in new funnel_position layer → emit Layer heading
        │       render_widget(widget_content)
        │         └── dispatch to render_* function by widget_type
        │
        ├── for each mirror page: emit one-line note
        │
        └── render How the funnel connects + cross_page_patterns + closing_paragraph + footer
```

---

## Function Details

### `assemble(dashboard, root) → str`
Main assembler. Builds a `doc` list of markdown strings, then joins with `"\n"`. Handles action pages (no layer headings — just widgets inline). Deduplicates page display names for the header line (LY + LM both → "Overview").

### `display_name(page_name) → str`
Local helper (same logic as `funnel_mapper.py`'s `get_page_base_name()`). Strips trailing time-period suffix for display: `"Overview LY"` → `"Overview"`.

### `render_widget(content) → str`
Dispatcher. Checks `status` (NOT_IMPLEMENTED / ERROR → renders warning placeholder). Looks up `widget_type` in `RENDERERS` dict.

### Widget renderers — one per type

| Function | Output structure |
|---|---|
| `render_kpi_card_row(w)` | H3 widget name, screenshot, group_intro, per-metric: definition + direction table + italic_callout, Reading cards together patterns table |
| `render_trend_lines(w)` | H3 widget name, screenshot, group_intro, per chart: definition + patterns table + italic_callout |
| `render_detail_table(w)` | H3 widget name, screenshot, group_intro, then either SEGMENT_FOCUSED (Status/Expected/Red flag table) or COLUMN_FOCUSED (Key columns table + Critical patterns table) |
| `render_clinical_pair(w)` | H3 widget name, screenshot, group_intro, bar chart: definition + patterns table, detail table: column table, italic_callout |
| `render_entity_scatter(w)` | H3 widget name, screenshot, group_intro, entity table: definition + key columns + reading patterns, scatter plot: definition + position table |
| `render_multi_chart(w)` | H3 widget name, screenshot, group_intro, per chart: definition + segment table |
| `render_action_table(w)` | H3 widget name, screenshot, group_intro, optional bar chart, column table, italic_callout |
| `render_segmentation(w)` | H3 widget name, screenshot, group_intro, per chart: definition + segment table with outreach_action column |

### `md_table(headers, rows) → str`
Renders a GitHub-flavored markdown table. Computes column widths dynamically. Handles empty rows gracefully.

### `screenshot(label) → str`
Returns a blockquote italic placeholder: `> *📷 Insert: Screenshot of ...*`

---

## `LAYER_LABELS` mapping

```python
LAYER_LABELS = {
    "TOP":    ("Layer 1", "The risk position"),
    "MIDDLE": ("Layer 2", "The diagnosis"),
    "BOTTOM": ("Layer 3", "The action"),
}
```
Layer headings in the final document. ACTION pages use no layer headings.

---

## File Connections

**No imports from other Page_wise files.** Pure stdlib + json + datetime.

**Called by:** `runner.py` (Step 5, as subprocess)

**Input from:** `funnel_mapper_step1.py` (funnel_map), `widget_group_writer_step3.py` (widget_content), `funnel_connector_step4.py` (funnel_connector)

---

## Hardcoded Parts (Change for New Dashboards)

### `LAYER_LABELS` (line ~505)
```python
LAYER_LABELS = {
    "TOP":    ("Layer 1", "The risk position"),
    "MIDDLE": ("Layer 2", "The diagnosis"),
    "BOTTOM": ("Layer 3", "The action"),
}
```
Layer names `"The risk position"`, `"The diagnosis"`, `"The action"` are **risk-dash specific** narrative labels. For a new domain, update these to match the business vocabulary.

### `TIME_SUFFIXES` inside `assemble()` (line ~547)
```python
TIME_SUFFIXES = {
    "ly","lm","ytd","mtd","qtd","q1","q2","q3","q4", ...
}
```
Same suffix set as `funnel_mapper_step1.py`. Must be kept in sync if time-period naming conventions change.

### Footer text (line ~689)
```python
"*Generated by Story Guide Generator | "
"For metric definitions or SQL queries, query the L5 Knowledge Base*\n"
```
References `"L5 Knowledge Base"` — Innovaccer-specific. Update for other organizations.

### `render_segmentation()` — outreach_action column (line ~453)
```python
headers = ["Segment", "Interpretation", "Suggested outreach action"]
```
The "Suggested outreach action" column is specific to the healthcare outreach use case. For non-healthcare dashboards using `SEGMENTATION` widgets, update this header.

### `render_detail_table()` — table format types (line ~247)
```python
if w.get("table_format") == "SEGMENT_FOCUSED":
    headers = ["Status", "Expected behavior", "Red flag"]
else:
    # COLUMN_FOCUSED
```
The `SEGMENT_FOCUSED` variant with `"Status"`, `"Expected behavior"`, `"Red flag"` columns is specific to risk model / attribution status tables. For new domains with different table analysis needs, the widget processor (detail_table_processor.py) and this renderer must be updated together.
