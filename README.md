# Story Guide Generator

Converts a Power BI dashboard (`.pbix` decomposed into `.Report` + `.SemanticModel` folders) into a structured **Story Guide** — a Word document that explains every visual on every page in plain business English, including metric definitions, SQL equivalents, directional signals, and drill-down sequences.

---

## What it produces

For each dashboard, the pipeline outputs a `.docx` Story Guide containing:

- **Page-by-page narrative** — every widget explained in business terms
- **Metric definitions** — DAX measures translated to SQL with business context
- **Funnel structure** — Top / Middle / Bottom / Action layers linking pages into a coherent story
- **Global filters** — slicer and filter documentation
- **Glossary & FAQ** — auto-generated from the dashboard content
- **Dashboard overview** — executive summary of what the dashboard measures and why

---

## Pipeline overview

```
Stage 1  [sequential]   Extraction          — parse .pbix, resolve DAX measures
Stage 2  [parallel]     Visual_wise         — enrich visuals (L0 → L1 → L2 → L3)
                        Filter_section      — document global filters
                        Metric_dictionary   — DAX → SQL + LLM definitions
Stage 3  [sequential]   Page_wise           — build page narratives and funnel map
Stage 4  [parallel]     Dashboard_overview  — executive summary
                        Glossary_FAQ        — glossary and FAQ generation
                        Word_generator      — assemble final .docx
```

---

## Project structure

```
input/                          ← Power BI .SemanticModel + .Report folders
output/
├── dashboards/<name>/          ← per-dashboard outputs
│   ├── extraction/
│   ├── metric_dictionary/
│   ├── visual_wise/
│   ├── filter_section/
│   ├── page_wise/
│   ├── dashboard_overview/
│   └── glossary_faq/
└── <name>_story_guide.docx     ← final Word document

src/
├── utils/                      ← shared utilities (LLM client, paths, config)
├── Extraction/
├── Metric_dictionary/
├── Visual_wise/
├── Page_wise/
│   └── Widgets/
├── filter_section/
├── dashboard_overview/
├── glossary_faq/
└── word_generator/

api/                            ← FastAPI backend
frontend/                       ← React + Tailwind UI
main.py                         ← top-level pipeline runner
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+ (for the web UI)
- `pandoc` installed and on PATH ([pandoc.org](https://pandoc.org/installing.html))
- Access to a TrueFoundry-hosted Claude model endpoint

---

## Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd story-guide-generator

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install frontend dependencies
cd frontend
npm install
cd ..

# 5. Copy and fill in environment variables
cp .env.example .env
```

### `.env` variables

```env
TF_BASE_URL=https://your-truefoundry-endpoint
TF_API_KEY=your-api-key
TF_MODEL=internal-bedrock/sonnet-46

# Optional — Snowflake SQL verification (skipped by default)
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_WAREHOUSE=
SNOWFLAKE_DATABASE=
SNOWFLAKE_SCHEMA=
```

---

## Running the pipeline

### Full pipeline (all dashboards)
```bash
python main.py
```

### Single dashboard
```bash
python main.py --dashboard risk-dash
```

### Resume from a specific stage
```bash
python main.py --dashboard risk-dash --from-stage 3
```

### Force re-run (bypass cache)
```bash
python main.py --dashboard risk-dash --from-stage 2 --force
```

### Dry run (no LLM or Snowflake calls)
```bash
python main.py --dry-run
```

### Resume from failure — quick reference

| Failed at | Restart command |
|-----------|----------------|
| Stage 1 | `python main.py --dashboard <dash> --from-stage 1` |
| Stage 2 | `python main.py --dashboard <dash> --from-stage 2` |
| Stage 3 step 3 (widget writer) | `python src/Page_wise/runner.py --dashboard <dash> --from-step 3 --force` |
| Stage 3 step 5 | `python src/Page_wise/runner.py --dashboard <dash> --from-step 5` |
| Stage 4 | `python main.py --dashboard <dash> --from-stage 4` |

---

## Web UI

```bash
# Terminal 1 — API server
uvicorn api.main:app --reload

# Terminal 2 — Frontend dev server
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) to launch, configure, and run pipelines from the browser. The UI streams live logs and provides a one-click download for the final `.docx`.

---

## Adding a new dashboard

1. Place Power BI files in `input/`
2. Add the dashboard to `src/utils/config.py`:

```python
DASHBOARDS: dict[str, dict] = {
    ...
    "my-new-dash": {
        "semantic_model": ROOT / "input" / "MyDashboard.SemanticModel",
        "report":         ROOT / "input" / "MyDashboard.Report",
    },
}
```

3. Run the pipeline:

```bash
python main.py --dashboard my-new-dash
```

---

## Output

The final Word document is saved to:

```
output/<dashboard-name>_story_guide.docx
```

It follows a consistent structure:
1. Cover page
2. About this guide (domain context + funnel overview)
3. Page-by-page narrative (Layer 1 → 2 → 3 per page)
4. How the funnel connects (summary table)
5. Glossary & FAQ

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Pipeline | Python 3.11 |
| LLM | Claude (via TrueFoundry / Anthropic API) |
| Retry logic | Tenacity |
| Word generation | python-docx + pypandoc |
| API | FastAPI |
| UI | React + Tailwind CSS + Vite |
| Optional SQL verification | Snowflake Connector |
