# runner.py — Stage 1 Entry Point

## Purpose
Command-line entry point for Stage 1 (Extraction). Reads dashboard config from `utils/config.py`, resolves output paths via `utils/paths.py`, and delegates to `extractor.py`.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `--dashboard` CLI arg (`risk-dash` / `pac-dash` / `all`) |
| **Reads from** | `utils/config.py` → `DASHBOARDS` dict (semantic model path, report path) |
| **Reads from** | `utils/paths.py` → `get_paths(dash)` → resolves `stage1_schema` output path |
| **Output** | Calls `run_extraction()` which writes `extracted_schema.json` + section files |

---

## How to Run

```bash
python src/Extraction/runner.py                      # all dashboards
python src/Extraction/runner.py --dashboard risk-dash
python src/Extraction/runner.py --dashboard pac-dash
```

---

## Function Flow

```
main()
  ├── parse --dashboard arg
  ├── loop over dashboards
  │     ├── DASHBOARDS.get(dash)        ← reads src/utils/config.py
  │     ├── get_paths(dash)             ← reads src/utils/paths.py
  │     └── run_extraction(
  │               semantic_model_path,
  │               report_path,
  │               output_path=p.stage1_schema
  │           )                         ← calls extractor.py
  └── print "Done."
```

---

## Function Details

### `main()`
- Parses `--dashboard` arg; defaults to `"all"`
- Looks up each dashboard in `DASHBOARDS` dict — exits with error if unknown
- Calls `get_paths(dash)` to get the typed output path object
- Calls `run_extraction()` — that function internally also calls `resolve_all()` (measure resolver) and writes `measures_resolved.json`

---

## File Connections

| Imports from | Used for |
|---|---|
| `extractor.py` | `run_extraction()` — the actual work |
| `utils/config.py` | `DASHBOARDS`, `ALL_DASHBOARDS`, `ROOT` constants |
| `utils/paths.py` | `get_paths(dash)` → typed path object |

---

## Hardcoded Parts (Change for New Dashboards)

> **None in this file.** All dashboard configs live in `utils/config.py`.
> To add a new dashboard, add it to `DASHBOARDS` in `src/utils/config.py` — runner picks it up automatically.
