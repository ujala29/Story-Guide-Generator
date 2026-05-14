# visual_enricher_with_resolved_dax_adder_L0.py — Enricher + Page Splitter

## Purpose
Pre-processing step before any layer runs. Reads `visuals.json` and `measures_resolved.json`, attaches `measure_chains` to every visual, then saves two outputs: one combined `visuals_enriched.json` and one JSON per page under `enriched_pages/`.

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `output/dashboards/<dash>/extraction/schema_sections/visuals.json` — flat list of all visuals |
| **Input B** | `output/dashboards/<dash>/extraction/schema_sections/measures_resolved.json` — resolved DAX chains keyed by measure name |
| **Output A** | `output/dashboards/<dash>/visual_wise/visuals_enriched.json` — all visuals with `measure_chains` added |
| **Output B** | `output/dashboards/<dash>/visual_wise/enriched_pages/<safe_page_name>.json` — one file per page |

---

## Pipeline Steps

```
Step 1  load visuals.json + measures_resolved.json
Step 2  [per visual] attach measure_chains
Step 3  save visuals_enriched.json
Step 4  group visuals by page
Step 5  [per page] save enriched_pages/<page>.json
```

---

## Function Flow

```
enrich_and_split(visuals_path, resolved_path, out_dir)
  ├── load visuals (list or {"visuals": [...]} format)
  ├── load resolved measures
  ├── [per visual]
  │     ├── [per m_ref in measures_used]
  │     │     ├── strip table prefix: m_ref.split(".", 1)[1]
  │     │     ├── resolved.get(measure_name)
  │     │     └── if not found: stub chain with dax_summary="not found"
  │     └── append {**visual, "measure_chains": [...]}
  ├── save visuals_enriched.json  (parent of out_dir)
  ├── group by visual["page"]
  └── [per page]
        ├── sanitize page name  → lower, spaces→_, strip special chars
        ├── build payload: {page, visual_count, visuals}
        └── save out_dir/<safe_name>.json
```

---

## Function Details

### `enrich_and_split(visuals_path, resolved_path, out_dir) → dict`
Main (and only) function. Returns `{page_name: [visuals]}` dict. Prints warnings for unresolved measures but does NOT crash — missing measures get a stub chain with `"Measure definition not found in resolved measures"`.

**Stub chain shape (when measure not in resolved):**
```python
{
  "measure_name"    : measure_name,
  "table"           : "unknown",
  "dax_summary"     : "Measure definition not found in resolved measures",
  "business_meaning": "",
  "depth"           : -1,
  "depends_on"      : []
}
```

**Page file payload shape:**
```python
{
  "page"         : "Overview LY",
  "visual_count" : 14,
  "visuals"      : [...]
}
```

---

## File Connections

| Imports from | Used for |
|---|---|
| `pathlib.Path` | file I/O |
| `collections.defaultdict` | grouping visuals by page |

**Called by:** `visaul_pipeline_runner.py` `main()` — runs before page discovery

---

## Hardcoded Parts (Change for New Dashboards)

### Measure name strip logic (line ~43)
```python
measure_name = m_ref.split(".", 1)[1] if "." in m_ref else m_ref
```
Strips the table prefix (e.g. `ALL_DAX.RAF recapture rate` → `RAF recapture rate`). This works for both `TABLE.measure` and plain `measure` formats. After the extraction fix, PAC measures no longer carry the `ALL_DAX_PAC.` prefix in `measures_used`, so this split is a safety fallback.

### Page name sanitization (line ~84)
```python
safe_name = re.sub(r'[\\/*?:"<>|]', "", page.strip())
safe_name = re.sub(r'\s+', "_", safe_name).lower()
```
Converts display page name (e.g. "Main page LY") to a filesystem-safe filename (e.g. `main_page_ly.json`). If two pages produce the same safe name, the second one overwrites the first — ensure unique page names in Power BI.
