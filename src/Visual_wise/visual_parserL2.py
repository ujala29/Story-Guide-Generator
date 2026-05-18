



"""
Layer 2 — Context Builder
==========================
Input  : L0Packet + L1Packet
Output : L2Packet — saved to disk + passed to Layer 3

LLM ka kaam:
  L0 (page visuals, peer cards, filters) +
  L1 (direction, metric_type, definition) leke:
    1. Directional impact — 3 rows exactly
    2. Drill order        — 5-6 steps
    3. Cross-read patterns— per peer card

Temperature = 0.2 (structured reasoning)
"""

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from visual_parserL0 import L0Packet, PageVisual, PeerCard
from visaul_pareserL1 import L1Packet

# ============================================================
# CONFIG
# ============================================================

_HERE = Path(__file__).parent.resolve()

sys.path.insert(0, str(_HERE.parent))  # src/ — for paths.py
from paths import get_paths as _get_paths
from utils.llm_client import llm_chat

_DASHBOARD    = os.environ.get("STORY_DASHBOARD", "risk-dash")
L2_OUTPUT_DIR = str(_get_paths(_DASHBOARD).l2_packets_dir)

# ============================================================
# OUTPUT SCHEMA — L2Packet
# ============================================================

@dataclass
class DirectionalRow:
    """One row in the Directional impact table."""
    movement       : str   # "Rate increases versus prior period"
    signal         : str   # "Positive" | "Negative" | "Investigate"
    interpretation : str   # One line — what this means + which visual to check


@dataclass
class DrillStep:
    """One step in the drill-down sequence."""
    step        : int
    visual_name : str   # Exact name from page_visuals
    question    : str   # One-line diagnostic question


@dataclass
class CrossReadCombined:
    """
    Single combined multi-KPI key patterns table.
    One table — all important peers together.
    """
    # This KPI name
    primary_kpi : str

    # Selected peer KPIs (max 3 most business-relevant)
    partners    : list[str]

    # 6 meaningful combined state rows
    # Each row: {partner1: "High/Low", partner2: "High/Low", ..., "meaning": "..."}
    rows        : list[dict]


@dataclass
class L2Packet:
    """
    Layer 2 output — context + relationships.

    Fields consumed by Layer 3 (story writer).
    """
    # ── Pass-through from L0/L1 ───────────────────────────
    visual_id   : str
    title       : str
    visual_type : str
    page        : str
    comparison  : str
    active_filters : list[str]

    # ── Section 6 — Directional impact (3 rows) ───────────
    directional_rows : list[DirectionalRow]

    # ── Drill order (5-6 steps) ───────────────────────────
    drill_steps : list[DrillStep]

    # ── Section 10 — Combined multi-KPI key patterns ─────
    cross_read_combined : CrossReadCombined | None

    # ── Validation ────────────────────────────────────────
    warnings    : list[str] = field(default_factory=list)
    skip        : bool      = False
    skip_reason : str       = ""
    # ── Table-specific fields ─────────────────────────────
    is_table     : bool = False
    key_patterns : list = field(default_factory=list)
    # [
    #   {"pattern": "...", "meaning": "..."},
    #   {"pattern": "...", "meaning": "..."},
    #   {"pattern": "...", "meaning": "..."},
    #   {"pattern": "...", "meaning": "..."}
    # ]
    # ── Chart-specific flags ──────────────────────────────
    is_linechart : bool = False
    is_barchart  : bool = False
    is_donut     : bool = False
    is_scatter   : bool = False

# ============================================================
# PROMPTS
# ============================================================
TABLE_L2_SYSTEM = """
You are a dashboard analyst for a healthcare risk adjustment
Power BI matrix table.

Generate exactly 4 key patterns that analysts should watch
when reading this table.

Rules:
- Each pattern = a meaningful combined state across multiple
  columns in the same row (practice/PCP)
- Pattern column = combined business state description
  e.g. "High recapture rate with rising open coding gaps"
- What it means = one-line consequence + what action to take
- Return ONLY valid JSON. No markdown. No preamble.

Domain: healthcare risk adjustment dashboard.
Users: care managers, medical directors, payer analysts.

Key terms:
  RAF = Risk Adjustment Factor (composite HCC risk score)
  Recapture rate = % of gaps successfully closed
  PMPM = per-member-per-month cost
  Gap to potential risk = uncaptured risk opportunity
  YoY = year-over-year percentage change
"""

TABLE_L2_USER = """
Table title    : {title}
Row dimension  : {row_dimension}
Definition     : {definition}
Columns present: {columns_list}

Generate 4 actionable key patterns for this table.
Each pattern should describe a meaningful combined state
across multiple columns for the same practice/PCP row.

Return exactly:
{{
  "key_patterns": [
    {{"pattern": "...", "meaning": "..."}},
    {{"pattern": "...", "meaning": "..."}},
    {{"pattern": "...", "meaning": "..."}},
    {{"pattern": "...", "meaning": "..."}}
  ]
}}
"""


def _call_layer2_table(
    l0        : L0Packet,
    l1        : L1Packet,
    llm_client
) -> L2Packet:
    columns_list = ", ".join(l0.table_columns)

    user_prompt = TABLE_L2_USER.format(
        title         = l0.title,
        row_dimension = l0.row_dimension,
        definition    = l1.one_line_definition,
        columns_list  = columns_list
    )

    raw = llm_chat(
        [
            {"role": "system", "content": TABLE_L2_SYSTEM},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.2,
        client=llm_client,
    )
    if not raw:
        raise ValueError(f"LLM returned null content for table L2 visual {l0.visual_id}")
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
        return L2Packet(
            visual_id           = l0.visual_id,
            title               = l0.title,
            visual_type         = l0.visual_type,
            page                = l0.page,
            comparison          = l0.comparison,
            active_filters      = l0.active_filters,
            directional_rows    = [],
            drill_steps         = [],
            cross_read_combined = None,
            is_table            = True,
            key_patterns        = [],
            warnings            = [f"JSON parse error: {e}"],
            skip                = True,
            skip_reason         = "table_l2_json_parse_failed"
        )

    key_patterns = data.get("key_patterns", [])
    if len(key_patterns) != 4:
        warnings.append(
            f"key_patterns has {len(key_patterns)} rows — expected 4"
        )

    packet = L2Packet(
        visual_id           = l0.visual_id,
        title               = l0.title,
        visual_type         = l0.visual_type,
        page                = l0.page,
        comparison          = l0.comparison,
        active_filters      = l0.active_filters,
        directional_rows    = [],
        drill_steps         = [],
        cross_read_combined = None,
        is_table            = True,
        key_patterns        = key_patterns,
        warnings            = warnings,
        skip                = False,
        skip_reason         = ""
    )

    save_l2_packet(packet)
    return packet
LAYER2_SYSTEM = """
You are a dashboard context analyst for a healthcare
risk adjustment Power BI dashboard.

You receive a metric profile (from DAX interpretation)
and the full page context (all visuals on the page).

Your job is to produce three structured outputs:
  1. directional_rows  — exactly 3 rows
  2. drill_steps       — 5 to 6 steps
  3. cross_read_patterns — one block per peer card

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Return ONLY valid JSON — no markdown, no explanation
- Plain business language — no DAX, no column names
- Every field = one sentence maximum

DIRECTIONAL ROWS — exactly 3:
  Row 1: metric goes UP   -> what it signals
  Row 2: metric goes DOWN -> what it signals
  Row 3: unusual pattern  -> Investigate signal
         (e.g. rate rises while population falls,
          large YoY spike, divergence from related metric)
  signal must be one of: Positive, Negative, Investigate
  interpretation must end with: "Cross-check [visual name]"
  where [visual name] is taken from the page visuals list

DRILL STEPS — 5 to 6 steps:
  Each step = one specific visual from page_visuals
  Each step = one diagnostic question the analyst asks
  Steps must be in logical investigation order:
    broad -> specific -> action
  Last step must always end with:
    "Drill-down ends here. For member-level detail —
     go to Patient List on the Risk Capture Potential page."

CROSS-READ COMBINED TABLE — one single multi-KPI table:
  Select max 3 most business-relevant peers from the peer list.
  Generate exactly 6 meaningful combined state rows.

  Rules:
  - partners = list of selected peer KPI titles (max 3)
  - Each row has: this KPI state + each partner state + meaning
  - State values: "High" or "Low" only
  - meaning = one-line business consequence + what action to take
  - 6 rows total — pick the most actionable combinations
    (not exhaustive — only meaningful business scenarios)
  - Do NOT repeat similar scenarios
  - If peer_cards is empty — return cross_read_combined as null

  Example row structure:
  {
    "Potential risk": "High",
    "Documented risk": "Low",
    "Gap to potential risk": "High",
    "meaning": "Large uncaptured opportunity with poor documentation — urgent coding outreach needed."
  }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DASHBOARD DOMAIN KNOWLEDGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is a Risk Management Dashboard for healthcare
payer organizations. Key concepts:

- RAF (Risk Adjustment Factor): composite HCC risk score
- HCC: Hierarchical Condition Category — CMS condition grouping
- Gap: a condition that should be coded but has not been
- Documented risk: risk value for conditions already coded
- Potential risk: total risk including uncoded conditions
- Gap to potential risk: uncaptured risk opportunity
- Recapture rate: % of gaps successfully closed
- PMPM: per-member-per-month cost
- Attribution: assigning members to a payer/provider panel
- Dropped gap: condition coded last year, not yet this year
- Suspected gap: algorithmically predicted, not confirmed

Users are: care managers, medical directors, payer analysts.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

LAYER2_USER = """
Visual title   : {title}
Visual type    : {visual_type}
Primary measure: {primary_measure}
Direction      : {direction}
Metric type    : {metric_type}
Comparison     : {comparison}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
METRIC PROFILE (from Layer 1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Definition    : {one_line_definition}
Numerator     : {numerator_meaning}
Denominator   : {denominator_meaning}
Result        : {result_meaning}
Scope note    : {scope_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PAGE VISUALS — use these exact names in drill_steps
and interpretation cross-check references
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KPI cards  : {kpi_cards}
Tables     : {tables}
Charts     : {charts}
Trend lines: {trends}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PEER CARDS — available for cross-read selection
Pick max 3 most business-relevant from this list.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{peer_cards_block}

Return exactly this JSON — no other text:
{{
  "directional_rows": [
    {{
      "movement"      : "...",
      "signal"        : "Positive | Negative | Investigate",
      "interpretation": "... Cross-check [visual name]"
    }},
    {{
      "movement"      : "...",
      "signal"        : "Positive | Negative | Investigate",
      "interpretation": "... Cross-check [visual name]"
    }},
    {{
      "movement"      : "...",
      "signal"        : "Investigate",
      "interpretation": "... Cross-check [visual name]"
    }}
  ],
  "drill_steps": [
    {{
      "step"       : 1,
      "visual_name": "exact name from page visuals",
      "question"   : "one-line diagnostic question"
    }}
  ],
  "cross_read_combined": {{
    "primary_kpi": "{title}",
    "partners": ["peer1 title", "peer2 title", "peer3 title"],
    "rows": [
      {{
        "{title}": "High",
        "peer1 title": "Low",
        "peer2 title": "High",
        "meaning": "one-line business consequence and action"
      }},
      {{
        "{title}": "High",
        "peer1 title": "High",
        "peer2 title": "Low",
        "meaning": "one-line business consequence and action"
      }},
      {{
        "{title}": "High",
        "peer1 title": "High",
        "peer2 title": "High",
        "meaning": "one-line business consequence and action"
      }},
      {{
        "{title}": "Low",
        "peer1 title": "High",
        "peer2 title": "High",
        "meaning": "one-line business consequence and action"
      }},
      {{
        "{title}": "Low",
        "peer1 title": "Low",
        "peer2 title": "High",
        "meaning": "one-line business consequence and action"
      }},
      {{
        "{title}": "Low",
        "peer1 title": "Low",
        "peer2 title": "Low",
        "meaning": "one-line business consequence and action"
      }}
    ]
  }}
}}

Note: If peer_cards is "None" set cross_read_combined to null.
Replace peer1/peer2/peer3 with actual selected partner names.
Use exactly those partner names as keys in each row object.
"""


# ============================================================
# PROMPT BUILDER
# ============================================================

def _format_page_visuals(page_visuals: list[PageVisual]) -> dict:
    """
    Page visuals ko category wise group karo
    LLM ko clearly dikhane ke liye.
    """
    groups = {
        "kpi_card": [],
        "table"   : [],
        "chart"   : [],
        "trend"   : [],
        "other"   : []
    }
    for v in page_visuals:
        cat = v.category if v.category in groups else "other"
        groups[cat].append(v.title)

    return groups


def _format_peer_cards(peer_cards: list[PeerCard]) -> str:
    """
    Peer cards ko readable block mein.
    """
    if not peer_cards:
        return "None — skip cross_read_patterns"

    lines = []
    for p in peer_cards:
        lines.append(f"- {p.title}")
    return "\n".join(lines)


def build_layer2_prompts(
    l0: L0Packet,
    l1: L1Packet
) -> tuple[str, str]:
    """
    L0 + L1 se system + user prompt banao.
    """
    groups = _format_page_visuals(l0.page_visuals)

    peer_block = _format_peer_cards(l0.peer_cards)

    user_prompt = LAYER2_USER.format(
        title              = l1.title,
        visual_type        = l1.visual_type,
        primary_measure    = l0.primary_measure,
        direction          = l1.direction,
        metric_type        = l1.metric_type,
        comparison         = l1.comparison,
        one_line_definition= l1.one_line_definition,
        numerator_meaning  = l1.numerator_meaning,
        denominator_meaning= l1.denominator_meaning,
        result_meaning     = l1.result_meaning,
        scope_note         = l1.scope_note or "None",
        kpi_cards          = ", ".join(groups["kpi_card"]) or "None",
        tables             = ", ".join(groups["table"])    or "None",
        charts             = ", ".join(groups["chart"])    or "None",
        trends             = ", ".join(groups["trend"])    or "None",
        peer_cards_block   = peer_block
    )

    return LAYER2_SYSTEM, user_prompt


# ============================================================
# RESPONSE PARSER + VALIDATOR
# ============================================================

VALID_SIGNALS = {"Positive", "Negative", "Investigate"}


def _parse_l2_response(raw: str, l0: L0Packet, l1: L1Packet) -> L2Packet:
    """
    LLM response parse + validate karo.
    """
    warnings = []

    if not raw:
        raise ValueError(f"LLM returned null content for L2 visual {l0.visual_id}")

    # ── Strip markdown fences ────────────────────────────────
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        parts   = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()

    # ── JSON parse ───────────────────────────────────────────
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return L2Packet(
            visual_id           = l0.visual_id,
            title               = l1.title,
            visual_type         = l1.visual_type,
            page                = l0.page,
            comparison          = l1.comparison,
            active_filters      = l1.active_filters,
            directional_rows    = [],
            drill_steps         = [],
            cross_read_combined = None,
            warnings            = [
                f"JSON parse error: {e}",
                f"Raw (first 300): {raw[:300]}"
            ],
            skip        = True,
            skip_reason = "layer2_json_parse_failed"
        )

    # ── Validate directional_rows ────────────────────────────
    directional_rows = []
    raw_rows = data.get("directional_rows", [])

    if len(raw_rows) != 3:
        warnings.append(
            f"directional_rows has {len(raw_rows)} rows — expected 3"
        )

    for row in raw_rows:
        signal = row.get("signal", "")
        if signal not in VALID_SIGNALS:
            warnings.append(f"Invalid signal '{signal}' — must be Positive/Negative/Investigate")
            signal = "Investigate"
        directional_rows.append(DirectionalRow(
            movement       = row.get("movement", ""),
            signal         = signal,
            interpretation = row.get("interpretation", "")
        ))

    # ── Validate drill_steps ─────────────────────────────────
    drill_steps = []
    raw_steps = data.get("drill_steps", [])

    if not (5 <= len(raw_steps) <= 6):
        warnings.append(
            f"drill_steps has {len(raw_steps)} steps — expected 5-6"
        )

    for step in raw_steps:
        drill_steps.append(DrillStep(
            step        = step.get("step", 0),
            visual_name = step.get("visual_name", ""),
            question    = step.get("question", "")
        ))

    # ── Parse cross_read_combined ────────────────────────────
    cross_read_combined = None
    raw_combined = data.get("cross_read_combined")

    if raw_combined and isinstance(raw_combined, dict):
        partners = raw_combined.get("partners", [])
        rows     = raw_combined.get("rows", [])

        # Validate — 6 rows expected
        if len(rows) != 6:
            warnings.append(
                f"cross_read_combined has {len(rows)} rows — expected 6"
            )

        # Validate — max 3 partners
        if len(partners) > 3:
            warnings.append(
                f"cross_read_combined has {len(partners)} partners — max 3"
            )
            partners = partners[:3]

        # Validate — each row has meaning key
        for i, row in enumerate(rows):
            if "meaning" not in row:
                warnings.append(f"Row {i+1} missing 'meaning' key")

        cross_read_combined = CrossReadCombined(
            primary_kpi = raw_combined.get("primary_kpi", l1.title),
            partners    = partners,
            rows        = rows
        )
    elif l0.peer_cards:
        # LLM returned null but peer cards exist — warn
        warnings.append(
            "cross_read_combined is null but peer_cards exist"
        )

    return L2Packet(
        visual_id           = l0.visual_id,
        title               = l1.title,
        visual_type         = l1.visual_type,
        page                = l0.page,
        comparison          = l1.comparison,
        active_filters      = l1.active_filters,
        directional_rows    = directional_rows,
        drill_steps         = drill_steps,
        cross_read_combined = cross_read_combined,
        warnings            = warnings,
        skip                = False,
        skip_reason         = ""
    )


def _build_linechart_l2_packet(
    l0: L0Packet,
    l1: L1Packet
) -> L2Packet:
    packet = L2Packet(
        visual_id           = l0.visual_id,
        title               = l0.title,
        visual_type         = l0.visual_type,
        page                = l0.page,
        comparison          = l0.comparison,
        active_filters      = l0.active_filters,
        directional_rows    = [],
        drill_steps         = [],
        cross_read_combined = None,
        is_table            = False,
        key_patterns        = [],
        is_linechart        = True,
        is_barchart         = False,
        warnings            = [],
        skip                = False,
        skip_reason         = ""
    )
    save_l2_packet(packet)
    return packet


def _build_barchart_l2_packet(
    l0: L0Packet,
    l1: L1Packet
) -> L2Packet:
    packet = L2Packet(
        visual_id           = l0.visual_id,
        title               = l0.title,
        visual_type         = l0.visual_type,
        page                = l0.page,
        comparison          = l0.comparison,
        active_filters      = l0.active_filters,
        directional_rows    = [],
        drill_steps         = [],
        cross_read_combined = None,
        is_table            = False,
        key_patterns        = [],
        is_linechart        = False,
        is_barchart         = True,
        warnings            = [],
        skip                = False,
        skip_reason         = ""
    )
    save_l2_packet(packet)
    return packet


def _build_donut_l2_packet(l0, l1) -> L2Packet:
    packet = L2Packet(
        visual_id=l0.visual_id, title=l0.title,
        visual_type=l0.visual_type, page=l0.page,
        comparison=l0.comparison,
        active_filters=l0.active_filters,
        directional_rows=[], drill_steps=[],
        cross_read_combined=None,
        is_table=False, key_patterns=[],
        is_linechart=False, is_barchart=False,
        is_donut=True,
        warnings=[], skip=False, skip_reason=""
    )
    save_l2_packet(packet)
    return packet


def _build_scatter_l2_packet(l0, l1) -> L2Packet:
    packet = L2Packet(
        visual_id=l0.visual_id, title=l0.title,
        visual_type=l0.visual_type, page=l0.page,
        comparison=l0.comparison,
        active_filters=l0.active_filters,
        directional_rows=[], drill_steps=[],
        cross_read_combined=None,
        is_table=False, key_patterns=[],
        is_linechart=False, is_barchart=False,
        is_donut=False, is_scatter=True,
        warnings=[], skip=False, skip_reason=""
    )
    save_l2_packet(packet)
    return packet


# ============================================================
# MAIN — call_layer2
# ============================================================
def call_layer2(
    l0        : L0Packet,
    l1        : L1Packet,
    llm_client
) -> L2Packet:
    # ── Skip propagation ────────────────────────────────────
    if l0.skip or l1.skip:
        reason = l0.skip_reason if l0.skip else l1.skip_reason
        packet = L2Packet(
            visual_id           = l0.visual_id,
            title               = l0.title,
            visual_type         = l0.visual_type,
            page                = l0.page,
            comparison          = l1.comparison,
            active_filters      = l1.active_filters,
            directional_rows    = [],
            drill_steps         = [],
            cross_read_combined = None,
            is_table            = l0.is_table,
            key_patterns        = [],
            is_linechart        = l0.is_linechart,
            is_barchart         = l0.is_barchart,
            is_donut            = l0.is_donut,
            is_scatter          = l0.is_scatter,
            skip                = True,
            skip_reason         = f"upstream_skipped: {reason}"
        )
        save_l2_packet(packet)
        return packet

    # ── Table branch ─────────────────────────────────────────
    if l0.is_table:
        return _call_layer2_table(l0, l1, llm_client)

    # ── LineChart branch — no LLM ────────────────────────────
    if l0.is_linechart:
        return _build_linechart_l2_packet(l0, l1)

    # ── BarChart branch — no LLM ─────────────────────────────
    if l0.is_barchart:
        return _build_barchart_l2_packet(l0, l1)

    # ── DonutChart branch — no LLM ───────────────────────────
    if l0.is_donut:
        return _build_donut_l2_packet(l0, l1)

    # ── ScatterChart branch — no LLM ─────────────────────────
    if l0.is_scatter:
        return _build_scatter_l2_packet(l0, l1)

    # ── Build prompts (card path) ────────────────────────────
    system_prompt, user_prompt = build_layer2_prompts(l0, l1)

    # ── LLM call ────────────────────────────────────────────
    raw = llm_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.2,
        client=llm_client,
    )

    # ── Parse + validate ─────────────────────────────────────
    packet = _parse_l2_response(raw, l0, l1)

    # ── Save to disk ─────────────────────────────────────────
    save_l2_packet(packet)

    return packet

# ============================================================
# SAVE  (L2Packet -> disk)
# ============================================================

def save_l2_packet(
    packet     : L2Packet,
    output_dir : str = L2_OUTPUT_DIR
) -> str:
    """
    L2Packet ko JSON file mein save karo.
    Path: output/l2_packets/{visual_id}_{safe_title}.json
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

    # L2 JSON save disabled — uncomment to enable
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(l2_to_dict(packet), f, indent=2, ensure_ascii=False)

    status = "SKIP" if packet.skip else "OK"
    # print(f"  [L2-{status}] Saved: {filepath}")
    print(f"  [L2-{status}] {packet.title}")

    return filepath


# ============================================================
# SERIALISER
# ============================================================

def l2_to_dict(packet: L2Packet) -> dict:
    return {
        "visual_id"  : packet.visual_id,
        "title"      : packet.title,
        "visual_type": packet.visual_type,
        "page"       : packet.page,
        "comparison" : packet.comparison,
        "active_filters": packet.active_filters,
        "directional_rows": [
            {
                "movement"      : r.movement,
                "signal"        : r.signal,
                "interpretation": r.interpretation
            }
            for r in packet.directional_rows
        ],
        "drill_steps": [
            {
                "step"       : s.step,
                "visual_name": s.visual_name,
                "question"   : s.question
            }
            for s in packet.drill_steps
        ],
        "cross_read_combined": (
            {
                "primary_kpi": packet.cross_read_combined.primary_kpi,
                "partners"   : packet.cross_read_combined.partners,
                "rows"       : packet.cross_read_combined.rows
            }
            if packet.cross_read_combined else None
        ),
        "warnings"   : packet.warnings,
        "skip"       : packet.skip,
        "skip_reason": packet.skip_reason,
        "is_table"    : packet.is_table,
        "key_patterns": packet.key_patterns,
        "is_linechart": packet.is_linechart,
        "is_barchart" : packet.is_barchart,
        "is_donut"    : packet.is_donut,
        "is_scatter"  : packet.is_scatter,
    }


# ============================================================
# DEBUG PRINTER
# ============================================================

def print_l2_packet(packet: L2Packet):
    print("\n" + "=" * 60)
    print(f"  L2 PACKET — {packet.title}")
    print("=" * 60)
    print(f"  visual_id  : {packet.visual_id}")
    print(f"  page       : {packet.page}")
    print(f"  comparison : {packet.comparison}")
    print(f"  skip       : {packet.skip}"
          + (f" ({packet.skip_reason})" if packet.skip else ""))

    if packet.warnings:
        print(f"\n  Warnings:")
        for w in packet.warnings:
            print(f"    ⚠  {w}")

    if packet.skip:
        print("=" * 60 + "\n")
        return

    print(f"\n  Directional rows ({len(packet.directional_rows)}):")
    for r in packet.directional_rows:
        print(f"    [{r.signal}] {r.movement}")
        print(f"      -> {r.interpretation}")

    print(f"\n  Drill steps ({len(packet.drill_steps)}):")
    for s in packet.drill_steps:
        print(f"    {s.step}. {s.visual_name}")
        print(f"       -> {s.question}")

    if packet.cross_read_combined:
        cr = packet.cross_read_combined
        print(f"\n  Cross-read combined:")
        print(f"    Primary KPI : {cr.primary_kpi}")
        print(f"    Partners    : {cr.partners}")
        print(f"    Rows ({len(cr.rows)}):")
        for row in cr.rows:
            states = {k: v for k, v in row.items() if k != "meaning"}
            print(f"      {states}")
            print(f"        -> {row.get('meaning','')}")
    else:
        print(f"\n  Cross-read combined: None")

    print("=" * 60 + "\n")


# ============================================================
# DESERIALISER  (plain dict -> L2Packet)
# ============================================================

def _l2_from_dict(d: dict) -> "L2Packet":
    cr_raw = d.get("cross_read_combined")
    cross_read_combined = (
        CrossReadCombined(
            primary_kpi = cr_raw["primary_kpi"],
            partners    = cr_raw["partners"],
            rows        = cr_raw["rows"],
        )
        if cr_raw else None
    )
    return L2Packet(
        visual_id           = d["visual_id"],
        title               = d["title"],
        visual_type         = d["visual_type"],
        page                = d["page"],
        comparison          = d.get("comparison", "None"),
        active_filters      = d.get("active_filters", []),
        directional_rows    = [
            DirectionalRow(**r) for r in d.get("directional_rows", [])
        ],
        drill_steps         = [
            DrillStep(**s) for s in d.get("drill_steps", [])
        ],
        cross_read_combined = cross_read_combined,
        warnings            = d.get("warnings", []),
        skip                = d.get("skip", False),
        skip_reason         = d.get("skip_reason", ""),
        is_table            = d.get("is_table", False),
        key_patterns        = d.get("key_patterns", []),
        is_linechart        = d.get("is_linechart", False),
        is_barchart         = d.get("is_barchart", False),
        is_donut            = d.get("is_donut", False),
        is_scatter          = d.get("is_scatter", False),
    )