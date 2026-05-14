# glossary_generator.py — Glossary Builder

## Purpose
Collects metric definitions from 3 sources (widget_content, metric_catalog, final_measures_with_llm) and domain vocabulary from funnel_map, then sends them all to an LLM to produce a structured 3-section glossary table: Acronyms, Domain Terms, and Metric Definitions.

---

## Input / Output

| | Detail |
|---|---|
| **Input A** (primary) | `output/dashboards/<dash>/page_wise/widget_content/*.json` — rich metric definitions |
| **Input B** (secondary) | `output/dashboards/<dash>/metric_dictionary/metric_catalog.json` — business definitions |
| **Input C** (tertiary) | `output/dashboards/<dash>/metric_dictionary/final_measures_with_llm.json` — LLM fallback definitions |
| **Input D** | `output/dashboards/<dash>/page_wise/funnel_map.json` — `domain_context` field |
| **System prompt** | `prompt/system_prompt/glossary.txt` (if exists) else inline fallback |
| **Config** | `prompt/dashboard_config.json` — domain, users per dashboard |
| **Output** | `output/dashboards/<dashboard>/glossary_faq/glossary.md` |

---

## Source Priority

When the same metric appears in multiple sources, this priority applies:
```
widget_content  >  metric_catalog  >  final_measures_with_llm
```
A metric found in `widget_content` is never overridden by other sources.

---

## Pipeline Steps

```
Step 1  collect_terms()       → gather metrics from 4 sources
Step 2  load_glossary_prompt() → load system prompt (file or inline)
Step 3  build_glossary_prompt() → assemble user prompt with all terms
Step 4  generate_glossary()   → LLM call → markdown string
Step 5  save_glossary()       → write glossary.md
```

---

## Function Flow

```
main()
  ├── parse --dashboard arg
  ├── OpenAI client (TF_API_KEY + TF_BASE_URL)
  ├── collect_terms(dashboard, _ROOT)
  │     ├── Source A: widget_content/*.json
  │     │     └── skip SKIP_PAGES, extract metric.name + metric.definition
  │     ├── Source B: metric_catalog.json
  │     │     └── extract measure_name + business_definition (if not in widget_terms)
  │     ├── Source C: final_measures_with_llm.json
  │     │     └── extract measure_name + llm_definition (if not in A or B)
  │     └── Source D: funnel_map.json → domain_context string
  │
  ├── generate_glossary(data, llm_client, dashboard)
  │     ├── load_glossary_prompt(dashboard)
  │     │     ├── try: load prompt/system_prompt/glossary.txt
  │     │     │     + prepend domain_block (users, domain from dashboard_config.json)
  │     │     │     + prepend base_context.txt
  │     │     └── fallback: GLOSSARY_SYSTEM_INLINE (hardcoded string)
  │     ├── build_glossary_prompt(data, system_prompt)
  │     │     ├── formats each source as labelled metric list
  │     │     └── returns (system_prompt, user_prompt)
  │     └── llm_chat([system, user], temperature=0.2)
  │
  └── save_glossary(result, dashboard, _ROOT)
        └── write → glossary_faq/glossary.md
```

---

## Function Details

### `collect_terms(dashboard, root) → dict`
Reads from 4 sources and returns:
```python
{
  "widget_terms":    {name: definition},   # primary — visual-level context
  "catalog_terms":   {name: definition},   # secondary — metric_catalog business_def
  "llm_measures":    {name: definition},   # tertiary — llm_fallback definitions
  "domain_context":  str,
}
```
- Skips pages in `SKIP_PAGES` (utility/tooltip pages)
- Prints warnings if any source file is missing (does not crash — continues with empty dict)
- Each source only collects terms NOT already found in a higher-priority source

### `load_glossary_prompt(dashboard) → str`
Tries to load `prompt/system_prompt/glossary.txt`. If found:
- Prepends domain block from `prompt/dashboard_config.json` (users + domain)
- Prepends `base_context.txt` (shared base rules)
- Returns combined prompt

Falls back to `GLOSSARY_SYSTEM_INLINE` if `glossary.txt` doesn't exist.

### `build_glossary_prompt(data, system_prompt) → tuple[str, str]`
Assembles the user prompt. Formats all 3 term dicts as labelled sections (Source A / B / C). Truncates each definition to 200 chars in the prompt to stay within token limits. Returns `(system_prompt, user_prompt)`.

### `generate_glossary(data, llm_client, dashboard) → str`
Calls `llm_chat()` with `temperature=0.2` (low — want consistent, factual output). Returns raw markdown string from LLM.

### `save_glossary(content, dashboard, root) → Path`
Creates `output/dashboards/<dashboard>/glossary_faq/` dir and writes `glossary.md`.

### `_format_metric_list(terms, label) → str`
Helper that formats a `{name: definition}` dict into labelled bullet lines for the user prompt.

---

## LLM Output Structure
The LLM is instructed to produce exactly 3 sections:
```
### Acronyms & Abbreviations
| Term | Meaning |
...

### Domain Terms
| Term | Meaning |
...

### Metric Definitions
| Metric Name | Definition |
...
```

---

## File Connections

| Imports from | Used for |
|---|---|
| `utils/llm_client.py` | `llm_chat()` — LLM call with tenacity retry |
| `prompt/system_prompt/glossary.txt` | System prompt (optional — falls back to inline) |
| `prompt/system_prompt/base_context.txt` | Shared base rules prepended to system prompt |
| `prompt/dashboard_config.json` | `users` + `domain` per dashboard |

**Called by:** `runner.py` (as subprocess)

---

## Hardcoded Parts (Change for New Dashboards)

### `SKIP_PAGES` (line ~35)
```python
SKIP_PAGES = {"additional dimensions", "additional_dimensions",
              "scatter plot tooltip", "scatter_plot_tooltip"}
```
These are **risk-dash / pac-dash specific** utility page names that should not contribute metrics to the glossary. If a new dashboard has different utility pages, add them here (both spaced and underscore versions).

### `GLOSSARY_SYSTEM_INLINE` (line ~134)
```python
GLOSSARY_SYSTEM_INLINE = """\
You are a documentation writer for a healthcare risk adjustment dashboard.
...
[HCC, RAF, PMPM, YoY, MoM, YTD, KPI, LOB, PCP, etc.]
...
[Documented risk, Potential risk, Recapture rate, Gap to potential risk, ...]
"""
```
This inline fallback prompt is **hardcoded for healthcare risk adjustment** domain. It lists specific acronyms and domain terms. If a new dashboard is in a different domain, either:
- Create a `prompt/system_prompt/glossary.txt` for that dashboard (preferred), OR
- Update the inline fallback

### User prompt hardcoded text (line ~196)
```python
user_prompt = f"""Generate a Glossary of Terms for the Risk Management Dashboard.
...
─── USERS ───────────────────────────────────────────────────
Medical Director, Care Manager, Payer Analyst, Practice Manager
"""
```
"Risk Management Dashboard" and the user list are hardcoded. When `dashboard_config.json` has a `users` key, it is used in the system prompt but NOT in the user prompt. For a new dashboard, update this text or drive it from `dashboard_config.json`.

### Definition truncation (line ~191)
```python
lines = [f"  - {name}: {defn[:200]}" for name, defn in sorted(terms.items())]
```
Definitions are truncated at 200 chars in the prompt. Increase if definitions are longer and token budget allows.
