# funnel_connector_step4.py — Step 4: Funnel Connector

## Purpose
Single LLM call that reads `funnel_map.json` and generates `funnel_connector.json` containing:
1. **`funnel_table`** — "How the funnel connects" summary table (Layer | Section | Question it answers) — one row per widget
2. **`cross_page_patterns`** — 3–4 patterns requiring comparison across pages (entity in BOTTOM table + same entity in ACTION targeting list)
3. **`closing_paragraph`** — 2–3 sentences connecting all layers into one narrative arc

No widget content files are needed — `sub_question` per widget from `funnel_map.json` is sufficient input.

---

## Input / Output

| | Detail |
|---|---|
| **Input** | `output/dashboards/<dash>/page_wise/funnel_map.json` |
| **Output** | `output/dashboards/<dash>/page_wise/funnel_connector.json` |
| **Cache** | Checks `content_hash`. Override with `--force` |

---

## Function Flow

```
main()
  ├── load funnel_map.json
  ├── cache check (content_hash match → skip)
  └── run_funnel_connector(funnel_map)
        ├── build_prompt(funnel_map)
        │     ├── extracts non-mirrored widgets only
        │     ├── formats: [Layer] widget_name + sub_question
        │     └── includes funnel questions + domain_context
        └── for attempt in 1..3:
              call_llm(SYSTEM, prompt)
              parse_json_response()
              validate: funnel_table, closing_paragraph, cross_page_patterns all present
              return result on first success
              raise RuntimeError after 3 failures
```

---

## Function Details

### `run_funnel_connector(funnel_map) → dict`
3-attempt retry loop. Validates all 3 required keys are present and non-empty. Returns the parsed JSON result.

### `build_prompt(funnel_map) → str`
Builds the user prompt. Filters out mirrored widgets (they'd duplicate rows). Formats each widget as `[Layer] widget_name\n    sub_question: ...`. Includes the funnel question for each layer as context. Uses `POSITION_TO_LAYER` dict to convert `"TOP"` → `"Top"`.

### `call_llm(system, user) → str`
Wraps `llm_chat()` with `temperature=0.1`, `max_completion_tokens=6000`.

### `parse_json_response(raw) → dict`
Strips markdown fences if present. Returns parsed JSON.

---

## LLM Output Schema

```json
{
  "cross_page_patterns": [
    {
      "pattern": "situation involving data comparison across two pages",
      "interpretation": "what this combination means operationally"
    }
  ],
  "funnel_table": [
    {
      "layer": "Top / Mid / Bottom / Action",
      "section": "short section name",
      "question_it_answers": "one sentence"
    }
  ],
  "closing_paragraph": "2-3 sentences"
}
```

---

## File Connections

| Imports from | Used for |
|---|---|
| `utils/llm_client.py` | `llm_chat()` — LLM call with tenacity retry |

**Called by:** `runner.py` (Step 4, as subprocess)

**Input from:** `funnel_mapper_step1.py` → `funnel_map.json`

**Output consumed by:** `document_assembler_step5.py`, `glossary_faq/faq_generator.py`

---

## Hardcoded Parts (Change for New Dashboards)

### `POSITION_TO_LAYER` (line ~89)
```python
POSITION_TO_LAYER = {
    "TOP":    "Top",
    "MIDDLE": "Mid",
    "BOTTOM": "Bottom",
    "ACTION": "Action",
}
```
Maps internal position keys to display labels used in the funnel table. Change if the layer labels in the story guide template change.

### Cross-page patterns instruction in `build_prompt()` (line ~177)
```python
"cross_page_patterns: 3-4 patterns that require comparing an entity or metric across
 the overview/diagnostic page AND the action/targeting page together.
 Example: a provider appears both in the BOTTOM entity table AND in the ACTION targeting list..."
```
The example uses healthcare concepts (`"provider"`, `"targeted gaps"`, `"ACTION targeting list"`). For a different domain, update this instruction to reference the new domain's entities.

### `max_completion_tokens=6000` (line ~72)
Increase if dashboards with many widgets cause truncation. The funnel table has one row per widget, so more widgets = more tokens needed.
