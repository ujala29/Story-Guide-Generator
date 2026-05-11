# Senior Code Review — Story Guide Generator

## Executive Summary

This pipeline is **not production-ready**. The critical Layer 2 entry point (`call_layer2`) exists in two contradictory definitions in the same file: the first at line 76 raises `NotImplementedError`, overriding the real implementation at line 1477 — Python executes both and the later definition silently wins, but this only works by accident. Both L1 and L2 save functions write print statements while leaving the actual file-write commented out, meaning no intermediate packets are persisted to disk for debugging or resume. The top three blockers before senior handoff: (1) resolve the duplicate `call_layer2` definition and the four-argument call-site mismatch in the pipeline runner, (2) fix all remaining `TRUEFOUNDRY_MODEL/API_KEY/BASE_URL` env var references in `visaul_pareserL1.py`, `filter_story_guidemaker.py`, and `dashboard_overview_generator.py`, and (3) replace module-level file I/O in `visaul_pipeline_runner.py` that crashes on import if files are missing.

---

## Pipeline Flow Map

```
Stage 1 — Extraction
  extractor.py::run_extraction()          ✅ works
    └── tmdl_parser.py::TMDLExtractor     ✅ works
    └── dependency_graph.py               ✅ works
    └── visual_parser.py (all classes)    ✅ works
    └── measure_resolver_.py::resolve_all ✅ works  [hardcoded "risk-dash" default path]
    └── _write_section_files()            ✅ works

Stage 2 — Metric Dictionary
  pipeline_step9.py::run_pipeline()       ✅ works  [hardcoded "risk-dash" in OUTPUT_DIR default]
    └── cleaner, lexer, parser, etc.      ✅ works
  llm_fallback_step10.py::run_llm_fallback()
    └── load_prompts()                    ❌ raises FileNotFoundError — prompts/ dir missing
    └── validate_sql / build_sql          ⚠ no retry, no timeout
    └── registry save inside thread       ⚠ threading: _save_reg called inside lock is fine
                                            but api_calls[0] counter non-atomic increment
  metric_catalog_step12.py::run_catalog() ⚠ partial — LLM call has no retry/timeout

Stage 3 — Visual Stories
  visaul_pipeline_runner.py::main()
    └── module-level open(FIXES_PATH)     ❌ crashes on import if file missing
    └── module-level open(MEASURES_RESOLVED_PATH) ❌ same crash
    └── process_page()
          Phase 1: build_l0_packet (parallel)    ✅ works
          Phase 2: call_layer1 (parallel)        ⚠ TRUEFOUNDRY_MODEL env var (wrong key ×6)
                                                   save commented out — no disk persistence
          Phase 3: call_layer2 (4 args passed)  ❌ real call_layer2() at line 1477 takes 3 args
                                                   4th arg (peer L1 list) silently dropped
                                                   save commented out — no disk persistence
          Phase 4: call_layer3 (llm_client=None) ✅ works (no LLM, pure Python)

  visual_parserL2.py
    └── line 76: call_layer2() raises NotImplementedError  ❌ DUPLICATE DEFINITION
    └── line 1477: real call_layer2() (3 args, works)     ⚠ shadows the stub

  visaul_pareserL1.py
    └── 6 LLM calls use TRUEFOUNDRY_MODEL                 ❌ wrong env var
    └── __main__ block uses TRUEFOUNDRY_API_KEY/BASE_URL  ❌ wrong env var

  filter_story_guidemaker.py                              ❌ TRUEFOUNDRY_* env vars
  dashboard_overview_generator.py                         ❌ TRUEFOUNDRY_* env vars

Stage 4 — Document Assembly
  document_assembler_step5.py                             ⚠ reads stage3 output that may not exist
```

---

## Findings

### [BROKEN] Duplicate `call_layer2` definition — stub still present

**File:** `src/Visual_wise/visual_parserL2.py`  **Line:** 76  
**Severity:** Critical  
**What is wrong:** The file contains two `def call_layer2(...)` definitions. The first at line 76 raises `NotImplementedError` with signature `(l0_packet, l1_packet, client, model: str)`. The second, fully implemented version at line 1477 has signature `(l0: L0Packet, l1: L1Packet, llm_client)`. Python silently executes both and the later one wins at runtime. The stub is dead code, but it creates confusion and will cause breakage if the file is refactored.  
**Impact:** If anyone reorders the code, imports only the first definition, or calls the function before line 1477 is parsed, they get `NotImplementedError`.  
**Fix:**
```python
# DELETE lines 76-78 entirely:
# def call_layer2(l0_packet, l1_packet, client, model: str) -> "L2Packet":
#     raise NotImplementedError("Layer 2 LLM logic not yet implemented")
```

---

### [BROKEN] Wrong argument count passed to `call_layer2` in pipeline runner

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Line:** 751-753  
**Severity:** Critical  
**What is wrong:** The pipeline runner calls `call_layer2(active_l0s[vid], active_l1s[vid], llm_client, list(active_l1s.values()))` — four arguments. The real `call_layer2` signature at `visual_parserL2.py:1477` accepts exactly three: `(l0, l1, llm_client)`. Python raises `TypeError` at runtime.  
**Impact:** Every Phase 3 L2 task crashes with `TypeError: call_layer2() takes 3 positional arguments but 4 were given`. The entire Stage 3 pipeline fails for all non-skipped visuals.  
**Fix:**
```python
# In visaul_pipeline_runner.py line 750-754:
futures = {
    ex.submit(
        call_layer2,
        active_l0s[vid], active_l1s[vid],
        llm_client         # remove the 4th arg — call_layer2 doesn't accept peer_l1s
    ): vid
    for vid in active_l1s
}
# Note: if cross-visual L2 reasoning against all peers is needed, the call_layer2
# signature must be updated to accept an optional peer_l1s: list[L1Packet] = None
```

---

### [BROKEN] Wrong env var names in `visaul_pareserL1.py` — 6 call sites

**File:** `src/Visual_wise/visaul_pareserL1.py`  **Lines:** 635, 750, 867, 980, 1114, 1239, 1386, 1387  
**Severity:** Critical  
**What is wrong:** Every `llm_client.chat.completions.create()` call in this file reads `os.environ.get("TRUEFOUNDRY_MODEL", ...)` instead of `os.environ.get("TF_MODEL", ...)`. The `__main__` block also uses `os.environ["TRUEFOUNDRY_API_KEY"]` and `os.environ["TRUEFOUNDRY_BASE_URL"]`. The project's `.env` file only defines `TF_MODEL`, `TF_API_KEY`, and `TF_BASE_URL`. All six visual-type branches (card, table, linechart, barchart, donut, scatter) will use the hardcoded fallback model string `"internal-bedrock/sonnet-46"` or raise `KeyError` from the `__main__` block.  
**Impact:** Model is never read from `.env`. If the fallback model name is invalid for the configured endpoint, every LLM call fails. `__main__` block raises `KeyError` immediately.  
**Fix:**
```python
# Replace all 6 occurrences:
# BEFORE:
model = os.environ.get("TRUEFOUNDRY_MODEL", "internal-bedrock/sonnet-46")
# AFTER:
model = os.environ.get("TF_MODEL", "internal-bedrock/sonnet-46")

# __main__ block (lines 1386-1387):
# BEFORE:
llm_client = OpenAI(
    api_key  = os.environ["TRUEFOUNDRY_API_KEY"],
    base_url = os.environ["TRUEFOUNDRY_BASE_URL"],
)
# AFTER:
llm_client = OpenAI(
    api_key  = os.environ["TF_API_KEY"],
    base_url = os.environ["TF_BASE_URL"],
)
```

---

### [BROKEN] Wrong env var names in `filter_story_guidemaker.py` and `dashboard_overview_generator.py`

**File:** `src/filter_section/filter_story_guidemaker.py`  **Lines:** 201, 232, 233  
**File:** `src/dashboard_overview/dashboard_overview_generator.py`  **Lines:** 169, 200, 201  
**Severity:** Critical  
**What is wrong:** Both files use `TRUEFOUNDRY_MODEL`, `TRUEFOUNDRY_API_KEY`, `TRUEFOUNDRY_BASE_URL` — the wrong env var names. These stages will use the hardcoded fallback or raise `KeyError`.  
**Fix:** Replace all three env var names with `TF_MODEL`, `TF_API_KEY`, `TF_BASE_URL` in both files.

---

### [BROKEN] `load_prompts()` raises `FileNotFoundError` — prompts directory does not exist

**File:** `src/Metric_dictionary/llm_fallback_step10.py`  **Lines:** 353-388, 795-800  
**Severity:** Critical  
**What is wrong:** `run_llm_fallback()` calls `load_prompts(dashboard)` which opens files from `prompts/<dashboard>/*.txt`. The CLAUDE.md explicitly states "prompts/ directory with .txt files — NOT CREATED". The function raises `FileNotFoundError` on first run, and the fallback inline constants (`SCHEMA_CONTEXT_RISK`, `VALIDATOR_SYSTEM`, etc.) defined earlier in the file are never used because the hard raise at line 375 prevents fallback logic.  
**Impact:** `llm_fallback.py` crashes immediately on startup for every dashboard, blocking Stage 2b entirely.  
**Fix:**
```python
def load_prompts(dashboard: str) -> dict:
    d = PROMPTS_DIR / dashboard
    schema_ctx = DASHBOARD_SCHEMA_CONTEXT.get(dashboard, SCHEMA_CONTEXT_RISK)
    defaults = {
        "schema_context":      schema_ctx,
        "schema_rules_only":   schema_ctx,
        "validator_system":    VALIDATOR_SYSTEM,
        "validator_checklist": "Check table, date column, date filter, aggregation.",
        "builder_system":      BUILDER_SYSTEM,
        "definer_system":      DEFINER_SYSTEM,
    }
    if not d.exists():
        return defaults
    prompts = {}
    for key in defaults:
        path = d / f"{key}.txt"
        prompts[key] = path.read_text(encoding="utf-8").strip() if path.exists() else defaults[key]
    return prompts
```

---

### [BROKEN] Module-level file I/O in `visaul_pipeline_runner.py` crashes on import

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Lines:** 149-157  
**Severity:** Critical  
**What is wrong:** At module level (not inside any function), the runner executes:
```python
with open(FIXES_PATH, encoding="utf-8") as f:
    FIXES = json.load(f)
...
with open(MEASURES_RESOLVED_PATH, encoding="utf-8") as f:
    MEASURES_RESOLVED: dict = json.load(f)
```
If `config/fixes.json` or the stage1 output `measures_resolved.json` do not exist, the module raises `FileNotFoundError` on `import`. This also means any test that imports this module without those files present fails before the first test runs.  
**Impact:** Importing the module from any other file or test suite crashes the process.  
**Fix:** Move both opens inside `main()` or inside a `_load_config()` function called at startup, not import time.

---

### [BROKEN] L1 and L2 packet save functions have file write commented out

**File:** `src/Visual_wise/visaul_pareserL1.py`  **Lines:** 1290-1292  
**File:** `src/Visual_wise/visual_parserL2.py`  **Lines:** 1581-1583  
**Severity:** High  
**What is wrong:** Both `save_l1_packet()` and `save_l2_packet()` have the actual `json.dump(...)` call commented out. They only print a status line. No L1 or L2 JSON files are written to disk.  
**Impact:** (1) Pipeline has no checkpoint/resume — crash at visual 47 of 80 means restart from zero with zero recovery artifacts. (2) The `__main__` blocks of both L2 and L3 files try to read L1/L2 JSON files from disk and will find nothing. (3) Debugging is impossible without intermediate state.  
**Fix:**
```python
# In save_l1_packet() — visaul_pareserL1.py lines 1290-1292:
# REMOVE the comment markers:
with open(filepath, "w", encoding="utf-8") as f:
    json.dump(l1_to_dict(packet), f, indent=2, ensure_ascii=False)

# Same pattern in save_l2_packet() — visual_parserL2.py lines 1581-1583
```

---

### [BROKEN] `_l2_from_dict()` self-imports from `visual_parserL2`

**File:** `src/Visual_wise/visual_parserL2.py`  **Line:** 1694  
**Severity:** High  
**What is wrong:** Inside the deserialiser function `_l2_from_dict()`, there is:
```python
from visual_parserL2 import DirectionalRow, DrillStep
```
This is a self-import inside a function inside the same file. `DirectionalRow` and `DrillStep` are defined at lines 42 and 47 of the same file and are already in scope. The import is redundant and causes a circular import if this module is re-imported during testing.  
**Fix:** Delete line 1694 entirely. The classes are already available at module scope.

---

### [BROKEN] `CrossReadPattern` imported from `visual_parserL2` but class does not exist there

**File:** `src/Visual_wise/visual_parserL3_storymaking.py`  **Line:** 23  
**Severity:** High  
**What is wrong:** Line 23 imports `CrossReadPattern` from `visual_parserL2`. In the current (post-rewrite) version of `visual_parserL2.py`, the dataclass is named `CrossReadCombined` (line 806), not `CrossReadPattern`. The old `CrossReadPattern` is only defined in the commented-out section at the top of the file (around line 55). This import will raise `ImportError` at runtime.  
**Fix:**
```python
# In visual_parserL3_storymaking.py line 23:
# BEFORE:
from visual_parserL2 import L2Packet, DirectionalRow, DrillStep, CrossReadPattern
# AFTER:
from visual_parserL2 import L2Packet, DirectionalRow, DrillStep, CrossReadCombined
# Then update all references to CrossReadPattern in this file to CrossReadCombined
```

---

### [BROKEN] `call_layer3` defined but `L3Packet` and `build_markdown` are also only in comments

**File:** `src/Visual_wise/visual_parserL3_storymaking.py`  **Lines:** 2348-2389  
**Severity:** High  
**What is wrong:** `call_layer3()` calls `build_markdown(l0, l1, l2)` and `save_l3_packet(packet, l0)`. These functions must be defined somewhere in the active (non-commented) sections of this ~2700-line file. However, 99% of this file is commented out. The entire `L3Packet` dataclass definition, `build_markdown()`, `save_l3_packet()`, and `_validate()` were verified to be in the bottom commented sections. Only the final `call_layer3` (around line 2348) and a few helper functions near it appear to be live code. The exact boundary needs verification, but if `build_markdown` is still commented out, every L3 call raises `NameError`.  
**Impact:** All L3 output fails with `NameError: name 'build_markdown' is not defined`.

---

### [BROKEN] `load_prompt()` in pipeline runner opens files without context manager

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Lines:** 370-371  
**Severity:** Medium  
**What is wrong:** 
```python
base     = open(base_path,     encoding="utf-8").read()
template = open(template_path, encoding="utf-8").read()
```
Files are opened without `with` blocks, leaving file handles unclosed. On Windows, unclosed handles block file writes. No `try/except` — if either file is missing, the exception propagates upward and kills the visual's thread with a bare traceback.  
**Fix:**
```python
try:
    with open(base_path,     encoding="utf-8") as f: base     = f.read()
    with open(template_path, encoding="utf-8") as f: template = f.read()
except FileNotFoundError:
    return None   # caller already checks for None return
```

---

### [HARDCODED] Dashboard name `"risk-dash"` hardcoded in multiple module-level constants

**File:** `src/Metric_dictionary/llm_fallback_step10.py`  **Lines:** 204-207  
**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Lines:** 44-46  
**File:** `src/Extraction/measure_resolver_.py`  **Line:** 15  
**Severity:** High  
**What is wrong:**
- `llm_fallback_step10.py` lines 204-207: `FINAL_JSON`, `OUTPUT_DIR`, `REGISTRY_PATH`, `UPDATED_FINAL` all hard-code `"risk-dash"` as the default, despite the file supporting multiple dashboards.
- `visaul_pipeline_runner.py` line 44: `MEASURES_RESOLVED_PATH` hard-codes `"risk-dash"` in the path — running this for `pac-dash` reads the wrong measures.
- `measure_resolver_.py` line 15: `DEFAULT_MEASURES_PATH` hard-codes `"risk-dash"` as a module-level default.

**Impact:** Running any stage for `pac-dash` silently reads `risk-dash` data, producing wrong SQL and wrong visual packets with no error.  
**Fix:** Accept `dashboard` as a function parameter and construct paths dynamically:
```python
# In measure_resolver_.py:
def resolve_all(measures_path: str) -> dict:  # already parameterised — no change needed
# Remove the hard-coded DEFAULT_MEASURES_PATH or make it use an env var:
DEFAULT_MEASURES_PATH = Path(os.environ.get(
    "MEASURES_PATH",
    str(SCRIPT_DIR.parent.parent / "output" / "dashboards" / "risk-dash" / ...)
))
```

---

### [HARDCODED] Page filenames and visual type lists hardcoded in `visaul_pipeline_runner.py`

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Lines:** 70-105  
**Severity:** High  
**What is wrong:** `SKIP_FILES`, `DUPLICATE_PAGE_PAIRS`, and `PAGE_COMPARISON_CONTEXT` are hardcoded with specific page filenames (`"additional_dimensions.json"`, `"overview_lm.json"`, `"risk_capture_potential.json"`). These are risk-dash specific. Running this runner against `pac-dash` pages would silently skip or misidentify pages.  
**Impact:** Non-generic. The runner cannot be used for a second dashboard without code changes.  
**Fix:** Move these to a per-dashboard config dict (keyed by dashboard name) or to an external JSON config file in `config/<dashboard>/pipeline_config.json`.

---

### [HARDCODED] Healthcare domain terms baked into LLM system prompts

**File:** `src/Visual_wise/visaul_pareserL1.py`  **Lines:** 124-210 (LAYER1_SYSTEM)  
**File:** `src/Visual_wise/visual_parserL2.py`  **Lines:** 996-1076 (LAYER2_SYSTEM)  
**File:** `src/Metric_dictionary/llm_fallback_step10.py`  **Lines:** 681-691 (DEFINER_SYSTEM)  
**Severity:** Medium  
**What is wrong:** System prompts contain hard references to `"healthcare risk adjustment Power BI dashboard"`, RAF, HCC, recapture rate, CMS, and other domain-specific concepts. These are baked into `LAYER1_SYSTEM`, `LAYER2_SYSTEM`, and `DEFINER_SYSTEM` constants defined at module level. Adding a new dashboard (e.g., PAC dashboard) currently means duplicating all prompts.  
**Impact:** Not usable for a second domain without code changes. A PAC or clinical quality dashboard would receive system instructions about RAF coding.  
**Fix:** Load system prompts from `prompts/<dashboard>/` files (already partially done in `load_prompts()` for Stage 2, but not for Stage 3 layers).

---

### [NO_ERROR_HANDLING] LLM calls in L1/L2 have no retry, no timeout, no error check on response

**File:** `src/Visual_wise/visaul_pareserL1.py`  **Lines:** 631-644 (table branch), 748-758, 864-875, 977-988, 1111-1122, 1236-1247  
**File:** `src/Visual_wise/visual_parserL2.py`  **Lines:** 930-942, 1530-1542  
**Severity:** High  
**What is wrong:** Every `llm_client.chat.completions.create()` call in L1 and L2 is a bare call with no:
- Retry on transient failures (HTTP 429, 503, timeout)
- `timeout=` parameter
- Check that `response.choices` is non-empty before indexing `[0]`
- Handling of `finish_reason == "length"` (truncated response)

If the API returns an empty choices list or a rate-limit error, the code raises `IndexError` or propagates the exception and marks the visual as failed with no retry.  
**Impact:** A single API hiccup during a 3-hour pipeline run fails that visual permanently (no retry).  
**Fix:**
```python
import time

def _call_llm_with_retry(client, model, messages, temperature, max_retries=3):
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages,
                temperature=temperature, timeout=60,
            )
            if not resp.choices:
                raise ValueError("Empty choices list")
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
```

---

### [NO_ERROR_HANDLING] `metric_catalog_step12.py` catches all exceptions and stores error as definition

**File:** `src/Metric_dictionary/metric_catalog_step12.py`  **Lines:** 268-272  
**Severity:** Medium  
**What is wrong:**
```python
except Exception as exc:
    entry["technical_definition"] = f"ERROR: {exc}"
    entry["business_definition"]  = f"ERROR: {exc}"
```
Bare `except Exception` silently converts every failure (network error, JSON parse error, key error) into a string stored as the definition. The catalog output will contain `"ERROR: ..."` strings as if they were real definitions, and downstream stages that read the catalog will receive corrupted data.  
**Impact:** Downstream word document assembly reads these error strings and writes them to the final deliverable document.  
**Fix:** Separate retryable errors (network) from parse errors. Log the full traceback. Store a `None` sentinel instead of an error string, and filter these out before writing catalog output.

---

### [NO_ERROR_HANDLING] `dependency_graph.py::get_depth()` uses mutable default argument

**File:** `src/Extraction/dependency_graph.py`  **Line:** 112  
**Severity:** Medium  
**What is wrong:**
```python
def get_depth(self, name: str, visited: set = None) -> int:
```
Using `None` as default then creating `set()` inside the function is the correct pattern here (the code does this correctly). However, when `build_summary()` calls `self.get_depth(m.name)` for every measure (line 176), each call creates a fresh `visited` set, meaning the recursion for shared dependencies is recomputed from scratch for every measure. On a model with 200+ measures each calling 3-5 shared base measures, `get_depth` is called O(N × depth) times redundantly. Not a bug, but a significant performance issue (see Optimisation section).

---

### [THREADING] Global `_counters` dict reset with direct assignment while threads may be running

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Lines:** 822-824  
**Severity:** High  
**What is wrong:**
```python
_counters["success"] = 0
_counters["skipped"] = 0
_counters["failed"]  = 0
```
This reset happens in `main()` after `discover_pages()` but before the first `process_page()` call, so no threads are running yet — fine in the current single-process flow. However, `_counters` is a global dict and `_increment()` does take a lock. The issue is the counter reset is done without the lock (`_lock`). If `main()` is ever called in a loop or from a test harness that runs it multiple times, a race condition exists.  
**Impact:** Low in current flow. Becomes a real race if `main()` is called concurrently or refactored.  
**Fix:**
```python
with _lock:
    _counters["success"] = 0
    _counters["skipped"] = 0
    _counters["failed"]  = 0
```

---

### [THREADING] `api_calls[0] += 1` in `llm_fallback_step10.py` is a non-atomic increment

**File:** `src/Metric_dictionary/llm_fallback_step10.py`  **Lines:** 939, 1018, 1035, 1107  
**Severity:** Medium  
**What is wrong:** `api_calls = [0]` is a shared mutable list. The increment `api_calls[0] += 1` is done inside `with lock:` blocks, so it is actually protected by `_lock`. This is correct. However, the stats inside `registry["stats"]` are updated with `registry["stats"]["api_calls"] = registry["stats"].get("api_calls", 0) + 1` — a read-modify-write that is also inside the lock, so it is safe. No real bug here, but the lock acquisition pattern is inconsistent: some increments are inside the lock, some summary reads are outside it.

---

### [DUPLICATE] JSON markdown fence stripping code duplicated 6+ times

**File:** `src/Visual_wise/visaul_pareserL1.py`  **Lines:** 482-489, 644-651, 759-766, 877-884, 990-997, 1128-1135**  
**File:** `src/Visual_wise/visual_parserL2.py`  **Lines:** 943-950, 1268-1275**  
**Severity:** Medium  
**What is wrong:** The following block appears at least 8 times across L1, L2, and L3 storymaking:
```python
cleaned = raw.strip()
if cleaned.startswith("```"):
    parts   = cleaned.split("```")
    cleaned = parts[1] if len(parts) > 1 else cleaned
    if cleaned.startswith("json"):
        cleaned = cleaned[4:]
cleaned = cleaned.strip()
```
This is a manual fence-stripper. It has a subtle bug: if the LLM returns ` ```json\n{...}\n``` `, splitting on `"```"` gives `["", "json\n{...}\n", ""]`. `parts[1]` is `"json\n{...}\n"` — the `if cleaned.startswith("json")` then removes the `json` prefix. But if it returns `\`\`\`\n{...}\n\`\`\`` (no language tag), `parts[1]` is `"\n{...}\n"` which doesn't start with `"json"` — this works. However the stripping only handles the opening fence; a trailing ` ``` ` is not stripped.  
**Impact:** Duplicated fragile logic. A fix needs to be applied in 8+ places. One already-working stripper exists in `llm_fallback_step10.py::strip_markdown_fences()` at line 87 which uses a regex and handles both opening and closing fences correctly.  
**Fix:** Extract to a shared utility module `src/utils/llm_utils.py::strip_json_fences(raw: str) -> str` and import it everywhere. Use the regex from `llm_fallback_step10.py`.

---

### [DUPLICATE] `get_client()` / `OpenAI()` instantiation pattern duplicated in 4 files

**File:** `src/Metric_dictionary/llm_fallback_step10.py`  **Lines:** 214-232  
**File:** `src/Metric_dictionary/metric_catalog_step12.py`  **Lines:** 96-104  
**File:** `src/filter_section/filter_story_guidemaker.py`  **Lines:** ~229-234  
**File:** `src/dashboard_overview/dashboard_overview_generator.py`  **Lines:** ~196-202  
**Severity:** Medium  
**What is wrong:** Each file independently reads the same three env vars (`TF_BASE_URL`, `TF_API_KEY`, `TF_MODEL`), validates them, and constructs an `OpenAI()` client. Two of the four files still use `TRUEFOUNDRY_*` (wrong) names. There is no shared client factory.  
**Fix:** Create `src/utils/llm_client.py`:
```python
import os
from openai import OpenAI

def get_llm_client() -> OpenAI:
    base_url = os.getenv("TF_BASE_URL")
    api_key  = os.getenv("TF_API_KEY")
    missing  = [k for k, v in [("TF_BASE_URL", base_url), ("TF_API_KEY", api_key)] if not v]
    if missing:
        raise EnvironmentError(f"Missing env vars: {missing}")
    return OpenAI(base_url=base_url, api_key=api_key)
```

---

### [DUPLICATE] `.env` file loader duplicated verbatim in 4 files

**File:** `src/Metric_dictionary/llm_fallback_step10.py`  **Lines:** 55-67  
**File:** `src/Metric_dictionary/metric_catalog_step12.py`  **Lines:** 53-65  
**Severity:** Low  
**What is wrong:** Both files contain identical 12-line blocks that walk up the directory tree looking for `.env`. This is exactly what `load_dotenv()` with no argument already does. The manual walk-up is duplicated.  
**Fix:** Replace both blocks with `load_dotenv()` — python-dotenv's default search already walks parent directories.

---

### [DUPLICATE] `_l0_from_dict` / `_l1_from_dict` / `_dax_from_dict` defined in 2+ files

**File:** `src/Visual_wise/visaul_pareserL1.py`  **Lines:** 1405-1454 (in `__main__`)  
**File:** `src/Visual_wise/visual_parserL2.py`  **Lines:** 651-697 (commented, in `__main__`)  
**File:** `src/Visual_wise/visual_parserL2.py`  **Lines:** 1693-1718 (`_l2_from_dict`)  
**Severity:** Medium  
**What is wrong:** The reconstruction helpers `_dax_from_dict`, `_l0_from_dict`, and `_l1_from_dict` are defined inside the `__main__` block of `visaul_pareserL1.py` (lines 1405-1454) and duplicated in the `__main__` block of `visual_parserL2.py`. These should be module-level functions in each respective parser file — not buried in `__main__` where they cannot be imported.  
**Fix:** Promote `_l0_from_dict` to module level in `visual_parserL0.py`, `_l1_from_dict` to module level in `visaul_pareserL1.py`, and `_l2_from_dict` to module level in `visual_parserL2.py`, then import them wherever needed.

---

### [DUPLICATE] `_counters` global modified via `_increment()` inside `process_page()` AND directly inside `main()`

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Lines:** 787-789, 796  
**Severity:** Low  
**What is wrong:** Inside `process_page()`, successes/failures call `_increment("success")` and `_increment("failed")` (lines 787, 789). But `stats["skipped"]` is tracked in a local `stats` dict inside `process_page()`, and at line 796, `_counters["skipped"] += skipped_early` is added **directly** without the lock. This is a bare write to a global dict outside the lock.  
**Fix:**
```python
# Replace line 796:
_increment("skipped")  # for each skipped visual, or:
with _lock:
    _counters["skipped"] += skipped_early
```

---

### [OPTIMISATION] `get_all_dep_names()` called per-visual during prompt building, with no memoization

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Lines:** 420-427, 433**  
**Severity:** Medium  
**What is wrong:** `get_all_dep_names(name)` is called once per visual (line 433) and once per peer measure per peer card (lines 439-441). For a page with 15 visuals and 10 peers each with 3 measures, this is 15 + (15 × 10 × 3) = 465 recursive traversals of `MEASURES_RESOLVED`, each re-tracing the same dependency chains from scratch. There is no caching.  
**Before:**
```python
primary_deps = get_all_dep_names(primary["property"])
for peer in peer_cards:
    for m_name in peer["measures"]:
        peer_deps = get_all_dep_names(m_name)
```
**After:**
```python
from functools import lru_cache

@lru_cache(maxsize=None)
def get_all_dep_names_cached(name: str) -> frozenset:
    return frozenset(get_all_dep_names(name))  # existing function unchanged
```

---

### [OPTIMISATION] `MEASURES_RESOLVED` read from disk twice per pipeline run

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Line:** 156-157  
**File:** `src/Visual_wise/visual_parserL0.py`  *(loaded separately at module level in the L0 pre-commented version)*  
**Severity:** Low  
**What is wrong:** `MEASURES_RESOLVED` is loaded at module level in `visaul_pipeline_runner.py` (line 156-157). The file is ~5MB for a 200-measure model. There is only one load, so this is not a repeated read — it is acceptable. However, `visual_parserL0.py` in its active version loads the same file independently. As long as both modules are imported in the same process, the file is read twice.

---

### [OPTIMISATION] `build_page_context(all_visuals)` called once per page, not once globally

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Line:** 702  
**Severity:** Low  
**What is wrong:** `build_page_context(all_visuals)` is called inside `process_page()` after `deduplicate()` is run. The `deduplicated` list is the input to both `build_page_context` and the L0 phase. However, `build_page_context` needs ALL visuals (including the duplicates/skips) to correctly identify peer cards and page layout. Calling it on the deduplicated subset means some peer cards may be omitted from the context.  
**Impact:** L0 packets for cardVisuals may have an incomplete `peer_cards` list if a peer visual was deduplicated away.  
**Fix:**
```python
# Call build_page_context BEFORE deduplication:
page_context = build_page_context(all_visuals)   # ← move before deduplicate()
deduplicated = deduplicate(fixed_visuals)
```

---

### [QUALITY] `TEST_MODE = True` hardcoded in production orchestrator

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Lines:** 61-63  
**Severity:** High  
**What is wrong:**
```python
TEST_MODE        = True
TEST_VISUAL_TYPE = "cardVisual"
TEST_LIMIT       = 0
```
`TEST_MODE` is set to `True` at module level. When `apply_test_filter()` is called (line 701), it filters visuals down to only `cardVisual` type (and all other types with no limit). In production, this means the pipeline processes all visual types regardless — but the intent is unclear. If someone sets `TEST_LIMIT = 3`, they get only 3 cards.  
**Impact:** In current state with `TEST_LIMIT = 0`, all card visuals run. But the flag is misleading. A developer maintaining this will not know whether the pipeline is intentionally in test mode.  
**Fix:**
```python
# Use env var or CLI arg, not a hardcoded flag:
TEST_MODE = os.environ.get("PIPELINE_TEST_MODE", "false").lower() == "true"
```

---

### [QUALITY] `sys.path.insert(0, ...)` hacks in every Visual_wise file

**File:** `src/Visual_wise/visual_parserL2.py`  **Line:** 24  
**File:** `src/Visual_wise/visaul_pareserL1.py`  **Line:** 23  
**File:** `src/Visual_wise/visual_parserL3_storymaking.py`  **Line:** 20  
**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Line:** 11  
**File:** `src/Extraction/extractor.py`  **Lines:** 32-36  
**Severity:** Medium  
**What is wrong:** Every file in `Visual_wise/` and `Extraction/` manually inserts its own parent directory into `sys.path` to enable sibling imports. This is the classic sign of a missing `__init__.py` / package structure. The hacks work locally but fail when files are imported from a different working directory, run via pytest, or packaged.  
**Fix:** Add `__init__.py` to each `src/` subdirectory and install the package in editable mode via `pip install -e .`. Then replace all `sys.path.insert` calls with proper relative imports.

---

### [QUALITY] `process_single_visual()` defined but never called in the phase-based runner

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Lines:** 590-639  
**Severity:** Low  
**What is wrong:** `process_single_visual()` is a function defined between lines 590-639. It runs L0→L1→L2→L3 sequentially for one visual. It is never called in `process_page()` — the phase-based version replaced it. It is dead code.  
**Fix:** Delete lines 590-639 entirely.

---

### [FLOW] Stage 2b (`llm_fallback`) output path differs from Stage 2c (`metric_catalog`) input path

**File:** `src/Metric_dictionary/llm_fallback_step10.py`  **Line:** 207 (`UPDATED_FINAL`)  
**File:** `src/Metric_dictionary/metric_catalog_step12.py`  **Line:** 87 (`llm_json`)  
**Severity:** Medium  
**What is wrong:** `llm_fallback` writes its output to `final_measures_with_llm.json` (line 207). `metric_catalog` reads from the same path. However, both paths are constructed from the same `DASHBOARD_LLM_CONFIGS`/`DASHBOARD_CONFIGS` dict — they match for `risk-dash`. The flow is correct only if the dashboard name is the same in both files. The configs are separately defined in each file with slightly different key names (`llm_json` vs `final_json`), creating a maintenance trap. One file being updated without the other breaks the chain.  
**Fix:** Extract a single `DASHBOARD_OUTPUT_PATHS` dict into a shared `config/dashboard_paths.py` module imported by both files.

---

### [FLOW] No validation that Stage 2 output exists before Stage 3 reads it

**File:** `src/Visual_wise/visaul_pipeline_runner.py`  **Lines:** 44, 156**  
**Severity:** Medium  
**What is wrong:** The pipeline runner hard-codes `MEASURES_RESOLVED_PATH` at line 44 and opens it at module import time (line 156-157). There is no check that Stage 1 has completed or that the file exists — the `open()` raises `FileNotFoundError`. Similarly, `VISUAL_ENRICHER_DIR` at line 46 must contain enriched page JSONs from Stage 3-PRE-A. If Stage 1 has not been run, Stage 3 crashes immediately with no helpful message.  
**Fix:**
```python
def main():
    required = [FIXES_PATH, MEASURES_RESOLVED_PATH]
    missing = [p for p in required if not Path(p).exists()]
    if missing:
        print(f"ERROR: Run Stage 1 first. Missing files:\n" + "\n".join(missing))
        sys.exit(1)
    ...
```

---

## Optimisation Opportunities

### 1. Shared `strip_json_fences()` utility (8 duplicates → 1 function)

**Before** (repeated 8 times across L1, L2):
```python
cleaned = raw.strip()
if cleaned.startswith("```"):
    parts   = cleaned.split("```")
    cleaned = parts[1] if len(parts) > 1 else cleaned
    if cleaned.startswith("json"):
        cleaned = cleaned[4:]
cleaned = cleaned.strip()
```

**After** (single utility, already written in `llm_fallback_step10.py::strip_markdown_fences`):
```python
# src/utils/llm_utils.py
import re

def strip_json_fences(raw: str) -> str:
    """Remove markdown code fences from LLM JSON response."""
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```\s*$", raw, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else raw
```

### 2. `get_depth()` memoization in dependency graph

`build_summary()` calls `get_depth(m.name)` for every measure. For a 200-measure model, `get_depth` recurses into shared base measures thousands of times.

**Before:**
```python
max_dependency_depth = max((self.get_depth(m.name) for m in self.measures), default=0)
```

**After:**
```python
# Cache results in __init__ alongside self.deps:
self._depth_cache: dict[str, int] = {}

def get_depth(self, name: str, visited: set = None) -> int:
    if name in self._depth_cache:
        return self._depth_cache[name]
    if visited is None:
        visited = set()
    if name in visited:
        return 0
    visited.add(name)
    deps = self.deps.get(name, [])
    result = 0 if not deps else 1 + max(self.get_depth(d, visited.copy()) for d in deps)
    self._depth_cache[name] = result
    return result
```

### 3. L2 peer L1 list — pass via a page-scoped context object, not a 4th arg

Currently the pipeline runner passes `list(active_l1s.values())` as a 4th arg that `call_layer2()` doesn't accept. The right fix is a page context dataclass:

```python
@dataclass
class PageL1Context:
    peer_l1s: dict[str, L1Packet]   # vid → L1Packet for all active visuals on this page

# Pass it to call_layer2:
def call_layer2(l0: L0Packet, l1: L1Packet, llm_client, page_context: PageL1Context = None) -> L2Packet:
    peer_l1s = page_context.peer_l1s if page_context else {}
    ...
```

---

## What a Senior Developer Would Do First

1. **Fix the 4-arg `call_layer2` call** in `visaul_pipeline_runner.py` line 753 — the pipeline cannot complete Phase 3 until this is resolved.
2. **Replace all `TRUEFOUNDRY_*` env var references** with `TF_*` across `visaul_pareserL1.py` (6 sites), `filter_story_guidemaker.py`, and `dashboard_overview_generator.py` — no LLM call works until this is done.
3. **Fix `load_prompts()`** to fall back to inline constants when the `prompts/` directory is missing, so Stage 2b is not permanently blocked.
4. **Delete the stub `call_layer2` at line 76** of `visual_parserL2.py` — it is dead code that misleads every reader into thinking L2 is still unimplemented.
5. **Uncomment the file writes** in `save_l1_packet()` and `save_l2_packet()` — without disk persistence, there is no checkpoint/resume and no way to debug intermediate state.
6. **Move module-level file opens in `visaul_pipeline_runner.py`** (lines 149-157) inside `main()` with proper error messages.
7. **Fix the `CrossReadPattern` import** in `visual_parserL3_storymaking.py` line 23 — it imports a class name that no longer exists, causing `ImportError` on load.
8. **Extract `strip_json_fences()` to a shared utility** and replace 8 copies of manual fence-stripping logic.
9. **Move all page-name/file-name config** (`SKIP_FILES`, `DUPLICATE_PAGE_PAIRS`, `PAGE_COMPARISON_CONTEXT`) to an external config file keyed by dashboard name.
10. **Set `TEST_MODE = False`** or replace with an env var, and add a pre-run checklist that validates all input files exist before processing starts.

---

## Period Mode Terminology Bugs — Reviewer: Akash Bhasker (May 8)

**Complaint:** Output says "Last Year" and "Last Month" everywhere Period mode is mentioned.
Should say **YTD** (current year from Jan 1) and **Rolling** (last year's date to current date).

### What YTD and Rolling actually mean

| Label | Meaning |
|-------|---------|
| **YTD** | Year-to-date — data from **January 1 of the current year** to the selected month |
| **Rolling** | Rolling window — data from **the same date last year** to the current date (continuous trailing window) |

Period mode toggles which of these two date windows is used as the **comparison baseline** for all change indicators (▲/▼ tiles). It does **not** affect the primary KPI values themselves.

---

### Bug A — Root Cause: System prompt has the wrong answer hardcoded inside it

**File:** [prompt/prompts/system_prompt/prompt_for_filter.txt](prompt/prompts/system_prompt/prompt_for_filter.txt)
**Lines:** 14, 30, 37

`load_filter_prompt()` in `filter_story_guidemaker.py` concatenates `base_context.txt` and `prompt_for_filter.txt` and sends them as the **system prompt**. The `prompt_for_filter.txt` is not a set of instructions — it is a fully pre-filled example of the complete filter guide, with specific rows and bullets already written out. The LLM reads this pre-filled content as its reference and copies the terminology from it when generating new output.

That pre-filled content has three wrong entries:

| Line | What it says now | What it should say |
|------|-----------------|-------------------|
| 14 | `Period mode \| ... toggle between Last Year and Last Month \| Last Year` | toggle between **YTD** and **Rolling** \| default: **YTD** |
| 30 | "switching between **Last Year** and **Last Month** changes the ▲/▼ tiles" | switching between **YTD** and **Rolling**... |
| 37 | "Period mode is set to **Last Year**, change percentages will be year-over-year" | "...set to **YTD** = calendar year to date; **Rolling** = last year's date to today" |

**Why this is the root cause:** The LLM does not invent "Last Year" — it reads it from your own system prompt and reproduces it faithfully. Fixing filters.json or the user prompt alone will not fix this. The example in the system prompt wins.

---

### Bug B — Raw Power BI default values flow through with no translation

**File:** [src/filter_section/filter_story_guidemaker.py](src/filter_section/filter_story_guidemaker.py)
**Lines:** 113–121 (`build_filter_prompt`)

The user prompt is built by dumping raw slicer metadata from `filters.json` directly:

```python
f"default: {f['default_value'] or 'All'}"
```

Power BI stores the slicer's default selection as a raw internal string. For the Period mode slicer, `default_value` in `filters.json` is `"Last Year"`. There is no mapping, no translation, and no instruction to the LLM to interpret what these values mean in business terms. So even after Bug A is fixed, the LLM receives `default: Last Year` in the user message and may echo it back.

**What is missing:** A pre-processing map or a vocabulary note in the user prompt:
```
Period mode values: "Last Year" = YTD (current year from Jan 1), "Last Month" = Rolling (last year to current date)
```

---

### Bug C — Wrong environment variables in `filter_story_guidemaker.py` (causes crash)

**File:** [src/filter_section/filter_story_guidemaker.py](src/filter_section/filter_story_guidemaker.py)
**Lines:** 201, 233, 234

```python
# Line 201 — wrong
model=os.environ.get("TRUEFOUNDRY_MODEL", "internal-bedrock/sonnet-46")

# Lines 233–234 — wrong
api_key=os.environ["TRUEFOUNDRY_API_KEY"],
base_url=os.environ["TRUEFOUNDRY_BASE_URL"],
```

The correct env vars throughout this project are `TF_MODEL`, `TF_API_KEY`, `TF_BASE_URL`. This same fix was applied to other files (per CLAUDE.md) but was **missed in `filter_story_guidemaker.py`**. The `OpenAI()` constructor at line 233 raises `KeyError` immediately because `TRUEFOUNDRY_API_KEY` is never set — the filter guide never runs at all.

---

### Bug D — `TRUEFOUNDRY_MODEL` still present in `visaul_pareserL1.py` table path

**File:** [src/Visual_wise/visaul_pareserL1.py](src/Visual_wise/visaul_pareserL1.py)
**Line:** 636

```python
model = os.environ.get("TRUEFOUNDRY_MODEL", "internal-bedrock/sonnet-46")
```

CLAUDE.md records this fixed in "3 places" in this file, but `_call_layer1_table()` — the path for all **table-type visuals** (Payer/Plan details, PCP details) — was not among them. It silently falls back to the hardcoded string instead of reading `TF_MODEL` from `.env`.

---

### Bug E — Architectural: `prompt_for_filter.txt` is a filled example disguised as instructions

**Files:** [prompt/prompts/system_prompt/prompt_for_filter.txt](prompt/prompts/system_prompt/prompt_for_filter.txt), [src/filter_section/filter_story_guidemaker.py](src/filter_section/filter_story_guidemaker.py)

The file is structured as a **completed document** — it has the full filter reference table, interaction rules, and common mistakes already written with specific values. This is sent as the system prompt. Any factual error in that example becomes a factual error in every generated output, regardless of what the actual filter data shows. The correct design is to put format/tone/domain **instructions** in the system prompt and provide the actual filter data only in the user message.

---

### Period Mode Bug Summary

| # | File | Line(s) | Bug | Impact |
|---|------|---------|-----|--------|
| A | `prompt/prompts/system_prompt/prompt_for_filter.txt` | 14, 30, 37 | Hardcoded "Last Year"/"Last Month" in system prompt example | **Direct cause of all review feedback** |
| B | `src/filter_section/filter_story_guidemaker.py` | 113–121 | Raw Power BI `default_value` passed to LLM with no mapping | Secondary cause — echoes back Power BI internal strings |
| C | `src/filter_section/filter_story_guidemaker.py` | 201, 233, 234 | `TRUEFOUNDRY_*` env vars → should be `TF_*` | Filter guide crashes on startup; never runs |
| D | `src/Visual_wise/visaul_pareserL1.py` | 636 | `TRUEFOUNDRY_MODEL` in `_call_layer1_table()` not fixed | Table visuals silently use hardcoded fallback model |
| E | `prompt_for_filter.txt` design | all | System prompt is a filled example, not instructions | Wrong values in example propagate to all future output |