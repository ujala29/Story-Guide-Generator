# glossary_faq — Stage 4 README

Stage 4 (parallel with `dashboard_overview`) generates two reference sections for the Story Guide: a **Glossary of Terms** and a **FAQ**. Both read outputs from earlier stages and use an LLM to produce final markdown documents.

---

## File Overview

| File | Role |
|---|---|
| [runner.py](runner.md) | CLI entry point — runs both generators sequentially |
| [glossary_generator.py](glossary_generator.md) | Collects metric definitions → LLM → `glossary.md` |
| [faq_generator.py](faq_generator.md) | Collects watch-outs + filters + patterns → LLM → `faq.md` |

---

## How Files Are Connected

```
runner.py
  ├── subprocess → glossary_generator.py  (independent)
  └── subprocess → faq_generator.py       (independent)

Both generators:
  ├── utils/llm_client.py       (llm_chat with retry)
  ├── prompt/system_prompt/     (system prompts + base_context)
  └── prompt/dashboard_config.json (users + domain per dashboard)
```

---

## Full Pipeline Call Flow

```
runner.py
  │
  ├── glossary_generator.py
  │     │
  │     ├── collect_terms(dashboard, root)
  │     │     ├── page_wise/widget_content/*.json   → widget_terms{}
  │     │     ├── metric_dictionary/metric_catalog.json  → catalog_terms{}
  │     │     ├── metric_dictionary/final_measures_with_llm.json → llm_measures{}
  │     │     └── page_wise/funnel_map.json          → domain_context
  │     │
  │     ├── load_glossary_prompt(dashboard)
  │     │     ├── prompt/system_prompt/glossary.txt  (if exists)
  │     │     ├── prompt/system_prompt/base_context.txt
  │     │     └── prompt/dashboard_config.json
  │     │
  │     ├── build_glossary_prompt(data, system_prompt)
  │     │     └── _format_metric_list() × 3 sources
  │     │
  │     ├── llm_chat([system, user], temperature=0.2)
  │     │
  │     └── save_glossary() → glossary_faq/glossary.md
  │
  └── faq_generator.py
        │
        ├── collect_faq_signals(dashboard, root)
        │     ├── page_wise/widget_content/*.json    → callouts[] (italic_callout)
        │     ├── page_wise/funnel_connector.json    → cross_page_patterns[]
        │     ├── extraction/schema_sections/filters.json → filter_summaries[]
        │     └── page_wise/funnel_map.json          → sub_questions[], domain_context
        │
        ├── load_faq_prompt(dashboard)
        │     ├── prompt/system_prompt/faq.txt  (if exists)
        │     ├── prompt/system_prompt/base_context.txt
        │     └── prompt/dashboard_config.json
        │
        ├── build_faq_prompt(data, system_prompt)
        │     ├── _format_callouts()
        │     ├── _format_cross_page()
        │     ├── _format_filters()
        │     └── _format_sub_questions()
        │
        ├── llm_chat([system, user], temperature=0.3)
        │
        └── save_faq() → glossary_faq/faq.md
```

---

## Data Flow

```
Stage 1 outputs (extraction/)
  └── schema_sections/filters.json ──────────────────────────────► faq_generator.py
                                                                         │
Stage 2 outputs (metric_dictionary/)                                     │
  └── metric_catalog.json ──────────────────────────────────────► glossary_generator.py
  └── final_measures_with_llm.json ───────────────────────────── glossary_generator.py
                                                                         │
Stage 3 outputs (page_wise/)                                             │
  ├── widget_content/*.json ─────────────────────────────────┬─► glossary_generator.py
  │                                                           └─► faq_generator.py
  ├── funnel_map.json ────────────────────────────────────────┬─► glossary_generator.py
  │                                                           └─► faq_generator.py
  └── funnel_connector.json ──────────────────────────────────►  faq_generator.py
                                                                         │
                                                                         ▼
                                              output/.../glossary_faq/
                                                ├── glossary.md
                                                └── faq.md
```

---

## What Each File Reads vs Writes

| File | Reads | Writes |
|---|---|---|
| `glossary_generator.py` | `widget_content/*.json`, `metric_catalog.json`, `final_measures_with_llm.json`, `funnel_map.json` | `glossary_faq/glossary.md` |
| `faq_generator.py` | `widget_content/*.json`, `funnel_connector.json`, `filters.json`, `funnel_map.json` | `glossary_faq/faq.md` |

---

## LLM Usage

| File | Temperature | Reason |
|---|---|---|
| `glossary_generator.py` | 0.2 | Low — want consistent, factual definitions |
| `faq_generator.py` | 0.3 | Slightly higher — FAQ answers benefit from natural phrasing |

Both use `llm_chat()` from `utils/llm_client.py` which has 5-attempt tenacity retry with exponential backoff.

---

## How to Run

```bash
# Via runner (recommended)
python src/glossary_faq/runner.py --dashboard risk-dash

# Run generators individually
python src/glossary_faq/glossary_generator.py --dashboard risk-dash
python src/glossary_faq/faq_generator.py --dashboard risk-dash

# Via main.py (full pipeline — Stage 4)
python main.py --dashboard risk-dash --from-stage 4

# Skip one
python src/glossary_faq/runner.py --skip-faq         # glossary only
python src/glossary_faq/runner.py --skip-glossary     # FAQ only
```

---

## Hardcoded Parts — Summary Across All Files

| File | What's Hardcoded | Impact if Not Changed |
|---|---|---|
| `glossary_generator.py` | `SKIP_PAGES` | Utility pages of new dashboard contribute metrics to glossary |
| `glossary_generator.py` | `GLOSSARY_SYSTEM_INLINE` | Fallback prompt lists risk-dash acronyms/domain terms — wrong for other domains |
| `glossary_generator.py` | User prompt "Risk Management Dashboard" + user list | Wrong dashboard name and users in prompt |
| `faq_generator.py` | `SKIP_PAGES` | Same as above |
| `faq_generator.py` | `SKIP_TABLES` | Scatter axis parameter tables show up as filter FAQs |
| `faq_generator.py` | `PERIOD_MAP` | Period mode defaults not translated to YTD/Rolling terminology |
| `faq_generator.py` | `FAQ_SYSTEM_INLINE` | Wrong domain + wrong period mode vocabulary for inline fallback |
| `faq_generator.py` | User prompt "Risk Management Dashboard" + user list | Wrong in generated FAQ |
| `runner.py` | Default `--dashboard risk-dash` | Only affects direct CLI use; `main.py` always passes `--dashboard` |

**Best practice for a new dashboard**: create `prompt/system_prompt/glossary.txt` and `prompt/system_prompt/faq.txt` with dashboard-specific instructions, and add the dashboard to `prompt/dashboard_config.json`. This avoids needing to touch any Python files.
