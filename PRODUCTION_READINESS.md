# Production Readiness Audit — Story Guide Generator
_Last updated: 2026-05-13 | Audited by: Claude Code (deep line-level scan)_

---

## Legend

| Label | Meaning |
|-------|---------|
| CRITICAL | Will crash or silently corrupt output in production |
| HIGH     | Silent failure, wrong output, or hard-to-debug cascade without crashing |
| MEDIUM   | Performance or maintainability issue that hurts at scale |
| DONE     | Already fixed or correctly implemented |

---

## Section 1 — Crash Bugs

These will fail at runtime under normal operating conditions.

### C-1 | `funnel_mapper_step1.py` lines 102 + 185
`_is_action_page()` is defined twice. Python silently uses the second definition.
`build_page_plan()` at line 174 calls it but may get the wrong one depending on load order.
**Fix:** Delete the first definition at lines 102–104; keep only the one at line 185.

### C-2 | `visaul_pipeline_runner.py` lines 26, 28
Imports `visaul_pareserL1` (double typo: "visaul" + "pareser"). If the actual filename on disk has a different capitalisation or partial fix, this crashes at startup with `ModuleNotFoundError`.
**Fix:** Verify exact filename on disk; fix import to match exactly.

### C-3 | `document_assembler_step5.py` lines 645–658
`pages_processed[0]` is accessed without a length check. If no pages were processed (all pages skipped or filtered), this raises `IndexError`.
**Fix:** Guard with `if pages_processed:` before indexing.

### C-4 | `funnel_mapper_step1.py` lines 484–495
`call_llm()` creates a raw `OpenAI` client with no retry. A single `RateLimitError` or `APITimeoutError` crashes the entire funnel-mapping step with no recovery. Already retried 3x at lines 508–582 but those retries also use the raw client with no backoff — 3 rapid-fire failures, then crash.
**Fix:** Replace with `llm_chat()` from `utils/llm_client.py` (tenacity retry + singleton built in).

### C-5 | `dashboard_overview_generator.py` lines 303–306
Same raw-client pattern, zero retry. One transient API error kills the overview step.
**Fix:** Replace with `llm_chat()`.

### C-6 | `filter_story_guidemaker.py` lines 228–231
Same raw-client pattern, zero retry.
**Fix:** Replace with `llm_chat()`.

---

## Section 2 — Silent Failures (wrong output, no crash)

### H-1 | `funnel_mapper_step1.py` lines 620–660
`_do_mirror()` matches source-to-target visuals purely by list position. If two time-period pages have visuals in a different order (very likely for Overview LM vs Overview LY), wrong visual IDs get mapped. No title/type validation at all.
**Impact:** Mirrored pages write widget content for wrong visuals. Final document has mismatched sections.
**Fix:** Match by `(title, type)` pair, not list position. Log any titles that could not be matched.

### H-2 | `widget_group_writer_step3.py` lines 475–486
If the LLM call for a widget fails, the widget is silently absent from the `results` dict. `document_assembler` gets an incomplete page and renders empty placeholders — no error, no warning.
**Impact:** Sections silently missing from final document.
**Fix:** After `ThreadPoolExecutor` finishes, diff expected widgets vs results; log and raise if any are missing.

### H-3 | `document_assembler_step5.py` lines 530–534
If two pages share a `widget_id`, the second overwrites the first in `widget_lookup`.
**Impact:** Content from one page silently replaces another's.
**Fix:** Detect collision on insert; log warning and keep both under disambiguated keys.

### H-4 | `funnel_connector_step4.py` lines 122–126
`build_prompt()` filters to only non-mirrored widgets. But `document_assembler` renders mirrored pages too — LLM never sees them, so `funnel_table` is missing rows for mirrored pages.
**Impact:** Funnel table incomplete in final document.
**Fix:** Pass all pages (with a "mirrors: Overview LM" note) or post-fill mirrored rows by copying the representative row.

### H-5 | `metric_dictionary/runner.py` line 89
`--skip-verifier` uses `action="store_true", default=True`. With `store_true`, `default=True` means the flag can only confirm True — passing `--no-skip-verifier` has no effect because argparse does not auto-generate the negation for `store_true`. Step 11 is permanently disabled.
**Fix:** Change to `action=argparse.BooleanOptionalAction, default=True`.

### H-6 | `visaul_pipeline_runner.py` lines 622–671
`process_single_visual()` is defined but never called — dead code from the old per-visual architecture. Any bug fixes applied here have zero effect on runtime behaviour.
**Fix:** Delete the function.

### H-7 | `visaul_pipeline_runner.py` lines 741–750
L0 phase saves packets to disk even when `l0.skip = True`. Downstream phases (L1/L2/L3) may then pick up stale empty packets.
**Fix:** Check `l0.skip` before writing; skip the save when True.

### H-8 | `visaul_pipeline_runner.py` lines 840–843
If `TF_API_KEY` or `TF_BASE_URL` is not set in the environment, `OpenAI(api_key=..., base_url=...)` raises `KeyError` with no user-friendly message.
**Fix:** Validate env vars at startup using `utils/env_check.py` `assert_env()` before creating the client.

### H-9 | Multiple files — JSON loads without error handling
Corrupted or partially written JSON files crash the pipeline with a raw `JSONDecodeError` and no context about which file failed or which stage wrote it.
Files affected:
- `visaul_pipeline_runner.py` lines 159, 166, 225
- `visual_parserL3_storymaking.py` line 108–110 (catches `FileNotFoundError` but not `JSONDecodeError`)
- `glossary_generator.py` lines 48, 56, 67, 72, 87
- `faq_generator.py` lines 54, 78, 88
- `document_assembler_step5.py` lines 517–525

**Fix pattern:**
```python
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except (json.JSONDecodeError, FileNotFoundError) as e:
    print(f"[ERROR] Cannot read {path}: {e}")
    sys.exit(1)
```

---

## Section 3 — Performance Bottlenecks

### P-1 | `widget_group_writer_step3.py` line 369
A new `OpenAI` client is created per widget inside `ThreadPoolExecutor`. N widgets = N TCP connections opened. Clients do not share a rate-limit pool.
**Fix:** Create one client before the executor; pass it into all workers via a closure or argument.

### P-2 | `visaul_pipeline_runner.py` ~line 845
`enrich_and_split()` runs on every invocation with no cache check. Re-processes all visuals from disk even when nothing changed. Adds 5–30s of redundant I/O per run.
**Fix:** Check if `enriched_pages/*.json` already exist and are newer than `visuals.json`; skip if so.

### P-3 | `funnel_mapper_step1.py` lines 508–582
Retry loop has no exponential backoff. 3 retries fire immediately. If the issue is a rate-limit, all 3 attempts land in the same window and all fail.
**Fix:** Add `time.sleep(2 ** attempt)` between retries, or replace entire `call_llm()` with `llm_chat()` which handles this via tenacity automatically.

### P-4 | `Page_wise/runner.py` — sequential steps
Steps 0 through 5 are fully sequential with no cross-page parallelism. Step 3 (widget generation) parallelises within a page, but pages are processed one at a time.
**Fix:** Pages are independent after step 1 completes. Wrap step 3 per-page calls in a `ThreadPoolExecutor` at the runner level.

### P-5 | `dashboard_overview_generator.py`
Loads all `enriched_pages/*.json` into memory at once before building the prompt.
**Fix:** Stream one page at a time; extract only the fields the prompt needs (page name, visual titles, measure names).

### P-6 | `llm_fallback_step10.py` line 52
`WORKERS = 5` hardcoded. Cannot tune parallelism without editing source.
**Fix:** Expose as `--workers N` CLI argument.

### P-7 | `metric_catalog_step12.py` line 73
Same — `WORKERS = 5` hardcoded.
**Fix:** Expose as `--workers N` CLI argument.

---

## Section 4 — Fault Tolerance Gaps

### F-1 | All LLM callers outside `llm_client.py`
`dashboard_overview_generator.py`, `filter_story_guidemaker.py`, and `funnel_mapper_step1.py` all instantiate a raw `OpenAI` client directly. Zero retry on transient errors. One network blip kills the step permanently.
**Fix:** All LLM calls go through `llm_chat()` in `utils/llm_client.py`. That file already has tenacity retry (5 attempts, 4s→60s backoff). Nothing else should create OpenAI clients.

### F-2 | `funnel_connector_step4.py` — retry sends same prompt on parse failure
JSON parse failure retries 3 times but sends the identical prompt each time. LLM produced malformed JSON for that prompt once; it will likely produce the same malformed output again.
**Fix:** On parse failure, append a correction instruction before retrying:
```python
user_msg += "\n\nYour previous response was not valid JSON. Return JSON only. No markdown fences."
```

### F-3 | `Page_wise/runner.py` — no output validation between steps
No per-step output validation. If step N produces an empty or malformed file, step N+1 crashes with an opaque error with no pointer to step N as the root cause.
**Fix:** After each step subprocess completes with exit code 0, assert the expected output file exists and parses as valid JSON before invoking step N+1.

### F-4 | `visaul_pipeline_runner.py` — no L1/L2/L3 checkpoints
If the runner crashes mid-phase (OOM, timeout, API exhaustion), the entire page restarts from L0 on the next run. All completed L1/L2/L3 packets for that page are re-generated.
**Fix:** Before calling the LLM for L1/L2/L3, check if `l1_packets/<page>/<visual_id>.json` already exists on disk. Skip if present. L0 already does this — extend the same pattern to L1, L2, L3.

### F-5 | `funnel_mapper_step1.py` — cache written after full generation
The content hash is written to the output file after generation completes. If generation succeeds but the disk write fails, the next run finds no cache and re-generates everything, spending duplicate LLM budget.
**Fix:** Write to a `.tmp` file first; rename to the final path atomically only on full success.

### F-6 | `document_assembler_step5.py` — no protection against corrupted widget files
All `widget_content/*.json` files are loaded before any are used. One corrupted file crashes the entire assembly step, blocking the final document.
**Fix:** Wrap each file load in try/except; log the bad file and continue with a placeholder section so the rest of the document is produced.

### F-7 | No pre-flight checks in `main.py`
Pipeline does not verify that upstream stage outputs exist before starting a downstream stage. If Stage 1 output is missing, Stage 2 fails mid-run with a cryptic `FileNotFoundError`.
**Fix:**
```python
def preflight_stage2(dashboard: str) -> bool:
    p = ROOT / "output" / "dashboards" / dashboard / "stage1" / "schema_sections"
    required = ["measures_resolved.json", "visuals.json", "filters.json"]
    missing = [f for f in required if not (p / f).exists()]
    if missing:
        print(f"[preflight] Missing Stage 1 outputs: {missing}")
        return False
    return True
```

---

## Section 5 — Missing Components (CLAUDE.md roadmap, not yet created)

| # | Component | Impact if missing |
|---|-----------|------------------|
| M-1 | `src/stage3/page_context_builder.py` (Stage 3C) | L1/L2/L3 write visual narratives with no knowledge of what question the page is answering — descriptions, not analysis |
| M-2 | `src/stage3/page_story_assembler.py` (Stage 3H) | No assembled page stories; Word doc uses older Page_wise assembly path |
| M-3 | `src/stage3/orchestrator.py` | Phase-based execution not wired up; `visaul_pipeline_runner.py` still uses broken parallel-per-visual model |
| M-4 | `dashboard_overview.json` (machine-readable) | L1/L2/L3 receive no structured dashboard context; dashboard overview is a write-once dead end |
| M-5 | `prompts/risk-dash/*.txt` | `llm_fallback_step10.py` falls back to inline strings — prompts cannot be edited without touching source code |

---

## Section 6 — Hardcoded / Config Debt

| # | File | Issue |
|---|------|-------|
| D-1 | `dashboard_overview_generator.py` | `filters.json` path hardcoded instead of using `paths.py` |
| D-2 | `filter_story_guidemaker.py` | Same hardcoded path |
| D-3 | `dashboard_overview_generator.py` | Skip list (`"X Axis scatter plot"`, `"Y Axis scatter plot"`) hardcoded in source — belongs in `config/fixes.json` |
| D-4 | `filter_story_guidemaker.py` | `_translate_default()` period-name mapping hardcoded — breaks if new period modes are added |
| D-5 | `widget_group_writer_step3.py` line 554 | `"Overview"` page-ordering rule hardcoded — breaks for non-risk dashboards |
| D-6 | Multiple runners | Same `DASHBOARD_INPUTS` / `DASHBOARD_CONFIGS` dict copied across 5+ runner files — adding a dashboard requires editing all of them and risks drift |

---

## Section 7 — What Is Already Correct

| Component | Notes |
|-----------|-------|
| `utils/llm_client.py` | Tenacity retry (5 attempts, 4s→60s backoff), singleton client, handles `max_completion_tokens` — gold standard; all other callers should route through here |
| `llm_fallback_step10.py` `call_llm()` | Routes through `llm_chat()` correctly |
| `visual_parserL0.py` | Deterministic (no LLM), correct |
| `pipeline_step9.py` DAX→SQL compiler | Internal step chain well-structured |
| `funnel_input_builder_step0.py` | Content-hash caching, robust title resolution, clean output schema |
| `metric_catalog_step12.py` runner | Now sequential after step 10 (fixed 2026-05-13) |
| `max_completion_tokens` in Page_wise | Fixed in all 9 files: funnel_mapper, funnel_connector, widget_group_writer, all 6 Widget processors (2026-05-13) |
| `Page_wise/runner.py` subprocess timeout | `timeout=1800` added to `subprocess.run()` (fixed 2026-05-13) |

---

## Section 8 — Priority Fix Order

### Sprint 1 — Stop the crashes (do these before next run)

| # | Fix | File | Effort |
|---|-----|------|--------|
| 1 | C-1: Delete duplicate `_is_action_page()` | `funnel_mapper_step1.py` lines 102–104 | 2 min |
| 2 | C-4, C-5, C-6: Replace raw OpenAI clients with `llm_chat()` | `funnel_mapper_step1.py`, `dashboard_overview_generator.py`, `filter_story_guidemaker.py` | 1 hr |
| 3 | C-3: Guard `pages_processed[0]` | `document_assembler_step5.py` | 5 min |
| 4 | C-2: Verify and fix import typo | `visaul_pipeline_runner.py` | 5 min |
| 5 | H-8: Validate env vars at startup | `visaul_pipeline_runner.py` | 15 min |

### Sprint 2 — Stop the silent failures

| # | Fix | File | Effort |
|---|-----|------|--------|
| 6 | H-1: Fix `_do_mirror()` visual matching by title+type | `funnel_mapper_step1.py` | 1 hr |
| 7 | H-2: Detect missing widgets after executor | `widget_group_writer_step3.py` | 30 min |
| 8 | F-2: Add correction prompt on JSON parse failure | `funnel_connector_step4.py` | 20 min |
| 9 | F-3: Per-step output validation | `Page_wise/runner.py` | 45 min |
| 10 | H-5: Fix `--skip-verifier` argparse | `metric_dictionary/runner.py` | 10 min |
| 11 | H-6, H-7: Remove dead code; skip-packet save fix | `visaul_pipeline_runner.py` | 20 min |
| 12 | H-9: Wrap JSON loads in try/except | Multiple files | 1 hr |

### Sprint 3 — Speed and resilience

| # | Fix | File | Effort |
|---|-----|------|--------|
| 13 | P-1: Single OpenAI client passed to all workers | `widget_group_writer_step3.py` | 30 min |
| 14 | P-2: Cache check for `enrich_and_split()` | `visaul_pipeline_runner.py` | 30 min |
| 15 | F-4: L1/L2/L3 per-visual checkpoints | `visaul_pipeline_runner.py` | 1 hr |
| 16 | F-6: Wrap JSON loads in assembler | `document_assembler_step5.py` | 20 min |
| 17 | P-6, P-7: Expose `--workers` arg | `llm_fallback_step10.py`, `metric_catalog_step12.py` | 20 min |
| 18 | F-7: Pre-flight checks in `main.py` | `main.py` | 45 min |

### Sprint 4 — Architecture completion (CLAUDE.md roadmap)

| # | Component | Effort |
|---|-----------|--------|
| 19 | Stage 3C: `src/stage3/page_context_builder.py` | 1–2 days |
| 20 | Stage 3B enhancement: produce `dashboard_overview.json` | 2 hr |
| 21 | Stage 3H: `src/stage3/page_story_assembler.py` | 1 day |
| 22 | Stage 3 orchestrator: `src/stage3/orchestrator.py` | 1–2 days |

---

## Section 9 — Pipeline Run State (2026-05-13)

```
Stage 1   Extraction                    WORKING
Stage 2a  DAX to SQL compiler           WORKING
Stage 2b  LLM fallback                  WORKING
Stage 2c  Metric catalog                WORKING (sequential after step 10)
Stage 3-PRE-A  Visual enricher          WORKING
Stage 3-PRE-B  Filter guide             WARNING  — no retry on LLM (C-6)
Stage 3B  Dashboard overview            WARNING  — no retry on LLM (C-5)
Stage 3C  Page context builder          NOT CREATED (M-1)
Stage 3D  L0 extraction                 WORKING
Stage 3E  L1 semantic interpretation    WARNING  — no per-visual checkpoint (F-4)
Stage 3F  L2 cross-visual patterns      WARNING  — no per-visual checkpoint (F-4)
Stage 3G  L3 visual narrative           WARNING  — no per-visual checkpoint (F-4)
Stage 3H  Page story assembler          NOT CREATED (M-2)
Page_wise funnel mapper                 CRITICAL — crashes on API error (C-4); mirror bug (H-1)
Page_wise widget writer                 WARNING  — silent missing widgets (H-2); N clients (P-1)
Page_wise assembler                     WARNING  — IndexError risk (C-3); widget ID collision (H-3)
Stage 4   Word doc                      WORKING
```
