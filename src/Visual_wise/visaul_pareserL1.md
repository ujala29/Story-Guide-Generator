# visaul_pareserL1.py — L1 DAX Interpreter (LLM)

## Purpose
LLM layer that reads the primary measure's DAX formula + all companion measures + glossary and extracts structured business meaning. Produces `L1Packet` — the metric profile consumed by L2 (for directional/drill reasoning) and L3 (for definition and metric rows in the final markdown). Temperature = 0.1 (factual extraction, minimal creativity).

**NOTE: filename has a typo (`visaul_pareserL1`) — do not rename.**

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `L0Packet` — structured visual data from L0 |
| **System prompt** | `LAYER1_SYSTEM` (inline, hardcoded in this file) |
| **User prompt** | Built from `L0Packet` fields via `build_layer1_prompts()` |
| **Output** | `L1Packet` dataclass — metric profile |
| **Side effect** | `save_l1_packet()` writes `l1_packets/<page>/<id>.json` |

---

## Pipeline Steps

```
Step 1  detect_dax_pattern(primary_dax)  → pattern string
Step 2  build_layer1_prompts(l0)         → (system_prompt, user_prompt)
Step 3  llm_chat([system, user], temperature=0.1)  → raw JSON string
Step 4  parse + validate JSON response
Step 5  build L1Packet from parsed fields
Step 6  save_l1_packet(packet)
```

---

## Function Flow

```
call_layer1(l0, llm_client) → L1Packet
  ├── build_layer1_prompts(l0)
  │     ├── _format_measures_block(l0.all_dax, l0.paired_dax)
  │     │     └── deduplicate + format: Measure/Role/DAX/Columns/Deps per entry
  │     ├── _format_glossary_block(l0.glossary)
  │     │     └── flatten nested sections → "term : meaning" lines
  │     ├── detect_dax_pattern(l0.primary_dax.dax)
  │     │     ├── Pattern 6 → "color_measure"   (SWITCH + < 0, no unichar)
  │     │     ├── Pattern 4 → "yoy_card"         (SAMEPERIODLASTYEAR + unichar)
  │     │     ├── Pattern 5 → "mom_card"         (PREVIOUSMONTH + unichar)
  │     │     ├── Pattern 3 → "flag_set_ratio"   (2× KEEPFILTERS + IN {set})
  │     │     ├── Pattern 2 → "mixed_ratio"      (var a unfiltered / var b filtered)
  │     │     ├── Pattern 1 → "filtered_ratio"   (CALCULATE + DIVIDE + KEEPFILTERS)
  │     │     ├── "simple_sum"                   (SUM/COUNT/DISTINCTCOUNT/CALCULATE-no-divide)
  │     │     └── "unknown"
  │     └── format LAYER1_USER with all fields
  ├── llm_chat([system, user], temperature=0.1, client=llm_client)
  ├── strip markdown fences (``` json ... ```)
  ├── json.loads(cleaned)
  ├── validate required fields + enum values
  └── return L1Packet(...)  or skip packet on parse failure
```

---

## Output Schema — `L1Packet`

```python
# Pass-through identity
visual_id           : str
title               : str
visual_type         : str
page                : str
comparison          : str
active_filters      : list[str]

# Core metric profile (LLM fills these)
one_line_definition  : str   # plain English, one sentence
numerator_meaning    : str   # what numerator represents
denominator_meaning  : str   # what denominator represents (empty if not ratio)
result_meaning       : str   # what the final number tells the analyst
scope_note           : str   # which flag values are in/out of scope (empty if none)
direction            : str   # "higher_is_better" | "lower_is_better" | "context_dependent"
metric_type          : str   # "rate" | "count" | "average" | "gap" | "ratio"
measure_meanings     : dict  # {measure_name: one-sentence description}

# Type-specific flags (pass-through from L0)
is_table             : bool
column_definitions   : dict  # {col_name: {definition, increasing, decreasing}}
is_linechart         : bool
is_barchart          : bool
is_donut             : bool
is_scatter           : bool

# Validation
warnings    : list[str]
skip        : bool
skip_reason : str
```

---

## DAX Patterns Detected

| Pattern | Trigger | Name |
|---|---|---|
| 1 | `CALCULATE + DIVIDE + KEEPFILTERS` (single filter) | `filtered_ratio` |
| 2 | `var a = SUM` (unfiltered) + `var b = CALCULATE(KEEPFILTERS)` | `mixed_ratio` |
| 3 | 2× `KEEPFILTERS` + `IN {set}` | `flag_set_ratio` |
| 4 | `SAMEPERIODLASTYEAR + unichar` | `yoy_card` |
| 5 | `PREVIOUSMONTH + unichar` | `mom_card` |
| 6 | `SWITCH(TRUE()) + < 0 or > 0` (no unichar) | `color_measure` |
| — | `SUM(` / `DISTINCTCOUNT(` starts the DAX | `simple_sum` |
| — | none of the above | `unknown` |

---

## LLM Prompt Structure

**System prompt (`LAYER1_SYSTEM`):** Inline in this file. Instructs the LLM to act as a DAX formula interpreter, return only JSON, and describes all 6 DAX patterns with examples.

**User prompt (`LAYER1_USER`):** Built per visual. Contains:
- Visual title, type, primary measure, detected DAX pattern
- `ALL MEASURES ON THIS VISUAL` block (Measure/Role/DAX/Columns/Deps)
- `GLOSSARY` block
- Critical interpretation rules (pattern-specific scope note requirements)
- Required JSON output structure

---

## File Connections

| Imports from | Used for |
|---|---|
| `visual_parserL0` | `L0Packet`, `DaxEntry`, `ColumnRef`, `PageVisual`, `PeerCard` |
| `utils/llm_client.py` | `llm_chat()` with tenacity retry |
| `utils/paths.py` | `get_paths(dashboard)` — l1_packets output dir |

**Called by:** `visaul_pipeline_runner.py` Phase 2 (parallel, `MAX_WORKERS=3`)

---

## Hardcoded Parts (Change for New Dashboards)

### `LAYER1_SYSTEM` — inline system prompt (line ~130)
Describes 6 DAX patterns with healthcare risk adjustment examples. If a new dashboard uses different DAX patterns or different flag value names (e.g. `"Documented"` → `"Confirmed"`), update the pattern examples and glossary section.

### `detect_dax_pattern()` — pattern detection logic (line ~311)
Keyword-based pattern detection. If new DAX patterns are introduced in a new dashboard, add detection rules here and document them in `LAYER1_SYSTEM` under a new PATTERN number.

### `VALID_DIRECTIONS` / `VALID_METRIC_TYPES` — validation sets (line ~461)
```python
VALID_DIRECTIONS   = {"higher_is_better", "lower_is_better", "context_dependent"}
VALID_METRIC_TYPES = {"rate", "count", "average", "gap", "ratio"}
```
Add new allowed values if a new domain introduces metric types not covered here.

### Domain description in `LAYER1_SYSTEM`
Hardcoded to healthcare risk adjustment (RAF, HCC, gaps, etc.). For a non-healthcare dashboard, rewrite the system prompt domain context.
