# relationship_parser.py — Relationship Parser (Standalone)

## Purpose
Stateless parser for the `relationships.tmdl` file. Extracts all foreign-key relationships between tables and returns them as `RelationshipSchema` objects.

> **Note on current usage**: This file defines a `RelationshipParser` class, but `tmdl_parser.py` contains its own internal `_parse_relationships()` method that does the same job. The `extractor.py` pipeline currently calls `tmdl_parser.py`'s internal version. `relationship_parser.py` exists as a standalone reusable module for direct use or future refactoring.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | Raw text content of `relationships.tmdl` file (passed as string) |
| **Output** | `list[RelationshipSchema]` — one per relationship block found |

---

## Function Flow

```
RelationshipParser.parse(content)          ← class method, main entry point
  ├── re.split on "relationship" keyword boundary
  └── for each block:
        RelationshipParser._parse_block(block)
          ├── _get_prop(block, "fromColumn")  → "TableA.ColumnA"
          ├── _get_prop(block, "toColumn")    → "TableB.ColumnB"
          ├── _split_table_col(from_raw)      → ("TableA", "ColumnA")
          ├── _split_table_col(to_raw)        → ("TableB", "ColumnB")
          ├── _get_prop(block, "crossFilteringBehavior") → direction
          ├── regex check for "isActive: false"
          └── returns RelationshipSchema(...)
```

---

## Function Details

### `parse(content) → list[RelationshipSchema]` (classmethod)
Main entry point. Splits the full file content into individual relationship blocks using `re.split(r"(?=^relationship\s)", ...)`. The lookahead keeps the `relationship` keyword at the start of each chunk. Skips the preamble before the first block. Delegates each block to `_parse_block()`.

### `_parse_block(block) → Optional[RelationshipSchema]` (classmethod)
Extracts 4 pieces of information from one relationship block:
- `fromColumn` → many-side table + column
- `toColumn` → one-side table + column
- `crossFilteringBehavior` → filter direction (defaults to `"singleDirection"` if absent)
- `isActive: false` → whether relationship is inactive (defaults to active)

Returns `None` if either `fromColumn` or `toColumn` is missing (malformed block).

### `_get_prop(block, key) → Optional[str]` (classmethod)
Finds a `key: value` line inside a block and returns the value string. Uses regex `^\s*{key}\s*:\s*(.+)$`.

### `_split_table_col(raw) → tuple[str, str]` (classmethod)
Splits `"TableName.ColumnName"` on the first `.`. If no dot found, returns `(raw, "")`.

---

## File Connections

| Imports from | Used for |
|---|---|
| `models.py` | `RelationshipSchema` (via relative import `.models`) |

**Note**: Uses relative import (`.models`) — must be imported from within the `Extraction` package, not run as a standalone script.

---

## Hardcoded Parts (Change for New Dashboards)

> **None.** This parser is fully generic — it reads whatever relationships exist in the TMDL file without any hardcoded table or column names.
