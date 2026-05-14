# runner.py — Metric Dictionary Entry Point

## Purpose
Command-line entry point for the Metric Dictionary pipeline (Stage 2). Runs steps 9 → 10 → 12 sequentially as subprocesses. Step 11 (Snowflake verifier) is skipped by default.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `--dashboard` CLI arg (default: `risk-dash`) |
| **Input** | `--from-step` CLI arg to resume mid-pipeline (values: 9, 10, 11, 12) |
| **Output** | Delegates to each step script — see individual step MDs for outputs |

---

## How to Run

```bash
python src/Metric_dictionary/runner.py                        # risk-dash, all steps
python src/Metric_dictionary/runner.py --dashboard pac-dash
python src/Metric_dictionary/runner.py --dashboard all        # every dashboard
python src/Metric_dictionary/runner.py --skip-verifier        # skip step 11 (default)
python src/Metric_dictionary/runner.py --skip-catalog         # skip step 12
python src/Metric_dictionary/runner.py --dry-run              # no LLM / Snowflake calls
python src/Metric_dictionary/runner.py --from-step 10         # resume from llm_fallback
```

---

## Function Flow

```
main()
  ├── assert_env()              ← validates TF_API_KEY / TF_BASE_URL / TF_MODEL
  ├── [step 9]  _run("pipeline",  "pipeline_step9.py",  --dashboard <dash>)
  ├── [step 10] _run("llm_fallback", "llm_fallback_step10.py", --dashboard <dash>)
  ├── [step 12] _run("catalog", "metric_catalog_step12.py", --dashboard <dash>)
  │                             ← skipped if --skip-catalog
  └── [step 11] _run("verifier", "snowflake_verifier_step11.py")
                                ← skipped unless --no-skip-verifier
```

---

## Function Details

### `_run(label, script, extra_args) → int`
Runs a script as a subprocess using `subprocess.run()`. Streams output directly. Times out after 30 minutes. Returns exit code — runner calls `sys.exit(rc)` if non-zero.

### `main()`
Parses CLI args, calls `assert_env()` (unless `--dry-run`), then calls `_run()` for each enabled step in order.

---

## File Connections

| Imports from | Used for |
|---|---|
| `utils/env_check.py` | `assert_env()` — validates required env vars |

**Called by:** `main.py` Stage 2 (parallel with `Visual_wise` and `filter_section`)

---

## Hardcoded Parts (Change for New Dashboards)

> **None in this file.** Dashboard paths are resolved inside each step script.
> To add a new dashboard, update `DASHBOARD_INPUTS` / `DASHBOARD_SF_MAPS` in `pipeline_step9.py` and `DASHBOARD_LLM_CONFIGS` in `llm_fallback_step10.py`.
