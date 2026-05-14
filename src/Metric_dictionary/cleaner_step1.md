# cleaner_step1.py — DAX Cleaner (Step 1)

## Purpose
Takes a raw DAX string and returns a `CleanResult`. This is the first transformation step — downstream lexer and parser **only ever see `clean_dax`**, never the raw string. The cleaner never raises; all issues are captured in `CleanResult.warnings`.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | Raw DAX string from `measures_resolved.json → measure["dax"]` |
| **Output** | `CleanResult` dataclass (always returned, never `None`, never exception) |

---

## What It Does

| Step | Action | Edge case |
|---|---|---|
| 1 | Strip `formatString`, `lineageTag`, `annotation` metadata lines | EC5, EC14 |
| 2 | Strip `//` comment lines — captured in `stripped_comments` | EC6, EC15 |
| 3 | Strip `+0` suffix | EC1 |
| 4 | Normalize DAX keywords to UPPERCASE (`sum` → `SUM`, `var` → `VAR`, etc.) | — |
| 5 | Normalize whitespace (collapse blank lines, strip trailing spaces) | — |
| 6 | Detect hardcoded string measures (`INFO_TEXT`) | — |
| 7 | Detect known typos in string values — warn, pass through | EC22, EC20 |

---

## `CleanResult` Schema

```python
measure_name:        str           # display name
raw_dax:             str           # original untouched DAX
clean_dax:           str           # cleaned DAX ready for lexer
is_hardcoded_string: bool          # True if entire DAX is a string literal
stripped_comments:   list[str]     # // lines removed (may reveal hidden intent)
warnings:            list[str]     # human-readable warnings (typos, suspicious patterns)
had_metadata:        bool          # True if formatString/lineageTag were stripped
had_plus_zero:       bool          # True if +0 suffix was stripped (EC1)
```

---

## Function Flow

```
clean(measure_name, raw_dax) → CleanResult
  ├── remove_metadata_lines(dax)        → (dax, had_metadata)
  │     strips: formatString, lineageTag, annotation PBI_FormatHint
  ├── remove_commented_lines(dax)       → (dax, stripped_comments)
  │     strips: // comment lines; captures them for inspection
  ├── remove_trailing_plus_zero(dax)    → (dax, had_plus_zero)
  │     strips: +0 suffix (EC1)
  ├── normalize_keywords(dax)           → dax
  │     uppercases all keywords in NORMALIZE_KEYWORDS list
  ├── normalize_whitespace(dax)         → dax
  │     collapses blank lines, strips trailing spaces
  ├── is_hardcoded_string(dax)          → bool
  │     True if entire clean_dax is a string literal
  └── detect_typos(dax)                 → list[str]  (warnings)
        checks for KNOWN_TYPOS values inside string literals
```

---

## Function Details

### `remove_metadata_lines(dax) → (str, bool)`
Strips Power BI metadata injected at the end of DAX strings. Looks for `formatString:`, `lineageTag:`, `annotation` lines. Returns `had_metadata=True` if any were found.

### `remove_commented_lines(dax) → (str, list[str])`
Removes `//` comment lines. Captures them in a list — EC15 notes these sometimes contain commented-out alternate DAX that may reveal hidden intent.

### `remove_trailing_plus_zero(dax) → (str, bool)`
Strips `+ 0` or `+0` appended to some DAX measures (EC1). Returns `had_plus_zero=True` if stripped.

### `normalize_keywords(dax) → str`
Case-insensitive replace of all entries in `NORMALIZE_KEYWORDS` to their UPPERCASE forms. Handles whole-word matching to avoid replacing substrings.

### `normalize_whitespace(dax) → str`
Collapses multiple consecutive blank lines to one; strips trailing spaces from each line.

### `is_hardcoded_string(dax) → bool`
Returns `True` if the cleaned DAX is just a string literal (starts/ends with `"` or `'`). These become `INFO_TEXT` / `HARDCODED_STRING` in scope_classifier.

### `detect_typos(dax) → list[str]`
Checks for known bad string values in `KNOWN_TYPOS`. Warns but does NOT correct — SQL must match whatever the database actually contains.

---

## `NORMALIZE_KEYWORDS` List
Covers: `SUM`, `CALCULATE`, `DIVIDE`, `COUNTROWS`, `DISTINCTCOUNT`, `MAX`, `MIN`, `AVERAGE`, `FILTER`, `KEEPFILTERS`, `RETURN`, `VAR`, `IF`, `ISBLANK`, `SWITCH`, `TRUE`, `FALSE`, `SAMEPERIODLASTYEAR`, `PREVIOUSMONTH`, `DATEADD`, `ALLEXCEPT`, `ALL`, `VALUES`, `SELECTEDVALUE`, `HASONEVALUE`, `ABS`, `FORMAT`, `UNICHAR`, `CONCATENATE`, `BLANK`, `SUMMARIZE`, `ADDCOLUMNS`, `TOPN`, `RANKX`, `COUNT`, `IN`.

## `KNOWN_TYPOS` Dict
```python
KNOWN_TYPOS = {
    "Undoumented"  : "Undocumented",     # EC22
    "comparision"  : "comparison",       # EC20
    "Undoucomented": "Undocumented",     # variant
}
```

---

## File Connections

| Imports from | Used by |
|---|---|
| `dataclasses` (stdlib) | — |
| `ast_nodes_step0` | — (cleaner is pre-AST; does not need AST node types) |

**Called by:** `pipeline_step9.py` — `clean(raw_dax)` is the first call per measure

---

## Hardcoded Parts (Change for New Dashboards)

### `KNOWN_TYPOS` (line ~114)
```python
KNOWN_TYPOS = {
    "Undoumented"  : "Undocumented",
    "comparision"  : "comparison",
}
```
Dashboard-specific typos found inside DAX string literals. If a new dashboard has measures with different misspellings in their filter values, add them here so humans are warned.

### `NORMALIZE_KEYWORDS` (line ~95)
Add any additional DAX function names used in a new dashboard that should be uppercased. Missing a function name here means the lexer/parser sees it in mixed case — usually harmless but can cause parse failures on case-sensitive token matching.
