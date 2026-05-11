"""
lexer.py
────────
Stage 2 — Step 2 (Part 1 of 2)

PURPOSE:
    Takes clean_dax string (from CleanResult.clean_dax) and returns
    a flat list of Token objects. No AST yet — just tokens.

INPUT:
    clean_dax string  (already cleaned by cleaner.py)

OUTPUT:
    LexResult dataclass:
        tokens  : list[Token]   on success
        error   : str | None    on failure (never raises)

WHY HAND-WRITTEN (not lark's built-in lexer):
    lark is used in parser.py for grammar rules.
    The lexer is hand-written because DAX has 3 quirks that
    generic tokenizers handle poorly:

    QUIRK 1 — Quoted table names:
        'date'[month_of_date]
        Single-quoted identifier is a TABLE NAME only when followed by [.
        Generic tokenizers treat 'date' as a string literal.
        We need QUOTED_NAME token, not STRING.

    QUIRK 2 — Curly brace sets (EC2):
        IN {"Undocumented", "Suspected"}
        { and } are SET delimiters in DAX (not block delimiters).
        Must become LBRACE / RBRACE tokens.

    QUIRK 3 — && operator (CompoundAnd):
        col = TRUE() && col = "X"
        Two chars, must become one AND_AND token.

TOKEN TYPES:
    IDENT        → SUM, CALCULATE, VAR, RETURN, TRUE, FALSE, IN, ALL
                   unquoted identifiers and keywords
    QUOTED_NAME  → 'date', 'Y Axis scatter plot'
                   single-quoted table names (quotes stripped from value)
    STRING       → "Documented", "Home Health", "true", "Undoumented"
                   double-quoted string values (quotes stripped from value)
                   EC9: "true" → STRING (not BOOL) — parser decides type later
    NUMBER       → 0, 1, 12000, 0.5
    LBRACKET     → [
    RBRACKET     → ]
    LPAREN       → (
    RPAREN       → )
    LBRACE       → {   (EC2: set delimiter)
    RBRACE       → }   (EC2: set delimiter)
    COMMA        → ,
    DOT          → .
    EQ           → =
    NEQ          → <>  (EC3: not-equal, two chars, one token)
    GT           → >
    LT           → <
    GTE          → >=
    LTE          → <=
    PLUS         → +
    MINUS        → -
    STAR         → *
    SLASH        → /
    AMP          → &   (string concat in DAX — for DISPLAY measures)
    AND_AND      → &&  (compound filter — two chars, one token)

WHAT GETS SKIPPED:
    Whitespace and newlines — DAX is whitespace-insensitive
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


# ══════════════════════════════════════════════════════════════
# TOKEN
# ══════════════════════════════════════════════════════════════

@dataclass
class Token:
    """
    A single token produced by the lexer.

    Fields:
        type  : token type string (e.g. "IDENT", "STRING", "LPAREN")
        value : exact text — quotes stripped for STRING and QUOTED_NAME
        pos   : character position in input string (for error messages)

    Examples:
        Token("IDENT",       "SUM",              0)
        Token("LPAREN",      "(",                3)
        Token("QUOTED_NAME", "date",             4)   ← quotes stripped
        Token("LBRACKET",    "[",               10)
        Token("IDENT",       "month_of_date",   11)
        Token("RBRACKET",    "]",               24)
        Token("STRING",      "Documented",      30)   ← quotes stripped
        Token("NUMBER",      "12000",           50)
        Token("NEQ",         "<>",              60)
        Token("AND_AND",     "&&",              70)
    """
    type:  str
    value: str
    pos:   int

    def __repr__(self):
        return f"Token({self.type}, {self.value!r}, pos={self.pos})"


# ══════════════════════════════════════════════════════════════
# LEX RESULT
# ══════════════════════════════════════════════════════════════

@dataclass
class LexResult:
    """
    Output of tokenize(). Always returned — never raises.

    Fields:
        tokens : list of Token  (empty list on failure)
        error  : None on success, error message string on failure
        dax    : the input string (for debugging)
    """
    tokens: list
    error:  Optional[str]
    dax:    str

    @property
    def ok(self) -> bool:
        return self.error is None


# ══════════════════════════════════════════════════════════════
# TOKENIZER
# ══════════════════════════════════════════════════════════════

def tokenize(dax: str) -> LexResult:
    """
    Tokenize a clean DAX string into a flat list of tokens.

    Returns LexResult — always. Never raises.

    Algorithm:
        Single pass through the string using pos cursor.
        Rules tried in priority order at each position:
          1. Skip whitespace / newlines
          2. Two-char operators first  (<>, >=, <=, &&)
          3. Single-char operators / delimiters
          4. Quoted table name  'name'[  (QUIRK 1)
          5. Double-quoted string  "value"
          6. Number  (digits, optional decimal point)
          7. Identifier / keyword
          8. Unknown character → LexResult with error
    """
    tokens = []
    pos    = 0
    n      = len(dax)

    try:
        while pos < n:

            # ── 1. Skip whitespace ───────────────────────────
            if dax[pos] in ' \t\n\r':
                pos += 1
                continue

            # ── 2. Two-char operators ────────────────────────
            two = dax[pos:pos+2]

            if two == '<>':
                tokens.append(Token("NEQ",     "<>", pos)); pos += 2; continue
            if two == '>=':
                tokens.append(Token("GTE",     ">=", pos)); pos += 2; continue
            if two == '<=':
                tokens.append(Token("LTE",     "<=", pos)); pos += 2; continue
            if two == '&&':
                tokens.append(Token("AND_AND", "&&", pos)); pos += 2; continue

            # ── 3. Single-char operators / delimiters ────────
            ch = dax[pos]

            if ch == '(':
                tokens.append(Token("LPAREN",   "(", pos)); pos += 1; continue
            if ch == ')':
                tokens.append(Token("RPAREN",   ")", pos)); pos += 1; continue
            if ch == '[':
                tokens.append(Token("LBRACKET", "[", pos)); pos += 1; continue
            if ch == ']':
                tokens.append(Token("RBRACKET", "]", pos)); pos += 1; continue
            if ch == '{':
                tokens.append(Token("LBRACE",   "{", pos)); pos += 1; continue
            if ch == '}':
                tokens.append(Token("RBRACE",   "}", pos)); pos += 1; continue
            if ch == ',':
                tokens.append(Token("COMMA",    ",", pos)); pos += 1; continue
            if ch == '=':
                tokens.append(Token("EQ",       "=", pos)); pos += 1; continue
            if ch == '>':
                tokens.append(Token("GT",       ">", pos)); pos += 1; continue
            if ch == '<':
                tokens.append(Token("LT",       "<", pos)); pos += 1; continue
            if ch == '+':
                tokens.append(Token("PLUS",     "+", pos)); pos += 1; continue
            if ch == '-':
                tokens.append(Token("MINUS",    "-", pos)); pos += 1; continue
            if ch == '*':
                tokens.append(Token("STAR",     "*", pos)); pos += 1; continue
            if ch == '/':
                tokens.append(Token("SLASH",    "/", pos)); pos += 1; continue
            if ch == '&':
                tokens.append(Token("AMP",      "&", pos)); pos += 1; continue
            if ch == '.':
                tokens.append(Token("DOT",      ".", pos)); pos += 1; continue

            # ── 4. Single-quoted name  'table'[  (QUIRK 1) ──
            # A single-quoted identifier is a TABLE NAME when followed by [.
            # e.g. 'date'[month_of_date]  or  'Y Axis scatter plot'[Y axis]
            # Value stored WITHOUT quotes.
            if ch == "'":
                end = dax.find("'", pos + 1)
                if end == -1:
                    return LexResult(
                        tokens = [],
                        error  = (f"Unterminated single-quoted name at pos {pos}: "
                                  f"{dax[pos:pos+20]!r}"),
                        dax    = dax,
                    )
                name  = dax[pos+1 : end]       # content between the quotes
                after = dax[end+1:].lstrip()   # text after closing quote

                if after.startswith('['):
                    tokens.append(Token("QUOTED_NAME", name, pos))
                else:
                    # Lone single-quoted string — treat as STRING
                    tokens.append(Token("STRING", name, pos))
                pos = end + 1
                continue

            # ── 5. Double-quoted string  "value" ─────────────
            # EC9:  "true"        → STRING (not BOOL — parser decides)
            # EC22: "Undoumented" → STRING (typo passed through as-is)
            # Value stored WITHOUT quotes.
            if ch == '"':
                end = pos + 1
                while end < n:
                    if dax[end] == '\\':   # escaped character — skip both
                        end += 2
                        continue
                    if dax[end] == '"':
                        break
                    end += 1
                if end >= n:
                    return LexResult(
                        tokens = [],
                        error  = (f"Unterminated double-quoted string at pos {pos}: "
                                  f"{dax[pos:pos+30]!r}"),
                        dax    = dax,
                    )
                value = dax[pos+1 : end]       # content between the quotes
                tokens.append(Token("STRING", value, pos))
                pos = end + 1
                continue

            # ── 6. Number  (integer or float) ────────────────
            if ch.isdigit():
                start = pos
                while pos < n and dax[pos].isdigit():
                    pos += 1
                # optional decimal part
                if (pos < n and dax[pos] == '.'
                        and pos + 1 < n and dax[pos+1].isdigit()):
                    pos += 1   # consume the dot
                    while pos < n and dax[pos].isdigit():
                        pos += 1
                tokens.append(Token("NUMBER", dax[start:pos], start))
                continue

            # ── 7. Identifier / keyword ───────────────────────
            # Covers: SUM, CALCULATE, VAR, RETURN, TRUE, FALSE, IN,
            #         risk_core, attribution, member_count, etc.
            # Also covers measure name parts after [ e.g. #Members, % Members
            # Fix1: % added — measure names like [% Members with open coding gaps]
            if ch.isalpha() or ch in "_#%":
                start = pos
                while pos < n and (dax[pos].isalnum() or dax[pos] in "_#%"):
                    pos += 1
                tokens.append(Token("IDENT", dax[start:pos], start))
                continue

            # ── 8. Unknown character → error ─────────────────
            return LexResult(
                tokens = [],
                error  = (f"Unexpected character {ch!r} at pos {pos} "
                          f"near: {dax[max(0,pos-10):pos+10]!r}"),
                dax    = dax,
            )

    except Exception as exc:
        return LexResult(
            tokens = [],
            error  = f"Lexer internal error at pos {pos}: {exc}",
            dax    = dax,
        )

    return LexResult(tokens=tokens, error=None, dax=dax)


# ══════════════════════════════════════════════════════════════
# DEBUG HELPER
# ══════════════════════════════════════════════════════════════

def tokens_to_str(tokens: list) -> str:
    """
    Human-readable one-line summary of a token list.
    Used in test output and error messages.

    Example output:
        [IDENT:SUM, LPAREN, QUOTED_NAME:date, LBRACKET, IDENT:month_of_date, RBRACKET, RPAREN]
    """
    parts = []
    for t in tokens:
        if t.type in ("IDENT", "QUOTED_NAME", "STRING", "NUMBER"):
            parts.append(f"{t.type}:{t.value}")
        else:
            parts.append(t.type)
    return "[" + ", ".join(parts) + "]"


# ══════════════════════════════════════════════════════════════
# SELF-TEST  —  run: python lexer.py
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    all_pass = True

    def check(label: str, condition: bool):
        global all_pass
        status = "✅" if condition else "❌"
        print(f"  {status}  {label}")
        if not condition:
            all_pass = False

    def types(dax: str) -> list:
        r = tokenize(dax)
        return [t.type for t in r.tokens] if r.ok else [f"ERROR:{r.error}"]

    def vals(dax: str) -> list:
        r = tokenize(dax)
        return [t.value for t in r.tokens] if r.ok else [f"ERROR:{r.error}"]

    print("=== lexer.py self-test ===\n")

    # ── Basic tokens ─────────────────────────────────────────
    print("Basic tokens:")
    r = tokenize("SUM()")
    check("SUM() → 3 tokens",           len(r.tokens) == 3)
    check("token[0] IDENT:SUM",         r.tokens[0].type == "IDENT"
                                        and r.tokens[0].value == "SUM")
    check("token[1] LPAREN",            r.tokens[1].type == "LPAREN")
    check("token[2] RPAREN",            r.tokens[2].type == "RPAREN")
    check("ok=True",                    r.ok is True)

    # ── Unquoted table[column] ───────────────────────────────
    print("\nUnquoted table[column]:")
    r = tokenize("attribution[member_count]")
    check("4 tokens",                   len(r.tokens) == 4)
    check("IDENT:attribution",          r.tokens[0].value == "attribution")
    check("LBRACKET",                   r.tokens[1].type  == "LBRACKET")
    check("IDENT:member_count",         r.tokens[2].value == "member_count")
    check("RBRACKET",                   r.tokens[3].type  == "RBRACKET")

    # ── QUIRK 1: Quoted table name ───────────────────────────
    print("\nQUIRK 1 — quoted table name 'date'[col]:")
    r = tokenize("'date'[month_of_date]")
    check("4 tokens",                   len(r.tokens) == 4)
    check("QUOTED_NAME:date",           r.tokens[0].type == "QUOTED_NAME"
                                        and r.tokens[0].value == "date")
    check("LBRACKET",                   r.tokens[1].type == "LBRACKET")
    check("IDENT:month_of_date",        r.tokens[2].value == "month_of_date")
    check("quotes stripped",            "'" not in r.tokens[0].value)

    # ── Quoted name with spaces ──────────────────────────────
    print("\nQuoted name with spaces:")
    r = tokenize("'Y Axis scatter plot'[Y axis]")
    check("QUOTED_NAME with spaces",    r.tokens[0].value == "Y Axis scatter plot")

    # ── QUIRK 2: Curly braces ────────────────────────────────
    print("\nQUIRK 2 — curly braces EC2:")
    r = tokenize('flag IN {"Undocumented","Suspected"}')
    tlist = [t.type for t in r.tokens]
    check("LBRACE present",             "LBRACE" in tlist)
    check("RBRACE present",             "RBRACE" in tlist)
    check("STRING:Undocumented",        any(t.type=="STRING" and t.value=="Undocumented"
                                            for t in r.tokens))
    check("STRING:Suspected",           any(t.type=="STRING" and t.value=="Suspected"
                                            for t in r.tokens))

    # ── EC22: typo passthrough ───────────────────────────────
    print("\nEC22 — typo passthrough:")
    r = tokenize('flag IN {"Undoumented","Suspected"}')
    check("Undoumented stored as-is",   any(t.value == "Undoumented" for t in r.tokens))

    # ── QUIRK 3: && operator ─────────────────────────────────
    print("\nQUIRK 3 — && operator:")
    r = tokenize("flag1 = TRUE() && flag2 = TRUE()")
    and_toks = [t for t in r.tokens if t.type == "AND_AND"]
    check("AND_AND token present",      len(and_toks) == 1)
    check("AND_AND value = '&&'",       and_toks[0].value == "&&")
    check("not two separate tokens",    not (
                                            any(t.type=="AMP" for t in r.tokens)))

    # ── EC3: <> operator ────────────────────────────────────
    print("\nEC3 — <> not-equal:")
    r = tokenize('pac_view[type] <> "Home Health"')
    neq_toks = [t for t in r.tokens if t.type == "NEQ"]
    check("NEQ token present",          len(neq_toks) == 1)
    check("NEQ value = '<>'",           neq_toks[0].value == "<>")
    check("no separate LT + GT",        not (any(t.type=="LT" for t in r.tokens)
                                             and any(t.type=="GT" for t in r.tokens)))

    # ── EC9: "true" string vs TRUE keyword ──────────────────
    print("\nEC9 — string true vs keyword TRUE:")
    r1 = tokenize('"true"')
    check('"true" → STRING',            r1.tokens[0].type  == "STRING")
    check('"true" value = true',        r1.tokens[0].value == "true")

    r2 = tokenize("TRUE")
    check("TRUE → IDENT",               r2.tokens[0].type  == "IDENT")
    check("TRUE value = TRUE",          r2.tokens[0].value == "TRUE")

    # ── Numbers ──────────────────────────────────────────────
    print("\nNumbers:")
    check("12000 → NUMBER",             types("12000") == ["NUMBER"])
    check("12000 value correct",        vals("12000")  == ["12000"])
    check("0.5 → NUMBER",               types("0.5")   == ["NUMBER"])
    check("0.5 value correct",          vals("0.5")    == ["0.5"])
    check("0 → NUMBER",                 types("0")     == ["NUMBER"])

    # ── Double-quoted string ─────────────────────────────────
    print("\nDouble-quoted string:")
    r = tokenize('"Documented"')
    check("STRING token",               r.tokens[0].type  == "STRING")
    check("quotes stripped",            r.tokens[0].value == "Documented")
    check("no quotes in value",         '"' not in r.tokens[0].value)

    # ── All single-char operators ─────────────────────────────
    print("\nSingle-char operators:")
    check("= → EQ",      types("=")  == ["EQ"])
    check("> → GT",      types(">")  == ["GT"])
    check("< → LT",      types("<")  == ["LT"])
    check("+ → PLUS",    types("+")  == ["PLUS"])
    check("- → MINUS",   types("-")  == ["MINUS"])
    check("* → STAR",    types("*")  == ["STAR"])
    check("/ → SLASH",   types("/")  == ["SLASH"])
    check("& → AMP",     types("&")  == ["AMP"])
    check(", → COMMA",   types(",")  == ["COMMA"])
    check("{ → LBRACE",  types("{")  == ["LBRACE"])
    check("} → RBRACE",  types("}")  == ["RBRACE"])

    # ── Two-char operators ────────────────────────────────────
    print("\nTwo-char operators:")
    check(">= → GTE",    types(">=") == ["GTE"])
    check("<= → LTE",    types("<=") == ["LTE"])
    check("<> → NEQ",    types("<>") == ["NEQ"])
    check("&& → AND_AND",types("&&") == ["AND_AND"])

    # ── Whitespace ignored ───────────────────────────────────
    print("\nWhitespace:")
    r1 = tokenize("SUM(a[b])")
    r2 = tokenize("SUM( a [ b ] )")
    r3 = tokenize("SUM(\n  a[b]\n)")
    check("spaces ignored",             vals("SUM(a[b])") == vals("SUM( a [ b ] )"))
    check("newlines ignored",           vals("SUM(a[b])") == vals("SUM(\n  a[b]\n)"))

    # ── LexResult fields ────────────────────────────────────
    print("\nLexResult:")
    r_ok = tokenize("SUM(a[b])")
    check("ok=True on valid input",     r_ok.ok)
    check("error=None on valid input",  r_ok.error is None)
    check("tokens populated",           len(r_ok.tokens) > 0)

    r_bad = tokenize("SUM('unterminated")
    check("ok=False on bad input",      not r_bad.ok)
    check("error message set",          r_bad.error is not None)
    check("tokens=[] on error",         r_bad.tokens == [])

    # ── #Members measure ref ─────────────────────────────────
    print("\nMeasureRef [#Members]:")
    r = tokenize("[#Members]")
    check("3 tokens",                   len(r.tokens) == 3)
    check("LBRACKET first",             r.tokens[0].type == "LBRACKET")
    check("#Members as IDENT",          r.tokens[1].value == "#Members")
    check("RBRACKET last",              r.tokens[2].type == "RBRACKET")

    # ── Token positions increase ─────────────────────────────
    print("\nToken positions:")
    r = tokenize("SUM(a[b])")
    check("pos=0 for SUM",              r.tokens[0].pos == 0)
    check("positions increase",         all(r.tokens[i].pos < r.tokens[i+1].pos
                                            for i in range(len(r.tokens)-1)))

    # ── Full real measure: P1 SUM ────────────────────────────
    print("\nFull measure — P1 SUM:")
    r = tokenize("SUM(attribution[member_count])")
    check("ok",                         r.ok)
    check("7 tokens",                   len(r.tokens) == 7)
    check("correct types",              [t.type for t in r.tokens] ==
                                        ["IDENT","LPAREN","IDENT","LBRACKET","IDENT","RBRACKET","RPAREN"])

    # ── Full real measure: P5 CALCULATE+KEEPFILTERS ──────────
    print("\nFull measure — P5 CALCULATE+KEEPFILTERS:")
    dax = 'CALCULATE(SUM(risk_core[risk_value]), KEEPFILTERS(risk_core[risk_documentation_flag] = "Documented"))'
    r = tokenize(dax)
    check("ok",                         r.ok)
    check("has IDENT:CALCULATE",        any(t.value=="CALCULATE"  for t in r.tokens))
    check("has IDENT:KEEPFILTERS",      any(t.value=="KEEPFILTERS" for t in r.tokens))
    check("has STRING:Documented",      any(t.type=="STRING" and t.value=="Documented"
                                            for t in r.tokens))

    # ── Full real measure: P11 time intel ────────────────────
    print("\nFull measure — P11 SAMEPERIODLASTYEAR:")
    dax = "CALCULATE([#Members], SAMEPERIODLASTYEAR('date'[month_of_date]))"
    r = tokenize(dax)
    check("ok",                         r.ok)
    check("has QUOTED_NAME:date",       any(t.type=="QUOTED_NAME" and t.value=="date"
                                            for t in r.tokens))
    check("has IDENT:SAMEPERIODLASTYEAR", any(t.value=="SAMEPERIODLASTYEAR"
                                              for t in r.tokens))

    # ── Full real measure: P4 DIVIDE × scalar ────────────────
    print("\nFull measure — P4 DIVIDE × scalar:")
    dax = ("VAR Num = CALCULATE(COUNT(pac_view[join_key]))\n"
           "VAR Denom = SUM(attribution[member_count])\n"
           "RETURN DIVIDE(Num, Denom) * 12000")
    r = tokenize(dax)
    check("ok",                         r.ok)
    check("has VAR",                    any(t.value=="VAR"    for t in r.tokens))
    check("has RETURN",                 any(t.value=="RETURN" for t in r.tokens))
    check("has STAR",                   any(t.type =="STAR"   for t in r.tokens))
    check("has NUMBER:12000",           any(t.type =="NUMBER" and t.value=="12000"
                                            for t in r.tokens))

    # ── Summary ─────────────────────────────────────────────
    print()
    if all_pass:
        print("✅  All lexer.py tests passed.")
        print("    Next step: parser.py")
    else:
        print("❌  Some tests failed — fix before moving to parser.py")