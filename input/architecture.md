INPUT FILES
───────────
measures_resolved.json          → raw DAX measures
bi_snowflakes_naming.json       → BI table → SF table mapping
static_table_values.json        → static tables ka data
relationships.json              → table join paths

        │
        ▼

┌─────────────────────────────────────────────────────┐
│ STEP 1: CLEANER                                     │
│                                                     │
│ File    : cleaner.py                                │
│ Input   : raw DAX string                            │
│ Output  : clean DAX string                          │
│                                                     │
│ Kya karta hai:                                      │
│   - formatString / lineageTag remove                │
│   - // comments remove                              │
│   - +0 remove                                       │
│   - lowercase keywords → uppercase                  │
│   - extra whitespace clean                          │
│                                                     │
│ Fail kab hoga: almost never                         │
│ Fail hone pe: log karo, continue karo               │
└──────────────────────┬──────────────────────────────┘
                       │
                       │ {name: {clean_dax, raw_dax, 
                       │         depends_on, is_leaf, depth}}
                       ▼

┌─────────────────────────────────────────────────────┐
│ STEP 2: PARSER                                      │
│                                                     │
│ Files   : ast_nodes.py                              │
│           lexer.py                                  │
│           parser.py                                 │
│ Input   : clean DAX string                          │
│ Output  : AST (tree structure)                      │
│                                                     │
│ Kya karta hai:                                      │
│   - DAX string ko tokens mein todta hai (lexer)     │
│   - Tokens se tree banata hai (parser)              │
│   - Har node ek DAX concept represent karta hai     │
│                                                     │
│ Fail kab hoga:                                      │
│   - Unknown DAX syntax                              │
│   - Unsupported function                            │
│ Fail hone pe:                                       │
│   - ParseFailure return karo                        │
│   - Step 8 (LLM) pe bhejo                          │
└──────────────────────┬──────────────────────────────┘
                       │
                       │ {name: {ast, parse_status,
                       │         parse_error}}
                       ▼

┌─────────────────────────────────────────────────────┐
│ STEP 3: DEPENDENCY RESOLVER                         │
│                                                     │
│ File    : dep_resolver.py                           │
│ Input   : sabhi measures ke ASTs                    │
│ Output  : dependency graph + processing order       │
│                                                     │
│ Kya karta hai:                                      │
│   - Har AST mein MeasureRef nodes dhundta hai       │
│   - Dependency graph banata hai                     │
│   - Topological sort karta hai (leaves first)       │
│   - Circular dependencies detect karta hai          │
│                                                     │
│ Example:                                            │
│   #Members YoY → needs #Members PY                 │
│   #Members PY  → needs #Members                    │
│   Order: #Members → #Members PY → #Members YoY     │
│                                                     │
│ Fail kab hoga: circular dependency                  │
│ Fail hone pe: mark circular → Step 8               │
└──────────────────────┬──────────────────────────────┘
                       │
                       │ ordered list of measure names
                       │ dependency graph
                       ▼

┌─────────────────────────────────────────────────────┐
│ STEP 4: SEMANTIC RESOLVER                           │
│                                                     │
│ File    : semantic_resolver.py                      │
│ Input   : AST + schema mapping + static registry    │
│ Output  : annotated AST (SF names)                  │
│                                                     │
│ Kya karta hai:                                      │
│   Har ColumnRef ke liye check karo:                 │
│   ┌─────────────────────────────────────────────┐   │
│   │ static_ prefix?  → tag "static", CTE attach │   │
│   │ parameter table? → tag "parameter"          │   │
│   │ SF mapping mein? → SF name map karo         │   │
│   │ Kuch nahi mila?  → tag "unresolved"         │   │
│   └─────────────────────────────────────────────┘   │
│                                                     │
│   tables_used list banata hai                       │
│   join_paths list banata hai                        │
│                                                     │
│ Fail kab hoga: table/column mapping nahi mila       │
│ Fail hone pe: mark unresolved → Step 8             │
└──────────────────────┬──────────────────────────────┘
                       │
                       │ {name: {semantic_ast,
                       │         tables_used,
                       │         join_paths,
                       │         static_tables_referenced}}
                       ▼

┌─────────────────────────────────────────────────────┐
│ STEP 5: CLASSIFIER                                  │
│                                                     │
│ File    : classifier.py                             │
│ Input   : semantic AST                              │
│ Output  : dax_pattern label + sql_applicable flag   │
│                                                     │
│ Patterns jo Python handle karega:                   │
│   SIMPLE_AGG          → SUM, COUNT, MAX, MIN        │
│   SIMPLE_DIVIDE       → DIVIDE(SUM, SUM)            │
│   FILTERED_AGG        → CALCULATE + KEEPFILTERS     │
│   VAR_FILTERED_DIVIDE → VAR+CALCULATE+DIVIDE        │
│   TIME_INTEL_YOY      → SAMEPERIODLASTYEAR          │
│   TIME_INTEL_MOM      → PREVIOUSMONTH               │
│   MEASURE_RATIO       → [A] / [B]                   │
│   COMPLEX_VAR_DIVIDE  → YoY/MoM computation         │
│   STATIC_FILTERED     → static table reference      │
│                                                     │
│ Patterns jo LLM handle karega:                      │
│   DISPLAY             → UNICHAR, FORMAT+SWITCH      │
│   INFO_TEXT           → hardcoded string            │
│   UNSUPPORTED         → SUMX, USERELATIONSHIP       │
│                                                     │
│ Fail kab hoga: never — worst case "UNSUPPORTED"     │
└──────────────────────┬──────────────────────────────┘
                       │
                       │ {name: {dax_pattern,
                       │         sql_applicable,
                       │         needs_llm_sql}}
                       ▼

┌─────────────────────────────────────────────────────┐
│ STEP 6: SQL GENERATOR                               │
│                                                     │
│ File    : sql_generator.py                          │
│ Input   : semantic AST + dax_pattern + sql_cache    │
│ Output  : SQL string                                │
│                                                     │
│ Kya karta hai:                                      │
│   - AST tree walk karta hai                         │
│   - Har node type ke liye SQL emit karta hai        │
│   - Static tables ke liye WITH block add karta hai  │
│   - sql_cache se resolved deps leta hai             │
│   - Pattern registry check karta hai PEHLE          │
│                                                     │
│ Decision flow:                                      │
│   ┌──────────────────────────────────────────────┐  │
│   │ 1. Registry mein pattern hai?                │  │
│   │    YES → instantiate template, done          │  │
│   │    NO  → compile karo                        │  │
│   │                                              │  │
│   │ 2. sql_applicable = False?                   │  │
│   │    YES → sql=None, needs_llm=True (definer)  │  │
│   │    NO  → compile karo                        │  │
│   │                                              │  │
│   │ 3. Pattern compiler handle kar sakta hai?    │  │
│   │    YES → SQL generate karo                   │  │
│   │    NO  → needs_llm=True (builder)            │  │
│   └──────────────────────────────────────────────┘  │
│                                                     │
│ Fail kab hoga: unsupported pattern                  │
│ Fail hone pe: sql_status="unsupported" → Step 8    │
└──────────────────────┬──────────────────────────────┘
                       │
                       │ {name: {sql, sql_status,
                       │         sql_source,
                       │         needs_llm,
                       │         llm_role}}
                       ▼

┌─────────────────────────────────────────────────────┐
│ STEP 7: VERIFIER                                    │
│                                                     │
│ File    : verifier.py                               │
│ Input   : generated SQL strings                     │
│ Output  : verified=True/False + error               │
│                                                     │
│ Kya karta hai:                                      │
│   - Sirf compiler-generated SQL ke liye             │
│   - Snowflake pe LIMIT 1 run karta hai              │
│   - Check karta hai: parse error nahi               │
│   - Check karta hai: 1 numeric column return hoti   │
│   - sample_value store karta hai                    │
│                                                     │
│ Verification fail hone pe:                          │
│   - failure_type classify karo                      │
│     (SQL_SYNTAX_ERROR, SQL_COLUMN_NOT_FOUND, etc.)  │
│   - needs_llm=True, llm_role="fixer"               │
│                                                     │
│ Fail kab hoga: SQL syntax wrong, column not found   │
│ Fail hone pe: mark unverified → Step 8             │
└──────────────────────┬──────────────────────────────┘
                       │
                       │ {name: {verified,
                       │         sample_value,
                       │         verification_error,
                       │         failure_type}}
                       ▼

┌─────────────────────────────────────────────────────┐
│ STEP 8: LLM FALLBACK                                │
│                                                     │
│ File    : llm_fallback.py                           │
│ Input   : measures with needs_llm=True              │
│ Output  : sql_final + definitions                   │
│                                                     │
│ Teen roles:                                         │
│   ┌──────────────────────────────────────────────┐  │
│   │ DEFINER                                      │  │
│   │   Kaun: compiler succeeded ya na measures    │  │
│   │   Kya: sirf definitions likhta hai           │  │
│   │   SQL: nahi banata                           │  │
│   │   Cost: cheap, fast                          │  │
│   │                                              │  │
│   │ BUILDER                                      │  │
│   │   Kaun: compiler fail hua                    │  │
│   │   Kya: DAX se SQL banata hai                 │  │
│   │   Context: schema + deps + DAX               │  │
│   │   Cost: expensive                            │  │
│   │                                              │  │
│   │ FIXER                                        │  │
│   │   Kaun: verifier fail hua                    │  │
│   │   Kya: wrong SQL fix karta hai               │  │
│   │   Context: bad SQL + exact error             │  │
│   │   Cost: medium                               │  │
│   └──────────────────────────────────────────────┘  │
│                                                     │
│ LLM output bhi verify hota hai                      │
│ Hallucination check hota hai                        │
└──────────────────────┬──────────────────────────────┘
                       │
                       │ {name: {sql_final,
                       │         sql_source,
                       │         confidence,
                       │         business_def,
                       │         technical_def}}
                       ▼

┌─────────────────────────────────────────────────────┐
│ STEP 9: LEARNING RECORDER                           │
│                                                     │
│ File    : learning_recorder.py                      │
│ Input   : all final results                         │
│ Output  : execution_log.db update                   │
│           pattern_registry.db update                │
│                                                     │
│ Kya karta hai:                                      │
│   - Har measure ka result log karta hai             │
│   - Verified SQL → IR extract → pattern store       │
│   - Failure type classify karta hai                 │
│   - Run summary report generate karta hai           │
│                                                     │
│ Ye step sirf record karta hai                       │
│ Koi transformation nahi karta                       │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼

┌─────────────────────────────────────────────────────┐
│ FINAL OUTPUT                                        │
│                                                     │
│ Files:                                              │
│   final_measures.json     → sabhi measures ka SQL   │
│   execution_log.db        → har run ka record       │
│   pattern_registry.db     → reusable patterns       │
│   run_report.json         → is run ki summary       │
└─────────────────────────────────────────────────────┘


dax_compiler/
│
├── ast_nodes.py              ← Step 2 ke liye data shapes
├── ir_nodes.py               ← Step 6 ke liye data shapes
│
├── cleaner.py                ← Step 1
├── lexer.py                  ← Step 2 (part 1)
├── parser.py                 ← Step 2 (part 2)
├── dep_resolver.py           ← Step 3
├── semantic_resolver.py      ← Step 4
├── classifier.py             ← Step 5
├── sql_generator.py          ← Step 6
├── verifier.py               ← Step 7
├── llm_fallback.py           ← Step 8
├── learning_recorder.py      ← Step 9
│
├── pattern_registry.py       ← Supporting component
├── execution_log.py          ← Supporting component
├── failure_classifier.py     ← Supporting component
│
├── pipeline.py               ← Sab steps ko jodta hai
│                               (LAST mein likhna)
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




    WEEK 1 — Foundation
──────────────────
Day 1   ast_nodes.py         → data shapes, koi logic nahi
Day 2   cleaner.py           → string clean karo
Day 2   test_cleaner.py      → sab tests pass karwao
Day 3   lexer.py             → tokens banao
Day 3   test_lexer.py        → sab tests pass karwao
Day 4   parser.py            → AST banao
Day 4   test_parser.py       → sab tests pass karwao
Day 5   dep_resolver.py      → dependency graph
Day 5   test_dep_resolver.py → sab tests pass karwao

WEEK 2 — Core Pipeline
──────────────────────
Day 6   ir_nodes.py           → IR data shapes
Day 7   semantic_resolver.py  → BI → SF names
Day 7   test_semantic.py      → tests
Day 8   classifier.py         → pattern labels
Day 8   test_classifier.py    → tests
Day 9   sql_generator.py      → SQL emit karo
Day 9   test_sql_generator.py → tests
Day 10  verifier.py           → Snowflake pe run karo

WEEK 3 — Learning + Integration
────────────────────────────────
Day 11  execution_log.py      → results record karo
Day 12  pattern_registry.py   → patterns store karo
Day 13  failure_classifier.py → failures classify karo
Day 14  learning_recorder.py  → Step 9
Day 15  llm_fallback.py       → Step 8
Day 16  pipeline.py           → sab jodo
Day 17  End to end test       → full Risk dashboard run






# Step 1 — Pipeline
python pipeline.py --dashboard risk_management

# Step 2 — LLM fallback
python llm_fallback.py --skip-registry

# Step 3 — Verify on Snowflake
python snowflake_verifier.py

# Step 4 — Record patterns (reads final_measures_with_llm.json automatically)
python learning_recorder.py --record --dashboard risk_management

# Step 5 — PCP dashboard pe
python pipeline.py --dashboard pcp_dashboard
python learning_recorder.py --suggest --dashboard pcp_dashboard
python learning_recorder.py --apply --dashboard pcp_dashboard