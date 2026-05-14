# snowflake_verifier_step11.py — Snowflake Verifier (Step 11)

## Purpose
Optional step — **skipped by default** in `runner.py`. Reads `final_measures.json`, runs each measure's `sql_query` against Snowflake, and compares the result to a `DAX_GROUND_TRUTH` dict populated from DAX Studio. Writes a `verification_report.json` with pass/fail status and delta percentage.

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `output/dashboards/risk-dash/metric_dictionary/final_measures.json` |
| **Input B** | `DAX_GROUND_TRUTH` dict (hardcoded in file — values from DAX Studio) |
| **Input C** | Snowflake connection env vars (see below) |
| **Output** | `output/dashboards/risk-dash/metric_dictionary/verification_report.json` |

---

## How to Run

```bash
python src/Metric_dictionary/snowflake_verifier_step11.py
python src/Metric_dictionary/snowflake_verifier_step11.py --limit 10     # first 10 measures only
python src/Metric_dictionary/snowflake_verifier_step11.py --measure "#Members"
python src/Metric_dictionary/snowflake_verifier_step11.py --dry-run       # print SQL, don't run
```

---

## Required Environment Variables

```
SNOWFLAKE_ACCOUNT    e.g. xyz12345.us-east-1
SNOWFLAKE_USER
SNOWFLAKE_PASSWORD
SNOWFLAKE_DATABASE
SNOWFLAKE_SCHEMA
SNOWFLAKE_WAREHOUSE
SNOWFLAKE_ROLE       (optional)
SNOWFLAKE_HOST       (optional — for Satoricyber proxy)
```

---

## Function Flow

```
main()
  ├── get_connection()
  │     reads SNOWFLAKE_* env vars
  │     handles both direct Snowflake and Satoricyber proxy (SNOWFLAKE_HOST)
  │     returns snowflake.connector.connect(...)
  │
  ├── load final_measures.json
  ├── filter to measures with sql_query + entry in DAX_GROUND_TRUTH
  │
  ├── for each measure (up to --limit):
  │     run_query(conn, sql_query)     → (result_value, duration_ms)
  │     compare_result(result, ground_truth_value, TOLERANCE_PCT)
  │     → pass / fail / delta_pct
  │
  └── write verification_report.json
        {passed, failed, skipped, per_measure_results}
```

---

## Function Details

### `get_connection()`
Creates Snowflake connector using env vars. Supports Satoricyber proxy: if `SNOWFLAKE_HOST` is set (full proxy URL), extracts account from the first 3 segments of the hostname. Exits with clear error message if any required env var is missing.

### `run_query(conn, sql) → (value, duration_ms)`
Executes the SQL, fetches the first row/column. Returns `(None, duration_ms)` on error. Dry-run mode prints SQL and returns without executing.

### `compare_result(actual, expected, tolerance) → (pass/fail, delta_pct)`
Computes percentage difference. Pass if `abs(delta) <= TOLERANCE_PCT`. `TOLERANCE_PCT = 0.1` (0.1%).

---

## `DAX_GROUND_TRUTH` (Hardcoded)

```python
DAX_GROUND_TRUTH = {
    "Members"          : 2_390_624,
    "#Members"         : 2_390_624,
    "Documented risk"  : 0.7647413105392060,
    "Potential risk"   : 0.9652988774408191,
    "PMPM"             : 478.878443395427,
    "Risk recapture rate": 0.492157006902749,
    # add more from DAX Studio...
}
```
These are unfiltered values from DAX Studio with `ALL()` applied. Only measures listed here are verified — all others are skipped.

---

## File Connections

| Imports from | Used by |
|---|---|
| `snowflake.connector` (optional) | Snowflake queries — graceful ImportError if not installed |

**Called by:** `runner.py` as Step 11 — only if `--no-skip-verifier` flag is passed

---

## Hardcoded Parts (Change for New Dashboards)

### `FINAL_JSON` / `OUTPUT_DIR` (line ~62)
```python
FINAL_JSON  = BASE_DIR / "output/dashboards/risk-dash/metric_dictionary/final_measures.json"
OUTPUT_DIR  = BASE_DIR / "output/dashboards/risk-dash/metric_dictionary"
```
Currently hardcoded to `risk-dash`. Add `--dashboard` CLI arg support and path selection if this step needs to run on other dashboards.

### `DAX_GROUND_TRUTH` (line ~73)
Populate with expected unfiltered values from DAX Studio before running. Empty entries leave those measures unverified. Add new dashboard's measures + ground truth values when adding a dashboard.

### `TOLERANCE_PCT = 0.1` (line ~87)
Allowed percentage difference between SQL result and DAX Studio ground truth. Increase if floating-point rounding differences cause false failures.
