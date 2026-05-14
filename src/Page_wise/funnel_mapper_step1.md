# funnel_mapper_step1.py — Step 1: Funnel Mapper

## Purpose
Reads `funnel_llm_input.json` and uses **3 focused LLM calls per page** to classify every visual into funnel positions (TOP / MIDDLE / BOTTOM / ACTION) and group them into named widgets. Produces `funnel_map.json` — the backbone of the entire Page_wise story structure.

The 3-call design prevents visual ID loss that occurred with a single large call on pages with 25+ visuals.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `output/dashboards/<dash>/page_wise/funnel_llm_input.json` |
| **Output** | `output/dashboards/<dash>/page_wise/funnel_map.json` |
| **Cache** | Skips re-run if `content_hash` matches existing output. Override with `--force` |

---

## 3-Call Design Per Page

| Call | What it Does | Why Separate |
|---|---|---|
| **Call 1** — Funnel questions | Extracts domain_context + 4 funnel questions | Tiny call, no visual IDs, run once for whole dashboard |
| **Call 2** — Classify | Maps every `visual_id` → `TOP/MIDDLE/BOTTOM/ACTION` | Flat dict, easy to validate completeness |
| **Call 3** — Group per bucket | Groups visuals in one position bucket into widgets | Small, focused — one call per non-empty bucket |

---

## Function Flow

```
main()
  └── run_funnel_mapper(llm_input)
        ├── build_page_plan(all_pages)
        │     ├── group pages by get_page_base_name() (strips time-period suffix)
        │     ├── _rank_representative() → pick LY over LM, YTD over MTD
        │     └── sort: non-action first (by order), action pages last
        │
        └── for each plan step (representative page):
              ├── [Call 1 — once] get_funnel_questions(dashboard_name, all_pages, ...)
              │     └── build_funnel_questions_prompt() → call_llm()
              │           retries up to 3x; raises if required fields missing
              │
              ├── if action page → group_bucket(all visuals, "ACTION", ...)
              │
              └── else (normal page):
                    ├── [Call 2] classify_visuals(rep_visuals, rep_ids)
                    │     └── build_classify_prompt() → call_llm()
                    │           strips invalid IDs + positions silently
                    │           defaults unclassified to TOP after 3 retries
                    │
                    └── [Call 3 × N] for each non-empty bucket in [TOP, MIDDLE, BOTTOM, ACTION]:
                          group_bucket(bucket_visuals, position, funnel_questions, ...)
                            └── build_group_bucket_prompt() → call_llm()
                                  validates completeness (no missing/invented IDs)
                                  on retry: sends back error list + previous response
```

---

## Function Details

### `build_page_plan(all_pages) → list[dict]`
Groups pages by base name (strips time-period suffix). Picks the best representative per group using `_rank_representative()` — LY beats LM, YTD beats MTD. Mirror pages are recorded but not sent to LLM. Sorts: analytical pages first (by order), action pages last.

### `get_page_base_name(page_name) → str`
Strips the last 1–2 words if they are in `TIME_PERIOD_SUFFIXES`. E.g. `"Overview LY"` → `"Overview"`, `"Summary Prior Year"` → `"Summary"`.

### `_is_action_page(page_name) → bool`
Checks page name against `ACTION_PAGE_KEYWORDS`. Action pages skip classification and go directly to ACTION bucket.

### `get_funnel_questions(dashboard_name, all_pages, sample_measures, action_page_names) → dict`
Call 1. Returns `{domain_context, funnel_question_top, funnel_question_middle, funnel_question_bottom, funnel_question_action}`. Action page names are pre-detected in code and passed explicitly — prevents LLM from returning null when action pages exist.

### `classify_visuals(visuals, page_visual_ids) → dict`
Call 2. Returns `{visual_id: "TOP"|"MIDDLE"|"BOTTOM"|"ACTION"}`. Strips invented IDs and invalid positions silently. Falls back to defaulting all unclassified to TOP after 3 retries — never raises.

### `group_bucket(bucket_visuals, position, funnel_questions, reading_order_start) → list`
Call 3. Groups visuals in one bucket into widgets. Validates completeness using `validate_page_widgets()`. On retry, sends back the error list + previous LLM response as context. Raises `RuntimeError` after 3 failed attempts.

### `validate_page_widgets(widgets, page_visual_ids) → list[str]`
Checks:
- No visual ID appears in multiple widgets
- All page visual IDs appear in exactly one widget
- No invented visual IDs
- All funnel positions are valid (`VALID_POSITIONS`)

### `mirror_widgets_for_page(source_widgets, source_page, target_page, target_visuals, widget_id_offset) → list`
Maps source (LY) widget structure onto target (LM) page by matching visuals by `(title, type)`. Appends a catch-all widget for any unmatched target visuals.

### `_format_visuals(visuals) → str`
Compact text format: `[visual_id] "title" (type)\n    measure: definition`. Truncates definitions at 70 chars. No full DAX — keeps token count low.

---

## SYSTEM_PROMPT (shared across all 3 calls)
Contains 7 rules that govern how visuals are grouped:
- **Rule 1** — KPI cards: EXACTLY TWO widgets (landscape + performance rows)
- **Rule 2** — Trend charts: ALL line charts on a page → EXACTLY ONE widget
- **Rule 3** — Bar chart + detail table on same dimension → ONE widget
- **Rule 4** — Entity table + scatter plot → ONE widget
- **Rule 5** — Table position by row dimension type (payer/LOB=TOP, model/cohort=MIDDLE, provider/practice=BOTTOM)
- **Rule 6** — Operational breakdown charts (donut) → BOTTOM
- **Rule 7** — Action page: funnel_question_action must be non-null

---

## File Connections

| Imports from | Used for |
|---|---|
| `utils/llm_client.py` | Not used directly — has own `call_llm()` using OpenAI directly |
| `openai.OpenAI` | Direct LLM calls (bypasses `llm_chat` retry wrapper) |

**Called by:** `runner.py` (Step 1, as subprocess)

**Input from:** `funnel_input_builder_step0.py` → `funnel_llm_input.json`

**Output consumed by:** `widget_group_writer_step3.py`, `funnel_connector_step4.py`, `document_assembler_step5.py`

---

## Hardcoded Parts (Change for New Dashboards)

### `TIME_PERIOD_SUFFIXES` (line ~54)
```python
TIME_PERIOD_SUFFIXES = {
    "ly", "lm", "ytd", "mtd", "qtd",
    "q1", "q2", "q3", "q4",
    "prior year", "current year",
    "prior month", "current month",
    "yoy", "mom", "qoq", "py", "cy",
}
```
Suffixes used to detect mirror pages and group them. If a new dashboard uses different time-period naming (e.g. `"H1"`, `"H2"`, `"week"`, `"rolling"`), add them here.

### `ACTION_PAGE_KEYWORDS` (line ~64)
```python
ACTION_PAGE_KEYWORDS = {
    "capture potential", "action", "targeting", "outreach",
    "intervention", "chase list", "worklist", "prioritization",
}
```
Keywords used to identify action pages (bypass classification → go straight to ACTION bucket). If a new dashboard's action page has a different name that doesn't match these keywords, add it here.

### `SYSTEM_PROMPT` — hardcoded domain rules (line ~181)
The 7 grouping rules in the system prompt reference healthcare-specific concepts: `"HCC"`, `"LOB"`, `"RAF"`, `"PCP"`, `"risk_model_name"`, `"recapture rates"`, `"PMPM"`. For a non-healthcare dashboard, these rules would produce incorrect groupings. Update the system prompt to match the new domain's dimension taxonomy.

### `VALID_POSITIONS` (line ~51)
```python
VALID_POSITIONS = {"TOP", "MIDDLE", "BOTTOM", "ACTION"}
```
The 4-layer funnel structure. If a different framework (e.g. 3-layer, or different labels) is needed for a new dashboard, this set and all related prompt text must change together.

### `LLM temperature + max_completion_tokens` (line ~498)
```python
response = client.chat.completions.create(
    model=TF_MODEL,
    temperature=0.1,
    max_completion_tokens=16000,
    ...
)
```
`max_completion_tokens=16000` is set for pages with many visuals. For a simpler dashboard with fewer visuals, this could be reduced.
