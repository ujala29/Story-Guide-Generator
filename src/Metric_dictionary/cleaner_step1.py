"""
cleaner.py
──────────
Stage 2 — Step 1

PURPOSE:
    Takes a raw DAX string and returns a CleanResult.
    Downstream steps (lexer, parser) only ever see clean_dax — never raw.

INPUT:
    raw DAX string  (from measures_resolved.json → measure["dax"])

OUTPUT:
    CleanResult dataclass  (always returned, never raises)

WHAT THIS FILE DOES:
    1. Strip formatString / lineageTag metadata lines
    2. Strip // comment lines  (log them — may reveal hidden intent, EC6/EC15)
    3. Strip +0 suffix         (EC1)
    4. Normalize DAX keywords to UPPERCASE  (sum → SUM, var → VAR, etc.)
    5. Normalize whitespace    (collapse blank lines, strip trailing spaces)
    6. Detect hardcoded string measures  (INFO_TEXT pattern)
    7. Detect known typos in string values  (EC22, EC20 — warn, pass through)

WHAT THIS FILE DOES NOT DO:
    - Does NOT parse. Does NOT build AST nodes.
    - Does NOT touch depends_on recursion (that was step1's concern —
      stage2 gets clean deps from measures_resolved.json already)
    - Does NOT fail silently. Every issue → warning in CleanResult.warnings.

REUSE FROM step1_cleaner.py:
    remove_metadata_lines()   → direct copy
    remove_commented_lines()  → direct copy + captures comments
    remove_trailing_plus_zero()→ direct copy
    normalize_keywords()      → direct copy
    normalize_whitespace()    → direct copy
    is_hardcoded_string()     → direct copy
    NORMALIZE_KEYWORDS list   → direct copy

ADDITIONS vs step1_cleaner.py:
    CleanResult dataclass     → structured output instead of raw string
    detect_typos()            → EC22, EC20 — warn on known bad values
    clean()                   → single entry point returning CleanResult

EDGE CASES HANDLED:
    EC1   +0 suffix            → stripped
    EC5   formatString lines   → stripped
    EC6   // comments          → stripped, captured in CleanResult.stripped_comments
    EC14  lineageTag lines      → stripped
    EC15  commented-out DAX    → stripped, captured, flagged for human review
    EC22  "Undoumented" typo   → pass through, warning added
    EC20  "comparision" typo   → pass through, warning added
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


# ══════════════════════════════════════════════════════════════
# RESULT DATACLASS
# ══════════════════════════════════════════════════════════════

@dataclass
class CleanResult:
    """
    Output of clean(). Always returned — never None, never exception.

    Fields:
        measure_name        : display name of the measure
        raw_dax             : original DAX string, untouched
        clean_dax           : cleaned DAX ready for lexer/parser
        is_hardcoded_string : True if DAX is just a string literal (INFO_TEXT)
        stripped_comments   : list of // comment lines that were removed
                              May reveal hidden intent (EC6/EC15)
        warnings            : list of human-readable warning strings
                              (typos, suspicious patterns, etc.)
        had_metadata        : True if formatString/lineageTag were stripped
        had_plus_zero       : True if +0 suffix was stripped (EC1)
    """
    measure_name:        str
    raw_dax:             str
    clean_dax:           str
    is_hardcoded_string: bool
    stripped_comments:   list[str] = field(default_factory=list)
    warnings:            list[str] = field(default_factory=list)
    had_metadata:        bool = False
    had_plus_zero:       bool = False


# ══════════════════════════════════════════════════════════════
# KEYWORD LIST  (from step1_cleaner.py — direct copy)
# ══════════════════════════════════════════════════════════════

NORMALIZE_KEYWORDS = [
    "sum", "calculate", "divide", "countrows", "distinctcount",
    "max", "min", "average", "filter", "keepfilters", "return",
    "var", "if", "isblank", "switch", "true", "false",
    "sameperiodlastyear", "previousmonth", "dateadd",
    "allexcept", "all", "values", "selectedvalue", "hasonevalue",
    "abs", "format", "unichar", "concatenate", "blank",
    "summarize", "addcolumns", "topn", "rankx", "count",
    "in",  # Fix2: IN keyword for set membership (col IN {set})
]

# ══════════════════════════════════════════════════════════════
# KNOWN TYPOS  (EC22, EC20)
# ══════════════════════════════════════════════════════════════

# Maps known bad value → correct spelling
# These appear inside string literals in DAX.
# We do NOT correct them — SQL would then not match the database.
# We WARN so a human can check whether DB has the typo or correct spelling.
KNOWN_TYPOS = {
    "Undoumented"  : "Undocumented",   # EC22 — risk_documentation_flag value
    "comparision"  : "comparison",     # EC20 — column name typo
    "Undoucomented": "Undocumented",   # variant seen in some files
}


# ══════════════════════════════════════════════════════════════
# INDIVIDUAL CLEANER FUNCTIONS
# (from step1_cleaner.py — direct copies with minor additions)
# ══════════════════════════════════════════════════════════════

def remove_metadata_lines(dax: str) -> tuple[str, bool]:
    """
    Strip formatString, lineageTag, annotation lines from end of DAX.
    These are Power BI metadata injected into the DAX string — not DAX logic.

    Returns (cleaned_dax, had_metadata).

    EC5 / EC14:
        Utilization measure has:
            DIVIDE(Num, Denom) * 12000
            formatString: #,0
            lineageTag: b2578648-...
            annotation PBI_FormatHint = ...
        All three trailing lines must be stripped.
    """
    lines   = dax.split('\n')
    clean   = []
    found   = False

    for line in lines:
        stripped = line.strip()
        if (
            stripped.startswith('formatString')
            or stripped.startswith('lineageTag')
            or stripped.startswith('annotation ')
        ):
            found = True
            break
        clean.append(line)

    return '\n'.join(clean), found


def remove_commented_lines(dax: str) -> tuple[str, list[str]]:
    """
    Strip DAX // comment lines and capture them for review.

    Returns (cleaned_dax, list_of_stripped_comments).

    EC6 / EC15:
        Info text risk cohort has:
            "The cohort is built on latest risk execution data..."
            // IF(SELECTEDVALUE('measure'[period_mode]) = "ytd","...")
        The comment reveals the original intent was SELECTEDVALUE-dependent.
        We strip it but keep it in stripped_comments for human review.
    """
    lines    = dax.split('\n')
    clean    = []
    comments = []

    for line in lines:
        if line.strip().startswith('//'):
            comments.append(line.strip())
        else:
            clean.append(line)

    return '\n'.join(clean), comments


def remove_trailing_plus_zero(dax: str) -> tuple[str, bool]:
    """
    Strip +0 suffix from DAX expression.

    Returns (cleaned_dax, had_plus_zero).

    EC1:
        SUM(attribution[member_count]) + 0
            → SUM(attribution[member_count])

        In DAX, +0 forces BLANK → 0 (numeric coercion).
        In SQL, SUM already returns 0 on empty result (or NULL if no rows,
        which COALESCE handles). The +0 is noise for SQL generation.

    Handles both:
        expr + 0      (space before 0)
        expr +0       (no space)
        expr + 0      (trailing whitespace after 0)
    """
    cleaned = re.sub(r'\+\s*0\s*$', '', dax.strip())
    had     = cleaned != dax.strip()
    return cleaned, had


def normalize_keywords(dax: str) -> str:
    """
    Uppercase DAX keywords. Skips quoted strings so string values
    like "true" or "format" inside quotes are not uppercased.

    EC8 partial:
        true → TRUE    (keyword form — BoolLiteral later)
        "true" stays "true"  (string form — StringLiteral later)

    Strategy:
        Split on quoted segments (alternating code/quoted).
        Uppercase keywords only in code segments (even indices).
    """
    # Split: even indices = code, odd indices = quoted strings
    parts  = re.split(r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')', dax)
    result = []

    for i, part in enumerate(parts):
        if i % 2 == 0:   # code segment — normalize
            for kw in NORMALIZE_KEYWORDS:
                part = re.compile(
                    r'\b' + re.escape(kw) + r'\b', re.IGNORECASE
                ).sub(kw.upper(), part)
        result.append(part)

    return ''.join(result)


def normalize_whitespace(dax: str) -> str:
    """
    Remove consecutive blank lines and trailing spaces per line.
    Trim leading/trailing blank lines from the whole string.
    """
    lines      = dax.split('\n')
    clean      = []
    prev_blank = False

    for line in lines:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue          # skip consecutive blank lines
        clean.append(line.rstrip())
        prev_blank = is_blank

    # trim leading and trailing blank lines
    while clean and not clean[0].strip():
        clean.pop(0)
    while clean and not clean[-1].strip():
        clean.pop()

    return '\n'.join(clean)


def is_hardcoded_string(dax: str) -> bool:
    """
    Returns True if the entire DAX expression is just a string literal.
    These are INFO_TEXT measures — no SQL equivalent exists.

    Examples:
        "The cohort is built on latest risk execution data..."  → True
        ""                                                       → True
        SUM(attribution[member_count])                          → False
        CALCULATE(SUM(...), ...)                                → False
    """
    s = dax.strip()
    return s.startswith('"') or s.startswith("'")


def detect_typos(dax: str) -> list[str]:
    """
    Scan DAX string for known value typos.
    Returns list of warning strings — one per typo found.

    EC22: "Undoumented" in DAX → will match no rows in DB silently
    EC20: "comparision" column name → will cause column-not-found in SQL

    We do NOT correct the typos. Reasons:
        1. DB might also have the typo (matches correctly)
        2. DB might have correct spelling (SQL fails with column-not-found)
        3. Human must check the actual database before deciding

    Warnings are stored in CleanResult.warnings for reporting.
    """
    warnings = []
    dax_lower = dax.lower()

    for bad, correct in KNOWN_TYPOS.items():
        if bad.lower() in dax_lower:
            warnings.append(
                f"TYPO_DETECTED: '{bad}' found in DAX — correct spelling is '{correct}'. "
                f"Check whether database column/value uses the typo or correct spelling. "
                f"Passed through unchanged."
            )

    return warnings


# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def clean(measure_name: str, raw_dax: str) -> CleanResult:
    """
    Master cleaner — single entry point for all stage2 downstream steps.

    Args:
        measure_name : display name of the measure (for CleanResult and logging)
        raw_dax      : raw DAX string from measures_resolved.json

    Returns:
        CleanResult — always. Never raises. Never returns None.

    Pipeline order (matters — each step feeds the next):
        1. remove_metadata_lines   → strip formatString/lineageTag
        2. remove_commented_lines  → strip // comments, capture them
        3. normalize_whitespace    → clean up blank lines
        4. remove_trailing_plus_zero → strip +0
        5. normalize_keywords      → uppercase DAX keywords (skip quoted strings)
        6. normalize_whitespace    → final pass after keyword normalization
        7. is_hardcoded_string     → detect INFO_TEXT pattern
        8. detect_typos            → warn on EC22/EC20 typos

    NOTE on step order:
        Metadata must be stripped BEFORE keyword normalization.
        Otherwise "formatString" gets its 'f' normalized (harmless but messy).

        Comments stripped BEFORE +0 removal.
        A comment like "// +0 added for blank handling" must not confuse +0 stripper.

        Both whitespace passes needed:
        First after comment removal (removes blank lines left by stripped comments).
        Second after keyword normalization (normalization can leave trailing spaces).
    """
    warnings = []

    # Step 1: strip metadata
    dax, had_metadata = remove_metadata_lines(raw_dax)

    # Step 2: strip comments, capture them
    dax, stripped_comments = remove_commented_lines(dax)

    # Step 3: whitespace pass 1
    dax = normalize_whitespace(dax)

    # Step 4: strip +0
    dax, had_plus_zero = remove_trailing_plus_zero(dax)

    # Step 5: uppercase keywords (skip quoted strings)
    if not is_hardcoded_string(dax):
        dax = normalize_keywords(dax)

    # Step 6: whitespace pass 2
    dax = normalize_whitespace(dax)

    # Step 7: detect INFO_TEXT
    hardcoded = is_hardcoded_string(dax)

    # Step 8: warn on typos (warn only — do not correct)
    typo_warnings = detect_typos(dax)
    warnings.extend(typo_warnings)

    # Warn if comments were stripped that look like hidden logic
    for comment in stripped_comments:
        if any(kw in comment.upper() for kw in ['IF(', 'SWITCH', 'SELECTEDVALUE', 'VAR ']):
            warnings.append(
                f"HIDDEN_LOGIC_IN_COMMENT: Stripped comment may contain meaningful DAX: "
                f"'{comment[:80]}{'...' if len(comment) > 80 else ''}' — review manually."
            )

    return CleanResult(
        measure_name        = measure_name,
        raw_dax             = raw_dax,
        clean_dax           = dax,
        is_hardcoded_string = hardcoded,
        stripped_comments   = stripped_comments,
        warnings            = warnings,
        had_metadata        = had_metadata,
        had_plus_zero       = had_plus_zero,
    )


# ══════════════════════════════════════════════════════════════
# BATCH HELPER  — for pipeline.py
# ══════════════════════════════════════════════════════════════

def clean_all(measures: dict) -> dict[str, CleanResult]:
    """
    Clean all measures from measures_resolved.json.

    Args:
        measures : dict of {measure_name: measure_object}
                   measure_object must have a "dax" key

    Returns:
        dict of {measure_name: CleanResult}

    Called by pipeline.py — not used directly in tests.
    """
    return {
        name: clean(name, m.get("dax", "") or m.get("clean_dax", ""))
        for name, m in measures.items()
    }


# ══════════════════════════════════════════════════════════════
# SELF-TEST  —  run: python cleaner.py
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    Tests cover every edge case this file handles.
    All must pass before moving to lexer.py.

    Run from stage2/ folder:
        python cleaner.py
    """
    all_pass = True

    def check(label: str, condition: bool):
        global all_pass
        if condition:
            print(f"  ✅  {label}")
        else:
            print(f"  ❌  {label}")
            all_pass = False

    print("=== cleaner.py self-test ===\n")

    # ── EC1: +0 strip ───────────────────────────────────────
    print("EC1 — +0 strip:")
    r = clean("#Members", "SUM(attribution[member_count]) + 0")
    check("+0 stripped from clean_dax",    "+0" not in r.clean_dax)
    check("had_plus_zero=True",            r.had_plus_zero is True)
    check("SUM still present",             "SUM" in r.clean_dax)
    check("is_hardcoded_string=False",     r.is_hardcoded_string is False)

    # ── EC1 variant: no +0 ──────────────────────────────────
    print("\nEC1 — no +0 (should not flag):")
    r2 = clean("PMPM", "DIVIDE(SUM(attribution[ytd_visit_amount]), SUM(attribution[ytd_member_count]))")
    check("had_plus_zero=False",           r2.had_plus_zero is False)
    check("DIVIDE preserved",              "DIVIDE" in r2.clean_dax)

    # ── EC5/EC14: metadata strip ─────────────────────────────
    print("\nEC5/EC14 — formatString/lineageTag strip:")
    raw_meta = (
        "DIVIDE(Num, Denom) * 12000\n"
        "formatString: #,0\n"
        "lineageTag: b2578648-abc\n"
        "annotation PBI_FormatHint = {}"
    )
    r3 = clean("Utilization", raw_meta)
    check("formatString stripped",         "formatString" not in r3.clean_dax)
    check("lineageTag stripped",           "lineageTag"   not in r3.clean_dax)
    check("annotation stripped",           "annotation"   not in r3.clean_dax)
    check("had_metadata=True",             r3.had_metadata is True)
    check("DIVIDE preserved",              "DIVIDE"       in r3.clean_dax)

    # ── EC6/EC15: comment strip + capture ───────────────────
    print("\nEC6/EC15 — comment strip + capture:")
    raw_comment = (
        '"The cohort is built on latest risk execution data..."\n'
        "// IF(SELECTEDVALUE('measure'[period_mode]) = \"ytd\",\"...\")"
    )
    r4 = clean("Info text risk cohort", raw_comment)
    check("comment stripped from clean_dax",  "//" not in r4.clean_dax)
    check("comment captured in list",         len(r4.stripped_comments) == 1)
    check("captured comment has IF(",         "IF(" in r4.stripped_comments[0])
    check("warning about hidden logic",       any("HIDDEN_LOGIC" in w for w in r4.warnings))
    check("is_hardcoded_string=True",         r4.is_hardcoded_string is True)

    # ── INFO_TEXT: empty string ──────────────────────────────
    print("\nINFO_TEXT — empty string:")
    r5 = clean("Blank DAX", '""')
    check('is_hardcoded_string=True for ""',  r5.is_hardcoded_string is True)

    # ── Keyword normalization ────────────────────────────────
    print("\nKeyword normalization:")
    raw_lower = "var a = sum(risk_core[risk_value])\nreturn divide(a, 2)"
    r6 = clean("test measure", raw_lower)
    check("VAR uppercase",     "VAR"    in r6.clean_dax)
    check("SUM uppercase",     "SUM"    in r6.clean_dax)
    check("RETURN uppercase",  "RETURN" in r6.clean_dax)
    check("DIVIDE uppercase",  "DIVIDE" in r6.clean_dax)

    # ── EC9: quoted "true" NOT uppercased ───────────────────
    print('\nEC9 — "true" string not touched:')
    raw_str_true = 'CALCULATE(COUNTROWS(t), t[readmission_flag] = "true")'
    r7 = clean("test", raw_str_true)
    check('"true" preserved in quotes',   '"true"' in r7.clean_dax)
    check("CALCULATE uppercased",         "CALCULATE" in r7.clean_dax)
    check("COUNTROWS uppercased",         "COUNTROWS" in r7.clean_dax)

    # ── EC8: unquoted true/TRUE normalized ──────────────────
    print("\nEC8 — unquoted true normalized to TRUE:")
    raw_true = "CALCULATE(COUNTROWS(t), t[flag] = true)"
    r8 = clean("test", raw_true)
    # after normalization, 'true' keyword becomes 'TRUE'
    check("TRUE uppercase (unquoted)",    "= TRUE" in r8.clean_dax or "=TRUE" in r8.clean_dax)

    # ── EC22: typo warning ───────────────────────────────────
    print("\nEC22 — typo detection:")
    raw_typo = 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[flag] IN {"Undoumented","Suspected"}))'
    r9 = clean("Gap to potential risk", raw_typo)
    check("typo warning added",                len(r9.warnings) > 0)
    check("warning mentions Undoumented",       any("Undoumented" in w for w in r9.warnings))
    check("typo NOT corrected in clean_dax",    "Undoumented" in r9.clean_dax)

    # ── EC20: column name typo ───────────────────────────────
    print("\nEC20 — column name typo:")
    raw_col_typo = "COUNTROWS(VALUES(attribution[last_year_comparision_flag]))"
    r10 = clean("Info text PAC LY", raw_col_typo)
    check("comparision typo warning",           any("comparision" in w for w in r10.warnings))
    check("NOT corrected in clean_dax",         "comparision" in r10.clean_dax)

    # ── CleanResult fields ───────────────────────────────────
    print("\nCleanResult fields:")
    r11 = clean("#Members", "SUM(attribution[member_count]) + 0")
    check("measure_name set",     r11.measure_name == "#Members")
    check("raw_dax preserved",    "+ 0" in r11.raw_dax)
    check("clean_dax different",  r11.raw_dax != r11.clean_dax)
    check("warnings is list",     isinstance(r11.warnings, list))
    check("stripped_comments is list", isinstance(r11.stripped_comments, list))

    # ── CALCULATE with no filters (EC16) ────────────────────
    print("\nEC16 — CALCULATE with no filters:")
    raw_ec16 = "CALCULATE(count(pac_opp_patient_view[visit_id])) + 0"
    r12 = clean("IP Discharges", raw_ec16)
    check("+0 stripped",           "+0" not in r12.clean_dax)
    check("CALCULATE preserved",   "CALCULATE" in r12.clean_dax)
    check("COUNT uppercase",       "COUNT" in r12.clean_dax)

    # ── Full real measure: Gap to potential risk ─────────────
    print("\nFull measure — Gap to potential risk:")
    raw_gap = (
        'VAR a = CALCULATE(SUM(risk_core[risk_value]),\n'
        '  KEEPFILTERS(risk_core[risk_documentation_flag]\n'
        '  IN {"Undocumented","Suspected"}))\n'
        'VAR b = CALCULATE(SUM(risk_core[patient_count]),\n'
        '  KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))\n'
        'RETURN DIVIDE(a,b)'
    )
    r13 = clean("Gap to potential risk", raw_gap)
    check("VAR uppercase",           "VAR"      in r13.clean_dax)
    check("CALCULATE uppercase",     "CALCULATE" in r13.clean_dax)
    check("KEEPFILTERS uppercase",   "KEEPFILTERS" in r13.clean_dax)
    check("RETURN uppercase",        "RETURN"   in r13.clean_dax)
    check("DIVIDE uppercase",        "DIVIDE"   in r13.clean_dax)
    check("string values unchanged", '"Undocumented"' in r13.clean_dax)
    check("no +0",                   "+0" not in r13.clean_dax)
    check("no warnings",             r13.warnings == [])

    # ── Summary ─────────────────────────────────────────────
    print()
    if all_pass:
        print("✅  All cleaner.py tests passed.")
        print("    Next step: lexer.py")
    else:
        print("❌  Some tests failed — fix before moving to lexer.py")