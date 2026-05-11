import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# ── Path setup (must precede layer imports so STORY_DASHBOARD is visible) ──
os.environ.setdefault("STORY_DASHBOARD", "risk-dash")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # src/ — for paths.py
sys.path.insert(0, str(Path(__file__).resolve().parent))          # Visual_wise/ — for layers
from Visual_wise.visual_enricher_with_resolved_dax_adder_L0 import enrich_and_split
from paths import get_paths, get_config

# ── Layer imports ────────────────────────────────────────────
from visual_parserL0 import (
    build_page_context,
    build_l0_packet,
    save_l0_packet,
)
from visaul_pareserL1 import call_layer1
from visual_parserL2 import call_layer2
from visual_parserL3_storymaking import call_layer3

"""
Pre-processor + Story Guide Generator
Parallel processing — sare visuals, multiple pages

Pages to process: data_availability, overview_ly, risk_capture_potential
Skip: additional_dimensions, scatter_plot_tooltip, pages_summary

overview_ly and overview_lm are the SAME visuals with different
comparison periods (YoY vs MoM). We run only overview_ly as canonical.
In the output, both comparison methods are documented together.
"""

# ============================================================
# CONFIG
# ============================================================

_HERE         = Path(__file__).parent.resolve()
_PROJECT_ROOT = _HERE.parent.parent.resolve()

# ── Dashboard selection ───────────────────────────────────────
DASHBOARD = os.environ["STORY_DASHBOARD"]
_p        = get_paths(DASHBOARD)
_cfg      = get_config()

# ── Input paths ──────────────────────────────────────────────
FIXES_PATH             = str(_cfg.fixes)
MEASURES_RESOLVED_PATH = str(_p.measures_resolved)
PROMPT_DIR             = str(_cfg.system_prompts_dir) + os.sep
VISUAL_ENRICHER_DIR    = _p.enriched_pages_dir

# ── Output paths ─────────────────────────────────────────────
OUTPUT_DIR = str(_p.story_guide_dir)

# ── Dotenv ───────────────────────────────────────────────────
DOTENV_PATH = str(_PROJECT_ROOT / ".env")
load_dotenv(DOTENV_PATH)

# ── PARALLEL EXECUTION CONFIG ────────────────────────────────
MAX_WORKERS    = 3
L0_WORKERS     = 8
LLM_CALL_DELAY = 0.5

# ── TEST MODE ────────────────────────────────────────────────
TEST_MODE        = True
TEST_VISUAL_TYPE = "cardVisual"
TEST_LIMIT       = 0

# ============================================================
# PAGE CONFIG
# ============================================================

# Ye files process NAHI hongi
SKIP_FILES = {
    "additional_dimensions.json",
    "scatter_plot_tooltip.json",
    "pages_summary.json",
}

# overview_lm aur overview_ly same visuals hain
# sirf comparison period alag hai (MoM vs YoY)
# Hum sirf overview_ly chalate hain — canonical page
# overview_lm ko skip karte hain with explanation
DUPLICATE_PAGE_PAIRS = {
    # skip_file         : canonical_file
    "overview_lm.json"  : "overview_ly.json",
}

# Comparison method per page — output mein yeh note add hoga
PAGE_COMPARISON_CONTEXT = {
    "overview_ly.json": {
        "label"          : "Overview",
        "periods"        : ["YoY (Year-over-Year)", "MoM (Month-over-Month)"],
        "canonical_note" : (
            "This page covers both YoY and MoM comparison logic. "
            "overview_lm.json is the same page with MoM as primary comparison — "
            "it is NOT processed separately to avoid redundancy. "
            "Both comparison methods are documented here."
        ),
    },
    "data_availability.json": {
        "label"  : "Data Availability",
        "periods": ["N/A — data freshness indicators only"],
    },
    "risk_capture_potential.json": {
        "label"  : "Risk Capture Potential",
        "periods": ["YoY", "MoM"],
    },
}


# ============================================================
# THREAD-SAFE HELPERS
# ============================================================

_lock     = threading.Lock()
_counters = {"success": 0, "skipped": 0, "failed": 0}

def _increment(key: str):
    with _lock:
        _counters[key] += 1

def _print_safe(*args, **kwargs):
    with _lock:
        print(*args, **kwargs)


# ============================================================
# VISUAL TYPE MAP
# ============================================================

VISUAL_TYPE_MAP = {
    "card"              : None,
    "cardVisual"        : "card.txt",
    "multiRowCard"      : None,
    "lineChart"         : "lineChart.txt",
    "areaChart"         : "lineChart.txt",
    "donutChart"        : "donutChart.txt",
    "clusteredBarChart" : "clusteredBarChart.txt",
    "barChart"          : "clusteredBarChart.txt",
    "columnChart"       : "clusteredBarChart.txt",
    "pivotTable"        : "pivotTable.txt",
    "tableEx"           : "pivotTable.txt",
    "scatterChart"      : "scatterChart.txt",
    "slicer"            : None,
}


# ============================================================
# FIXES LOAD
# ============================================================

with open(FIXES_PATH, encoding="utf-8") as f:
    FIXES = json.load(f)

TITLE_OVERRIDES = FIXES["title_overrides"]
GENERIC_TITLES  = set(FIXES["generic_titles"])
SKIP_TYPES      = set(FIXES["skip_types"])

with open(MEASURES_RESOLVED_PATH, encoding="utf-8") as f:
    MEASURES_RESOLVED: dict = json.load(f)


# ============================================================
# PAGE LOADER — all valid pages
# ============================================================

def discover_pages() -> list[dict]:
    """
    visaul_enricher_pages/ se saare JSON files load karo.

    Returns list of:
    {
      'file'      : 'overview_ly.json',
      'path'      : Path(...),
      'data'      : {...},
      'skip'      : False,
      'skip_reason: '',
      'context'   : PAGE_COMPARISON_CONTEXT entry or {}
    }
    """
    pages = []

    json_files = sorted(VISUAL_ENRICHER_DIR.glob("*.json"))

    for fpath in json_files:
        fname = fpath.name

        # ── Hard skip ────────────────────────────────────────
        if fname in SKIP_FILES:
            pages.append({
                'file'       : fname,
                'path'       : fpath,
                'data'       : None,
                'skip'       : True,
                'skip_reason': 'explicitly excluded',
                'context'    : {},
            })
            continue

        # ── Duplicate page skip ───────────────────────────────
        if fname in DUPLICATE_PAGE_PAIRS:
            canonical = DUPLICATE_PAGE_PAIRS[fname]
            pages.append({
                'file'       : fname,
                'path'       : fpath,
                'data'       : None,
                'skip'       : True,
                'skip_reason': (
                    f"duplicate of '{canonical}' — same visuals, "
                    f"different comparison period. "
                    f"Documented in '{canonical}' output instead."
                ),
                'context'    : {},
            })
            continue

        # ── Load ─────────────────────────────────────────────
        data = json.loads(fpath.read_text(encoding='utf-8'))
        pages.append({
            'file'       : fname,
            'path'       : fpath,
            'data'       : data,
            'skip'       : False,
            'skip_reason': '',
            'context'    : PAGE_COMPARISON_CONTEXT.get(fname, {}),
        })

    return pages


def print_page_plan(pages: list[dict]):
    print("\n" + "=" * 60)
    print("  PAGE PLAN")
    print("=" * 60)
    run_count  = sum(1 for p in pages if not p['skip'])
    skip_count = sum(1 for p in pages if p['skip'])
    print(f"  Will run : {run_count} pages")
    print(f"  Skipped  : {skip_count} pages\n")

    for p in pages:
        if p['skip']:
            print(f"  ⏭️  {p['file']}")
            print(f"       reason: {p['skip_reason']}")
        else:
            ctx     = p['context']
            label   = ctx.get('label', p['file'].replace('.json', ''))
            periods = ctx.get('periods', [])
            note    = ctx.get('canonical_note', '')
            print(f"  ✅ {p['file']}  [{label}]")
            if periods:
                print(f"       comparison: {', '.join(periods)}")
            if note:
                print(f"       note: {note}")
    print("=" * 60 + "\n")


# ============================================================
# PRE-PROCESSOR
# ============================================================

def fix_title(visual: dict) -> str:
    if visual["id"] in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[visual["id"]]
    title = visual.get("title", "").strip()
    if title in GENERIC_TITLES:
        measures = visual.get("measures_used", [])
        if measures:
            return measures[0].split(".")[-1]
    if not title:
        measures = visual.get("measures_used", [])
        if measures:
            return measures[0].split(".")[-1]
        return visual.get("type", "unknown")
    return title


def detect_issues(visual: dict) -> list:
    issues = []
    title  = visual.get("title", "").strip()
    if visual["id"] in TITLE_OVERRIDES:
        issues.append({"type": "wrong_title_hardcoded", "current": title, "fixed": TITLE_OVERRIDES[visual["id"]]})
    elif title in GENERIC_TITLES:
        issues.append({"type": "generic_title", "current": title, "fixed": fix_title(visual)})
    elif not title and visual["type"] not in SKIP_TYPES:
        issues.append({"type": "blank_title", "current": "(blank)", "fixed": fix_title(visual)})
    return issues


def preprocess(all_visuals: list) -> tuple[list, dict]:
    fixed_visuals = []
    report = {"total": len(all_visuals), "fixed": 0, "skipped": 0, "issues_found": []}
    for visual in all_visuals:
        if visual["type"] in SKIP_TYPES:
            report["skipped"] += 1
            continue
        issues      = detect_issues(visual)
        fixed_title = fix_title(visual)
        if issues:
            report["fixed"] += 1
            report["issues_found"].append({"id": visual["id"], "type": visual["type"], "issues": issues})
        fixed_visuals.append({**visual, "title": fixed_title})
    return fixed_visuals, report


def print_report(report: dict, page_file: str):
    print(f"\n  [{page_file}] Pre-processor: "
          f"total={report['total']}, "
          f"skipped={report['skipped']}, "
          f"fixed={report['fixed']}")


# ============================================================
# PAIRING + DAX LOOKUP (unchanged)
# ============================================================

def lookup_all_measures_dax(measures_used: list) -> str:
    if not measures_used:
        return "N/A"
    blocks, missing = [], []
    for raw in measures_used:
        name     = raw.split(".")[-1].strip()
        resolved = MEASURES_RESOLVED.get(name)
        if not resolved:
            missing.append(name)
            continue
        dax  = resolved.get("dax", "").strip()
        cols = resolved.get("referenced_columns", [])
        deps = [d["measure_name"] for d in resolved.get("depends_on", [])]
        blocks.append(f"Measure : {name}\nDAX     : {dax}\nColumns : {cols}\nDepends : {deps}")
    if missing:
        blocks.append(f"[NOT FOUND in measures_resolved]: {missing}")
    return "\n\n".join(blocks) if blocks else "N/A"


def find_all_paired_cards(visual: dict, all_visuals: list) -> dict:
    result = {"cardVisual": visual, "multiRowCard": None, "card": None}
    measures = visual.get("measures_used", [])
    if not measures:
        return result
    primary_measure = measures[0].split(".")[-1].strip().lower()
    if not primary_measure:
        return result
    best_score = 0
    for v in all_visuals:
        if v["id"] == visual["id"]:
            continue
        v_measures = v.get("measures_used", [])
        if not v_measures:
            continue
        measure = v_measures[0].split(".")[-1].strip().lower()
        if v["type"] == "multiRowCard":
            if primary_measure in measure:
                score = len(primary_measure)
                if score > best_score:
                    best_score = score
                    result["multiRowCard"] = v
        if v["type"] == "card":
            if primary_measure in measure:
                result["card"] = v
    return result


# ============================================================
# PROMPT LOADER
# ============================================================

def load_prompt(visual_type: str) -> str | None:
    filename = VISUAL_TYPE_MAP.get(visual_type)
    if filename is None:
        return None
    base_path     = PROMPT_DIR + "base_context.txt"
    template_path = PROMPT_DIR + filename
    try:
        with open(base_path,     encoding="utf-8") as f: base     = f.read()
        with open(template_path, encoding="utf-8") as f: template = f.read()
    except FileNotFoundError:
        return None
    return base + "\n\n" + template


# ============================================================
# USER PROMPT BUILDER
# ============================================================

def build_prompt(visual: dict, all_visuals: list, system_prompt: str,
                 page_context_meta: dict = None):
    axis = visual.get("axis_bindings", {})
    primary_list = (
        axis.get("y_axis") or axis.get("other") or
        axis.get("x_axis") or axis.get("rows") or
        axis.get("columns") or []
    )
    if not primary_list:
        return system_prompt, None

    primary = primary_list[0]
    if primary.get("field_type") == "Column":
        chains = visual.get("measure_chains", [])
        if chains:
            primary = {"property": chains[0]["measure_name"], "field_type": "Measure", "table": chains[0]["table"]}
        else:
            return system_prompt, None

    chain        = next((m for m in visual.get("measure_chains", []) if m["measure_name"] == primary["property"]), None)
    all_dax_block = lookup_all_measures_dax(visual.get("measures_used", []))
    active_filters = [f for f in visual.get("filter_config", []) if f.get("conditions")]

    TREND_TYPES    = {"lineChart", "areaChart"}
    KPI_CARD_TYPES = {"cardVisual"}
    related, trend_visuals, peer_cards = [], [], []

    for v in all_visuals:
        if v["id"] == visual["id"]:
            continue
        v_measures      = v.get("measures_used", [])
        v_measure_names = [m.split(".")[-1].strip() for m in v_measures]
        shares_primary  = any(primary["property"] in m for m in v_measures)
        if shares_primary:
            if v["type"] in TREND_TYPES:
                trend_visuals.append(v["title"] or v["type"])
            else:
                related.append(f"{v['title'] or v['type']} ({v['type']})")
        if v["type"] in KPI_CARD_TYPES and not shares_primary:
            peer_cards.append({"title": v["title"] or v["type"], "measures": v_measure_names})

    def get_all_dep_names(resolved_name, seen=None):
        if seen is None:
            seen = set()
        entry = MEASURES_RESOLVED.get(resolved_name)
        if not entry:
            return seen
        for d in entry.get("depends_on", []):
            dep_name = d["measure_name"]
            if dep_name not in seen:
                seen.add(dep_name)
                get_all_dep_names(dep_name, seen)
        return seen

    primary_deps        = get_all_dep_names(primary["property"])
    cross_read_partners = []

    for peer in peer_cards:
        for m_name in peer["measures"]:
            peer_deps  = get_all_dep_names(m_name)
            primary_cols = set(col for dep in [primary["property"]] + list(primary_deps)
                               for col in MEASURES_RESOLVED.get(dep, {}).get("referenced_columns", []))
            peer_cols    = set(col for dep in [m_name] + list(peer_deps)
                               for col in MEASURES_RESOLVED.get(dep, {}).get("referenced_columns", []))
            if (primary["property"] in peer_deps or m_name in primary_deps or bool(primary_cols & peer_cols)):
                cross_read_partners.append(peer["title"])
                break

    cross_read_partners = list(dict.fromkeys(cross_read_partners))

    def flatten_deps(c, seen=None):
        if seen is None:
            seen = set()
        deps = []
        for d in c.get("depends_on", []):
            if d["measure_name"] not in seen:
                seen.add(d["measure_name"])
                deps.append(d["measure_name"])
                deps.extend(flatten_deps(d, seen))
        return deps

    deps      = flatten_deps(chain) if chain else []
    supporting = [m["property"] for m in axis.get("y_axis", [])[1:]]
    pairs         = find_all_paired_cards(visual, all_visuals)
    paired_measures = []
    if pairs["multiRowCard"]:
        paired_measures.extend(pairs["multiRowCard"].get("measures_used", []))
    if pairs["card"]:
        paired_measures.extend(pairs["card"].get("measures_used", []))
    paired_dax_block = lookup_all_measures_dax(paired_measures) if paired_measures else "None"

    # Page-level comparison context note
    comparison_note = ""
    if page_context_meta:
        periods = page_context_meta.get("periods", [])
        note    = page_context_meta.get("canonical_note", "")
        if periods:
            comparison_note = f"\nPage comparison periods: {', '.join(periods)}"
        if note:
            comparison_note += f"\nNote: {note}"

    user_prompt = f"""
Generate a Story Guide for the following visual.

Title: {visual['title']}
Type: {visual['type']}{comparison_note}

Primary Measure: {primary['property']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALL DAX MEASURES ON THIS VISUAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{all_dax_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PAIRED CARD MEASURES (multiRowCard / card)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{paired_dax_block}

Active filters applied:
{[f['property'] + ': ' + str(f['conditions']) for f in active_filters]}

Upstream measure dependencies:
{deps}

Supporting measures also on this visual:
{supporting}

Related visuals on the same page (excluding trend lines):
{related}

Trend visuals sharing this measure (context only — not cross-read):
{trend_visuals}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CROSS-READ PARTNERS FOR "Key patterns" SECTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cross-read partners found : {cross_read_partners if cross_read_partners else "None"}

RULES for "Key patterns" section:
- ONLY generate if cross_read_partners is NOT empty / "None"
- ALL partners in the list must be covered — not just one
- For each partner generate one "Key patterns" block with its own
  bold label: "Key patterns (cross-read with [Partner Name]):"
  followed by its own 4-row table
- Pattern column = combined state of THIS KPI + that partner KPI
- Every block must have exactly 4 rows
- If cross_read_partners is empty — omit section entirely

Domain: Healthcare risk adjustment dashboard.
Users are care managers, medical directors, payer analysts.
    """

    return system_prompt, user_prompt


# ============================================================
# LLM CALL
# ============================================================

def generate_story_guide(visual: dict, all_visuals: list,
                         llm_client, page_context_meta: dict = None) -> str | None:
    visual_type   = visual["type"]
    system_prompt = load_prompt(visual_type)
    if system_prompt is None:
        return None

    system_prompt, user_prompt = build_prompt(
        visual, all_visuals, system_prompt, page_context_meta
    )
    if user_prompt is None:
        return None

    response = llm_client.chat.completions.create(
        model=os.environ.get("TF_MODEL", "internal-bedrock/sonnet-46"),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt}
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content


# ============================================================
# SAVE OUTPUT — page subfolder mein
# ============================================================

def save_output(visual: dict, content: str, page_name: str):
    # Page ke naam ka subfolder
    page_dir = os.path.join(OUTPUT_DIR, page_name)
    os.makedirs(page_dir, exist_ok=True)

    safe_title = (
        visual["title"]
        .replace(" ", "_").replace("%", "pct")
        .replace("/", "_").replace("(", "").replace(")", "")
    )
    filename = f"{visual['id']}_{safe_title}.md"
    filepath = os.path.join(page_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    _print_safe(f"  [SAVED] {page_name}/{filename}")


# ============================================================
# PARALLEL WORKER
# ============================================================

def process_single_visual(args):
    visual, page_context, llm_client, i, total, page_name, page_context_meta = args
    vid   = visual["id"]
    title = visual.get("title", vid)

    _print_safe(f"\n[{i+1}/{total}] START: {title} (id: {vid}, type: {visual['type']}, page: {page_name})")

    try:
        l0 = build_l0_packet(visual, page_context)
        save_l0_packet(l0)
        if l0.skip:
            _print_safe(f"  [SKIP-L0] {vid} — {l0.skip_reason}")
            _increment("skipped")
            return "skipped", visual

        time.sleep(LLM_CALL_DELAY)

        l1 = call_layer1(l0, llm_client)
        if l1.skip:
            _print_safe(f"  [SKIP-L1] {vid} — {l1.skip_reason}")
            _increment("skipped")
            return "skipped", visual

        _print_safe(f"  [L1-OK] {title}")

        l2 = call_layer2(l0, l1, llm_client)
        if l2.skip:
            _print_safe(f"  [SKIP-L2] {vid} — {l2.skip_reason}")
            _increment("skipped")
            return "skipped", visual

        _print_safe(f"  [L2-OK] {title}")

        l3 = call_layer3(l0, l1, l2, llm_client)
        if l3.skip:
            _print_safe(f"  [SKIP-L3] {vid} — {l3.skip_reason}")
            _increment("skipped")
            return "skipped", visual

        warn_count = len(l3.warnings)
        _print_safe(f"  [L3-OK] {title}" + (f" ⚠ {warn_count} warnings" if warn_count else ""))
        _increment("success")
        return "success", visual

    except Exception as e:
        import traceback
        _print_safe(f"  [ERROR] {vid} — {e}")
        _print_safe(traceback.format_exc())
        _increment("failed")
        return "failed", visual


# ============================================================
# TEST MODE FILTER
# ============================================================

def apply_test_filter(visuals: list) -> list:
    if not TEST_MODE:
        return visuals
    cards    = [v for v in visuals if v["type"] == TEST_VISUAL_TYPE]
    if TEST_LIMIT > 0:
        cards = cards[:TEST_LIMIT]
    tables   = [v for v in visuals if v["type"] in {"pivotTable", "tableEx"}]
    lines    = [v for v in visuals if v["type"] in {"lineChart", "areaChart"}]
    charts   = [v for v in visuals if v["type"] in {"clusteredBarChart", "barChart", "columnChart"}]
    donuts   = [v for v in visuals if v["type"] == "donutChart"]
    scatters = [v for v in visuals if v["type"] == "scatterChart"]
    limited = cards + tables + lines + charts + donuts + scatters  # ← change this to test different types

    print(f"\n  [TEST] cards={len(cards)}, tables={len(tables)}, lines={len(lines)}, "
          f"charts={len(charts)}, donuts={len(donuts)}, scatters={len(scatters)}")
    print(f"  [TEST] Running: {len(limited)} visuals")
    return limited

def deduplicate(fixed_visuals: list) -> list:
    processed_measures = set()
    deduplicated = []
    TABLE_LIKE = {"pivotTable", "tableEx", "lineChart", "areaChart",
                  "clusteredBarChart", "barChart", "columnChart",
                  "donutChart", "scatterChart"}
    for visual in fixed_visuals:
        measures = visual.get("measures_used", [])
        if not measures:
            fallback = visual.get("title", "").strip() or visual.get("type", "unknown")
            if fallback not in processed_measures:
                deduplicated.append(visual)
                processed_measures.add(fallback)
            continue
        if visual.get("type") in TABLE_LIKE:
            if visual["id"] not in processed_measures:
                deduplicated.append(visual)
                processed_measures.add(visual["id"])
            continue
        primary = measures[0].split(".")[-1].strip()
        if primary not in processed_measures:
            deduplicated.append(visual)
            processed_measures.add(primary)
    return deduplicated
# ============================================================
# PROCESS ONE PAGE
# ============================================================
def process_page(page: dict, llm_client) -> dict:
    fname             = page['file']
    page_name         = fname.replace('.json', '')
    data              = page['data']
    page_context_meta = page['context']

    all_visuals = data["visuals"]
    fixed_visuals, report = preprocess(all_visuals)
    print_report(report, fname)
    deduplicated = deduplicate(fixed_visuals)
    deduplicated = apply_test_filter(deduplicated)
    page_context = build_page_context(all_visuals)

    total = len(deduplicated)
    print(f"  Processing {total} visuals in phases")

    # ── PHASE 1: all L0s in parallel ─────────────────────────
    l0_packets = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(build_l0_packet, v, page_context): v
            for v in deduplicated
        }
        for future in as_completed(futures):
            visual = futures[future]
            l0 = future.result()
            save_l0_packet(l0)
            l0_packets[visual["id"]] = l0

    active_l0s = {
        vid: l0 for vid, l0 in l0_packets.items()
        if not l0.skip
    }
    print(f"  [PHASE 1 done] {len(active_l0s)}/{total} L0s active")

    # ── PHASE 2: all L1s in parallel ─────────────────────────
    l1_packets = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(call_layer1, l0, llm_client): vid
            for vid, l0 in active_l0s.items()
        }
        for future in as_completed(futures):
            vid = futures[future]
            l1 = future.result()
            l1_packets[vid] = l1

    active_l1s = {
        vid: l1 for vid, l1 in l1_packets.items()
        if not l1.skip
    }
    print(f"  [PHASE 2 done] {len(active_l1s)}/{total} L1s active")

    # ── PHASE 3: all L2s in parallel ─────────────────────────
    # NOW all L1 packets are complete — L2 can safely do
    # cross-visual reasoning against all peers
    l2_packets = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(
                call_layer2,
                active_l0s[vid], active_l1s[vid],
                llm_client
            ): vid
            for vid in active_l1s
        }
        for future in as_completed(futures):
            vid = futures[future]
            l2 = future.result()
            l2_packets[vid] = l2

    active_l2s = {
        vid: l2 for vid, l2 in l2_packets.items()
        if not l2.skip
    }
    print(f"  [PHASE 3 done] {len(active_l2s)}/{total} L2s active")

    # ── PHASE 4: all L3s in parallel ─────────────────────────
    stats = {"success": 0, "skipped": 0, "failed": 0, "total": total}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(
                call_layer3,
                active_l0s[vid], active_l1s[vid],
                active_l2s[vid], llm_client
            ): vid
            for vid in active_l2s
        }
        for future in as_completed(futures):
            vid = futures[future]
            try:
                l3 = future.result()
                if l3.skip:
                    stats["skipped"] += 1
                else:
                    stats["success"] += 1
                    _increment("success")
            except Exception as e:
                _print_safe(f"  [ERROR] {vid} — {e}")
                stats["failed"] += 1
                _increment("failed")

    # Count skipped at L0/L1/L2
    skipped_early = total - len(active_l2s)
    stats["skipped"] += skipped_early
    _counters["skipped"] += skipped_early

    print(f"  [PHASE 4 done] success={stats['success']} "
          f"skipped={stats['skipped']} failed={stats['failed']}")
    return stats


# ============================================================
# MAIN
# ============================================================

def main():
    llm_client = OpenAI(
        api_key  = os.environ["TF_API_KEY"],
        base_url = os.environ["TF_BASE_URL"],
    )
    print(f"Model: {os.environ.get('TF_MODEL', 'internal-bedrock/sonnet-46')}")
    print("\nRunning visual enricher...")
    enrich_and_split(
        visuals_path  = _p.visuals,           # adjust to your actual path key
        resolved_path = Path(MEASURES_RESOLVED_PATH),
        out_dir       = _p.enriched_pages_dir,
    )
    print("Enricher done.\n")
    # ── Discover all pages ───────────────────────────────────
    pages = discover_pages()
    print_page_plan(pages)

    pages_to_run = [p for p in pages if not p['skip']]
    print(f"Pages to run: {len(pages_to_run)}")

    # ── Reset counters ───────────────────────────────────────
    _counters["success"] = 0
    _counters["skipped"] = 0
    _counters["failed"]  = 0

    all_page_stats = {}

    # ── Run each page sequentially ───────────────────────────
    # (visuals within each page run in parallel)
    for page in pages_to_run:
        stats = process_page(page, llm_client)
        all_page_stats[page['file']] = stats

    # ── Final summary ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print("=" * 60)

    print("\n  Per-page results:")
    total_visuals = 0
    for fname, stats in all_page_stats.items():
        total_visuals += stats['total']
        print(f"  {fname}")
        print(f"    total={stats['total']}, "
              f"success={stats['success']}, "
              f"skipped={stats['skipped']}, "
              f"failed={stats['failed']}")

    print(f"\n  Overall:")
    print(f"    Pages run    : {len(pages_to_run)}")
    print(f"    Pages skipped: {sum(1 for p in pages if p['skip'])}")
    print(f"    Total visuals: {total_visuals}")
    print(f"    Success      : {_counters['success']}")
    print(f"    Skipped      : {_counters['skipped']}")
    print(f"    Failed       : {_counters['failed']}")

    print(f"\n  Outputs saved to:")
    for page in pages_to_run:
        page_name = page['file'].replace('.json', '')
        print(f"    {OUTPUT_DIR}/{page_name}/")

    skipped_pages = [p for p in pages if p['skip']]
    if skipped_pages:
        print(f"\n  Skipped pages:")
        for p in skipped_pages:
            print(f"    ⏭️  {p['file']} — {p['skip_reason']}")
    print("=" * 60)


if __name__ == "__main__":
    main()