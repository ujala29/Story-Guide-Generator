# Work Report — Story Guide Generator
**Period:** Last 3 Weeks | **Author:** Ujala Gupta | **Date:** 11 May 2026
**Project:** Automated Story Guide Generator for Power BI Dashboards

---

## 1. Project Overview

Built and stabilized an end-to-end pipeline that converts a Power BI dashboard (`.pbix`) into a structured **Story Guide** — a Word/PDF document explaining every visual on every page in plain business English, including metric definitions, SQL equivalents, directional signals, and drill-down sequences.

The pipeline covers four stages:

| Stage | What it does |
|---|---|
| Stage 1 — Extraction | Parses Power BI `.tmdl` + `.Report` files into structured JSON |
| Stage 2 — Metric Dictionary | Compiles DAX → SQL, validates via LLM, builds metric catalog |
| Stage 3 — Story Generation | Enriches visuals, generates per-visual narratives (L0→L1→L2→L3) |
| Stage 4 — Document Assembly | Assembles all narratives into a formatted Word + PDF document |

---

## 2. Architecture Decisions

### Root Cause Analysis — Four Compounding Failures Found

The original pipeline was producing descriptions instead of business interpretation. Root cause investigation identified four compounding design failures:

| # | Failure | Impact |
|---|---|---|
| 1 | No Page Intent Layer — pipeline ran bottom-up (visual → story) instead of top-down (page question → visual role → story) | Every visual narrated in a vacuum with no page context |
| 2 | Layer 2 (`visual_parserL2.py`) was a stub — `raise NotImplementedError` at line ~76 | Entire cross-visual interpretation layer missing; L3 had no data to write from |
| 3 | Wrong parallelization — all visuals processed simultaneously across L0→L3 | L2 needs all L1 packets for a page first; concurrent execution broke dependency order |
| 4 | Dashboard overview generated but never read back by L1/L2/L3 | Visual narratives had no knowledge of dashboard purpose, user roles, or key questions |

### Corrected 8-Stage Pipeline Design

Redesigned the pipeline to be **phase-based per page**:

```
Stage 1 → Stage 2a → 2b → 2c
  ↓
3-PRE-A (Visual Enrichment) → 3-PRE-B (Filter Guide) → 3B (Dashboard Overview)
  ↓
FOR EACH PAGE (in parallel):
  3D: All L0s  →  3C: Page Context  →  3E: All L1s  →  3F: All L2s  →  3G: All L3s  →  3H: Page Assembler
  ↓
Stage 4: Word + PDF Assembly
```

---

## 3. Bug Fixes

### Stage 2 — Metric Dictionary

| Bug | File | Fix |
|---|---|---|
| Missing `sys.path` setup — imports failed unless run from exact directory | `pipeline_step9.py` | Added `sys.path.insert` at top |
| `load_prompts()` crashed with `FileNotFoundError` when `prompts/` directory missing | `llm_fallback_step10.py` | Added fallback to inline prompt strings |

### Stage 3 — Visual Parser

| Bug | File | Fix |
|---|---|---|
| Self-import: `from visual_parserL2 import DirectionalRow, DrillStep` inside `_l2_from_dict()` — classes are in same file | `visual_parserL2.py` | Removed self-import |
| Wrong environment variable `TRUEFOUNDRY_MODEL` (3 occurrences) | `visual_parserL2.py` | Changed to `TF_MODEL` |
| Wrong environment variables `TRUEFOUNDRY_MODEL/API_KEY/BASE_URL` (3 occurrences) | `visaul_pareserL1.py` | Changed to `TF_MODEL/API_KEY/BASE_URL` |
| L2 packet save was commented out — packets never written to disk | `visual_parserL2.py` | Enabled save |
| L1 packet save was commented out — packets never written to disk | `visaul_pareserL1.py` | Enabled save |

### Stage 4 — Word Document Generator

| Bug | File | Fix |
|---|---|---|
| All file paths pointed to wrong root (`output/stage3/`, `output/faq/`, `output/glossary/`) | `generate_word_doc.py` | Fixed to correct dashboard-specific paths (`output/dashboards/<dashboard>/stage3/`) |
| Dashboard overview injected a redundant `# Dashboard Overview` heading — the `.md` file already has its own title | `generate_word_doc.py` | Removed injected heading |
| Dead code: checked for `page_wise_story.md` and `business_questions.md` inside page directories — neither file exists there | `generate_word_doc.py` | Removed dead checks |
| `sort_visuals` key function was broken — visuals not sorting by type correctly | `generate_word_doc.py` | Rewrote sort key using `VISUAL_PRIORITY` dict lookup |
| Metric catalog embedded in Word doc caused pandoc to hang for 6+ minutes — huge table with 100+ rows and 500-char cells | `generate_word_doc.py` | Removed from Word doc (catalog available separately at `stage2/metric_catalog.md`) |
| Table "Direction" column rendered as single character per line — pandoc set column width from markdown separator length | `generate_word_doc.py` | Added `w:tblLayout type="autofit"` so Word redistributes column widths by content |
| Tables had no visual formatting — no borders, no header row color, plain text | `generate_word_doc.py` | Added `style_tables()` post-processing (borders, alternating rows, dark header) |

---

## 4. Features Delivered

### Story Guide Document Structure

Established the correct document flow with page breaks between every section:

```
1. Dashboard Overview        ← existing md, no duplicate heading injected
2. Global Filters            ← page break before
3. Page-Wise Story           ← assembled narrative across all pages
4. Visual-Wise (per page)    ← each page on new page, overview first
5. FAQ                       ← page break before
6. Glossary                  ← page break before
```

### Visual Ordering Within Each Page

Visuals now render in a consistent reading order regardless of file system order:

```
Cards → Trend/Line charts → Bar/Column charts → Tables/Matrix → Donut/Pie charts
```

### Page Ordering

Dashboard pages render in a fixed business-logical sequence:
1. `overview_ly` (first by default)
2. `risk_capture_potential`
3. `data_availability`

### Table Formatting (Word Post-Processing)

Applied via `python-docx` after pandoc conversion in a single pass:
- Dark header row (`#2E2E2E` background, white bold text)
- Alternating data rows (white / `#F5F5F5`)
- Light grey borders (`#CCCCCC`) on all cells
- 6pt cell padding
- Calibri 10pt font throughout
- Full page width (100%)
- Auto-fit column widths (no crushed columns)

### PDF Export

Integrated `docx2pdf` (uses Microsoft Word's PDF engine) to generate a pixel-perfect PDF alongside the Word document. Toggle via comment/uncomment in `main()`.

---

## 5. Environment & Configuration

Standardized all environment variable names across Stage 3:

| Correct (use this) | Wrong (old — caused silent failures) |
|---|---|
| `TF_MODEL` | `TRUEFOUNDRY_MODEL` |
| `TF_API_KEY` | `TRUEFOUNDRY_API_KEY` |
| `TF_BASE_URL` | `TRUEFOUNDRY_BASE_URL` |

All variables loaded from `.env` at project root.

---

## 6. Output Artifacts Produced

| Artifact | Location |
|---|---|
| Extracted schema (JSON) | `output/dashboards/risk-dash/stage1/schema_sections/` |
| Metric dictionary with SQL | `output/dashboards/risk-dash/stage2/final_measures_with_llm.json` |
| Metric catalog (MD + JSON) | `output/dashboards/risk-dash/stage2/metric_catalog.md` |
| Per-visual L0/L1/L2 packets | `output/dashboards/risk-dash/stage3/l0_packets/`, `l1_packets/`, `l2_packets/` |
| Per-visual story markdown | `output/dashboards/risk-dash/stage3/story_guide/<page>/<visual>.md` |
| Assembled page story | `output/dashboards/risk-dash/stage3/page_wise_story.md` |
| Dashboard overview | `output/dashboards/risk-dash/stage3/dashboard_overview.md` |
| Global filters guide | `output/dashboards/risk-dash/stage3/global_filters.md` |
| FAQ | `output/dashboards/risk-dash/stage3/faq.md` |
| Glossary | `output/dashboards/risk-dash/stage3/glossary.md` |
| Final Word document | `output/risk-dash_story_guide.docx` |
| Final PDF | `output/risk-dash_story_guide.pdf` |

---

## 7. Pending / Next Steps

| Component | Status | File |
|---|---|---|
| Stage 3C: Page Context Builder | Not created | `src/stage3/page_context_builder.py` |
| Stage 3H: Page Story Assembler | Not created | `src/stage3/page_story_assembler.py` |
| Phase-based orchestrator | Not created | `src/stage3/orchestrator.py` |
| `dashboard_overview.json` companion (machine-readable) | Not created | Enhancement to `dashboard_overview_generator.py` |
| L3 storymaking — partially commented sections | Partial | `visual_parserL3_storymaking.py` |

---

## 8. Tech Stack

| Tool | Purpose |
|---|---|
| Python 3.11 | Core pipeline language |
| TrueFoundry LLM API (`claude-sonnet-46`) | All LLM calls (L1, L2, L3, overview, catalog) |
| Snowflake | SQL verification of generated queries |
| pypandoc + Pandoc | Markdown → Word conversion |
| python-docx | Word document post-processing (table styling) |
| docx2pdf | Word → PDF export via Microsoft Word engine |
| Power BI `.tmdl` / `.Report` | Input format |
