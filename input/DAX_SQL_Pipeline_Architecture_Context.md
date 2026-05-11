# DAX → SQL Pipeline: Complete Architecture Context
# Next Session ke liye Full Context Document
# Version: 1.0 | Last Updated: May 2026

---

## 1. PROBLEM STATEMENT

**Kya build kar rahe hain:**
Ek automated system jo Power BI DAX measures ko Snowflake SQL mein convert karta hai.

```
INPUT:  DAX measure string + schema mapping (BI table → Snowflake object)
OUTPUT: Snowflake SQL string jo same numeric result produce kare jaise DAX measure Power BI mein karta hai
CORRECT matlab: SQL Snowflake pe execute karke same value aaye jo Power BI mein DAX measure dikhata hai
```

**Scale:**
- Shuru: Risk dashboard (~80 measures)
- Expand: Quality dashboard, PAC dashboard, aur baaki dashboards
- Goal: Near 100% accuracy, self-improving system

---

## 2. WHY WE ARE REBUILDING (Purane System Ki Problems)

Tumhare paas already ek working pipeline thi (step1 to step5). Hum usse rebuild kar rahe hain kyunki:

### Problem 1: Regex-Based — 17+ Bug Patches
```
step4_sql_builder.py mein:
  B1-B9 (original bug fixes)
  NB1-NB8 (new bug fixes)
  = 17 patches for ONE dashboard

Root cause: DAX string ko regex se parse karna
Har naya pattern → naya bug → naya patch
Doosra dashboard → same bugs repeat
```

### Problem 2: Koi Real Verification Nahi
```
Purana system: sql_accuracy = "high" (manually rated)
Nayi system:   Snowflake pe actually run karke verify karo
```

### Problem 3: Koi Memory Nahi
```
Dashboard A → manual patches likhe → step4_patch.py
Dashboard B → same patterns → patches kaam nahi karte (different measure names)
System seekhta nahi tha
```

### Problem 4: LLM Pe Bahut Zyada Depend
```
Purana: 80 measures × LLM call = expensive + slow
Naya:   ~10 measures × expensive LLM call (rest Python handle karta hai)
```

### Root Cause of Everything:
```
Purana: String → Regex → SQL → Hope it's right
Naya:   String → Tree (AST) → IR → SQL → Verify → Learn
```

---

## 3. WHAT IS AN AST (Kyun Parser Chahiye)

**Parser** = text padhke structure samajhne wala
**AST** = tree-shaped data structure jo parser produce karta hai

### Example — Purana System (Regex):
```python
# Bug NB1 ka reason:
has_where = 'WHERE' in base_sql.upper()   # string scan
if has_where:
    sql = f"{base_sql}\n  AND {filter}"   # string concatenation
# AND kabhi wrong line pe aa jaata tha
```

### Example — Nayi System (AST):
```python
# Same logic:
def generate_calculate(node):
    filters = collect_filters(node)        # tree se, string scan nahi
    where = " AND ".join(filters)
    return f"SELECT {agg}\nFROM {table}\nWHERE {where}"
# Generator khud WHERE likhta hai — galti impossible hai
```

### Concrete AST Example:
```
DAX: CALCULATE(SUM(risk_core[risk_value]),
       KEEPFILTERS(risk_core[flag] = "Documented"))

AST Tree:
FunctionCall
  name = "CALCULATE"
  args = [
    FunctionCall
      name = "SUM"
      args = [ColumnRef(table="risk_core", col="risk_value")]

    FunctionCall
      name = "KEEPFILTERS"
      args = [
        BinaryOp
          op    = "="
          left  = ColumnRef(table="risk_core", col="flag")
          right = StringLiteral("Documented")
      ]
  ]

Navigation (no regex needed):
  node.name              → "CALCULATE"
  node.args[1].name      → "KEEPFILTERS"
  node.args[1].args[0].right.value → "Documented"
```

---

## 4. COMPLETE PIPELINE ARCHITECTURE (9 Steps)

```
INPUT FILES:
  measures_resolved.json          → raw DAX measures
  bi_snowflakes_naming.json       → BI table → SF table mapping
  static_table_values.json        → static tables (Power BI only)
  relationships.json              → table join paths

                    │
                    ▼

┌─────────────────────────────────────────────────────────┐
│ STEP 1: CLEANER                                         │
│ File: cleaner.py                                        │
│                                                         │
│ Input:  raw DAX string                                  │
│ Output: clean DAX string                                │
│                                                         │
│ Kya karta hai:                                          │
│   - formatString / lineageTag remove                    │
│   - // comments remove (lekin log karo)                 │
│   - +0 suffix remove                                    │
│   - lowercase keywords → uppercase (SUM, CALCULATE)    │
│   - extra whitespace clean                              │
│   - typos detect karo (Undoumented, comparision)        │
│                                                         │
│ STATUS: Purana step1_cleaner.py DIRECTLY REUSE karo    │
│ CHANGE: CleanResult dataclass add karo                  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼

┌─────────────────────────────────────────────────────────┐
│ STEP 2: PARSER                                          │
│ Files: ast_nodes.py + lexer.py + parser.py             │
│                                                         │
│ Input:  clean DAX string                                │
│ Output: AST (Abstract Syntax Tree)                      │
│                                                         │
│ Lexer:  string → token list                             │
│ Parser: token list → AST tree                           │
│                                                         │
│ Fail hone pe: ParseFailure return karo → Step 8        │
│ NEVER raise exception outside parser                    │
│                                                         │
│ STATUS: BILKUL NAYA likhna hoga                         │
│ Library: lark (pip install lark)                        │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼

┌─────────────────────────────────────────────────────────┐
│ STEP 3: DEPENDENCY RESOLVER                             │
│ File: dep_resolver.py                                   │
│                                                         │
│ Input:  sabhi measures ke ASTs                          │
│ Output: dependency graph + processing order             │
│                                                         │
│ Kya karta hai:                                          │
│   - Har AST mein MeasureRef nodes dhundta hai           │
│   - Dependency graph banata hai                         │
│   - Topological sort (leaves first)                     │
│   - Circular dependencies detect karta hai              │
│                                                         │
│ Example order:                                          │
│   #Members → #Members PY → #Members YoY               │
│                                                         │
│ STATUS: BILKUL NAYA likhna hoga                         │
│ Algorithm: Kahn's topological sort                      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼

┌─────────────────────────────────────────────────────────┐
│ STEP 4: SEMANTIC RESOLVER                               │
│ File: semantic_resolver.py                              │
│                                                         │
│ Input:  AST + schema mapping + static registry          │
│ Output: annotated AST with SF names                     │
│                                                         │
│ Har ColumnRef ke liye:                                  │
│   static_ prefix? → tag "static", CTE attach           │
│   parameter table? → tag "parameter"                    │
│   SF mapping mein? → SF name map karo (uppercase)       │
│   Kuch nahi mila? → tag "unresolved" → Step 8          │
│                                                         │
│ Boolean handling:                                       │
│   TRUE() ya TRUE → BoolLiteral(True)                   │
│   "true" (string) → StringLiteral("true") ← alag!     │
│   Column type check karo → sahi SQL type use karo      │
│                                                         │
│ STATUS: Purana step2_enricher.py ka logic REUSE karo   │
│ CHANGE: String input → AST node input                   │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼

┌─────────────────────────────────────────────────────────┐
│ STEP 5: CLASSIFIER                                      │
│ File: classifier.py                                     │
│                                                         │
│ Input:  semantic AST                                    │
│ Output: dax_pattern label + sql_applicable flag         │
│                                                         │
│ Python handle karega (sql_applicable=True):             │
│   SIMPLE_AGG          SUM/COUNT/MAX/MIN/AVGERAGE       │
│   SIMPLE_DIVIDE       DIVIDE(SUM,SUM)                  │
│   ARITHMETIC          SUM+SUM, ABS(SUM)+SUM            │
│   FILTERED_AGG        CALCULATE + KEEPFILTERS          │
│   VAR_FILTERED_DIVIDE VAR+CALCULATE+DIVIDE             │
│   TIME_INTEL_YOY      SAMEPERIODLASTYEAR               │
│   TIME_INTEL_MOM      PREVIOUSMONTH                    │
│   MEASURE_RATIO       [A]/[B]                          │
│   COMPLEX_VAR_DIVIDE  YoY/MoM computation              │
│   CONTEXT_REMOVER     CALCULATE+ALL()                  │
│   STATIC_FILTERED     static table reference           │
│                                                         │
│ LLM handle karega (sql_applicable=False/needs_llm):    │
│   DISPLAY             UNICHAR, FORMAT+SWITCH           │
│   INFO_TEXT           hardcoded string                 │
│   UNSUPPORTED         SUMX, SELECTEDVALUE, RANDBETWEEN │
│                                                         │
│ NEVER FAILS — worst case "UNSUPPORTED"                  │
│ STATUS: Purana step3 ka pattern names REUSE, rewrite   │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼

┌─────────────────────────────────────────────────────────┐
│ STEP 6: SQL GENERATOR                                   │
│ File: sql_generator.py                                  │
│                                                         │
│ Input:  semantic AST + dax_pattern + sql_cache          │
│ Output: SQL string                                      │
│                                                         │
│ Decision flow:                                          │
│   1. Pattern registry mein hai? → instantiate, done    │
│   2. sql_applicable=False? → sql=None, needs_llm=True  │
│   3. Compiler handle kare? → generate SQL              │
│   4. Nahi? → needs_llm=True (builder role)             │
│                                                         │
│ AST tree walk karta hai — NO REGEX                      │
│ Har node type ke liye alag handler                      │
│                                                         │
│ Static tables: WITH block CTE inject karta hai         │
│ ALL() present: date filter inject NAHI karta           │
│ DIVIDE args: 2 args=NULLIF, 3 args=COALESCE            │
│                                                         │
│ STATUS: Purana step4 ka SQL TEMPLATES reuse karo       │
│ CHANGE: Regex builders → tree walk handlers             │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼

┌─────────────────────────────────────────────────────────┐
│ STEP 7: VERIFIER                                        │
│ File: verifier.py                                       │
│                                                         │
│ Input:  generated SQL strings                           │
│ Output: verified=True/False + error                     │
│                                                         │
│ Sirf compiler-generated SQL ke liye:                    │
│   - Snowflake pe LIMIT 1 run karo                       │
│   - Check: parse error nahi                             │
│   - Check: 1 numeric column return hoti hai            │
│   - sample_value store karo                             │
│                                                         │
│ Fail hone pe:                                           │
│   - failure_type classify karo                          │
│   - needs_llm=True, llm_role="fixer"                   │
│                                                         │
│ STATUS: BILKUL NAYA likhna hoga                         │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼

┌─────────────────────────────────────────────────────────┐
│ STEP 8: LLM FALLBACK                                    │
│ File: llm_fallback.py                                   │
│                                                         │
│ Input:  measures with needs_llm=True                    │
│ Output: sql_final + definitions                         │
│                                                         │
│ Teen roles:                                             │
│   DEFINER  → compiler succeeded, sirf definitions       │
│              Fast, cheap (~65 measures)                 │
│   BUILDER  → compiler failed, SQL banana hai           │
│              Slow, expensive (~10 measures)             │
│   FIXER    → verifier failed, SQL fix karna hai        │
│              Medium cost (~5 measures)                  │
│                                                         │
│ LLM output bhi verify hota hai                          │
│ Hallucination check: invented names block karo          │
│                                                         │
│ STATUS: Purana step5_llm_definitions.py MOSTLY REUSE   │
│ CHANGE: Fixer role add karo, routing logic update karo  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼

┌─────────────────────────────────────────────────────────┐
│ STEP 9: LEARNING RECORDER                               │
│ File: learning_recorder.py                              │
│                                                         │
│ Input:  all final results                               │
│ Output: execution_log.db + pattern_registry.db update   │
│                                                         │
│ Kya karta hai:                                          │
│   - Har measure result log karo (pass ya fail)          │
│   - Verified SQL → IR extract → pattern store           │
│   - Failure type classify karo                          │
│   - Run summary report generate karo                    │
│                                                         │
│ STATUS: BILKUL NAYA likhna hoga                         │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼

OUTPUT:
  final_measures.json     → sabhi measures ka SQL
  execution_log.db        → har run ka record
  pattern_registry.db     → reusable patterns
  run_report.json         → is run ki summary
```

---

## 5. SUPPORTING COMPONENTS

### Pattern Registry (Step 6 use karta hai)
```
File: pattern_registry.py
DB:   pattern_registry.db

Kab bharti hai:
  Step 7 verification pass → IR signature compute → store

Kab use hoti hai:
  Step 6 shuru se pehle → check karo → mili toh instantiate

Kya store hota hai:
  ir_signature   → structural hash (SF names stripped)
  ir_template    → normalized IR with placeholders
  sql_template   → SQL with typed placeholders
  verified       → Snowflake pe test hua?
  dashboards_used → kahan use hua
  confidence     → high/medium/low

STATUS: Purana pattern_registry.py ka schema REUSE
CHANGE: IR hash add karo (string hash nahi)
```

### Execution Log (har run record karta hai)
```
File: execution_log.py
DB:   execution_log.db

Tables:
  execution_log:
    run_id, dashboard, measure_name, clean_dax
    dax_pattern, ir_signature
    generated_by (compiler/llm/pattern_reuse/manual)
    sql_generated, verified, sample_value
    verification_error, failure_type, failure_detail
    fix_applied, fix_type, fix_sql, fix_verified
    run_at, duration_ms

STATUS: BILKUL NAYA likhna hoga
```

### Failure Classifier
```
File: failure_classifier.py

Failure types:
  PARSE_FAILED          → lexer/parser fail
  UNRESOLVED_TABLE      → BI table not in mapping
  UNRESOLVED_COLUMN     → BI column not in mapping
  UNSUPPORTED_PATTERN   → pattern not in compiler
  UNSUPPORTED_FUNCTION  → SUMX, USERELATIONSHIP, etc.
  SQL_SYNTAX_ERROR      → Snowflake parse error
  SQL_COLUMN_NOT_FOUND  → column doesn't exist in SF
  SQL_TABLE_NOT_FOUND   → table doesn't exist in SF
  SQL_WRONG_RESULT      → 0 rows / wrong shape
  SQL_SEMANTIC_ERROR    → syntactically valid but wrong
  LLM_HALLUCINATED_NAMES → invented names
  LLM_RETURNED_NULL     → LLM couldn't generate
  DATA_QUALITY_TYPO     → Undoumented, comparision
  CIRCULAR_DEPENDENCY   → A→B→A

STATUS: BILKUL NAYA likhna hoga
```

---

## 6. COMPLETE FILE STRUCTURE

```
dax_compiler/
│
├── ast_nodes.py              ← Step 2 ke liye data shapes (NAYA)
├── ir_nodes.py               ← Step 6 ke liye data shapes (NAYA)
│
├── cleaner.py                ← Step 1 (step1_cleaner.py REUSE)
├── lexer.py                  ← Step 2 part 1 (NAYA)
├── parser.py                 ← Step 2 part 2 (NAYA)
├── dep_resolver.py           ← Step 3 (NAYA)
├── semantic_resolver.py      ← Step 4 (step2_enricher.py logic REUSE)
├── classifier.py             ← Step 5 (step3 patterns REUSE, rewrite)
├── sql_generator.py          ← Step 6 (step4 SQL templates REUSE)
├── verifier.py               ← Step 7 (NAYA)
├── llm_fallback.py           ← Step 8 (step5_llm_definitions REUSE)
├── learning_recorder.py      ← Step 9 (NAYA)
│
├── pattern_registry.py       ← Supporting (purana REUSE + upgrade)
├── execution_log.py          ← Supporting (NAYA)
├── failure_classifier.py     ← Supporting (NAYA)
├── static_table_handler.py   ← Supporting (purana DIRECTLY REUSE)
│
├── pipeline.py               ← Orchestrator (LAST mein likhna)
│
├── tests/
│   ├── test_cleaner.py
│   ├── test_lexer.py
│   ├── test_parser.py
│   ├── test_dep_resolver.py
│   ├── test_semantic_resolver.py
│   ├── test_classifier.py
│   ├── test_sql_generator.py
│   └── test_verifier.py
│
└── output/
    ├── final_measures.json
    ├── run_report.json
    ├── execution_log.db
    └── pattern_registry.db
```

---

## 7. PURANE CODE KA STATUS (Kya Reuse Karna Hai)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE                    STATUS          NAYI FILE MEIN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
step1_cleaner.py        ✅ DIRECTLY     cleaner.py
                        REUSE           + CleanResult dataclass add

step2_enricher.py       ✅ LOGIC        semantic_resolver.py
                        REUSE           (AST input lega, string nahi)
                                        Functions reuse:
                                          build_snowflake_lookup()
                                          build_rel_graph()
                                          get_join_paths()

step3_classifier.py     ⚠️ PARTIAL      classifier.py
                        REUSE           Pattern names + priority order reuse
                                        String checks → AST node checks

step4_sql_builder.py    ⚠️ PARTIAL      sql_generator.py
                        REUSE           SQL templates reuse
                                        Regex builders → tree walk

step4_patch.py          ✅ TEMPORARY    pipeline.py mein
                        REUSE           temp patches (baad mein delete)

step5_llm_definitions   ✅ MOSTLY       llm_fallback.py
                        REUSE           + Fixer role add
                                        + routing logic update

dax_analyzer.py         📖 REFERENCE    classifier.py mein
                        ONLY            DAX_CATEGORIES list reference

pattern_registry.py     ✅ REUSE        pattern_registry.py
                        + UPGRADE       + IR hash add karo

static_table_handler.py ✅ DIRECTLY     semantic_resolver.py +
                        REUSE           sql_generator.py mein use
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 8. AST_NODES.PY — COMPLETE FILE (Day 1 Ka Kaam)

```python
# ast_nodes.py — WRITE THIS FIRST, NO LOGIC, PURE DATA SHAPES

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


# ── LEAF NODES (koi children nahi) ───────────────────────────

@dataclass
class ColumnRef:
    """
    table[column] or 'table name'[column]
    Examples: risk_core[risk_value], 'date'[month_of_date]
    """
    table:  str
    column: str


@dataclass
class MeasureRef:
    """
    [MeasureName] — reference to another measure
    Examples: [#Members], [Documented risk]
    NOTE: Parser nahi resolve karta — dep_resolver karta hai
    """
    name: str


@dataclass
class VarRef:
    """
    VAR block ke andar defined variable ka reference
    Example: VAR a = SUM(...) RETURN DIVIDE(a, b)
             yahan 'a' aur 'b' VarRef hain
    """
    name: str


@dataclass
class StringLiteral:
    """String value: "Documented", "Undocumented" """
    value: str


@dataclass
class NumberLiteral:
    """Numeric value: 0, 1, 12000, 0.5"""
    value: float


@dataclass
class BoolLiteral:
    """
    EC8 se: TRUE() aur TRUE dono → BoolLiteral(True)
    EC9 se: "true" (string) → StringLiteral("true") ← ALAG HAI!
    """
    value: bool


# ── EXPRESSION NODES (children hain) ─────────────────────────

@dataclass
class FunctionCall:
    """
    Koi bhi DAX function call
    Examples:
      SUM(t[c]) → FunctionCall("SUM", [ColumnRef])
      CALCULATE([M], KEEPFILTERS(...)) → FunctionCall("CALCULATE", [...])
      DIVIDE(a, b) → FunctionCall("DIVIDE", [VarRef, VarRef])
    name ALWAYS uppercase hai
    """
    name: str
    args: list


@dataclass
class DivideNode:
    """
    P3, EC19 se: DIVIDE 2 args vs 3 args — alag SQL generate hoga
    DIVIDE(a, b)    → NULL on /0   → a / NULLIF(b, 0)
    DIVIDE(a, b, 0) → 0 on /0     → COALESCE(a / NULLIF(b, 0), 0)
    """
    numerator:   Any
    denominator: Any
    default_val: Any = None   # None = DIVIDE(a,b), 0 = DIVIDE(a,b,0)


@dataclass
class BinaryOp:
    """
    left OPERATOR right
    Operators: +, -, *, /, =, <>, >, <, >=, <=
    EC3 se: <> operator bhi handle karo (→ SQL !=)
    """
    op:    str
    left:  Any
    right: Any


@dataclass
class InSetExpr:
    """
    EC2 se: column IN {"val1", "val2"} — curly braces DAX mein
    SQL mein → column IN ('val1', 'val2') — parentheses
    """
    column: ColumnRef
    values: list   # list of strings


@dataclass
class CompoundAnd:
    """
    EC9 (B9) se: col=TRUE() && col="X" compound KEEPFILTERS
    SQL mein → WHERE cond1 AND cond2
    """
    left:  Any
    right: Any


@dataclass
class InlineFilter:
    """
    EC24 se: CALCULATE mein KEEPFILTERS wrapper ke bina filter
    CALCULATE(expr, col = "val")         ← inline (no KEEPFILTERS)
    CALCULATE(expr, KEEPFILTERS(col="val")) ← with KEEPFILTERS
    SQL mein dono WHERE ban jaate hain
    has_keepfilters note ke liye track karo
    """
    expr:           Any
    has_keepfilters: bool


@dataclass
class ScalarMultiplier:
    """
    EC10 se: DIVIDE(a,b) * 12000 — annualization multiplier
    SQL mein → (divide_sql) * 12000
    """
    base_expr:  Any
    multiplier: float


# ── BLOCK NODES (structural) ──────────────────────────────────

@dataclass
class VarDef:
    """Ek VAR definition"""
    name: str
    expr: Any


@dataclass
class VarBlock:
    """
    Full VAR...RETURN structure
    bindings LIST hai dict nahi — order matters in DAX
    """
    bindings:    list   # list of VarDef, in order
    return_expr: Any


# ── RESULT NODES (parser return karta hai) ────────────────────

@dataclass
class ParseSuccess:
    measure_name: str
    ast:          Any


@dataclass
class ParseFailure:
    measure_name: str
    error:        str
    dax_text:     str
    # → ye Step 8 (LLM Fallback) pe jaayega


# Type alias
ParseResult = ParseSuccess | ParseFailure
```

---

## 9. PATTERNS FROM ACTUAL DATA (22 Patterns — Do Dashboards)

### In Scope — Python Compiler Handle Karega

```
P1  Plain SUM
    DAX:  SUM(attribution[member_count]) + 0
    SQL:  SELECT SUM(member_count) FROM attribution
    EC1:  +0 strip karo pehle (Step 1 karta hai)

P2  CALCULATE + COUNT / DISTINCTCOUNT
    DAX:  COUNTROWS(cohort) + 0
          CALCULATE(count(pac_opp[visit_id])) + 0
    SQL:  SELECT COUNT(*) FROM cohort
    EC16: CALCULATE with NO filters = plain COUNT
          → CALCULATE ignore karo, inner expression use karo

P3  DIVIDE — simple ratio
    DAX:  DIVIDE(SUM(attr[visit]), SUM(attr[members]))
    SQL:  SELECT SUM(visit) / NULLIF(SUM(members), 0)
    EC19: DIVIDE(a,b) → NULL | DIVIDE(a,b,0) → COALESCE

P4  DIVIDE × scalar multiplier
    DAX:  DIVIDE(Num, Denom) * 12000
    SQL:  (COUNT(jk) / NULLIF(SUM(mc), 0)) * 12000
    EC10: * 12000 miss mat karna (annualization)
    EC5:  formatString/lineageTag strip karo

P5  CALCULATE + KEEPFILTERS (single value)
    DAX:  CALCULATE(AVERAGE(pac[los]),
            KEEPFILTERS(pac[type] <> "Home Health")) + 0
    SQL:  SELECT AVG(los) FROM pac WHERE type != 'Home Health'
    EC3:  <> → SQL != (not equal)
    EC18: AVERAGE → SQL AVG()

P6  CALCULATE + KEEPFILTERS IN {set}
    DAX:  KEEPFILTERS(flag IN {"Undocumented","Suspected"})
    SQL:  WHERE flag IN ('Undocumented','Suspected')
    EC2:  {} curly braces → () parentheses
    EC22: "Undoumented" typo — pass through, log karo

P7  CALCULATE inline filter (no KEEPFILTERS)
    DAX:  CALCULATE(expr, pac[type] = "Hospice")
    SQL:  WHERE pac_visit_type = 'Hospice'
    EC24: Semantic gap note karo — SQL same hai

P8  VAR + boolean flag filter
    DAX:  CALCULATE(COUNTROWS(t), t[flag] = TRUE)
    SQL:  SELECT COUNT(*) FROM t WHERE flag = TRUE
    EC8:  TRUE() aur TRUE dono handle karo
    EC9:  "true" (string) vs TRUE (boolean) — alag SQL

P9  Multi-flag CALCULATE
    DAX:  CALCULATE(DISTINCTCOUNT(t[c]), t[f1]="x", t[f2]="y")
    SQL:  WHERE f1='x' AND f2='y'
    EC17: max_month_flag column exist karna chahiye verify karo

P10 Direct measure-to-measure division
    DAX:  [Members with open gaps] / [#Members]
          DIVIDE([IP Discharges], [IP to PAC])
    SQL:  dep resolve karo pehle, phir divide karo
    EC_DEP: Bottom-up process karo

P13 MAX / MIN aggregation
    DAX:  MAX(risk_core[month_of_measurement])
    SQL:  SELECT MAX(month_of_measurement) FROM risk_core
    EC_COL: Same concept, different column names across tables

P22 ABS() utility wrapper
    DAX:  ABS(SUM(attr[visit])) + SUM(attr[members])
    SQL:  SELECT ABS(SUM(visit)) + SUM(members) FROM attr
    EC23: ABS on raw agg → translatable
          ABS inside FORMAT → not translatable (DISPLAY)
```

### Partial — Compiler + Date Parameter

```
P11 Time intelligence — PY / PM snapshot
    DAX:  CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month]))
    SQL:  WHERE month = DATEADD(year, -1, :selected_month)
    EC_DATE: Date parameter MUST be passed — no date = NULL silently

P12 YoY / MoM ratio
    DAX:  VAR py = CALCULATE([#M], SAMEPERIODLASTYEAR(...))
          RETURN DIVIDE([#M] - py, py, 0)
    SQL:  WITH curr AS (...), prev AS (...) SELECT (c-p)/NULLIF(p,0)
    EC19b: DIVIDE(a,b,0) → COALESCE | DIVIDE(a,b) → NULL
           Check karo kaunsa behavior expected hai

P14 ALL() — removes date filter context
    DAX:  CALCULATE(MAX(cohort[month]), ALL('DATE'))
    SQL:  SELECT MAX(month) FROM cohort  ← NO WHERE on date
    EC4:  ALL() present → date filter inject NAHI karo
```

### Out of Scope — LLM Sirf Definitions

```
P15 Card measures (UNICHAR + FORMAT)     → DISPLAY
P16 Color signal (SWITCH TRUE())         → DISPLAY
P17 Formatted display (FORMAT only)      → DISPLAY
P18 SELECTEDVALUE runtime router         → UNSUPPORTED
P19 CONCATENATEX row iterator            → UNSUPPORTED
P20 RANDBETWEEN demo measures            → UNSUPPORTED (flag & skip)
P21 Hardcoded string / empty string      → INFO_TEXT
```

---

## 10. SELF-LEARNING SYSTEM

### Learning Loop:
```
PHASE 1: RUN
  Pipeline runs → every result recorded (success + failure)

PHASE 2: CAPTURE
  execution_log.db mein har measure ka result

PHASE 3: VERIFY
  Generated SQL → Snowflake pe run → pass/fail

PHASE 4: CLASSIFY FAILURES
  failure_classifier.py → exact failure_type

PHASE 5: FIX
  Human fix OR LLM fix → recorded in execution_log

PHASE 6: STORE PATTERN
  Verified SQL → IR extract → pattern_registry.db mein store

PHASE 7: REUSE
  Next dashboard → IR signature match → template instantiate
  No LLM, no recompilation, instant

PHASE 8: REPORT
  Run summary → what improved, what failed, what was reused
```

### Concrete Example:
```
Dashboard A (Risk):
  "Potential risk" → compiled → verified → pattern "a3f92c81" stored

Dashboard B (Quality):
  "Quality gap rate" → same DAX pattern → ir_signature "a3f92c81"
  → Registry mein found!
  → Template instantiate with Quality SF names
  → 0ms, no LLM, no recompilation ✅
```

---

## 11. BUILD ORDER (Exactly Follow Karo)

```
WEEK 1 — Foundation
────────────────────
Day 1  ast_nodes.py          Write FIRST, no logic, pure shapes
                              Test: Python shell mein manually trees banao
Day 2  cleaner.py            step1 REUSE + CleanResult dataclass
       test_cleaner.py       ALL tests GREEN before Day 3
Day 3  lexer.py              Tokens banao
       test_lexer.py         ALL tests GREEN before Day 4
Day 4  parser.py             AST banao from tokens
       test_parser.py        ALL tests GREEN before Day 5
Day 5  dep_resolver.py       Topological sort
       test_dep_resolver.py  ALL tests GREEN

WEEK 2 — Core Pipeline
───────────────────────
Day 6  ir_nodes.py            IR data shapes
Day 7  semantic_resolver.py   BI → SF names
       test_semantic.py       Tests
Day 8  classifier.py          Pattern labels
       test_classifier.py     Tests
Day 9  sql_generator.py       SQL emit karo
       test_sql_generator.py  Tests
Day 10 verifier.py            Snowflake pe run karo

WEEK 3 — Learning + Integration
─────────────────────────────────
Day 11 execution_log.py      Results record karo
Day 12 pattern_registry.py   Patterns store karo (upgrade purana)
Day 13 failure_classifier.py Failures classify karo
Day 14 learning_recorder.py  Step 9
Day 15 llm_fallback.py       Step 8 (step5 reuse + fixer role)
Day 16 pipeline.py           SAB JODO (LAST mein likhna)
Day 17 End to end test       Full Risk dashboard run
```

---

## 12. KEY RULES (Never Break These)

```
RULE 1: Parser ke baad koi module raw DAX string touch nahi karta
         Sirf cleaner.py aur lexer.py string handle karte hain

RULE 2: SQL strings sirf sql_generator.py mein banta hai
         Koi aur module SQL fragments nahi banata

RULE 3: LLM sirf llm_fallback.py aur pipeline.py jaanta hai
         sql_generator.py LLM ko nahi jaanta

RULE 4: Har module jo fail ho sakta hai → result object return karo
         NEVER return None for failure
         NEVER raise Exception outside the module

RULE 5: Logging pipeline.py mein hota hai
         Modules print ya log nahi karte — result return karte hain

RULE 6: Test pehle, code baad mein
         Har module ke tests likho PEHLE, phir implement karo

RULE 7: Ek module ek kaam karta hai
         Cleaner clean karta hai. Parser parse karta hai. Generator generate karta hai.
         Mix mat karo.
```

---

## 13. EDGE CASES — IMPORTANT ONES TO REMEMBER

```
EC1   +0 suffix → Step 1 mein strip karo
EC2   IN {} curly braces → IN () parentheses
EC3   <> operator → SQL !=
EC4   ALL() → date filter inject NAHI karo
EC8   TRUE() aur TRUE dono = BoolLiteral(True)
EC9   "true" string vs TRUE boolean — ALAG types
EC10  * scalar multiplier after DIVIDE — miss mat karna
EC16  CALCULATE with no filters = plain aggregation
EC17  max_month_flag column existence verify karo
EC19  DIVIDE(a,b) vs DIVIDE(a,b,0) — alag SQL
EC22  "Undoumented" typo — pass through, log karo
EC23  ABS on raw agg = translatable, ABS in FORMAT = not
EC24  Inline filter vs KEEPFILTERS — SQL same, note different
EC_DATE Date parameter required for time intelligence
EC_DEP  Measure deps bottom-up resolve karo
```

---

## 14. LLM EFFICIENCY IMPROVEMENT

```
PURANA SYSTEM:
  80 measures × LLM call = 80 expensive calls

NAYI SYSTEM:
  80 measures total:
  → 55 compiler handles (verified) = 0 LLM SQL calls
  → 15 display/info = LLM sirf definitions (cheap, fast)
  → 10 genuinely complex = LLM SQL generation (expensive)

  Expensive LLM calls: 80 → 10  (87% reduction)
```

---

## 15. STATIC TABLES HANDLING

```
Kya hain: Power BI mein manually created tables (static_ prefix)
Snowflake mein NAHI hain

Strategy A: CTE substitution (fixed values known)
Strategy B: Parameter injection (SELECTEDVALUE se used)
Strategy C: Skip (entire logic runtime-dependent)

Pipeline mein:
  Step 4: ColumnRef check karo → static? → tag + CTE attach
  Step 6: WITH block inject karo jab static table referenced ho

Example output:
  WITH static_risk_buckets AS (
    SELECT '<bucket_name_value>' AS bucket_name
    -- TODO: Replace with actual values from Power BI
  )
  SELECT SUM(RISK_VALUE) FROM RISK_CORE_V4_VIEW
  WHERE RISK_BUCKET IN (SELECT bucket_name FROM static_risk_buckets)

Source: static_table_handler.py → DIRECTLY REUSE karo
```

---

## 16. NEXT SESSION MEIN KYA KARNA HAI

```
STATUS: Architecture complete, planning done, no code written yet

NEXT STEP: ast_nodes.py likhna

DAY 1 TASKS:
  1. dax_compiler/ folder banao
  2. ast_nodes.py likhao (Section 8 ka code copy karo)
  3. Python shell mein manually trees banao:
       from ast_nodes import *
       tree = FunctionCall("SUM", [ColumnRef("attribution", "member_count")])
       print(tree.args[0].table)   # → attribution
  4. P1-P10 patterns ke trees manually banao (on paper first)
  5. Jab manually tree banana easy lage → lexer.py start karo

INSTALL FIRST:
  pip install lark

DONT DO YET:
  - lexer.py mat likho yet
  - parser.py mat likho yet
  - pipeline.py kabhi nahi (last mein)
```

---

## 17. QUICK REFERENCE — Data Flow

```
measures_resolved.json
  → Step 1 (Cleaner)       → clean_dax string
  → Step 2 (Parser)        → AST tree
  → Step 3 (Dep Resolver)  → processing order
  → Step 4 (Sem Resolver)  → SF-annotated AST
  → Step 5 (Classifier)    → dax_pattern label
  → Step 6 (SQL Generator) → SQL string or None
  → Step 7 (Verifier)      → verified True/False
  → Step 8 (LLM Fallback)  → sql_final + definitions
  → Step 9 (Recorder)      → execution_log + pattern_registry
  → final_measures.json
```

---

*Context prepared for next Claude session — May 2026*
*Paste this entire document at the start of next session*
