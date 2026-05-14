# runner.py — Glossary & FAQ Entry Point

## Purpose
CLI entry point for Stage 4 glossary and FAQ generation. Runs `glossary_generator.py` and `faq_generator.py` sequentially. Both generators are independent (they share the same inputs but don't depend on each other's output), so sequential execution is fine.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `--dashboard` CLI arg (default: `risk-dash`) |
| **Input** | `--skip-glossary` / `--skip-faq` flags to run only one |
| **Output** | Delegates to `glossary_generator.py` → `glossary.md` |
| **Output** | Delegates to `faq_generator.py` → `faq.md` |
| **Output dir** | `output/dashboards/<dashboard>/glossary_faq/` |

---

## How to Run

```bash
python src/glossary_faq/runner.py                        # risk-dash, both
python src/glossary_faq/runner.py --dashboard pac-dash
python src/glossary_faq/runner.py --skip-glossary        # FAQ only
python src/glossary_faq/runner.py --skip-faq             # Glossary only
```

---

## Function Flow

```
main()
  ├── parse args (--dashboard, --skip-glossary, --skip-faq)
  ├── assert_env()                   ← validates TF_API_KEY, TF_BASE_URL, TF_MODEL
  ├── if not skip_glossary:
  │     _run("glossary", "glossary_generator.py", ["--dashboard", dash])
  │           └── subprocess.run → exits if non-zero return code
  └── if not skip_faq:
        _run("faq", "faq_generator.py", ["--dashboard", dash])
              └── subprocess.run → exits if non-zero return code

_run(label, script, extra_args)
  ├── builds command: [python, script_path] + extra_args
  ├── subprocess.run with timeout=1800 (30 min)
  └── returns returncode
```

---

## Function Details

### `_run(label, script, extra_args) → int`
Runs a Python script as a subprocess. Uses `sys.executable` so the same Python interpreter is used. `cwd` is set to the `glossary_faq/` folder so relative imports work. 30-minute timeout guard. Returns exit code — `main()` stops on non-zero.

### `main()`
Parses args, calls `assert_env()` to fail fast if env vars are missing, then conditionally runs each generator. Prints the output paths on success.

---

## File Connections

| Imports from | Used for |
|---|---|
| `utils/env_check.py` | `assert_env()` — validates required env vars before running |

**Calls (as subprocesses):**
- `glossary_generator.py`
- `faq_generator.py`

**Called by:** `main.py` Stage 4 (in parallel with `dashboard_overview`)

---

## Hardcoded Parts (Change for New Dashboards)

### Default dashboard (line ~53)
```python
parser.add_argument("--dashboard", default="risk-dash", ...)
```
Default is `risk-dash`. When called from `main.py`, the `--dashboard` arg is always passed explicitly — this default only applies when running `runner.py` directly.

### Timeout (line ~41)
```python
result = subprocess.run(cmd, check=False, cwd=str(HERE), timeout=1800)
```
30-minute timeout. If a new dashboard has vastly more metrics and the LLM call takes longer (unlikely), increase this value.
