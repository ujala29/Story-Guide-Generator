# tmdl_parser.py — TMDL File Parser

## Purpose
Reads the Power BI `.SemanticModel` folder and extracts all **tables**, **columns**, **DAX measures**, and **relationships** by parsing raw TMDL text files. This is the first parser called in Stage 1.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | Path to `.SemanticModel` folder |
| **Reads** | `definition/tables/*.tmdl` — one file per table |
| **Reads** | `definition/relationships.tmdl` — all model relationships |
| **Output** | `list[TableSchema]` — each table with its columns + measures |
| **Output** | `list[RelationshipSchema]` — all table-to-table foreign key links |
| **Output** | `list[MeasureSchema]` (flattened from all tables via `extract_all_measures`) |

---

## TMDL Format Notes
- Indentation uses **TAB (`\t`)** — all regex patterns use `\t`, not spaces
- One `.tmdl` file = one table (columns + measures + Power Query)
- Relationships are in a single file: `definition/relationships.tmdl`
- Three DAX encoding formats exist (Format A/B/C) — all handled

---

## Function Flow

```
TMDLExtractor(semantic_model_path)
  ├── __init__()
  │     └── sets self.root, self.tables_dir, self.rel_file
  │
  ├── extract_tables()
  │     └── loops *.tmdl files
  │           └── _parse_table_file(path)
  │                 ├── _get_table_name()        → table name string
  │                 ├── _parse_columns()          → list[ColumnSchema]
  │                 ├── _parse_measures()         → list[MeasureSchema]
  │                 ├── _parse_power_query()      → M expression or None
  │                 └── _classify_table()         → "source" | "measure_container" | "parameter" | "static_lookup"
  │
  ├── extract_all_measures(tables)
  │     └── flattens t.measures for all tables → list[MeasureSchema]
  │
  └── extract_relationships()
        └── reads relationships.tmdl
              └── _parse_relationships(content)
                    ├── splits on "relationship" keyword
                    └── per block: _get_prop() + _split_tc()
```

---

## Function Details

### `__init__(semantic_model_path)`
Sets up `self.root`, `self.tables_dir`, `self.rel_file`. Asserts that the tables directory exists — fails fast if path is wrong.

### `extract_tables() → list[TableSchema]`
Iterates all `.tmdl` files alphabetically. Skips auto-generated hidden date tables (`LocalDateTable_*`, `DateTableTemplate_*`). Calls `_parse_table_file()` for each.

### `extract_all_measures(tables) → list[MeasureSchema]`
Flattens `table.measures` from all tables into a single list. Needed by `MeasureDependencyGraph` which works across all tables.

### `extract_relationships() → list[RelationshipSchema]`
Reads `relationships.tmdl`. Returns empty list if file doesn't exist (some models have no relationships). Calls `_parse_relationships()`.

### `_classify_table(name, columns, measures, power_query) → str`
Classifies each table into one of 4 types:

| Type | Detection Logic |
|---|---|
| `measure_container` | Name matches `MEASURE_CONTAINER_NAMES` OR has measures but zero physical columns |
| `parameter` | Name in `PARAM_TABLES` OR name starts with `"static"` OR contains `"parameter"`, `"x axis"`, `"y axis"` |
| `static_lookup` | Power Query contains `#table` / `{` / `table {` AND has no database connector keywords |
| `source` | Everything else — real data table (e.g. Snowflake-connected) |

### `_parse_table_file(path) → TableSchema`
Full parse pipeline for one `.tmdl` file. Order: name → columns → measures → Power Query → classify.

### `_get_table_name(lines, fallback) → str`
Matches the first `table 'Name'` or `table Name` line. Falls back to the filename stem.

### `_parse_measures(lines, table_name) → list[MeasureSchema]`
Line-by-line state machine. Handles all 3 DAX encoding formats:

| Format | Pattern | How parsed |
|---|---|---|
| A (single line) | `measure 'Name' = EXPRESSION` | Takes everything after `=` |
| B (backtick fence) | ` measure 'Name' = ``` ` | Collects lines until closing ` ``` ` |
| C (bare multiline) | `measure 'Name' =` (empty after `=`) | Collects indented lines until next TMDL keyword or metadata line |

After extracting DAX, looks ahead 5 lines to check for `isHidden = true`.
Calls `_tables_from_dax()` and `_cols_from_dax()` to extract references.

### `_parse_columns(lines, table_name) → list[ColumnSchema]`
Extracts column declarations. Detects `dataType`, `calculatedTableColumn`/`type: calculated`, and `expression` property to determine if a column is calculated.

### `_parse_power_query(lines) → Optional[str]`
Looks for M (Power Query) expression in two patterns:
1. `type = m ... ``` expression ```
2. `expression = ``` ... ```

Used by `_classify_table()` to detect static lookup tables.

### `_parse_relationships(content) → list[RelationshipSchema]`
Splits on `relationship` keyword boundaries. For each block extracts `fromColumn`, `toColumn`, `crossFilteringBehavior`, `isActive`. Skips blocks involving auto-generated date tables.

### `_tables_from_dax(dax) → list[str]`
Regex extracts table names from `'TableName'[Col]` and `TableName[Col]` patterns. Returns deduplicated list.

### `_cols_from_dax(dax) → list[str]`
Regex extracts full `Table[Column]` references. Returns deduplicated list.

### `_get_prop(block, key) → Optional[str]`
Generic key-value extractor: finds `key: value` in a text block.

### `_split_tc(raw) → tuple[str, str]`
Splits `"TableName.ColumnName"` into `("TableName", "ColumnName")`.

---

## File Connections

| Imports from | Used for |
|---|---|
| `models.py` | `ColumnSchema`, `MeasureSchema`, `TableSchema`, `RelationshipSchema` |

**Called by:** `extractor.py` → `run_extraction()` (Step 1)

---

## Hardcoded Parts (Change for New Dashboards)

### `PARAM_TABLES` (line ~43)
```python
PARAM_TABLES = {
    "parameter", "x axis scatter plot", "y axis scatter plot",
    "static_observation_window_table", "static_observation_win",
}
```
These are **risk-dash / pac-dash specific** table names. If a new dashboard has different parameter table names, add them here. Otherwise those tables will be classified as `"source"` instead of `"parameter"`.

### `MEASURE_CONTAINER_NAMES` (line ~55)
```python
MEASURE_CONTAINER_NAMES = {
    "all_dax_pac", "all_dax", "measures", "_measures",
    "key measures", "dax measures", "dax",
}
```
If a new dashboard stores measures in a table with a different name (e.g. `"kpi_measures"`), add it here. Same set is duplicated in `visual_parser.py` as `_MEASURE_CONTAINER_TABLES`.

### `AUTO_DATE_PREFIXES` (line ~51)
```python
AUTO_DATE_PREFIXES = ("LocalDateTable_", "DateTableTemplate_")
```
Power BI auto-generated hidden tables. These are standard across all Power BI files — unlikely to need changes.

### `_classify_table()` — static_lookup detection (line ~137)
```python
has_hardcode = any(k in pq for k in ['#table', '{"', "table {"])
no_db        = not any(k in pq for k in ["snowflake", "sql", "odbc", "oledb", "server"])
```
If a new dashboard uses a different database connector (e.g. BigQuery, Databricks), add its connector keyword to the `no_db` check list. Otherwise static lookup detection may misclassify source tables.
