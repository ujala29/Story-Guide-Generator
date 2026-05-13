# Production Readiness — Story Guide Generator

Audit date: 2026-05-13  
Audited by: Claude Code (automated line-level scan)

---

## Priority Legend

| Label | Meaning |
|-------|---------|
| 🔴 CRITICAL | Will crash or silently corrupt output in production |
| 🟠 HIGH | Will cause hard-to-debug failures under real load |
| 🟡 MEDIUM | Reduces maintainability / observability |
| 🟢 LOW | Nice-to-have improvements |

---

## 🔴 CRITICAL

---

---



---

## 🟠 HIGH

### H-1 — JSON loads without error handling

Corrupted or partially written JSON files will crash the pipeline mid-run with a raw `JSONDecodeError` and no context about which file failed.

| File | Line(s) | Issue |
|------|---------|-------|
| `src/Visual_wise/visaul_pipeline_runner.py` | 159 | `json.load(FIXES)` — no try/except |
| `src/Visual_wise/visaul_pipeline_runner.py` | 166 | `json.load(MEASURES_RESOLVED)` — no try/except |
| `src/Visual_wise/visaul_pipeline_runner.py` | 225 | `json.loads(fpath.read_text(...))` inside page loop — no try/except |
| `src/Visual_wise/visual_parserL3_storymaking.py` | 108–110 | catches `FileNotFoundError` but not `JSONDecodeError` |
| `src/glossary_faq/glossary_generator.py` | 48, 56, 67, 72, 87 | multiple `json.load(f)` in `collect_terms()` |
| `src/glossary_faq/faq_generator.py` | 54, 78, 88 | `json.load(f)` in `collect_faq_signals()` |

**Fix pattern:**
```python
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
except json.JSONDecodeError as e:
    print(f"ERROR: Malformed JSON in {path}: {e}")
    sys.exit(1)
except FileNotFoundError:
    print(f"ERROR: File not found: {path}")
    sys.exit(1)
```

---

### H-2 — Subprocess calls without timeout

Long-running subprocesses (LLM calls, Snowflake queries) can hang indefinitely. The parent process waits forever with no watchdog.

| File | Line(s) | Call |
|------|---------|------|
| `main.py` | 52 | `subprocess.run(cmd, check=False)` |
| `main.py` | 78–84 | `subprocess.Popen(cmd, ...)` — `.join()` with no timeout |
| `src/Visual_wise/runner.py` | 43 | `subprocess.run(cmd, env=env, check=False)` |
| `src/filter_section/runner.py` | 26 | `subprocess.run(cmd, check=False, ...)` |
| `src/dashboard_overview/runner.py` | ~60 | `subprocess.run(...)` |
| `src/Page_wise/runner.py` | 42 | `subprocess.run(cmd, check=False)` |
| `src/glossary_faq/runner.py` | 26 | `subprocess.run(cmd, check=False, ...)` |
| `src/Metric_dictionary/runner.py` | 48, 71 | `subprocess.run()` and `subprocess.Popen()` |

**Fix:** Add `timeout=` to all `subprocess.run()` calls. For `Popen`, add timeout to `.join()`:
```python
# subprocess.run
result = subprocess.run(cmd, check=False, timeout=1800)  # 30 min max

# threading join with timeout
for t in threads:
    t.join(timeout=1800)
    if t.is_alive():
        print(f"[main] WARNING: thread still running after 30min timeout")
```

---

### H-3 — Prompt files read with no error handling

If the `prompt/system_prompt/` directory or any `.txt` file is missing, the pipeline crashes with an unhandled `FileNotFoundError` mid-run.

| File | Line(s) | Issue |
|------|---------|-------|
| `src/Visual_wise/visaul_pipeline_runner.py` | 381–385 | `open(base_path)` and `open(template_path)` — no try/except |
| `src/filter_section/filter_story_guidemaker.py` | 102–104 | `(PROMPT_DIR / "base_context.txt").read_text()` — no error handling |
| `src/dashboard_overview/dashboard_overview_generator.py` | 128–130 | `(PROMPT_DIR / "base_context.txt").read_text()` |
| `src/glossary_faq/glossary_generator.py` | ~55 | prompt file read without guard |
| `src/glossary_faq/faq_generator.py` | ~40 | prompt file read without guard |

**Fix:** Validate prompt directory exists at startup:
```python
def assert_prompts(prompt_dir: Path):
    if not prompt_dir.exists():
        print(f"ERROR: Prompt directory not found: {prompt_dir}")
        print("Ensure prompt/system_prompt/ is present and populated.")
        sys.exit(1)
```

---

### H-4 — Duplicate DASHBOARD_CONFIGS across 7 files

The same dashboard name → path mapping is repeated in every runner. Adding a third dashboard requires editing 7+ files and risks them going out of sync.

| File | Line(s) |
|------|---------|
| `src/Extraction/runner.py` | 24–35 |
| `src/Extraction/extractor.py` | 254–265 |
| `src/Visual_wise/runner.py` | 19–22 |
| `src/filter_section/runner.py` | 35–38 |
| `src/dashboard_overview/runner.py` | 33–36 |
| `main.py` | 41 |
| `src/Metric_dictionary/runner.py` | (internal pipeline config) |

**Fix:** Create `src/config.py` as the single source of truth:
```python
# src/config.py
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

DASHBOARDS = {
    "risk-dash": {
        "semantic_model": ROOT / "input" / "Risk-Management-v4_Insights_v1.SemanticModel",
        "report":         ROOT / "input" / "Risk-Management-v4_Insights_v1.Report",
    },
    "pac-dash": {
        "semantic_model": ROOT / "input" / "PAC-v4_Insights_v1.SemanticModel",
        "report":         ROOT / "input" / "PAC-v4_Insights_v1.Report",
    },
}
```
All runners import from `src/config.py`.

---

## 🟡 MEDIUM

### M-1 — No logging module (print-only)

Every file uses only `print()`. In production there is no way to: set log levels, write to a file, filter noise, or correlate logs across parallel stages.

| Files affected | All source files — 15+ files |
|----------------|-------------------------------|

**Fix:** Add a shared logger setup in `src/utils/logger.py`:
```python
import logging, sys

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(h)
    logger.setLevel(logging.INFO)
    return logger
```

Replace `print(...)` with `logger.info(...)` / `logger.error(...)` / `logger.warning(...)`.

---

### M-2 — No `.env.example` file

New developers have no reference for what variables to set. The project will silently fail or crash in non-obvious ways.

**Location:** Project root — file does not exist

**Fix:** Create `.env.example`:
```
TF_BASE_URL=https://truefoundry...
TF_API_KEY=your-api-key-here
TF_MODEL=internal-bedrock/sonnet-46

SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_WAREHOUSE=
SNOWFLAKE_DATABASE=
SNOWFLAKE_SCHEMA=

# Pipeline settings
STORY_TEST_MODE=0
STORY_TEST_VISUAL_TYPE=cardVisual
STORY_TEST_LIMIT=0
```

---

### M-3 — STORY_DASHBOARD env var set before import but re-read after

`visaul_pipeline_runner.py` line 12 calls `os.environ.setdefault(...)` but then line 48 does `DASHBOARD = os.environ["STORY_DASHBOARD"]`. If the module is imported (not `__main__`) without the env var set, the `setdefault` on line 12 runs first, which is fine — but this is fragile ordering that will confuse future developers.

| File | Line(s) |
|------|---------|
| `src/Visual_wise/visaul_pipeline_runner.py` | 12 and 48 |

**Fix:** Replace line 48 with `DASHBOARD = os.environ.get("STORY_DASHBOARD", "risk-dash")` and remove the `setdefault` on line 12.

---

### M-4 — Broad exception handlers that hide failures

| File | Line(s) | Issue |
|------|---------|-------|
| `src/Extraction/extractor.py` | 29–31 | `except Exception: pass` silently swallows stdout encoding errors |
| `src/Visual_wise/visaul_pipeline_runner.py` | 647–652 | `except Exception as e:` marks visual as "failed" but pipeline continues — output is silently incomplete |
| `src/Visual_wise/visaul_pareserL1.py` | 1500–1509 | Catches all exceptions and prints but does not propagate |

**Fix:** At minimum, log the exception type + stack trace. For visual failures, write a `<visual_id>_FAILED.md` sentinel file so the assembler can flag missing visuals instead of silently skipping them.

---

---

### M-6 — No pre-flight check before pipeline starts

The pipeline does not verify that upstream stage outputs exist before starting a downstream stage. If Stage 1 output is missing, Stage 2 will fail mid-run with a cryptic `FileNotFoundError`.

| File | Needed at |
|------|-----------|
| `main.py` | Before each `stage_fn()` call |

**Fix:** Add a preflight check per stage:
```python
def check_stage1_output(dashboard: str) -> bool:
    p = ROOT / "output" / "dashboards" / dashboard / "stage1" / "schema_sections"
    required = ["measures_resolved.json", "visuals.json", "filters.json"]
    missing = [f for f in required if not (p / f).exists()]
    if missing:
        print(f"[preflight] Missing Stage 1 outputs for {dashboard}: {missing}")
        return False
    return True
```

---

## 🟢 LOW

### L-1 — Large JSON files read entirely into memory

| File | Line(s) | File read |
|------|---------|-----------|
| `src/Visual_wise/visaul_pipeline_runner.py` | 225 | Entire enriched page JSON |
| `src/Visual_wise/visaul_pareserL1.py` | 1171–1172 | L0 packet JSON |
| `src/Visual_wise/visual_parserL3_storymaking.py` | 1171–1172 | L0/L1/L2 packet JSONs |

For current dashboard sizes this is fine, but for large dashboards (100+ visuals) this will spike memory. No fix needed immediately — flag for future if dashboard grows.

---

### L-2 — Race condition in `_run_parallel` in main.py

| File | Line(s) |
|------|---------|
| `main.py` | 96–103 |

`first_fail = 0` is written from the main thread after all procs finish (`proc.wait()` is sequential). Not actually a race — safe as written. But the variable should be a `threading.Lock`-protected value if the pattern ever moves to concurrent `.wait()` calls.

---

### L-3 — No Dockerfile or deployment manifest

**Location:** Project root — no `Dockerfile`, `docker-compose.yml`, or cloud deployment config

For true production deployment, a minimal `Dockerfile` is needed:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["python", "main.py"]
```

---

## Recommended Fix Order

Do these first — they are the ones most likely to cause silent failures or hard crashes:

| Priority | Fix | Effort |
|----------|-----|--------|
| 1 | **C-1** Create `requirements.txt` | 30 min |
| 2 | **C-3** Add `assert_env()` at startup in `main.py` + each runner | 1 hr |
| 3 | **C-2** Add `tenacity` retry wrapper to all LLM calls | 2–3 hr |
| 4 | **C-4** Wire `TEST_MODE` to env var in `visaul_pipeline_runner.py` line 71 | 15 min |
| 5 | **H-1** Wrap all `json.load()` calls with try/except | 1 hr |
| 6 | **H-3** Add prompt directory existence check at startup | 30 min |
| 7 | **H-4** Consolidate dashboard configs into `src/config.py` | 1 hr |
| 8 | **H-2** Add `timeout=1800` to all `subprocess.run()` calls | 30 min |
| 9 | **M-2** Create `.env.example` | 15 min |
| 10 | **M-6** Add preflight checks to `main.py` | 1 hr |
| 11 | **M-1** Replace `print()` with `logging` | 2–4 hr |
| 12 | **L-3** Add `Dockerfile` | 30 min |
