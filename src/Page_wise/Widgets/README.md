# Widgets/ — Widget Processors

Each file processes one widget type. All follow the same pattern:
1. `SYSTEM` prompt constant
2. `build_*_prompt(widget, visuals, funnel_context)` → builds user prompt
3. `process_*(widget, visuals, funnel_context, client, model)` → LLM call + retry + return dict
4. Imported and called by `widget_group_writer_step3.py`

---

## Files and Widget Types

| File | Widget Type | When Used | `max_completion_tokens` |
|---|---|---|---|
| `trend_lines_processor.py` | `TREND_LINES` | All `lineChart` visuals on a page | 6000 |
| `detail_table_processor.py` | `DETAIL_TABLE` | Standalone pivot/detail tables | 6000 |
| `clinical_pair_processor.py` | `CLINICAL_PAIR` | Bar chart + detail table on disease/HCC dimension | 6000 |
| `entity_scatter_processor.py` | `ENTITY_SCATTER` | Entity table (provider/practice) + scatter plot | 6000 |
| `multi_chart_processor.py` | `MULTI_CHART` | Multiple bar/donut operational breakdown charts | 6000 |
| `action_table_processor.py` | `ACTION_TABLE` | ACTION page table (payer/LOB targeting summary) | 6000 |
| `segmentation_processor.py` | `SEGMENTATION` | ACTION page bar/donut charts segmenting members | 8000 |

> `segmentation_processor.py` uses `max_completion_tokens=8000` because segmentation widgets can have up to 9 visuals, each with a full segment_table.

---

## Common Pattern (all processors)

```python
SYSTEM_PROMPT = """..."""          # domain-specific instructions

def build_*_prompt(widget, visuals, funnel_context) -> str:
    # formats visual data into user prompt
    # embeds expected JSON schema inline
    # returns user prompt string

def process_*(widget, visuals, funnel_context, client, model) -> dict:
    prompt = build_*_prompt(...)
    for attempt in range(1, max_retries + 1):
        try:
            raw = llm_chat([system, user], temperature=0.1,
                           max_completion_tokens=N, client=client)
        except Exception as e:
            print(finish_reason + response tail on failure)
            continue
        try:
            result = parse json
        except:
            continue
        if validate(result): return result
    raise RuntimeError(f"... failed after {max_retries} attempts")
```

---

## Output Schema Per Type

### `TREND_LINES`
```json
{
  "widget_id", "widget_type": "TREND_LINES",
  "widget_name", "screenshot_label", "group_intro",
  "charts": [
    {
      "name": "chart title",
      "definition": "what this chart tracks",
      "patterns": [{"pattern": "...", "interpretation": "..."}],
      "italic_callout": "optional"
    }
  ]
}
```

### `DETAIL_TABLE`
```json
{
  "widget_id", "widget_type": "DETAIL_TABLE",
  "widget_name", "screenshot_label", "group_intro",
  "table_format": "COLUMN_FOCUSED" | "SEGMENT_FOCUSED",
  "column_table": [{"column": "...", "what_to_look_for": "..."}],
  "patterns": [{"pattern": "...", "interpretation": "..."}],
  "italic_callout": "optional"
}
```
SEGMENT_FOCUSED variant uses `segment_table` with `{segment, expected_behavior, red_flag}`.

### `CLINICAL_PAIR`
```json
{
  "widget_id", "widget_type": "CLINICAL_PAIR",
  "widget_name", "screenshot_label", "group_intro",
  "bar_chart": {
    "name", "definition",
    "patterns": [{"pattern", "interpretation"}]
  },
  "detail_table": {
    "name",
    "column_table": [{"column", "what_to_look_for"}]
  },
  "italic_callout": "optional"
}
```

### `ENTITY_SCATTER`
```json
{
  "widget_id", "widget_type": "ENTITY_SCATTER",
  "widget_name", "screenshot_label", "group_intro",
  "entity_table": {
    "definition",
    "column_table": [{"column", "what_to_look_for"}],
    "reading_patterns": [{"pattern", "interpretation"}]
  },
  "scatter_plot": {
    "name", "definition",
    "position_table": [{"position", "interpretation"}]
  }
}
```

### `MULTI_CHART`
```json
{
  "widget_id", "widget_type": "MULTI_CHART",
  "widget_name", "screenshot_label", "group_intro",
  "charts": [
    {
      "name", "visual_id", "definition",
      "segment_table": [{"segment", "interpretation"}]
    }
  ]
}
```

### `ACTION_TABLE`
```json
{
  "widget_id", "widget_type": "ACTION_TABLE",
  "widget_name", "screenshot_label", "group_intro",
  "bar_chart": {"name", "definition"},
  "column_table": [{"column", "what_to_look_for"}],
  "italic_callout": "optional"
}
```

### `SEGMENTATION`
```json
{
  "widget_id", "widget_type": "SEGMENTATION",
  "widget_name", "screenshot_label", "group_intro",
  "charts": [
    {
      "name", "visual_id", "definition",
      "segment_table": [{"segment", "interpretation", "outreach_action"}]
    }
  ]
}
```

---

## How to Add a New Widget Processor

1. Create `Widgets/my_widget_processor.py` following the common pattern above
2. Define a `SYSTEM` prompt and `build_my_widget_prompt()` and `process_my_widget()`
3. Import in `widget_group_writer_step3.py`
4. Add detection logic in `detect_widget_type()` in `widget_group_writer_step3.py`
5. Add dispatch case in `process_widget()` in `widget_group_writer_step3.py`
6. Add renderer `render_my_widget()` in `document_assembler_step5.py`
7. Register in `RENDERERS` dict in `document_assembler_step5.py`

---

## Hardcoded Parts Across All Processors

### System prompts — healthcare audience
All processors reference a **healthcare analyst** or **care manager** audience. For a new domain, update the audience and domain references in each `SYSTEM` constant.

### `segmentation_processor.py` — outreach_action field
```python
SEGMENTATION_SYSTEM = """...
  outreach_action: the specific recommended outreach action for this segment
    (e.g. "schedule AWV", "mail/phone outreach", "chart review", "telehealth")
"""
```
AWV (Annual Wellness Visit) and the outreach channel types are **healthcare-specific**. For a new domain, replace with domain-appropriate action types.

### `trend_lines_processor.py` — PY detection
```python
primary = next(
    (m for m in measures if "PY" not in m["name"] and "previous" not in ...),
    ...
)
```
`"PY"` (Previous Year) measure naming convention is risk-dash specific. For dashboards using different naming (e.g. `"_LY"`, `"_Prior"`), update this filter.

### `detail_table_processor.py` — SEGMENT_FOCUSED vs COLUMN_FOCUSED
The LLM is prompted to choose between two table formats. The SEGMENT_FOCUSED format with `"expected_behavior"` and `"red_flag"` columns is designed for risk model / attribution status tables. For new domains with different table semantics, update the prompt and the renderer accordingly.
