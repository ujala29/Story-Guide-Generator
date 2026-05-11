"""
Layer 1 — DAX Interpreter
==========================
Input  : L0Packet  (from layer0_preprocessor.py)
Output : L1Packet  (metric_profile — saved to disk + passed to Layer 2)

LLM ka ek kaam sirf:
  DAX formula + columns + glossary leke
  business meaning extract karo

No hallucination — sirf jo DAX mein likha hai wahi interpret karo.
Temperature = 0.1 (factual extraction)
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ensure stage1_extraction dir is on path so visual_parserL0 resolves
sys.path.insert(0, str(Path(__file__).resolve().parent))
from visual_parserL0 import L0Packet, DaxEntry, ColumnRef, PageVisual, PeerCard

# ============================================================
# CONFIG
# ============================================================

# Absolute path — working directory se independent
_HERE         = Path(__file__).parent.resolve()
_PROJECT_ROOT = _HERE.parent.parent.resolve()

sys.path.insert(0, str(_HERE.parent))  # src/ — for paths.py
from paths import get_paths as _get_paths

_DASHBOARD    = os.environ.get("STORY_DASHBOARD", "risk-dash")
L1_OUTPUT_DIR = str(_get_paths(_DASHBOARD).l1_packets_dir)

# ============================================================
# OUTPUT SCHEMA — L1Packet
# ============================================================

@dataclass
class L1Packet:
    """
    Layer 1 output — metric profile.

    Fields consumed by:
      Layer 2 — directional signals, cross-read patterns
      Layer 3 — Definition, Primary metric, Comparison rows
    """

    # ── Pass-through from L0 (identity) ───────────────────
    visual_id   : str
    title       : str
    visual_type : str          # cardVisual / lineChart etc.
    page        : str
    comparison  : str          # "YoY % change" | "MoM % change" | "None"
    active_filters : list[str] # ["year", "month", "payer"]

    # ── Core definition (Section 3) ───────────────────────
    one_line_definition : str
    # "RAF recapture rate measures what share of known dropped
    #  and undocumented HCC risk has been recoded through
    #  coded encounters."

    # ── Calculation breakdown ─────────────────────────────
    numerator_meaning   : str
    # "Risk value of conditions successfully coded this year"

    denominator_meaning : str
    # "Risk value of all known conditions — coded and uncoded
    #  (Suspected excluded)"
    # Empty string "" if not a ratio

    # ── Primary metric description (Section 4 row 2) ──────
    result_meaning : str
    # "Percentage of identified RAF opportunity captured
    #  through documentation — higher means more gaps closed"

    # ── Scope note ────────────────────────────────────────
    scope_note : str
    # "Suspected conditions excluded from both numerator
    #  and denominator"
    # Empty string "" if nothing notable

    # ── Direction + type ──────────────────────────────────
    direction   : str
    # "higher_is_better" | "lower_is_better" | "context_dependent"

    metric_type : str
    # "rate" | "count" | "average" | "gap" | "ratio"

    # ── Per-measure plain-english meanings ────────────────
    # key   = exact measure name
    # value = one sentence what it shows
    # Covers primary + YoY Card + MoM Card + Color etc.
    measure_meanings : dict[str, str]
    # ── Table-specific fields ─────────────────────────────
    is_table           : bool = False
    column_definitions : dict = field(default_factory=dict)
    # {
    #   "Members": {
     #     "definition": "...",
    #     "increasing": "...",
    #     "decreasing": "..."
    #   }, ...
    # }
    # ── LineChart-specific fields ─────────────────────────
    is_linechart       : bool = False
    # ── BarChart-specific fields ───────────────────────────
    is_barchart        : bool = False
    # ── DonutChart-specific fields ─────────────────────────
    is_donut           : bool = False
    # ── ScatterChart-specific fields ───────────────────────
    is_scatter         : bool = False

    # ── Validation ────────────────────────────────────────
    warnings    : list[str] = field(default_factory=list)
    skip        : bool      = False
    skip_reason : str       = ""


# ============================================================
# PROMPTS
# ============================================================

LAYER1_SYSTEM = """
You are a DAX formula interpreter for a healthcare
risk adjustment Power BI dashboard.

Your only job is to read DAX formulas and return
their business meaning as structured JSON.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Return ONLY valid JSON — no markdown, no explanation,
  no preamble, no triple backticks
- Interpret ONLY from the formula and glossary given
- Do NOT invent context not present in the formula
- Plain English only in all fields — no DAX syntax
  (no CALCULATE, DIVIDE, KEEPFILTERS, VAR, RETURN etc.)
- Every field = one sentence maximum
- denominator_meaning = empty string ""
  if the measure is not a ratio (SUM / COUNT / DISTINCTCOUNT)
- scope_note: mention ONLY if formula explicitly filters
  on a specific flag value (e.g. flag = "Documented" only,
  or flag IN {"Documented","Undocumented"} explicitly).
  Empty string "" if no flag filter present.
- measure_meanings: interpret EVERY measure listed —
  primary, YoY Card, MoM Card, Color — all of them

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DAX PATTERN RECOGNITION — CRITICAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
These patterns appear in this dashboard. Recognise them
correctly — wrong pattern recognition = wrong definition.

PATTERN 1 — Filtered ratio (both num + denom filtered):
  CALCULATE(DIVIDE(SUM(col_a), SUM(col_b)),
            KEEPFILTERS(flag = "X"))
  Meaning : col_a / col_b WHERE flag = X only
  Scope   : Only "X" flagged rows — other flags excluded
  Example : Documented risk = risk_value / patient_count
            WHERE flag = "Documented" only

PATTERN 2 — Mixed ratio (unfiltered num / filtered denom):
  var a = SUM(col_a)                        ← ALL rows
  var b = CALCULATE(SUM(col_b),
          KEEPFILTERS(flag = "X"))           ← filtered
  return DIVIDE(a, b)
  Meaning : total col_a (all flags) / col_b WHERE flag = X
  Scope   : Numerator includes ALL flags including Suspected
  Example : Potential risk = total risk_value (all flags)
            / patient_count WHERE flag = "Documented"
  IMPORTANT: This is NOT the same as Pattern 1.
             Numerator includes Undocumented + Suspected too.

PATTERN 3 — Flag-set ratio (num filtered to subset of flags):
  var a = CALCULATE(SUM(col_a),
          KEEPFILTERS(flag IN {"X","Y"}))    ← subset
  var b = CALCULATE(SUM(col_a),
          KEEPFILTERS(flag IN {"X","Y","Z"}))← full set
  return DIVIDE(a, b)
  Meaning : share of col_a that has flag X or Y
            out of all col_a with any known flag
  Scope   : Only explicitly listed flags in scope —
            flags NOT listed are excluded
  Example : RAF recapture rate = Documented risk value
            / (Documented + Undocumented) risk value
            Suspected is EXCLUDED from both

PATTERN 4 — YoY Card:
  VAR py = CALCULATE([measure], SAMEPERIODLASTYEAR(...))
  VAR yoy = DIVIDE([measure] - py, py, 0)
  RETURN IF(ISBLANK(py), "", SWITCH(...arrow & format...))
  Meaning : Year-over-year percentage change of [measure]
            formatted as "▲ 12% from LY" or "▼ 5% from LY"

PATTERN 5 — MoM Card:
  VAR py = CALCULATE([measure], PREVIOUSMONTH(...))
  Same structure as YoY Card
  Meaning : Month-over-month percentage change

PATTERN 6 — Color measure:
  VAR a = [some_yoy_or_mom_measure]
  RETURN SWITCH(TRUE(), a < 0, 1, 2)
  or     SWITCH(TRUE(), a < 0, 2, a > 0, 1)
  Meaning : Returns a colour code (1=green, 2=red) to
            drive conditional formatting on the card tile.
            Not a business metric — formatting only.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

LAYER1_USER = """
Visual title   : {title}
Visual type    : {visual_type}
Primary measure: {primary_measure}
Detected DAX pattern: {dax_pattern}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALL MEASURES ON THIS VISUAL
Interpret each one separately in measure_meanings.
Role column tells you what each measure does:
  primary   = the main KPI number on the card
  yoy_card  = year-over-year change tile (Pattern 4)
  mom_card  = month-over-month change tile (Pattern 5)
  yoy_color = colour formatter only (Pattern 6) — not a metric
  mom_color = colour formatter only (Pattern 6) — not a metric
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{all_measures_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GLOSSARY — use these exact meanings
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{glossary_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL INTERPRETATION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Use the detected DAX pattern above to guide
   numerator_meaning and denominator_meaning.

2. If pattern is "mixed_ratio":
   - numerator includes ALL flag values
     (Documented + Undocumented + Suspected)
   - denominator is filtered to one flag only
   - scope_note MUST mention what numerator includes

3. If pattern is "filtered_ratio":
   - both numerator AND denominator use the same flag filter
   - scope_note MUST mention which flag is in scope

4. If pattern is "flag_set_ratio":
   - numerator = subset of flags
   - denominator = larger set of flags
   - scope_note MUST mention which flags are excluded

5. Color measures (role = yoy_color / mom_color):
   - measure_meanings value = "Drives conditional colour
     formatting on the change tile — not a business metric"
   - Do NOT include in one_line_definition analysis

6. YoY/MoM Card measures:
   - measure_meanings value must mention
     "year-over-year" or "month-over-month" change

Return exactly this JSON — no other text:
{{
  "one_line_definition": "One sentence — what the primary
                          measure calculates in plain
                          business terms",

  "numerator_meaning":   "What the numerator of the primary
                          measure represents — mention which
                          flag values are included",

  "denominator_meaning": "What the denominator represents —
                          mention any flag filter applied.
                          Empty string if not a ratio.",

  "result_meaning":      "What the final number tells
                          the analyst — one sentence
                          used as Primary metric description",

  "scope_note":          "Which flag values are included or
                          excluded from the calculation scope.
                          Empty string if no flag filter.",

  "direction":           "higher_is_better OR
                          lower_is_better OR
                          context_dependent",

  "metric_type":         "rate OR count OR average
                          OR gap OR ratio",

  "measure_meanings": {{
    "exact measure name 1": "one sentence what it shows",
    "exact measure name 2": "one sentence what it shows"
  }}
}}
"""

# ============================================================
# DAX PATTERN DETECTOR
# ============================================================

def detect_dax_pattern(dax: str) -> str:
    """
    Primary measure DAX se pattern detect karo.
    Pattern name system prompt ke PATTERN labels se match karta hai.

    Returns one of:
      "filtered_ratio"  — PATTERN 1
      "mixed_ratio"     — PATTERN 2
      "flag_set_ratio"  — PATTERN 3
      "yoy_card"        — PATTERN 4
      "mom_card"        — PATTERN 5
      "color_measure"   — PATTERN 6
      "simple_sum"      — SUM / COUNT leaf measure
      "unknown"         — nahi pakda
    """
    if not dax:
        return "unknown"

    d = dax.lower().strip()

    # Pattern 6 — Color measure
    # SWITCH(TRUE(), a < 0, 1, 2) or similar
    if "switch(true()" in d and ("< 0" in d or "> 0" in d):
        if "unichar" not in d:   # not a card formatter
            return "color_measure"

    # Pattern 4 — YoY Card
    if "sameperiodlastyear" in d and "unichar" in d:
        return "yoy_card"

    # Pattern 5 — MoM Card
    if "previousmonth" in d and "unichar" in d:
        return "mom_card"

    # Pattern 3 — Flag-set ratio
    # Both num and denom use flag IN {set}
    # Identified by: two CALCULATE blocks both with flag IN
    if d.count("keepfilters") >= 2 and " in {" in d:
        return "flag_set_ratio"

    # Pattern 2 — Mixed ratio
    # var a = SUM(...)           ← no filter
    # var b = CALCULATE(... flag = X)
    # return DIVIDE(a, b)
    has_var        = "var a" in d or "var b" in d
    has_unfiltered = "var a" in d and "sum(" in d
    has_filtered_b = "var b" in d and "keepfilters" in d
    if has_var and has_unfiltered and has_filtered_b:
        return "mixed_ratio"

    # Pattern 1 — Filtered ratio
    # CALCULATE(DIVIDE(...), KEEPFILTERS(flag = "X"))
    if "calculate" in d and "divide" in d and "keepfilters" in d:
        return "filtered_ratio"

    # Simple sum / count / distinctcount
    if d.startswith("sum(") or d.startswith("distinctcount("):
        return "simple_sum"
    if d.startswith("calculate(") and "divide" not in d:
        return "simple_sum"

    return "unknown"


# ============================================================
# PROMPT BUILDER
# ============================================================

def _format_measures_block(
    all_dax   : list[DaxEntry],
    paired_dax: list[DaxEntry]
) -> str:
    """
    L0Packet.all_dax + L0Packet.paired_dax se
    ek readable block banao LLM ke liye.

    Deduplication — same measure do baar nahi aaye.
    """
    seen   = set()
    blocks = []

    for entry in all_dax + paired_dax:
        if entry.name in seen:
            continue
        seen.add(entry.name)

        cols = [c.raw for c in entry.columns]

        block = (
            f"Measure : {entry.name}\n"
            f"Role    : {entry.role}\n"
            f"DAX     : {entry.dax}\n"
            f"Columns : {cols}\n"
            f"Deps    : {entry.deps}"
        )
        blocks.append(block)

    return "\n\n".join(blocks) if blocks else "N/A"


def _format_glossary_block(glossary: dict) -> str:
    """
    L0Packet.glossary dict ko flat string mein.
    Nested sections flatten karo.
    """
    lines = []
    for section, terms in glossary.items():
        if isinstance(terms, dict):
            for term, meaning in terms.items():
                lines.append(f"{term} : {meaning}")
        else:
            lines.append(f"{section} : {terms}")
    return "\n".join(lines) if lines else "N/A"


def build_layer1_prompts(l0: L0Packet) -> tuple[str, str]:
    """
    L0Packet fields se system + user prompt banao.
    Returns (system_prompt, user_prompt)
    """
    measures_block = _format_measures_block(
        l0.all_dax,
        l0.paired_dax
    )

    glossary_block = _format_glossary_block(l0.glossary)

    # ── DAX pattern detect karo primary measure se ──────────
    primary_dax_str = (
        l0.primary_dax.dax
        if l0.primary_dax else ""
    )
    dax_pattern = detect_dax_pattern(primary_dax_str)

    user_prompt = LAYER1_USER.format(
        title              = l0.title,
        visual_type        = l0.visual_type,
        primary_measure    = l0.primary_measure,
        dax_pattern        = dax_pattern,
        all_measures_block = measures_block,
        glossary_block     = glossary_block
    )

    return LAYER1_SYSTEM, user_prompt


# ============================================================
# RESPONSE PARSER + VALIDATOR
# ============================================================

VALID_DIRECTIONS = {
    "higher_is_better",
    "lower_is_better",
    "context_dependent"
}

VALID_METRIC_TYPES = {
    "rate", "count", "average", "gap", "ratio"
}

REQUIRED_FIELDS = [
    "one_line_definition",
    "result_meaning",
    "direction",
    "metric_type",
    "measure_meanings"
]


def _parse_l1_response(raw: str, l0: L0Packet) -> L1Packet:
    """
    LLM response JSON parse karo.
    Validation + fallbacks handle karo.
    """
    warnings = []

    # ── Strip accidental markdown fences ────────────────────
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts   = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    # ── JSON parse ──────────────────────────────────────────
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return L1Packet(
            visual_id           = l0.visual_id,
            title               = l0.title,
            visual_type         = l0.visual_type,
            page                = l0.page,
            comparison          = l0.comparison,
            active_filters      = l0.active_filters,
            one_line_definition = "",
            numerator_meaning   = "",
            denominator_meaning = "",
            result_meaning      = "",
            scope_note          = "",
            direction           = "",
            metric_type         = "",
            measure_meanings    = {},
            warnings            = [
                f"JSON parse error: {e}",
                f"Raw response (first 300): {raw[:300]}"
            ],
            skip        = True,
            skip_reason = "layer1_json_parse_failed"
        )

    # ── Required fields check ────────────────────────────────
    for fname in REQUIRED_FIELDS:
        if not data.get(fname):
            warnings.append(f"Missing or empty field: '{fname}'")

    # ── Direction validate ───────────────────────────────────
    direction = data.get("direction", "context_dependent")
    if direction not in VALID_DIRECTIONS:
        warnings.append(
            f"Invalid direction '{direction}' "
            f"— defaulting to 'context_dependent'"
        )
        direction = "context_dependent"

    # ── Metric type validate ─────────────────────────────────
    metric_type = data.get("metric_type", "")
    if metric_type not in VALID_METRIC_TYPES:
        warnings.append(
            f"Invalid metric_type '{metric_type}'"
        )

    # ── measure_meanings — verify all L0 measures covered ────
    measure_meanings = data.get("measure_meanings", {})
    all_measure_names = (
        {e.name for e in l0.all_dax} |
        {e.name for e in l0.paired_dax}
    )
    missing_meanings = all_measure_names - set(measure_meanings.keys())
    if missing_meanings:
        warnings.append(
            f"measure_meanings missing for: {missing_meanings}"
        )

    return L1Packet(
        visual_id           = l0.visual_id,
        title               = l0.title,
        visual_type         = l0.visual_type,
        page                = l0.page,
        comparison          = l0.comparison,
        active_filters      = l0.active_filters,
        one_line_definition = data.get("one_line_definition", ""),
        numerator_meaning   = data.get("numerator_meaning", ""),
        denominator_meaning = data.get("denominator_meaning", ""),
        result_meaning      = data.get("result_meaning", ""),
        scope_note          = data.get("scope_note", ""),
        direction           = direction,
        metric_type         = metric_type,
        measure_meanings    = measure_meanings,
        warnings            = warnings,
        skip                = False,
        skip_reason         = ""
    )
TABLE_L1_SYSTEM = """
You are a DAX interpreter for a healthcare risk adjustment
Power BI matrix table.

Your job: for each column in the table, write:
  1. definition   — one sentence what this column measures
  2. increasing   — one sentence what rising values signal
  3. decreasing   — one sentence what falling values signal

Return ONLY valid JSON. No markdown. No preamble.
Use exact column names as keys.

Domain: healthcare risk adjustment dashboard.
Users: care managers, medical directors, payer analysts.

Key terms:
  RAF = Risk Adjustment Factor (composite HCC risk score)
  HCC = Hierarchical Condition Category
  Documented risk = risk value for already-coded conditions
  Gap to potential risk = uncaptured risk opportunity
  Recapture rate = % of gaps successfully closed
  PMPM = per-member-per-month cost
  YoY = year-over-year percentage change
"""

TABLE_L1_USER = """
Table title    : {title}
Row dimension  : {row_dimension}
Comparison type: {comparison}

Columns to interpret:
{columns_list}

Return exactly this JSON structure:
{{
  "one_line_definition": "One sentence — what this table shows overall",
  "result_meaning": "One sentence — what analysts use this table for",
  "column_definitions": {{
    "Column name 1": {{
      "definition": "...",
      "increasing": "...",
      "decreasing": "..."
    }},
    "Column name 2": {{
      "definition": "...",
      "increasing": "...",
      "decreasing": "..."
    }}
  }}
}}
"""

def _call_layer1_table(l0: L0Packet, llm_client) -> L1Packet:
    columns_list = "\n".join(
        f"  - {col}" for col in l0.table_columns
    )

    user_prompt = TABLE_L1_USER.format(
        title         = l0.title,
        row_dimension = l0.row_dimension,
        comparison    = l0.comparison,
        columns_list  = columns_list
    )

    response = llm_client.chat.completions.create(
        model = os.environ.get(
            "TF_MODEL", "internal-bedrock/sonnet-46"
        ),
        messages = [
            {"role": "system", "content": TABLE_L1_SYSTEM},
            {"role": "user",   "content": user_prompt}
        ],
        temperature = 0.1,
    )

    raw     = response.choices[0].message.content.strip()
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts   = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    warnings = []
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return L1Packet(
            visual_id=l0.visual_id, title=l0.title,
            visual_type=l0.visual_type, page=l0.page,
            comparison=l0.comparison, active_filters=l0.active_filters,
            one_line_definition="", numerator_meaning="",
            denominator_meaning="", result_meaning="",
            scope_note="", direction="context_dependent",
            metric_type="count", measure_meanings={},
            is_table=True, column_definitions={},
            warnings=[f"JSON parse error: {e}"],
            skip=True, skip_reason="table_l1_json_parse_failed"
        )

    # Validate — all table_columns covered
    col_defs = data.get("column_definitions", {})
    missing  = [c for c in l0.table_columns if c not in col_defs]
    if missing:
        warnings.append(
            f"column_definitions missing for: {missing}"
        )

    packet = L1Packet(
        visual_id           = l0.visual_id,
        title               = l0.title,
        visual_type         = l0.visual_type,
        page                = l0.page,
        comparison          = l0.comparison,
        active_filters      = l0.active_filters,
        one_line_definition = data.get("one_line_definition", ""),
        numerator_meaning   = "",
        denominator_meaning = "",
        result_meaning      = data.get("result_meaning", ""),
        scope_note          = "",
        direction           = "context_dependent",
        metric_type         = "count",
        measure_meanings    = {},
        is_table            = True,
        column_definitions  = col_defs,
        warnings            = warnings,
        skip                = False,
        skip_reason         = ""
    )

    save_l1_packet(packet)
    return packet

LINECHART_L1_SYSTEM = """
You are a dashboard analyst for a healthcare risk adjustment
Power BI dashboard.

Your job: for a trend line chart, write:
1. one_line_definition — one sentence what this chart shows
2. how_to_read — one paragraph (3-4 sentences) guiding the
   analyst on what patterns to look for, what divergence
   between lines means, and what actions to take

Return ONLY valid JSON. No markdown. No preamble.
"""

LINECHART_L1_USER = """
Chart title   : {title}
Lines present : {lines}
X-axis        : {x_axis}
Comparison    : {comparison}
Measures      : {measures}

Return exactly:
{{
  "one_line_definition": "...",
  "how_to_read": "..."
}}
"""


def _call_layer1_linechart(l0: L0Packet, llm_client) -> L1Packet:
    lines_str    = ", ".join(
        f"{l['display_name']} ({l['measure']})"
        for l in l0.chart_lines
    )
    measures_str = ", ".join(
        e.name for e in l0.all_dax
    )

    user_prompt = LINECHART_L1_USER.format(
        title      = l0.title,
        lines      = lines_str,
        x_axis     = l0.x_axis_col,
        comparison = l0.comparison,
        measures   = measures_str
    )

    response = llm_client.chat.completions.create(
        model = os.environ.get(
            "TF_MODEL", "internal-bedrock/sonnet-46"
        ),
        messages = [
            {"role": "system", "content": LINECHART_L1_SYSTEM},
            {"role": "user",   "content": user_prompt}
        ],
        temperature = 0.1,
    )

    raw     = response.choices[0].message.content.strip()
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts   = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    warnings = []
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return L1Packet(
            visual_id=l0.visual_id, title=l0.title,
            visual_type=l0.visual_type, page=l0.page,
            comparison=l0.comparison,
            active_filters=l0.active_filters,
            one_line_definition="", numerator_meaning="",
            denominator_meaning="", result_meaning="",
            scope_note="", direction="context_dependent",
            metric_type="count", measure_meanings={},
            is_table=False, column_definitions={},
            is_linechart=True,
            warnings=[f"JSON parse error: {e}"],
            skip=True,
            skip_reason="linechart_l1_json_parse_failed"
        )

    packet = L1Packet(
        visual_id           = l0.visual_id,
        title               = l0.title,
        visual_type         = l0.visual_type,
        page                = l0.page,
        comparison          = l0.comparison,
        active_filters      = l0.active_filters,
        one_line_definition = data.get("one_line_definition", ""),
        numerator_meaning   = "",
        denominator_meaning = "",
        result_meaning      = data.get("how_to_read", ""),
        scope_note          = "",
        direction           = "context_dependent",
        metric_type         = "count",
        measure_meanings    = {},
        is_table            = False,
        column_definitions  = {},
        is_linechart        = True,
        warnings            = warnings,
        skip                = False,
        skip_reason         = ""
    )

    save_l1_packet(packet)
    return packet


BARCHART_L1_SYSTEM = """
You are a dashboard analyst for a healthcare risk adjustment
Power BI dashboard.

Your job: for a bar chart, write:
1. one_line_definition — one sentence what this chart compares
   and across what dimension
2. directional_rows — exactly 3 rows for the directional
   impact table. Each row must have:
   - movement: what bar movement to observe
   - signal: "Positive", "Negative", or "Investigate"
   - interpretation: one sentence what it means clinically

Return ONLY valid JSON. No markdown. No preamble.
"""

BARCHART_L1_USER = """
Chart title    : {title}
Primary metric : {primary_measure}
Category axis  : {category_axis}
Orientation    : {orientation}
Tooltip        : {tooltip}
Comparison     : {comparison}

Return exactly:
{{
  "one_line_definition": "...",
  "directional_rows": [
    {{"movement": "...", "signal": "...", "interpretation": "..."}},
    {{"movement": "...", "signal": "...", "interpretation": "..."}},
    {{"movement": "...", "signal": "...", "interpretation": "..."}}
  ]
}}
"""


def _call_layer1_barchart(l0: L0Packet, llm_client) -> L1Packet:
    tooltip_str = ", ".join(
        t["display_name"] for t in l0.tooltip_measures
    ) if l0.tooltip_measures else "None"

    user_prompt = BARCHART_L1_USER.format(
        title          = l0.title,
        primary_measure= l0.primary_measure,
        category_axis  = l0.category_axis,
        orientation    = l0.bar_orientation,
        tooltip        = tooltip_str,
        comparison     = l0.comparison,
    )

    response = llm_client.chat.completions.create(
        model = os.environ.get(
            "TF_MODEL", "internal-bedrock/sonnet-46"
        ),
        messages = [
            {"role": "system", "content": BARCHART_L1_SYSTEM},
            {"role": "user",   "content": user_prompt}
        ],
        temperature = 0.1,
    )

    raw     = response.choices[0].message.content.strip()
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts   = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    warnings = []
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return L1Packet(
            visual_id=l0.visual_id, title=l0.title,
            visual_type=l0.visual_type, page=l0.page,
            comparison=l0.comparison,
            active_filters=l0.active_filters,
            one_line_definition="", numerator_meaning="",
            denominator_meaning="", result_meaning="",
            scope_note="", direction="context_dependent",
            metric_type="rate", measure_meanings={},
            is_table=False, column_definitions={},
            is_linechart=False, is_barchart=True,
            warnings=[f"JSON parse error: {e}"],
            skip=True,
            skip_reason="barchart_l1_json_parse_failed"
        )

    dir_rows = data.get("directional_rows", [])

    packet = L1Packet(
        visual_id           = l0.visual_id,
        title               = l0.title,
        visual_type         = l0.visual_type,
        page                = l0.page,
        comparison          = l0.comparison,
        active_filters      = l0.active_filters,
        one_line_definition = data.get("one_line_definition", ""),
        numerator_meaning   = "",
        denominator_meaning = "",
        result_meaning      = json.dumps(dir_rows),
        scope_note          = "",
        direction           = "context_dependent",
        metric_type         = "rate",
        measure_meanings    = {},
        is_table            = False,
        column_definitions  = {},
        is_linechart        = False,
        is_barchart         = True,
        warnings            = warnings,
        skip                = False,
        skip_reason         = ""
    )

    save_l1_packet(packet)
    return packet


DONUT_L1_SYSTEM = """
You are a dashboard analyst for a healthcare risk adjustment
Power BI dashboard.

For a donut chart, write:
1. one_line_definition — 2 sentences ending with a quoted
   question the chart answers e.g.
   "Shows X by Y category. Answers 'through which Y are Z?'"
2. pattern_rows — exactly 3 meaningful pattern rows as JSON:
   Each row: {"pattern": "...", "interpretation": "..."}
   Pattern = a dominant slice or distribution scenario
   Interpretation = one-line business consequence

Return ONLY valid JSON. No markdown. No preamble.
Domain: healthcare risk adjustment.
"""

DONUT_L1_USER = """
Chart title    : {title}
Primary metric : {primary_measure}
Legend/category: {legend_col}
Active filters : {active_filters}

Return exactly:
{{
  "one_line_definition": "...",
  "pattern_rows": [
    {{"pattern": "...", "interpretation": "..."}},
    {{"pattern": "...", "interpretation": "..."}},
    {{"pattern": "...", "interpretation": "..."}}
  ]
}}
"""


def _call_layer1_donut(l0: L0Packet, llm_client) -> L1Packet:
    user_prompt = DONUT_L1_USER.format(
        title           = l0.title,
        primary_measure = l0.primary_measure,
        legend_col      = l0.legend_col,
        active_filters  = l0.active_filters or "None"
    )

    response = llm_client.chat.completions.create(
        model = os.environ.get(
            "TF_MODEL", "internal-bedrock/sonnet-46"
        ),
        messages = [
            {"role": "system", "content": DONUT_L1_SYSTEM},
            {"role": "user",   "content": user_prompt}
        ],
        temperature = 0.1,
    )

    raw     = response.choices[0].message.content.strip()
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts   = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    warnings = []
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return L1Packet(
            visual_id=l0.visual_id, title=l0.title,
            visual_type=l0.visual_type, page=l0.page,
            comparison=l0.comparison,
            active_filters=l0.active_filters,
            one_line_definition="", numerator_meaning="",
            denominator_meaning="", result_meaning="",
            scope_note="", direction="context_dependent",
            metric_type="count", measure_meanings={},
            is_table=False, column_definitions={},
            is_linechart=False, is_barchart=False,
            is_donut=True,
            warnings=[f"JSON parse error: {e}"],
            skip=True,
            skip_reason="donut_l1_json_parse_failed"
        )

    pattern_rows = data.get("pattern_rows", [])

    packet = L1Packet(
        visual_id           = l0.visual_id,
        title               = l0.title,
        visual_type         = l0.visual_type,
        page                = l0.page,
        comparison          = l0.comparison,
        active_filters      = l0.active_filters,
        one_line_definition = data.get("one_line_definition", ""),
        numerator_meaning   = "",
        denominator_meaning = "",
        result_meaning      = json.dumps(pattern_rows),
        scope_note          = "",
        direction           = "context_dependent",
        metric_type         = "count",
        measure_meanings    = {},
        is_table            = False,
        column_definitions  = {},
        is_linechart        = False,
        is_barchart         = False,
        is_donut            = True,
        warnings            = warnings,
        skip                = False,
        skip_reason         = ""
    )

    save_l1_packet(packet)
    return packet


# ============================================================
# SCATTER CHART — Layer 1
# ============================================================

SCATTER_L1_SYSTEM = """
You are a dashboard analyst for a healthcare risk adjustment
Power BI dashboard.

For a scatter plot / bubble chart, write:
1. one_line_definition — 2-3 sentences explaining:
   - what each bubble represents
   - what X and Y axes measure
   - what bubble size encodes
   - what the chart helps identify

2. position_rows — exactly 5 rows as JSON array:
   Each row: {"position": "...", "interpretation": "..."}
   Positions must be:
   Row 1: Upper-right (high X, high Y)
   Row 2: Upper-left (low X, high Y)
   Row 3: Lower-right (high X, low Y)
   Row 4: Lower-left (low X, low Y)
   Row 5: Outlier far above the cluster

Return ONLY valid JSON. No markdown. No preamble.
Domain: healthcare risk adjustment.
"""

SCATTER_L1_USER = """
Chart title      : {title}
Y-axis metric    : {y_measure} (selectable via dropdown)
X-axis metric    : {x_measure} (selectable via dropdown)
Bubble size      : {bubble_size}
Category/identity: {scatter_category} — each bubble = one {scatter_category}
Comparison       : {comparison}

Return exactly:
{{
  "one_line_definition": "...",
  "position_rows": [
    {{"position": "Upper-right (high X, high Y)", "interpretation": "..."}},
    {{"position": "Upper-left (low X, high Y)", "interpretation": "..."}},
    {{"position": "Lower-right (high X, low Y)", "interpretation": "..."}},
    {{"position": "Lower-left (low X, low Y)", "interpretation": "..."}},
    {{"position": "Outlier far above the cluster", "interpretation": "..."}}
  ]
}}
"""

def _call_layer1_scatter(l0: L0Packet, llm_client) -> L1Packet:
    x_measure = "Selected X Axis Value"
    y_measure  = l0.primary_measure

    user_prompt = SCATTER_L1_USER.format(
        title            = l0.title,
        y_measure        = y_measure,
        x_measure        = x_measure,
        bubble_size      = l0.bubble_size,
        scatter_category = l0.scatter_category,
        comparison       = l0.comparison
    )

    response = llm_client.chat.completions.create(
        model = os.environ.get(
            "TF_MODEL", "internal-bedrock/sonnet-46"
        ),
        messages = [
            {"role": "system", "content": SCATTER_L1_SYSTEM},
            {"role": "user",   "content": user_prompt}
        ],
        temperature = 0.1,
    )

    raw     = response.choices[0].message.content.strip()
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts   = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    warnings = []
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return L1Packet(
            visual_id=l0.visual_id, title=l0.title,
            visual_type=l0.visual_type, page=l0.page,
            comparison=l0.comparison,
            active_filters=l0.active_filters,
            one_line_definition="", numerator_meaning="",
            denominator_meaning="", result_meaning="",
            scope_note="", direction="context_dependent",
            metric_type="count", measure_meanings={},
            is_table=False, column_definitions={},
            is_linechart=False, is_barchart=False,
            is_donut=False, is_scatter=True,
            warnings=[f"JSON parse error: {e}"],
            skip=True,
            skip_reason="scatter_l1_json_parse_failed"
        )

    position_rows = data.get("position_rows", [])

    packet = L1Packet(
        visual_id           = l0.visual_id,
        title               = l0.title,
        visual_type         = l0.visual_type,
        page                = l0.page,
        comparison          = l0.comparison,
        active_filters      = l0.active_filters,
        one_line_definition = data.get("one_line_definition", ""),
        numerator_meaning   = "",
        denominator_meaning = "",
        result_meaning      = json.dumps(position_rows),
        scope_note          = "",
        direction           = "context_dependent",
        metric_type         = "count",
        measure_meanings    = {},
        is_table            = False,
        column_definitions  = {},
        is_linechart        = False,
        is_barchart         = False,
        is_donut            = False,
        is_scatter          = True,
        warnings            = warnings,
        skip                = False,
        skip_reason         = ""
    )

    save_l1_packet(packet)
    return packet


# ============================================================
# MAIN — call_layer1
# ============================================================

def call_layer1(l0: L0Packet, llm_client) -> L1Packet:
    """
    Layer 1 entry point.

    Input  : L0Packet
    Output : L1Packet
    """
    # ── Skip propagation ────────────────────────────────────
    if l0.skip:
        packet = L1Packet(
            visual_id           = l0.visual_id,
            title               = l0.title,
            visual_type         = l0.visual_type,
            page                = l0.page,
            comparison          = l0.comparison,
            active_filters      = l0.active_filters,
            one_line_definition = "",
            numerator_meaning   = "",
            denominator_meaning = "",
            result_meaning      = "",
            scope_note          = "",
            direction           = "",
            metric_type         = "",
            measure_meanings    = {},
            skip                = True,
            skip_reason         = f"l0_skipped: {l0.skip_reason}"
        )
        save_l1_packet(packet)   # skip packets bhi save karo
        return packet
    # ── Table branch ─────────────────────────────────────
    if l0.is_table:
      return _call_layer1_table(l0, llm_client)
    # ── LineChart branch ──────────────────────────────────
    if l0.is_linechart:
        return _call_layer1_linechart(l0, llm_client)
    # ── BarChart branch ───────────────────────────────────
    if l0.is_barchart:
        return _call_layer1_barchart(l0, llm_client)
    # ── DonutChart branch ─────────────────────────────────
    if l0.is_donut:
        return _call_layer1_donut(l0, llm_client)
    # ── ScatterChart branch ───────────────────────────────
    if l0.is_scatter:
        return _call_layer1_scatter(l0, llm_client)
    # ── Build prompts from L0 fields ────────────────────────
    system_prompt, user_prompt = build_layer1_prompts(l0)

    # ── LLM call ────────────────────────────────────────────
    response = llm_client.chat.completions.create(
        model = os.environ.get(
            "TF_MODEL",
            "internal-bedrock/sonnet-46"
        ),
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        temperature = 0.1,   # Low — factual extraction only
    )

    raw = response.choices[0].message.content.strip()

    # ── Parse + validate ─────────────────────────────────────
    packet = _parse_l1_response(raw, l0)

    # ── Save to disk ─────────────────────────────────────────
    save_l1_packet(packet)

    return packet


# ============================================================
# SAVE  (L1Packet → disk)
# ============================================================

def save_l1_packet(
    packet     : L1Packet,
    output_dir : str = L1_OUTPUT_DIR
) -> str:
    """
    L1Packet ko JSON file mein save karo.

    Path:
      output/l1_packets/{visual_id}_{safe_title}.json
    """
    os.makedirs(output_dir, exist_ok=True)

    safe_title = (
        packet.title
        .replace(" ", "_")
        .replace("%", "pct")
        .replace("/", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(":", "")
        .strip("_")
    )

    filename = f"{packet.visual_id}_{safe_title}.json"
    filepath = os.path.join(output_dir, filename)

    # L1 JSON save disabled — uncomment to enable
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(l1_to_dict(packet), f, indent=2, ensure_ascii=False)

    status = "SKIP" if packet.skip else "OK"
    # print(f"  [L1-{status}] Saved: {filepath}")
    print(f"  [L1-{status}] {packet.title}")

    return filepath


# ============================================================
# SERIALISER  (L1Packet → plain dict)
# ============================================================

def l1_to_dict(packet: L1Packet) -> dict:
    return {
        "visual_id"          : packet.visual_id,
        "title"              : packet.title,
        "visual_type"        : packet.visual_type,
        "page"               : packet.page,
        "comparison"         : packet.comparison,
        "active_filters"     : packet.active_filters,
        "one_line_definition": packet.one_line_definition,
        "numerator_meaning"  : packet.numerator_meaning,
        "denominator_meaning": packet.denominator_meaning,
        "result_meaning"     : packet.result_meaning,
        "scope_note"         : packet.scope_note,
        "direction"          : packet.direction,
        "metric_type"        : packet.metric_type,
        "measure_meanings"   : packet.measure_meanings,
        "warnings"           : packet.warnings,
        "skip"               : packet.skip,
        "skip_reason"        : packet.skip_reason,
        "is_table"          : packet.is_table,
        "column_definitions": packet.column_definitions,
        "is_linechart"      : packet.is_linechart,
        "is_barchart"       : packet.is_barchart,
        "is_donut"          : packet.is_donut,
        "is_scatter"        : packet.is_scatter,
    }


# ============================================================
# DEBUG PRINTER
# ============================================================

def print_l1_packet(packet: L1Packet):
    print("\n" + "=" * 60)
    print(f"  L1 PACKET — {packet.title}")
    print("=" * 60)
    print(f"  visual_id   : {packet.visual_id}")
    print(f"  visual_type : {packet.visual_type}")
    print(f"  page        : {packet.page}")
    print(f"  comparison  : {packet.comparison}")
    print(f"  filters     : {packet.active_filters}")
    print(f"  skip        : {packet.skip}"
          + (f" ({packet.skip_reason})" if packet.skip else ""))

    if packet.warnings:
        print(f"\n  Warnings:")
        for w in packet.warnings:
            print(f"    ⚠  {w}")

    if packet.skip:
        print("=" * 60 + "\n")
        return

    print(f"\n  one_line_definition : {packet.one_line_definition}")
    print(f"  numerator_meaning   : {packet.numerator_meaning}")
    print(f"  denominator_meaning : {packet.denominator_meaning}")
    print(f"  result_meaning      : {packet.result_meaning}")
    print(f"  scope_note          : {packet.scope_note}")
    print(f"  direction           : {packet.direction}")
    print(f"  metric_type         : {packet.metric_type}")

    print(f"\n  measure_meanings ({len(packet.measure_meanings)}):")
    for name, meaning in packet.measure_meanings.items():
        print(f"    [{name}]")
        print(f"      → {meaning}")

    print("=" * 60 + "\n")


# ============================================================
# MAIN — run Layer 1 over all saved L0 packets
# ============================================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(_PROJECT_ROOT / ".env")

    # ── LLM client (TrueFoundry) ─────────────────────────────────
    llm_client = OpenAI(
        api_key  = os.environ["TF_API_KEY"],
        base_url = os.environ["TF_BASE_URL"],
    )

    # ── Load L0 packets from disk ────────────────────────────────
    l0_dir   = _PROJECT_ROOT / "output" / "l0_packets"
    l0_files = sorted(l0_dir.glob("*.json"))

    if not l0_files:
        print(f"No L0 packets found in: {l0_dir}")
        sys.exit(1)

    print("=" * 60)
    print(f"  Layer 1 — DAX Interpreter")
    print(f"  L0 packets found : {len(l0_files)}")
    print(f"  Output dir       : {L1_OUTPUT_DIR}")
    print("=" * 60)

    # ── Helpers to reconstruct L0Packet from saved JSON ──────────
    def _dax_from_dict(x: dict) -> DaxEntry:
        return DaxEntry(
            name    = x["name"],
            dax     = x["dax"],
            columns = [ColumnRef(table=c["table"], column=c["column"], raw=c["raw"])
                       for c in x.get("columns", [])],
            deps    = x.get("deps", []),
            role    = x.get("role", "other"),
        )

    def _l0_from_dict(d: dict) -> L0Packet:
        return L0Packet(
            visual_id       = d["visual_id"],
            title           = d["title"],
            visual_type     = d["visual_type"],
            page            = d["page"],
            primary_measure = d["primary_measure"],
            primary_dax     = _dax_from_dict(d["primary_dax"]) if d.get("primary_dax") else None,
            all_dax         = [_dax_from_dict(x) for x in d.get("all_dax", [])],
            paired_dax      = [_dax_from_dict(x) for x in d.get("paired_dax", [])],
            comparison      = d.get("comparison", "None"),
            active_filters  = d.get("active_filters", []),
            all_columns     = [ColumnRef(table=c["table"], column=c["column"], raw=c["raw"])
                               for c in d.get("all_columns", [])],
            page_visuals    = [PageVisual(id=p["id"], title=p["title"],
                                          type=p["type"], category=p["category"])
                               for p in d.get("page_visuals", [])],
            peer_cards      = [PeerCard(title=p["title"], measures=p["measures"])
                               for p in d.get("peer_cards", [])],
            glossary        = d.get("glossary", {}),
            warnings        = d.get("warnings", []),
            skip            = d.get("skip", False),
            skip_reason     = d.get("skip_reason", ""),
            is_table          = d.get("is_table", False),
            table_columns     = d.get("table_columns", []),
            row_dimension     = d.get("row_dimension", ""),
            row_dim_col_names = set(d.get("row_dim_col_names", [])),
            is_linechart      = d.get("is_linechart", False),
            chart_lines       = d.get("chart_lines", []),
            x_axis_col        = d.get("x_axis_col", ""),
            is_barchart       = d.get("is_barchart", False),
            bar_orientation   = d.get("bar_orientation", ""),
            category_axis     = d.get("category_axis", ""),
            tooltip_measures  = d.get("tooltip_measures", []),
            is_donut          = d.get("is_donut", False),
            legend_col        = d.get("legend_col", ""),
            is_scatter        = d.get("is_scatter", False),
            bubble_size       = d.get("bubble_size", ""),
            scatter_category  = d.get("scatter_category", ""),
        )

    def _l1_from_dict(d: dict) -> L1Packet:
        return L1Packet(
            visual_id           = d["visual_id"],
            title               = d["title"],
            visual_type         = d["visual_type"],
            page                = d["page"],
            comparison          = d.get("comparison", "None"),
            active_filters      = d.get("active_filters", []),
            one_line_definition = d.get("one_line_definition", ""),
            numerator_meaning   = d.get("numerator_meaning", ""),
            denominator_meaning = d.get("denominator_meaning", ""),
            result_meaning      = d.get("result_meaning", ""),
            scope_note          = d.get("scope_note", ""),
            direction           = d.get("direction", "context_dependent"),
            metric_type         = d.get("metric_type", "count"),
            measure_meanings    = d.get("measure_meanings", {}),
            warnings            = d.get("warnings", []),
            skip                = d.get("skip", False),
            skip_reason         = d.get("skip_reason", ""),
            is_table            = d.get("is_table", False),
            column_definitions  = d.get("column_definitions", {}),
            is_linechart        = d.get("is_linechart", False),
            is_barchart         = d.get("is_barchart", False),
            is_donut            = d.get("is_donut", False),
            is_scatter          = d.get("is_scatter", False),
        )

    # ── Process each visual ──────────────────────────────────────
    ok_count   = 0
    skip_count = 0
    err_count  = 0

    for fpath in l0_files:
        with open(fpath, encoding="utf-8") as f:
            raw = json.load(f)

        l0 = _l0_from_dict(raw)
        print(f"\n→ [{l0.visual_type}] {l0.title}  |  page: {l0.page}")

        try:
            l1 = call_layer1(l0, llm_client)
            print_l1_packet(l1)
            if l1.skip:
                skip_count += 1
            else:
                ok_count += 1
        except Exception as e:
            print(f"  [ERROR] {fpath.name}: {e}")
            err_count += 1

    print("\n" + "=" * 60)
    print(f"  Done — OK: {ok_count}  Skipped: {skip_count}  Errors: {err_count}")
    print(f"  L1 packets saved → {L1_OUTPUT_DIR}")
    print("=" * 60)