# Metric_dictionary — Pipeline Documentation

## Purpose
Converts raw DAX measures (from Stage 1 extraction) into Snowflake SQL equivalents plus plain-English definitions. The pipeline runs as Stage 2 (parallel with `Visual_wise` and `filter_section`). Internally it has two layers: a deterministic compiler chain (steps 0–8, run together as `pipeline_step9.py`) that parses DAX into an AST and generates SQL, followed by LLM steps (10, 12) that validate/fix/build SQL and write business definitions. Step 11 (Snowflake verifier) is optional and skipped by default.

---

## Files in This Folder

| File | Role |
|---|---|
| `runner.py` | Entry point — runs steps 9 → 10 → 12 sequentially; step 11 skipped by default |
| `pipeline_step9.py` | Compiler orchestrator — calls steps 0–8 internally for every measure; writes `final_measures.json` + `run_report.json` |
| `scope_classifier.py` | Pre-step — splits measures into in-scope / out-of-scope before parsing begins |
| `ast_nodes_step0.py` | Step 0 — pure data shapes for the DAX AST; no logic, no parsing; imported by every other step |
| `cleaner_step1.py` | Step 1 — raw DAX string → `CleanResult`; strips metadata/comments/+0; normalizes keywords |
| `lexer_step3.py` | Step 2a — `clean_dax` → `LexResult` (flat token list); hand-written to handle DAX quirks |
| `parser_step4.py` | Step 2b — token list → `ParseResult` (`ParseSuccess` \| `ParseFailure`); recursive descent |
| `dep_resolver_step5.py` | Step 3 — walks ASTs, builds dependency graph, returns topological order (leaves first) |
| `semantic_resolver_step6.py` | Step 4 — annotates AST nodes with Snowflake table/column names; upgrades VarRef nodes |
| `classifier_step7.py` | Step 5 — assigns `dax_pattern` label and `llm_role` from AnnotatedAST |
| `sql_generator_step8.py` | Step 6 — walks AnnotatedAST + ClassifyResult → Snowflake SQL string; bottom-up traversal |
| `llm_fallback_step10.py` | Step 10 — four LLM roles: VALIDATOR, FIXER, BUILDER, DEFINER; results cached in `registry.json` |
| `snowflake_verifier_step11.py` | Step 11 (optional) — runs SQL on Snowflake, compares to DAX Studio ground truth |
| `metric_catalog_step12.py` | Step 12 (optional) — LLM generates `technical_definition` + `business_definition` per measure |

---

## Input / Output

| | Detail |
|---|---|
| **Input A** | `output/dashboards/<dash>/extraction/schema_sections/measures_resolved.json` — raw DAX measures from Stage 1 |
| **Input B** | `input/<dash>/bi_snowflakes_naming_matching.json` — BI table/column name → Snowflake name mapping |
| **Input C** | `input/<dash>/relationships.json` — table join paths |
| **Output A** | `output/dashboards/<dash>/metric_dictionary/final_measures.json` — all measures with SQL + LLM results |
| **Output B** | `output/dashboards/<dash>/metric_dictionary/final_measures_with_llm.json` — post-step-10 enriched version |
| **Output C** | `output/dashboards/<dash>/metric_dictionary/registry.json` — LLM result cache (keyed by measure name) |
| **Output D** | `output/dashboards/<dash>/metric_dictionary/run_report.json` — pipeline summary + stats |
| **Output E** | `output/dashboards/<dash>/metric_dictionary/metric_catalog.json` — structured catalog with tech + business definitions |
| **Output F** | `output/dashboards/<dash>/metric_dictionary/metric_catalog.md` — markdown table of all measures |
| **Output G** | `output/dashboards/<dash>/metric_dictionary/scope/measures_in_scope.json` |
| **Output H** | `output/dashboards/<dash>/metric_dictionary/scope/measures_out_of_scope.json` |
| **Output I** | `output/dashboards/<dash>/metric_dictionary/scope/scope_summary.json` |

---

## Pipeline Steps

```
runner.py calls:

[Step 9]  pipeline_step9.py          → compiler chain for all measures
              Pre-step  scope_classifier    → split in/out-of-scope
              Step 1    cleaner_step1       → raw DAX -> CleanResult
              Step 2a   lexer_step3         → clean_dax -> tokens
              Step 2b   parser_step4        → tokens -> AST (ParseSuccess|ParseFailure)
              Step 3    dep_resolver_step5  → dependency graph + topological order
              Step 4    semantic_resolver_step6 → BI names -> SF names; VarRef upgrade
              Step 5    classifier_step7    → dax_pattern + llm_role
              Step 6    sql_generator_step8 → AST -> Snowflake SQL

[Step 10] llm_fallback_step10.py     → VALIDATOR / FIXER / BUILDER / DEFINER roles
              (parallel, WORKERS=5; cached in registry.json)

[Step 11] snowflake_verifier_step11.py → optional, skipped by default
              (runs SQL on Snowflake, compares to DAX Studio ground truth)

[Step 12] metric_catalog_step12.py   → optional, generates tech + business definitions
              (parallel, WORKERS=5)
```

---

## Function Flow

```
runner.py  main()
  ├── assert_env()
  ├── [step 9] subprocess: pipeline_step9.py --dashboard <dash>
  │     └── pipeline_step9.main()
  │           ├── scope_classifier.run_scope_classification(measures)
  │           │     ├── classify_scope(name, measure) → (scope, reason)
  │           │     │     checks: HARDCODED_STRING | DISPLAY_SYMBOL | COLOR_CODE |
  │           │     │             DISPLAY_FORMAT | RUNTIME_ROUTER | ROW_ITERATOR | DEMO_MEASURE
  │           │     │     else → IN_SCOPE
  │           │     └── write scope/measures_in_scope.json + out_of_scope + summary
  │           │
  │           └── [per measure, topological order] for each in-scope measure:
  │                 ├── clean(raw_dax)            → CleanResult
  │                 │     strips: formatString, lineageTag, // comments, +0 suffix
  │                 │     normalizes: keywords UPPERCASE, whitespace
  │                 │
  │                 ├── tokenize(clean_dax)       → LexResult (tokens)
  │                 │     handles DAX quirks: 'quoted'[col], {set}, && operator
  │                 │
  │                 ├── parse_dax(tokens)         → ParseSuccess | ParseFailure
  │                 │     recursive descent: VAR blocks, CALCULATE, DIVIDE,
  │                 │     KEEPFILTERS, IN {set}, BoolLiteral, etc.
  │                 │     ParseFailure → routed to llm_fallback role=BUILDER
  │                 │
  │                 ├── dep_resolve(parse_results) → DepResult
  │                 │     Kahn's BFS topological sort; var_bindings collected
  │                 │
  │                 ├── resolve_one(parse_success, dep_result, sf_map, rels) → AnnotatedAST
  │                 │     ColumnRef("bi_table","col") → sf_table="SF_TABLE", sf_column="COL"
  │                 │     ColumnRef("py","*") where "py" in var_bindings → VarRef("py")
  │                 │     builds join_paths for multi-table measures
  │                 │
  │                 ├── do_classify(annotated_ast) → ClassifyResult
  │                 │     AST-based (not string-scanning) pattern detection
  │                 │     assigns: dax_pattern, sql_applicable, llm_role
  │                 │
  │                 └── generate(annotated_ast, classify_result, sql_cache) → GenerateResult
  │                       bottom-up AST walk → Snowflake SQL string
  │                       sql_cache: already-resolved dependency SQL reused inline
  │                       needs_llm=True → routed to llm_fallback role=BUILDER
  │
  ├── [step 10] subprocess: llm_fallback_step10.py --dashboard <dash>
  │     └── llm_fallback.main()
  │           for each measure in final_measures.json:
  │             ├── check registry.json → cache hit → skip API call
  │             ├── VALIDATOR role (scope=IN_SCOPE + sql_query exists)
  │             │     → LLM reviews compiler SQL for logic errors
  │             │     → verdict: ok | needs_fix | unsure
  │             ├── FIXER role (VALIDATOR returns needs_fix)
  │             │     → LLM applies corrected SQL
  │             ├── BUILDER role (scope=IN_SCOPE + llm_role=BUILDER, no SQL)
  │             │     → LLM generates SQL from scratch for COMPLEX patterns
  │             └── DEFINER role (scope != IN_SCOPE + llm_role=DEFINER)
  │                   → LLM writes plain-English definition only
  │
  └── [step 12] subprocess: metric_catalog_step12.py --dashboard <dash>
        └── metric_catalog.main()
              for each in-scope measure (parallel, WORKERS=5):
                ├── check registry for cached definitions
                └── LLM call → technical_definition + business_definition
              writes metric_catalog.json + metric_catalog.md
```

---

## AST Node Types (`ast_nodes_step0.py`)

All node types are pure dataclasses with no logic — only shapes.

| Node | What it represents | Example DAX |
|---|---|---|
| `ColumnRef` | `table[column]` reference | `risk_core[risk_value]` |
| `MeasureRef` | `[MeasureName]` reference | `[#Members]` |
| `VarRef` | Variable name in VAR...RETURN | `RETURN DIVIDE(a, b)` — `a`, `b` |
| `StringLiteral` | Double-quoted string | `"Documented"` |
| `NumberLiteral` | Numeric constant | `12000`, `0.5` |
| `BoolLiteral` | `TRUE()`, `TRUE`, `FALSE()`, `FALSE` | `= TRUE()` |
| `FunctionCall` | Any `FUNC(args)` | `SUM(...)`, `CALCULATE(...)` |
| `DivideNode` | `DIVIDE(num, den)` or `DIVIDE(num, den, 0)` | 2-arg vs 3-arg differ in SQL |
| `BinaryOp` | `left OP right` | `=`, `<>`, `+`, `-`, `/` |
| `InSetExpr` | `col IN {"v1","v2"}` | `risk_documentation_flag IN {...}` |
| `CompoundAnd` | `expr && expr` inside KEEPFILTERS | two conditions joined by `&&` |
| `InlineFilter` | Filter arg inside CALCULATE (with or without KEEPFILTERS) | `CALCULATE(SUM(...), col="val")` |
| `ScalarMultiplier` | `expr * scalar` | `DIVIDE(...) * 12000` |
| `VarDef` | Single `VAR name = expr` definition | `VAR a = SUM(...)` |
| `VarBlock` | Full `VAR...RETURN` structure | `VAR a = ... VAR b = ... RETURN DIVIDE(a, b)` |
| `ParseSuccess` | Parser result — success | contains root AST node |
| `ParseFailure` | Parser result — failure | contains error + dax_text for LLM BUILDER |

---

## Scope Decision Rules (`scope_classifier.py`)

Out-of-scope measures get `llm_role=DEFINER` (plain-English definition only, no SQL).

| Reason code | DAX pattern | Example |
|---|---|---|
| `HARDCODED_STRING` | Entire DAX is a string literal | `"The cohort is built on..."` |
| `DISPLAY_SYMBOL` | Contains `UNICHAR` | Arrow/trend symbols `▲▼` |
| `COLOR_CODE` | `SWITCH(TRUE(), x < 0, 1, 2)` | Conditional formatting integer |
| `DISPLAY_FORMAT` | `FORMAT + SWITCH` (no KEEPFILTERS) | Display string measure |
| `RUNTIME_ROUTER` | Contains `SELECTEDVALUE` | Depends on slicer at runtime |
| `ROW_ITERATOR` | Contains `SUMX`, `AVERAGEX`, `CONCATENATEX`, etc. | Row-context iterators |
| `DEMO_MEASURE` | Contains `RANDBETWEEN` | Non-deterministic demo metric |
| `IN_SCOPE` | Everything else | Compiler attempts parse + SQL |

---

## DAX Pattern Labels (`classifier_step7.py`)

| Pattern | Description | SQL approach |
|---|---|---|
| `SIMPLE_AGG` | `SUM` / `COUNT` / `MAX` / `MIN` / `AVERAGE` / `DISTINCTCOUNT` | `SELECT AGG(col) FROM table` |
| `SIMPLE_DIVIDE` | `DIVIDE(SUM, SUM)` — leaf, no VAR | `SELECT num / NULLIF(den, 0)` |
| `ARITHMETIC` | `ABS(SUM) + SUM` or similar | arithmetic on aggregations |
| `FILTERED_AGG` | `CALCULATE + KEEPFILTERS` | `SELECT AGG(col) WHERE conditions` |
| `VAR_FILTERED_DIVIDE` | `VAR + CALCULATE + DIVIDE` | Gap-to-potential risk pattern |
| `TIME_INTEL_YOY` | `SAMEPERIODLASTYEAR` | `WHERE date_col = DATEADD(year, -1, :param)` |
| `TIME_INTEL_MOM` | `PREVIOUSMONTH` | `WHERE date_col = DATEADD(month, -1, :param)` |
| `MEASURE_RATIO` | `[A] / [B]` direct measure division | `(sql_A) / NULLIF((sql_B), 0)` |
| `COMPLEX_VAR_DIVIDE` | VAR + DIVIDE on measure refs | YoY/MoM computation |
| `CONTEXT_REMOVER` | `CALCULATE + ALL()` | no date filter added |
| `STATIC_FILTERED` | References `static_` tables | CTE placeholder for static lookup |
| `COMPLEX` | Everything else | `needs_llm=True` → BUILDER role |

---

## LLM Roles (`llm_fallback_step10.py`)

| Role | Trigger | What LLM does |
|---|---|---|
| `VALIDATOR` | `scope=IN_SCOPE` + `sql_query` exists | Reviews compiler SQL for logic errors; returns `ok` / `needs_fix` / `unsure` |
| `FIXER` | VALIDATOR returns `needs_fix` | Rewrites SQL to fix the identified error |
| `BUILDER` | `scope=IN_SCOPE` + `llm_role=BUILDER` (no SQL from compiler) | Generates Snowflake SQL from scratch for COMPLEX patterns |
| `DEFINER` | `scope != IN_SCOPE` + `llm_role=DEFINER` | Writes plain-English business definition only — no SQL |

All results written to `registry.json`. Re-runs skip API calls for cached measures (keyed by measure name).

---

## Critical DAX Edge Cases

| Code | Issue | Handling |
|---|---|---|
| EC1 | `+0` suffix appended to DAX | Stripped in `cleaner_step1.py` before parsing |
| EC2 | `IN {"v1","v2"}` uses curly braces | Lexer emits `LBRACE`/`RBRACE`; parser → `InSetExpr`; SQL generator → `IN (...)` |
| EC3 | `<>` not-equal operator (two chars) | Lexer → `NEQ` token; SQL generator maps to `!=` |
| EC4 | `ALL()` context remover | `FunctionCall("ALL",...)` detected by classifier → no date filter injected |
| EC8 | `TRUE()` and bare `TRUE` are both valid | Parser normalizes both → `BoolLiteral(True)` |
| EC9 | `"true"` (string) ≠ `TRUE` (boolean) | `StringLiteral("true")` vs `BoolLiteral(True)` — different types, different SQL |
| EC10 | `DIVIDE(...) * 12000` annualization | Parser → `ScalarMultiplier`; SQL → `(divide_sql) * 12000` |
| EC19 | `DIVIDE(a,b)` vs `DIVIDE(a,b,0)` | `default_val=None` → `NULLIF`; `default_val=0.0` → `COALESCE(..., 0)` |
| EC22 | Typo `"Undoumented"` in string values | Stored as-is; cleaner logs warning; SQL returns 0 rows silently |
| EC24 | `CALCULATE(e, KEEPFILTERS(f))` vs `CALCULATE(e, f)` | Both → `InlineFilter`; `has_keepfilters` flag tracks original form; SQL output identical |

---

## File Connections

| Imports from | Used by | Purpose |
|---|---|---|
| `ast_nodes_step0` | every step 1–8 | all AST node types — single source of truth |
| `cleaner_step1` | `pipeline_step9.py` | `clean()` → `CleanResult` |
| `lexer_step3` | `pipeline_step9.py` | `tokenize()` → `LexResult` |
| `parser_step4` | `pipeline_step9.py` | `parse_dax()` → `ParseResult` |
| `dep_resolver_step5` | `pipeline_step9.py`, `semantic_resolver_step6` | `dep_resolve()` → `DepResult` |
| `semantic_resolver_step6` | `pipeline_step9.py` | `resolve_one()` → `AnnotatedAST` |
| `classifier_step7` | `pipeline_step9.py` | `do_classify()` → `ClassifyResult` |
| `sql_generator_step8` | `pipeline_step9.py` | `generate()` → `GenerateResult` |
| `scope_classifier` | `pipeline_step9.py` | `run_scope_classification()`, `write_outputs()` |
| `utils/llm_client.py` | `llm_fallback_step10.py` | `llm_chat()` with tenacity retry |
| `utils/env_check.py` | `runner.py` | `assert_env()` |

**Called by:** `main.py` Stage 2 (parallel with `Visual_wise` and `filter_section`)

---

## Hardcoded Parts (Change for New Dashboards)

### `DASHBOARD_INPUTS` / `DASHBOARD_SF_MAPS` / `DASHBOARD_RELS` — `pipeline_step9.py`
```python
DASHBOARD_INPUTS = {
    "risk-dash": BASE_DIR / "output/dashboards/risk-dash/extraction/.../measures_resolved.json",
    "pac-dash":  BASE_DIR / "output/dashboards/pac-dash/extraction/.../measures_resolved.json",
}
DASHBOARD_SF_MAPS = {
    "risk-dash": BASE_DIR / "input/risk-dash/bi_snowflakes_naming_matching.json",
    ...
}
```
Add new dashboard's input paths here when adding a new dashboard.

### `DASHBOARD_LLM_CONFIGS` — `llm_fallback_step10.py`
```python
DASHBOARD_LLM_CONFIGS = {
    "risk-dash": {
        "final_measures_path": ...,
        "registry_path": ...,
        "output_path": ...,
    },
    "pac-dash": {...},
}
```
Add config block for each new dashboard so step 10 knows where to read/write files.

### `DASHBOARD_CONFIGS` — `metric_catalog_step12.py`
```python
DASHBOARD_CONFIGS = {
    "risk-dash": {
        "final_measures_path": ...,
        "registry_path": ...,
        "catalog_json_path": ...,
        "catalog_md_path": ...,
    },
}
```
Add a config block for each new dashboard to enable metric catalog generation.

### `DAX_GROUND_TRUTH` — `snowflake_verifier_step11.py` (line ~73)
```python
DAX_GROUND_TRUTH = {
    "Members"          : 2_390_624,
    "Documented risk"  : 0.7647413105392060,
    ...
}
```
Expected unfiltered values from DAX Studio (ALL() applied). Update with new dashboard's DAX Studio results before running verification.

### `WORKERS = 5` — `llm_fallback_step10.py`, `metric_catalog_step12.py`
Parallel LLM call thread count. Reduce if hitting rate limits; increase for faster runs when API quota allows.
