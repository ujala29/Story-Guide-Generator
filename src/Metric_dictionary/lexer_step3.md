# lexer_step3.py — DAX Lexer (Step 2a)

## Purpose
Takes a `clean_dax` string (from `CleanResult.clean_dax`) and returns a flat list of `Token` objects. No AST yet — just tokenization. Hand-written (not a library lexer) to handle three DAX-specific quirks that generic tokenizers handle poorly.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `clean_dax` string from `CleanResult` |
| **Output** | `LexResult` dataclass — `tokens: list[Token]` on success, `error: str` on failure (never raises) |

---

## Why Hand-Written

| Quirk | Problem | Solution |
|---|---|---|
| Quoted table names | `'date'[col]` — single-quoted token is a table name only when followed by `[` | Emits `QUOTED_NAME` token, not `STRING` |
| Curly brace sets (EC2) | `IN {"v1","v2"}` — `{` and `}` are set delimiters in DAX, not block delimiters | Emits `LBRACE` / `RBRACE` tokens |
| `&&` operator | Two chars that must become one token | Emits `AND_AND` token |

---

## Token Types

| Token | Value | Example |
|---|---|---|
| `IDENT` | unquoted identifier / keyword | `SUM`, `CALCULATE`, `VAR`, `TRUE`, `IN` |
| `QUOTED_NAME` | single-quoted table name (quotes stripped) | `'date'` → `date` |
| `STRING` | double-quoted string value (quotes stripped) | `"Documented"` → `Documented` |
| `NUMBER` | numeric constant | `12000`, `0.5` |
| `LBRACKET` | `[` | — |
| `RBRACKET` | `]` | — |
| `LPAREN` | `(` | — |
| `RPAREN` | `)` | — |
| `LBRACE` | `{` (EC2 set delimiter) | — |
| `RBRACE` | `}` (EC2 set delimiter) | — |
| `COMMA` | `,` | — |
| `EQ` | `=` | — |
| `NEQ` | `<>` (EC3 — two chars, one token) | — |
| `GT` | `>` | — |
| `LT` | `<` | — |
| `GTE` | `>=` | — |
| `LTE` | `<=` | — |
| `PLUS` | `+` | — |
| `MINUS` | `-` | — |
| `STAR` | `*` | — |
| `SLASH` | `/` | — |
| `AMP` | `&` (string concat in DAX) | — |
| `AND_AND` | `&&` (compound filter — two chars, one token) | — |

Whitespace and newlines are skipped — DAX is whitespace-insensitive.

---

## `Token` Schema

```python
type:  str   # token type string (e.g. "IDENT", "STRING", "LPAREN")
value: str   # exact text — quotes stripped for STRING and QUOTED_NAME
pos:   int   # character position in input string (for error messages)
```

## `LexResult` Schema

```python
tokens: list[Token]   # populated on success
error:  str | None    # set on failure (e.g. unexpected character)
```
Always returned — never raises.

---

## Function Flow

```
tokenize(clean_dax) → LexResult
  ├── scan character by character with pos pointer
  ├── skip whitespace and newlines
  ├── match two-char tokens first: <>, >=, <=, &&
  ├── match single-quoted 'table name' → QUOTED_NAME (quotes stripped)
  ├── match double-quoted "string"     → STRING (quotes stripped)
  ├── match digits → NUMBER
  ├── match [bracket content]          → LBRACKET + IDENT + RBRACKET
  ├── match identifier / keyword       → IDENT
  └── on unknown char → LexResult(tokens=[], error="Unexpected char...")
```

---

## File Connections

| Imports from | Used by |
|---|---|
| `dataclasses` (stdlib) | — |

**Called by:** `pipeline_step9.py` — `tokenize(clean_result.clean_dax)` after `clean()`

---

## Hardcoded Parts

> **None.** Token types are fixed by DAX grammar — no dashboard-specific changes needed.
