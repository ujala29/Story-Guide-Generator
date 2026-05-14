# runner.py — Visual_wise Entry Point

## Purpose
Parses CLI arguments and launches `visaul_pipeline_runner.py` as a subprocess with `STORY_DASHBOARD` and `STORY_TEST_MODE` env vars set. One subprocess per dashboard.

---

## Input / Output

| | Detail |
|---|---|
| **CLI args** | `--dashboard risk-dash\|pac-dash\|all`, `--no-test` |
| **Env vars set** | `STORY_DASHBOARD=<dash>`, `STORY_TEST_MODE=1\|0` |
| **Delegates to** | `visaul_pipeline_runner.py` (subprocess, timeout=1800s) |

---

## Pipeline Steps

```
Step 1  parse_args()         → --dashboard, --no-test
Step 2  assert_env()         → check TF_API_KEY, TF_BASE_URL, TF_MODEL
Step 3  [per dashboard]
        run_dashboard()      → set env vars, launch subprocess
```

---

## Function Flow

```
main()
  ├── argparse: --dashboard (default "all"), --no-test (default test_mode=True)
  ├── assert_env()           ← from utils.env_check
  ├── expand dashboards      ← ALL_DASHBOARDS if "all"
  └── [per dash] run_dashboard(dash, test_mode)
        ├── env["STORY_DASHBOARD"] = dash
        ├── env["STORY_TEST_MODE"] = "1" | "0"
        └── subprocess.run(visaul_pipeline_runner.py, timeout=1800)
              → exit 1 on timeout or non-zero returncode
```

---

## Function Details

### `run_dashboard(dashboard, test_mode) → None`
Sets `STORY_DASHBOARD` + `STORY_TEST_MODE` in env, then runs `visaul_pipeline_runner.py` as a subprocess. Exits with the child's returncode on failure. Timeout is hardcoded to 1800s (30 minutes).

### `main() → None`
Parses `--dashboard` and `--no-test`, validates env, iterates over dashboards.

---

## File Connections

| Imports from | Used for |
|---|---|
| `utils.env_check` | `assert_env()` — validates TF_* env vars |
| `utils.config` | `ALL_DASHBOARDS` — list of all known dashboards |

**Called by:** `main.py` Stage 2 (spawns this as a subprocess)

---

## Hardcoded Parts (Change for New Dashboards)

### Timeout (line ~53)
```python
result = subprocess.run(cmd, env=env, check=False, timeout=1800)
```
30-minute timeout. For very large dashboards with many pages and visuals, increase this.

### Default test mode (line ~71)
```python
parser.add_argument("--no-test", dest="test_mode", action="store_false", default=True)
```
Test mode is ON by default. Pass `--no-test` for a full run. Change `default=True` to `default=False` to flip the default permanently.
