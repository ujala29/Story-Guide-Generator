# Crash Analysis — Story Guide Generator
> Kahan code fat sakta hai — file-by-file breakdown

---

## CRITICAL — Application Load Crashes

These crash before any pipeline runs, at import/startup time.

---

### 1. `src/Visual_wise/visual_parserL0.py` — Module-level JSON load with no fallback

**Lines 65–66**
```python
with open(MEASURES_RESOLVED_PATH, encoding="utf-8") as f:
    MEASURES_RESOLVED: dict = json.load(f)
```

**Crash condition:** `measures_resolved.json` doesn't exist yet (Stage 1 not run), or is empty/malformed.
**Effect:** `JSONDecodeError` or `FileNotFoundError` at import time — entire Visual_wise pipeline crashes before processing a single visual.
**Fix:** Wrap in try/except, return `{}` on failure, print warning.

---

### 2. `src/Visual_wise/visual_parserL0.py` — `_FIXES["title_overrides"]` KeyError

**Lines 61–63**
```python
TITLE_OVERRIDES : dict = _FIXES["title_overrides"]
GENERIC_TITLES  : set  = set(_FIXES["generic_titles"])
SKIP_TYPES      : set  = set(_FIXES["skip_types"])
```

**Crash condition:** `fixes.json` exists but is missing one of these keys (e.g., someone adds a dashboard with partial fixes.json).
**Effect:** `KeyError` at import time.
**Fix:** Use `.get()` with safe defaults.

---

## HIGH — Will crash in normal pipeline runs

---

### 3. `src/word_generator/generate_word_doc.py` — `existing[0]` on empty document body

**Line 97**
```python
ref = existing[0]
```

**Crash condition:** `pypandoc` generates a `.docx` with an empty body (e.g., all input markdown files are empty, or pandoc version mismatch produces malformed output).
**Effect:** `IndexError: list index out of range` — Word document generation fails entirely.
**Fix:**
```python
if not existing:
    raise RuntimeError("Pandoc produced an empty document body — check input markdown")
ref = existing[0]
```

---

### 4. `src/Page_wise/Widgets/clinical_pair_processor.py` — `m['display_name_in_visual']` KeyError

**Lines 75–77**
```python
bar_measure_lines = "\n".join(
    f"  - {m['display_name_in_visual'] or m['name']}: {m.get('definition','')[:100]}"
    for m in bar_measures
)
```

**Crash condition:** Any measure dict is missing `display_name_in_visual` or `name` key (happens when visual enrichment was partial or Extraction produced incomplete output).
**Effect:** `KeyError` mid-generation, widget content file never written, Stage 3 fails.
**Fix:**
```python
f"  - {m.get('display_name_in_visual') or m.get('name', 'Unknown')}: {m.get('definition','')[:100]}"
```
Same issue exists on lines 83–85 for `table_measure_lines`.

---

### 5. `src/Page_wise/funnel_connector_step4.py` — `json.loads()` without try/except on LLM response

**Line 81**
```python
return json.loads(text)
```
in `parse_json_response()`

**Crash condition:** LLM returns text that isn't valid JSON even after markdown fence stripping (partial response due to `finish_reason=length`, hallucinated prose before JSON, etc.).
**Effect:** `JSONDecodeError` — funnel connector file never written, Stage 3 step 4 halts.
**Fix:** Wrap in try/except, log the raw LLM response for debugging.

---

### 6. `src/dashboard_overview/dashboard_overview_generator.py` — Three bare `json.load()` calls

**Lines 43, 53, 64** — all without try/except:
```python
funnel_map      = json.load(f)   # line 43
funnel_connector = json.load(f)  # line 53
data            = json.load(f)   # line 64
```

**Crash condition:** Any of these files is malformed (partially written due to a prior crash in Stage 3).
**Effect:** `JSONDecodeError` — dashboard overview never generated.
**Fix:** Add try/except around each, log which file failed.

---

### 7. `src/Metric_dictionary/llm_fallback_step10.py` — Three bare `json.loads()` on file reads

**Lines 280, 799, 815** (approximate):
```python
json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))   # line 280
json.loads(final_json.read_text(encoding="utf-8"))       # line 799
json.loads(registry_path.read_text(encoding="utf-8"))    # line 815
```

**Crash condition:** Registry was half-written (pipeline killed mid-run), or disk full scenario.
**Effect:** `JSONDecodeError` — metric dictionary pipeline crashes, `registry.json` never finalized.
**Note:** Line 608 (`json.loads(clean)`) IS protected — good.

---

### 8. `src/Metric_dictionary/metric_catalog_step12.py` — Bare `json.loads()` on file reads

**Lines 433–434**:
```python
json.loads(llm_json.read_text(encoding="utf-8"))
json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {}
```

**Crash condition:** `reg_path.exists()` returns True but file is empty or malformed (zero-byte file after disk error).
**Effect:** `JSONDecodeError` in metric catalog generation.

---

### 9. `src/glossary_faq/faq_generator.py` — Missing try/except on `funnel_map` load

**Line 143**:
```python
funnel_map = json.load(f)  # no try/except here
```

**Crash condition:** `funnel_map.json` malformed.
**Effect:** FAQ never generated — Stage 4 partial failure (glossary may succeed, FAQ won't).
**Note:** Lines 65, 92, 106 DO have try/except — only line 143 is unprotected.

---

### 10. `src/Page_wise/funnel_mapper_step1.py` — `json.load()` on input files without try/except

**Line ~941**:
```python
data = json.load(f)
```

**Crash condition:** `visuals_enriched.json` or funnel input JSON is malformed.
**Effect:** Entire funnel mapping fails — all of Stage 3 downstream is blocked.

---

### 11. `src/dashboard_overview/runner.py` and `src/filter_section/runner.py` — Bare `json.load()`

Both have:
```python
filters = json.load(f)
```
without try/except.

**Crash condition:** `filters.json` from Extraction is malformed.
**Effect:** These Stage 2/4 modules fail silently or crash — no error message identifies which file caused it.

---

### 12. `src/filter_section/filter_story_guidemaker.py` — `pages[0]` assumption

**Lines 78–79**:
```python
pages = list(page_filters.values())
first = {f["column"] for f in pages[0]}
```

**Crash condition:** All pages are in the `SKIP_PAGES` set (e.g., dashboard has only "additional dimensions" and "scatter plot tooltip" pages). `page_filters` ends up empty, `pages` is `[]`, `pages[0]` crashes.
**Effect:** `IndexError` — global_filters.md never written.
**Fix:** Guard is already above (`if not page_filters: return []`) BUT it's in `get_global_filters()`, not before `pages[0]`. The `first = ...` line is in that same function — so the guard works. However if `page_filters` has one page and that page has 0 filters, `{f["column"] for f in pages[0]}` silently returns empty set — this is fine. **Actually safe** — but double-check `extract_filters_by_page()` return guarantees.

---

### 13. `src/Page_wise/Widgets/action_table_processor.py` — `json.loads(text)` without try/except

**Line ~218** in `parse_json_response()`:
```python
return json.loads(text)
```

**Crash condition:** LLM returns invalid JSON (truncated by token limit even after raising to 6000).
**Effect:** Action table widget content never written — page_wise_story.md has a gap.

---

### 14. `src/Extraction/measure_resolver_.py` — Bare `json.load()` at startup

**Line ~25**:
```python
data = json.load(f)
```

**Crash condition:** Input measure file doesn't exist or is malformed.
**Effect:** Stage 1 crashes before any schema is extracted.

---

## MEDIUM — Edge cases that break specific dashboards or inputs

---

### 15. `src/Visual_wise/visaul_pipeline_runner.py` — `measures[0].split(".")[-1]` on empty list

**Multiple lines (approx. 366, 370, 438, 502, 522, 794)**:
```python
primary = measures[0].split(".")[-1]
```

**Crash condition:** Visual has no measures (e.g., a text box, image card, or shape visual that slipped through type filtering).
**Effect:** `IndexError` — that visual's L0 packet fails, downstream L1/L2/L3 skips it silently or crashes.
**Fix:** `primary = measures[0].split(".")[-1] if measures else ""`

---

### 16. All Widget processors — LLM response `None` content

**Pattern in every `Widgets/*.py`**:
```python
raw = call_llm(system, user)
data = parse_json_response(raw)
```

**Crash condition:** `llm_chat()` returns `None` or empty string (API timeout, rate limit exhausted after retries). `parse_json_response(None)` crashes on `None.strip()`.
**Effect:** Widget processor raises `AttributeError: 'NoneType' object has no attribute 'strip'`.
**Fix:** Add `if not raw: raise ValueError("LLM returned empty response")` before parse.

---

### 17. `src/Page_wise/widget_group_writer_step3.py` — `parse_json_response()` on nested fences

**Pattern**: LLM occasionally wraps JSON inside a Python code block:
````
```python
{"key": "value"}
```
````

`parse_json_response()` strips the first line (` ```python`) but `json.loads()` then fails because the content has trailing `"` or other Python-specific markers.
**Effect:** `JSONDecodeError` — widget group never finalized, step 3 fails.
**Fix:** After stripping fences, add a second pass to strip any remaining non-JSON prefix.

---

### 18. `src/Metric_dictionary/pipeline_step9.py` — `{m["name"]: m for m in data}` KeyError

**Line ~115**:
```python
measure_map = {m["name"]: m for m in data}
```

**Crash condition:** Any measure dict in `measures_resolved.json` is missing the `"name"` key (partial Extraction output).
**Effect:** `KeyError` — entire DAX→SQL compilation fails for that dashboard.
**Fix:** `{m["name"]: m for m in data if "name" in m}` and log skipped entries.

---

### 19. `src/Visual_wise/visaul_pareserL1.py` and `visual_parserL2.py` — `response.choices[0].message.content` could be `None`

**Pattern** across LLM response handling:
```python
content = response.choices[0].message.content
result  = json.loads(content)
```

**Crash condition:** API returns `finish_reason="content_filter"` or `finish_reason="length"` with null content.
**Effect:** `TypeError: the JSON object must be str, bytes or bytearray, not NoneType` — visual enrichment fails silently for that page.

---

### 20. `src/Page_wise/funnel_mapper_step1.py` — `json.loads(text)` in LLM parse with no fallback

**Line ~522**:
```python
result = json.loads(text)
```

**Crash condition:** Call 1, 2, or 3 LLM responses are invalid JSON. All 3 calls must succeed for funnel_map.json to be written.
**Effect:** `JSONDecodeError` — entire Stage 3 is blocked since funnel_map is the entry point for step 3 → 4 → 5.

---

## LOW — Subtle bugs, wrong output (no crash, bad data)

---

### 21. `src/filter_section/filter_story_guidemaker.py` — `f["column"]` KeyError

**Lines 79, 83–84**:
```python
first = {f["column"] for f in pages[0]}
page_cols = {f["column"] for f in page}
```

**Crash condition:** A filter dict is missing the `"column"` key (e.g., a slicer with only a measure, no column binding).
**Effect:** `KeyError` — global filter computation fails.
**Fix:** `{f.get("column", "") for f in pages[0]} - {""}` to drop empties.

---

### 22. All `parse_json_response()` helpers — Double-fence edge case

**Pattern** when LLM returns:
```
Here is the JSON:
```json
{...}
```
```

`text.startswith("```")` is `False` (starts with "Here"), so fence stripping is skipped, and `json.loads()` fails on the prose prefix.
**Effect:** `JSONDecodeError`.
**Fix:** Use `re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)` to extract JSON block regardless of position.

---

### 23. `src/word_generator/generate_word_doc.py` — Missing import `WD_ALIGN_PARAGRAPH` and `Inches`

**Lines 57, 60**:
```python
p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_logo.add_run().add_picture(str(LOGO_PATH), width=Inches(2.2))
```

**Check:** These are from `docx.enum.text` and `docx.shared`. If the import list at the top doesn't include them, this crashes with `NameError`.
**Action:** Verify imports at top of file include `from docx.enum.text import WD_ALIGN_PARAGRAPH` and `from docx.shared import Inches`.

---

## Summary Table

| # | File | Crash Type | Severity |
|---|------|-----------|----------|
| 1 | `visual_parserL0.py` L65–66 | FileNotFoundError / JSONDecodeError at import | CRITICAL |
| 2 | `visual_parserL0.py` L61–63 | KeyError on fixes.json at import | CRITICAL |
| 3 | `generate_word_doc.py` L97 | IndexError on empty doc body | HIGH |
| 4 | `clinical_pair_processor.py` L76 | KeyError on missing measure key | HIGH |
| 5 | `funnel_connector_step4.py` L81 | JSONDecodeError on LLM response | HIGH |
| 6 | `dashboard_overview_generator.py` L43,53,64 | JSONDecodeError on malformed input | HIGH |
| 7 | `llm_fallback_step10.py` L280,799,815 | JSONDecodeError on registry files | HIGH |
| 8 | `metric_catalog_step12.py` L433–434 | JSONDecodeError on file reads | HIGH |
| 9 | `faq_generator.py` L143 | JSONDecodeError on funnel_map | HIGH |
| 10 | `funnel_mapper_step1.py` ~L941 | JSONDecodeError on input JSON | HIGH |
| 11 | `runner.py` (dashboard_overview, filter_section) | JSONDecodeError on filters.json | HIGH |
| 12 | `filter_story_guidemaker.py` L79 | IndexError if all pages skipped | HIGH |
| 13 | `action_table_processor.py` ~L218 | JSONDecodeError on LLM response | HIGH |
| 14 | `measure_resolver_.py` ~L25 | JSONDecodeError / FileNotFoundError | HIGH |
| 15 | `visaul_pipeline_runner.py` L366+ | IndexError on empty measures list | MEDIUM |
| 16 | All `Widgets/*.py` | AttributeError if LLM returns None | MEDIUM |
| 17 | `widget_group_writer_step3.py` | JSONDecodeError on nested fences | MEDIUM |
| 18 | `pipeline_step9.py` ~L115 | KeyError on missing name key | MEDIUM |
| 19 | `visaul_pareserL1.py`, `visual_parserL2.py` | TypeError on None LLM content | MEDIUM |
| 20 | `funnel_mapper_step1.py` ~L522 | JSONDecodeError, blocks all Stage 3 | MEDIUM |
| 21 | `filter_story_guidemaker.py` L79,83 | KeyError on missing column key | LOW |
| 22 | All `parse_json_response()` | JSONDecodeError when prose before fence | LOW |
| 23 | `generate_word_doc.py` L57,60 | NameError if imports missing | LOW |

---

## Quickest fixes (ek baar karo, bahut crashes band ho jayenge)

1. **Ek global `safe_json_load(path)` helper likho** in `src/utils/` — `try/except` with logging. 20+ locations mein replace karo.
2. **`parse_json_response()` ko robust banao** — regex-based JSON extraction instead of startswith check. Ek jagah fix, saare processors ko faida.
3. **`visual_parserL0.py` module-level loads** ko try/except mein wrap karo — yeh sabse dangerous hai kyunki import time crash hota hai.
4. **LLM None response check** — `llm_chat()` ke baad ek line: `if not raw: raise ValueError(...)`.
