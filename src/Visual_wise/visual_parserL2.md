# visual_parserL2.py — L2 Context Builder (LLM)

## Purpose
LLM layer that uses the metric profile from L1 + page context from L0 to produce three structured outputs: directional impact table (exactly 3 rows), drill-down sequence (5–6 steps), and combined cross-read key patterns table (multi-KPI, max 3 peers, 6 rows). Tables are handled separately via `_call_layer2_table()`. Temperature = 0.2 (structured reasoning).

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `L0Packet` + `L1Packet` |
| **System prompt** | `LAYER2_SYSTEM` (inline, for cards/charts) or `TABLE_L2_SYSTEM` (inline, for tables) |
| **User prompt** | Built from L0 + L1 fields |
| **Output** | `L2Packet` dataclass |
| **Side effect** | `save_l2_packet()` writes `l2_packets/<page>/<id>.json` |

---

## Pipeline Steps

```
Step 1  branch: is_table? → _call_layer2_table()
                else      → _call_layer2_card_or_chart()
Step 2  build prompt (table or card/chart path)
Step 3  llm_chat([system, user], temperature=0.2)
Step 4  strip markdown fences + json.loads()
Step 5  validate row counts
Step 6  build L2Packet + save
```

---

## Function Flow

```
call_layer2(l0, l1, llm_client) → L2Packet
  ├── if l0.is_table:
  │     └── _call_layer2_table(l0, l1, llm_client)
  │           ├── TABLE_L2_USER.format(title, row_dimension, definition, columns_list)
  │           ├── llm_chat(TABLE_L2_SYSTEM, user, temperature=0.2)
  │           ├── json.loads → {key_patterns: [{pattern, meaning}, ...]}
  │           └── validate: exactly 4 key_patterns
  │
  └── else: _call_layer2_card_or_chart(l0, l1, llm_client)
        ├── _format_page_visuals(l0.page_visuals)
        │     └── group by category: kpi_card / table / chart / trend / other
        ├── _format_peer_cards(l0.peer_cards)
        │     └── "- Title: measures = [...]" per peer
        ├── LAYER2_USER.format(all L1 + L0 fields)
        ├── llm_chat(LAYER2_SYSTEM, user, temperature=0.2)
        ├── json.loads → {directional_rows, drill_steps, cross_read_combined}
        ├── validate:
        │     ├── directional_rows == 3
        │     ├── drill_steps in [5, 6]
        │     └── cross_read_combined.rows == 6 (if not null)
        └── build L2Packet(directional_rows, drill_steps, cross_read_combined)
```

---

## Output Schema — `L2Packet`

```python
# Pass-through
visual_id       : str
title           : str
visual_type     : str
page            : str
comparison      : str
active_filters  : list[str]

# Card/chart path (LLM fills these)
directional_rows    : list[DirectionalRow]  # exactly 3 rows
    # DirectionalRow: movement (str), signal ("Positive"|"Negative"|"Investigate"),
    #                 interpretation (str — ends with "Cross-check [visual name]")
drill_steps         : list[DrillStep]       # 5-6 steps
    # DrillStep: step (int), visual_name (str), question (str)
cross_read_combined : CrossReadCombined | None
    # CrossReadCombined: primary_kpi, partners (max 3), rows (6 combined state rows)

# Table path (LLM fills this instead)
is_table     : bool
key_patterns : list  # [{pattern, meaning}, ...] — exactly 4

# Chart type flags (pass-through from L0)
is_linechart / is_barchart / is_donut / is_scatter : bool

# Validation
warnings    : list[str]
skip        : bool
skip_reason : str
```

---

## LLM Prompt Structure

### Card/chart path — `LAYER2_SYSTEM` + `LAYER2_USER`
**System:** Instructs 3 outputs (directional_rows, drill_steps, cross_read_combined). Rules:
- `directional_rows`: row 1=up signal, row 2=down signal, row 3=unusual/"Investigate". Each interpretation must end with "Cross-check [visual name]".
- `drill_steps`: 5–6 steps, logical order broad→specific→action. Last step must end with "Drill-down ends here. For member-level detail — go to Patient List..."
- `cross_read_combined`: one table, max 3 partners, 6 rows, "High"/"Low" states only.

**User:** Sends visual title/type, full L1 metric profile (definition, numerator, denominator, direction), page visuals grouped by category, and peer cards list.

### Table path — `TABLE_L2_SYSTEM` + `TABLE_L2_USER`
Generates exactly 4 `key_patterns` — meaningful combined states across multiple table columns for the same practice/PCP row.

---

## File Connections

| Imports from | Used for |
|---|---|
| `visual_parserL0` | `L0Packet`, `PageVisual`, `PeerCard` |
| `visaul_pareserL1` | `L1Packet` |
| `utils/llm_client.py` | `llm_chat()` with tenacity retry |
| `utils/paths.py` | `get_paths(dashboard)` — l2_packets output dir |

**Called by:** `visaul_pipeline_runner.py` Phase 3 — starts only after ALL L1s are complete (cross-visual reasoning requires full L1 picture)

---

## Hardcoded Parts (Change for New Dashboards)

### `LAYER2_SYSTEM` domain knowledge block (line ~312)
Explains RAF, HCC, gaps, recapture rate, PMPM in the system prompt. For non-healthcare dashboards, rewrite this section.

### Drill step last-step rule (line ~286)
```
Last step must always end with:
  "Drill-down ends here. For member-level detail —
   go to Patient List on the Risk Capture Potential page."
```
Hardcoded to "Risk Capture Potential page" — a risk-dash-specific page name. Update this instruction for new dashboards pointing to their equivalent patient-level drill page.

### `TABLE_L2_SYSTEM` domain terms (line ~127)
Lists key terms (RAF, recapture rate, PMPM, gap, YoY) used in table key pattern generation. Update for new dashboard domain vocabulary.

### Cross-read row count = 6 (validation, line ~varies)
Expected `cross_read_combined.rows == 6`. If prompt output differs, the warning fires but processing continues. Do not change this validation without updating the system prompt rule.
