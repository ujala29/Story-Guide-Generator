# Work Report — Story Guide Generator

**Author:** Ujala Gupta
**Date:** May 13, 2026
**Branch:** main

---

## Session: Page_wise Pipeline Fixes

### Context

The Page_wise pipeline (Stage 3) was failing on pages with 25+ visuals because `funnel_mapper_step1.py` sent all visuals in a single LLM call and asked it to simultaneously determine funnel questions, classify every visual, group them into widgets, name each widget, and write sub-questions. The LLM would drop visual IDs or invent placeholders like `pending_assignment_until_visuals_provided`.

---

## Fix 1 — `funnel_mapper_step1.py`: Three-call refactor

**File:** `src/Page_wise/funnel_mapper_step1.py`

**Problem:** One giant LLM call per page asked for funnel questions + classify 34 visuals + group them all at once. LLM dropped visual IDs on pages with 25+ visuals.

**Fix:** Replaced single call with three focused calls:

| Call | Job | Input size |
|------|-----|------------|
| Call 1 | Funnel questions only (dashboard context) | Page names + 15 measure names |
| Call 2 | Flat `{visual_id: position}` classification | All page visuals, one label per visual |
| Call 3 | Group widgets per bucket | One position bucket at a time (~5-15 visuals) |

New functions added: `get_funnel_questions()`, `classify_visuals()`, `group_bucket()`, `build_funnel_questions_prompt()`, `build_classify_prompt()`, `build_group_bucket_prompt()`

Old functions removed: `build_first_call_prompt()`, `build_action_page_prompt()`, `call_with_retry()`

Output schema of `funnel_map.json` unchanged.

---

## Fix 2 — `funnel_mapper_step1.py`: `max_tokens` → `max_completion_tokens`

**File:** `src/Page_wise/funnel_mapper_step1.py`

**Problem:** `call_llm()` used `max_tokens=16000` which the TF model backend rejects:
```
openai.BadRequestError: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.
```

**Fix:** Changed `max_tokens=16000` to `max_completion_tokens=16000` in `call_llm()`.

---

## Fix 3 — `funnel_mapper_step1.py`: Action funnel question returning null

**File:** `src/Page_wise/funnel_mapper_step1.py`

**Problem:** Call 1 asked the LLM to detect action pages from page names. LLM saw `"Risk capture potential"` and interpreted "capture" as a medical risk term, not an action/outreach page — returned `null`. This caused the Action bullet to disappear from the `.md` document header.

**Root cause:** Prompt said "write a sentence if page name suggests action" — too ambiguous for the LLM.

**Fix:** `_is_action_page()` detects action pages in code first (already working correctly, same function that routes ACTION bucket visuals). Result passed explicitly to the prompt:
```
ACTION PAGES (already detected): Risk capture potential
funnel_question_action MUST be a real sentence describing what these pages help the user do.
```

Changes: `build_funnel_questions_prompt()` now accepts `action_page_names: list`, `get_funnel_questions()` accepts and passes it, `run_funnel_mapper()` computes action pages from plan before calling Call 1.

---

## Fix 4 — `widget_group_writer_step3.py`: KPI token limit + uncaught error

**File:** `src/Page_wise/widget_group_writer_step3.py`

**Problem:** `process_kpi_card_row()` called `call_llm` with `max_tokens=3000` for 10 KPI metrics. Response truncated → TF backend returned empty content → `ValueError("Empty LLM response (finish_reason=length)")` raised outside the `try/except` block, bypassing all 3 retries entirely. Error surfaced as a one-line message with no actionable detail.

**Fix:**
- Raised token limit: `max_tokens=3000` → `max_tokens=6000`
- Moved `call_llm` inside `try/except` so token-limit errors trigger retries instead of crashing
- Added `import traceback` at module level
- `run_widget()` exception handler now prints full Python traceback via `traceback.print_exc()`

---

## Fix 5 — All 8 LLM retry loops: Better error logging

**Files:**
- `src/Page_wise/widget_group_writer_step3.py` (`process_kpi_card_row`)
- `src/Page_wise/Widgets/trend_lines_processor.py`
- `src/Page_wise/Widgets/detail_table_processor.py`
- `src/Page_wise/Widgets/clinical_pair_processor.py`
- `src/Page_wise/Widgets/entity_scatter_processor.py`
- `src/Page_wise/Widgets/multi_chart_processor.py`
- `src/Page_wise/Widgets/action_table_processor.py`
- `src/Page_wise/Widgets/segmentation_processor.py`
- `src/Page_wise/funnel_mapper_step1.py` (3 retry loops)

**Problem:** In all processors, the LLM call was outside the `try/except`. Any API error escaped all 3 retry attempts silently. Empty responses printed "empty response" with no reason. Parse errors only printed `str(e)` with no context.

**Fix applied identically to all locations:**
- LLM call wrapped in `try/except` — API errors now retry instead of crash
- `content` accessed safely: `(response.choices[0].message.content or "").strip()`
- `finish_reason` captured and printed on empty responses
- Parse failures print `finish_reason` + `response_length` + last 400 chars of the truncated response

---

## Summary of Files Changed

| File | Change |
|------|--------|
| `src/Page_wise/funnel_mapper_step1.py` | Three-call refactor, `max_completion_tokens`, action page fix, error logging |
| `src/Page_wise/widget_group_writer_step3.py` | KPI token limit 3000→6000, error logging, traceback |
| `src/Page_wise/Widgets/trend_lines_processor.py` | Error logging |
| `src/Page_wise/Widgets/detail_table_processor.py` | Error logging |
| `src/Page_wise/Widgets/clinical_pair_processor.py` | Error logging |
| `src/Page_wise/Widgets/entity_scatter_processor.py` | Error logging |
| `src/Page_wise/Widgets/multi_chart_processor.py` | Error logging |
| `src/Page_wise/Widgets/action_table_processor.py` | Error logging |
| `src/Page_wise/Widgets/segmentation_processor.py` | Error logging |
