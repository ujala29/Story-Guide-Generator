# word_generator — Pipeline Documentation

## Purpose
Converts all generated markdown outputs (dashboard overview, filters, page-wise story, visual-wise narratives, metric dictionary, FAQ, glossary) into a single formatted Word document (`.docx`). Runs after Stage 4. Two sequential steps: first build a `reference.docx` style template, then use `pypandoc` to assemble the full document against that template.

---

## Files in This Folder

| File | Role |
|---|---|
| `runner.py` | Entry point — runs Step 1 then Step 2 sequentially as subprocesses |
| `generate_reference_docx.py` | Step 1 — creates `output/reference.docx` with all Word paragraph styles (Heading 1–3, Code, Caption, Table styles, footer) |
| `generate_word_doc.py` | Step 2 — assembles all markdown sections, converts via `pypandoc`, post-processes table styling |

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `output/dashboards/<dash>/dashboard_overview/dashboard_overview.md` |
| **Input B** | `output/dashboards/<dash>/filter_section/global_filters.md` |
| **Input C** | `output/dashboards/<dash>/page_wise/page_wise_story.md` |
| **Input D** | `output/dashboards/<dash>/visual_wise/story_guide/<page>/<id>_<title>.md` — per-visual narratives |
| **Input E** | `output/dashboards/<dash>/metric_dictionary/metric_catalog.md` — first 10 rows shown |
| **Input F** | `output/dashboards/<dash>/glossary_faq/faq.md` |
| **Input G** | `output/dashboards/<dash>/glossary_faq/glossary.md` |
| **Input H** | `output/reference.docx` — style template (created by Step 1) |
| **Output** | `output/<dashboard>_story_guide.docx` — final formatted Word document |

---

## Pipeline Steps

```
Step 1   create_reference_doc()    → build output/reference.docx with all Word styles
Step 2   build_combined_md()       → assemble all section markdown in order
         style_tables()            → post-process table formatting in the generated .docx
```

---

## Function Flow

```
runner.py  main()
  ├── parse --dashboard arg (default: risk-dash)
  ├── [step 1] subprocess: generate_reference_docx.py
  │     └── create_reference_doc()
  │           ├── Document()  → new blank docx
  │           ├── set A4 page layout (21cm x 29.7cm, 1" margins)
  │           ├── style Normal    → Calibri 11pt, 1.15 line spacing
  │           ├── style Heading 1 → Calibri 16pt bold, black, bottom border
  │           ├── style Heading 2 → Calibri 12pt bold, black
  │           ├── style Heading 3 → Calibri 12pt bold, black
  │           ├── style List Paragraph → indented bullets
  │           ├── style Code      → Courier New 9pt, F5F5F5 background
  │           ├── style Caption   → Calibri 10pt italic, grey
  │           ├── style Table Paragraph → Calibri 10pt (pandoc body cells)
  │           ├── style Table Heading   → Calibri 10pt bold, white on #2E2E2E (pandoc header cells)
  │           ├── patch_table_grid_borders() → force CCCCCC borders on Table Grid style
  │           ├── footer → centered page number, top border
  │           ├── sample content (H1, H2, H3, Code, Table) so pandoc can see every style
  │           └── save output/reference.docx
  │
  └── [step 2] subprocess: generate_word_doc.py --dashboard <name>
        └── main()
              ├── build_combined_md(dashboard)
              │     ├── read dashboard_overview.md           → section 1
              │     ├── read global_filters.md               → section 2 (page break before)
              │     ├── read page_wise_story.md              → section 3 (page break before)
              │     ├── visual_wise/story_guide/             → section 4 (page break per page)
              │     │     ├── sort_pages()  → PAGE_ORDER first, then alphabetical
              │     │     └── sort_visuals() → card→trend→bar→table→donut→scatter order
              │     ├── build_metric_catalog_section()       → section 5 (first 10 rows + truncation note)
              │     ├── read faq.md                          → section 6 (page break before)
              │     └── read glossary.md                     → section 7 (page break before)
              ├── write combined markdown to temp .md file
              ├── check output .docx is not locked (open in Word)
              ├── pypandoc.convert_file(tmp.md → .docx, --standalone, --wrap=none, --reference-doc=reference.docx)
              └── style_tables(output_path)
                    └── for each table: full-width, autofit columns, alternating row bg, CCCCCC borders, cell padding, Calibri font
```

---

## Section Assembly Order (inside `build_combined_md`)

| # | Section | Source file | Page break |
|---|---|---|---|
| 1 | Dashboard at a Glance | `dashboard_overview/dashboard_overview.md` | No |
| 2 | Global Filters | `filter_section/global_filters.md` | Yes |
| 3 | Page-Wise Story | `page_wise/page_wise_story.md` | Yes |
| 4 | Visual-Wise (per page, per visual) | `visual_wise/story_guide/<page>/*.md` | Yes per page |
| 5 | Metric Dictionary | `metric_dictionary/metric_catalog.md` (first 10 rows) | Yes |
| 6 | FAQ | `glossary_faq/faq.md` | Yes |
| 7 | Glossary | `glossary_faq/glossary.md` | Yes |

---

## Word Styles Defined in `reference.docx`

| Style name | Font | Size | Notes |
|---|---|---|---|
| Normal | Calibri | 11pt | 1.15 line spacing, 6pt after |
| Heading 1 | Calibri bold | 16pt | Bottom border, 24pt before |
| Heading 2 | Calibri bold | 12pt | 12pt before |
| Heading 3 | Calibri bold | 12pt | 8pt before |
| List Paragraph | Calibri | 11pt | 0.5" left indent, -0.25" first line |
| Code | Courier New | 9pt | F5F5F5 background, 0.25" indent |
| Caption | Calibri italic | 10pt | Grey (#666666), 4pt before |
| Table Paragraph | Calibri | 10pt | Used by pandoc for table body cells |
| Table Heading | Calibri bold | 10pt | White text on #2E2E2E — used by pandoc for header row |

---

## File Connections

| Imports from | Used by | Purpose |
|---|---|---|
| `python-docx` | `generate_reference_docx.py`, `generate_word_doc.py` | Word document creation and post-processing |
| `pypandoc` | `generate_word_doc.py` | Markdown → .docx conversion |
| `output/reference.docx` | `generate_word_doc.py` | `--reference-doc` style template for pandoc |

**Called by:** `main.py` after Stage 4 completes (word generation is the final step)

---

## Hardcoded Parts (Change for New Dashboards)

### `PAGE_ORDER` — `generate_word_doc.py` (line ~23)
```python
PAGE_ORDER = [
    "overview_ly",
    "risk_capture_potential",
    "data_availability",
]
```
Controls which pages appear first in the Visual-Wise section. Pages not in this list appear after, sorted alphabetically. Add new dashboard page folder names here to control their order in the Word doc.

### `VISUAL_PRIORITY` — `generate_word_doc.py` (line ~29)
```python
VISUAL_PRIORITY = {
    "card": 1, "trend": 2, "line": 2,
    "bar": 3,  "column": 3,
    "table": 4, "matrix": 4,
    "donut": 5, "pie": 5,
}
```
Controls visual reading order within each page. Matched against the visual `.md` filename (lowercase). Visuals not matching any key get priority 999 (appear last). Update if a new dashboard introduces visual types with different ordering requirements.

### `MAX_METRIC_ROWS = 10` — `generate_word_doc.py` (line ~135)
Max rows shown from `metric_catalog.md` in the Metric Dictionary section. If truncated, a note directs readers to the full Excel catalog. Increase if more measures should be visible inline.

### `read_file()` — `**Widget:` → `##` conversion — `generate_word_doc.py` (line ~110)
```python
content = re.sub(
    r'^\*\*Widget:\s*(.+?)\*\*\s*$',
    r'## \1',
    content,
    flags=re.MULTILINE,
)
```
Converts `**Widget: Name**` bold labels (output format from `widget_group_writer_step3.py`) into proper `##` headings so pandoc renders them as Heading 2. If the widget label format ever changes, update this regex.
