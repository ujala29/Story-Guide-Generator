# measure_resolver_.py — Measure Chain Resolver

## Purpose
Takes the flat `measures.json` list (output of Stage 1 extraction) and builds a **recursive dependency chain** for every measure — showing the full chain of DAX calls from root measure down to leaf columns. The output `measures_resolved.json` is used by downstream stages (Visual_wise, Page_wise) to give the LLM full DAX context per measure.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `measures.json` — flat list of `MeasureSchema` objects with `depends_on` already populated |
| **Output** | `measures_resolved.json` — dict: `{measure_name: chain_object}` |

Each `chain_object` is a nested tree showing: measure name → DAX → depth → columns referenced → child chains (recursively).

---

## How It's Called

**Automatic path** (normal run):
```
extractor.py → _write_section_files() → resolve_all(measures_json_path)
```
Called automatically at the end of Stage 1. Writes `measures_resolved.json` into `schema_sections/`.

**CLI path** (direct run for debugging):
```bash
python measure_resolver_.py                        # uses DEFAULT_MEASURES_PATH (risk-dash)
python measure_resolver_.py path/to/measures.json  # custom path
```

---

## Function Flow

```
resolve_all(measures_path)
  ├── load_measures(measures_path)         → lookup dict: {name → measure_object}
  └── for each name in lookup:
        build_chain(name, lookup)          → nested chain dict
        chain_to_string(chain)             → human-readable string
        → stored as {name: {chain, chain_string}}
  └── returns full resolved dict

build_chain(name, lookup, visited)
  ├── if name in visited → return circular reference stub
  ├── lookup[name] → get deps[]
  └── recursively call build_chain for each dep
        → returns nested dict with dax, table, depth, referenced_columns, depends_on[]

chain_to_string(chain, indent)
  └── formats the nested chain as indented text tree
        root:    "MeasureName  [depth: N]"
                 "  -> DAX expression"
        child:   "  L-- ChildMeasure"
                 "       -> DAX"
        leaf:    "       -> raw columns: col1, col2"
```

---

## Function Details

### `load_measures(path) → dict`
Loads `measures.json`. Handles two formats:
- `list` — direct array of measure objects
- `dict` with `"measures"` key — wrapped format

Returns `{name: measure_object}` lookup dict.

### `build_chain(name, lookup, visited=None) → dict`
Recursively builds the dependency chain for one measure.

- **Cycle guard**: if `name` in `visited`, returns a stub with `"note": "circular reference"` instead of recursing
- **Missing measure**: if `name` not in `lookup`, returns stub with `"depth": -1`
- **Normal case**: returns full dict with `measure_name`, `table`, `dax`, `depth`, `is_leaf`, `referenced_columns`, and `depends_on` (each element is itself a recursive `build_chain()` result)

### `chain_to_string(chain, indent=0) → str`
Formats a chain dict as a human-readable indented text tree. Used for developer inspection and LLM context injection.

- Root level (indent=0): shows measure name + depth + DAX
- Child levels: indented `L--` prefix + DAX
- Leaf nodes: shows raw column references

### `resolve_all(measures_path) → dict`
Main entry point. Calls `load_measures()` then `build_chain()` for every measure. Returns:
```python
{
  "MeasureName": {
    "chain":        { nested chain object },
    "chain_string": "human-readable text tree"
  },
  ...
}
```
Only the `chain` part is saved to `measures_resolved.json` (not `chain_string`).

---

## File Connections

**No imports from other Extraction files** — this module only uses `json`, `sys`, `pathlib`.

**Called by:** `extractor.py` → `_write_section_files()` → `resolve_all(measures_json_path)`

**Output consumed by:**
- `src/Visual_wise/` — L0/L1/L2 parsers use `measures_resolved.json` for full DAX context
- `src/Page_wise/` — widget processors inject resolved chains into LLM prompts

---

## Hardcoded Parts (Change for New Dashboards)

### `DEFAULT_MEASURES_PATH` (line ~15)
```python
DEFAULT_MEASURES_PATH = SCRIPT_DIR.parent.parent / "output" / "dashboards" / "risk-dash" / "extraction" / "schema_sections" / "measures.json"
```
This hardcoded path is **only used when running `measure_resolver_.py` directly from the CLI** (for debugging). It points to `risk-dash`.

When called via `extractor.py` (the normal path), the actual `measures.json` path is passed as an argument — this default is never used.

**To debug a different dashboard directly:**
```bash
python measure_resolver_.py output/dashboards/pac-dash/extraction/schema_sections/measures.json
```

### Sample names in `__main__` block (lines ~141–147)
```python
sample_names = [
    "#Members YoY Color",
    "Documented risk MoM Card",
    "Gap to potential risk",
    "Potential risk PY",
]
```
These are **risk-dash measure names** used only for CLI sample output. They have no effect on actual processing — safe to ignore for other dashboards.
