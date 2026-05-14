# runner.py — Page_wise Pipeline Entry Point

## Purpose
CLI entry point for Stage 3 (Page_wise). Runs all 5 steps in order for a given dashboard by launching each step as a subprocess. Supports `--force` to bypass caches, `--from-step` to resume mid-pipeline, and `--workers` to control LLM parallelism in Step 3.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `--dashboard` (default: `risk-dash`), `--force`, `--from-step N`, `--workers N` |
| **Final output** | `output/dashboards/<dashboard>/page_wise/final_story_guide.md` |

---

## How to Run

```bash
python src/Page_wise/runner.py                          # risk-dash, all steps
python src/Page_wise/runner.py --dashboard pac-dash
python src/Page_wise/runner.py --force                  # bypass all caches
python src/Page_wise/runner.py --from-step 3            # resume from step 3
python src/Page_wise/runner.py --workers 5              # more parallel LLM calls in step 3
```

---

## Steps Executed (in order)

| Step | Label | Script |
|---|---|---|
| 0 | Build funnel input | `funnel_input_builder_step0.py` |
| 1 | Map funnel | `funnel_mapper_step1.py` |
| 3 | Write widget groups | `widget_group_writer_step3.py` |
| 4 | Connect funnel | `funnel_connector_step4.py` |
| 5 | Assemble document | `document_assembler_step5.py` |

> **Note:** There is no Step 2 — numbering is intentional to leave room for future insertion.

Steps that accept `--force`: `funnel_mapper_step1.py`, `widget_group_writer_step3.py`, `funnel_connector_step4.py`

---

## Function Flow

```
main()
  ├── parse args
  ├── assert_env()
  └── for each step in STEPS:
        if step_num < from_step → SKIP (print and continue)
        build cmd_args = ["--dashboard", dash]
        if step == widget_group_writer → add ["--all", "--workers", N]
        if force and step in SUPPORTS_FORCE → add ["--force"]
        run_step(script_name, cmd_args)
          └── subprocess.run(timeout=1800)
                exits on non-zero returncode
```

---

## Function Details

### `run_step(script_name, cmd_args)`
Runs a script as a subprocess using `sys.executable`. 30-minute timeout. Exits immediately on non-zero return code — downstream steps require upstream to succeed.

### `main()`
Parses args, validates env, loops over `STEPS` list. For `widget_group_writer_step3.py` always passes `--all` (process all pages) plus the `--workers` value.

---

## File Connections

| Imports from | Used for |
|---|---|
| `utils/env_check.py` | `assert_env()` — validates env vars before running |

**Called by:** `main.py` Stage 3

---

## Hardcoded Parts (Change for New Dashboards)

### Default dashboard (line ~69)
```python
parser.add_argument("--dashboard", default="risk-dash", ...)
```
Default `risk-dash` only applies when running `runner.py` directly. `main.py` always passes `--dashboard` explicitly.

### STEPS list (line ~39)
```python
STEPS = [
    (0, "Build funnel input",  "funnel_input_builder_step0.py"),
    (1, "Map funnel",          "funnel_mapper_step1.py"),
    (3, "Write widget groups", "widget_group_writer_step3.py"),
    (4, "Connect funnel",      "funnel_connector_step4.py"),
    (5, "Assemble document",   "document_assembler_step5.py"),
]
```
Step numbers and scripts are fixed. If a new step is added, insert it here.

### Timeout (line ~56)
```python
result = subprocess.run(cmd, check=False, timeout=1800)
```
30 minutes. Step 3 (widget writer) with many pages and few workers could approach this. Increase if needed.
