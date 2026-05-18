"""
document_assembler.py
=====================
Stage 3D — No LLM. Pure Python rendering.

Reads all stage3 output and renders final_story_guide.md
matching the PDF template structure exactly.

DOCUMENT STRUCTURE (matches Risk story guide PDF):
  H1: [Dashboard Name] — Story Guide
  subtitle: Dashboard | Pages | Last updated

  H2: About this guide
    [domain_context]
    [overview paragraph from funnel questions]
    The funnel: bullet list

  H2: Page 1: [Page Name]
  H2: Layer 1: [layer name]
    H3: [Widget name]
      📷 Insert: screenshot
      [group_intro]
      H3: [metric / sub-section]
      [definition]
      Direction | Interpretation table
      [italic callout]
    H3: Reading the cards together
      Pattern | Interpretation table

  H2: Layer 2: [layer name]
    ...

  H2: Layer 3: [layer name]
    ...

  H2: Page 2: [Action Page]
    [page intro — from funnel_question_action]
    H3: [widget name]
    ...

  H2: How the funnel connects
    Layer | Section | Question it answers table

  H3: Reading across pages
    Pattern | Interpretation table

  [closing_paragraph]

  footer

INPUT:
  output/dashboards/<dash>/stage3/funnel_map.json
  output/dashboards/<dash>/stage3/widget_content/*.json
  output/dashboards/<dash>/stage3/funnel_connector.json

OUTPUT:
  output/dashboards/<dash>/stage3/final_story_guide.md

Run:
  python document_assembler.py
  python document_assembler.py --dashboard risk-dash
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import json
import argparse
from pathlib import Path
from datetime import date


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "output").exists() and (parent / "config").exists():
            return parent
    return Path(__file__).resolve().parent.parent.parent


def load_json(path: Path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def page_to_slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("/", "_")


# ─────────────────────────────────────────────────────────────────────────────
# Markdown primitives — match PDF visual style
# ─────────────────────────────────────────────────────────────────────────────

HR  = "\n---\n"   # horizontal rule between major sections
NL  = "\n"


def md_table(headers: list, rows: list) -> str:
    """Render a markdown table. Handles empty rows gracefully."""
    if not rows:
        return ""
    # compute column widths
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    def fmt(cells):
        return "| " + " | ".join(
            str(c).ljust(widths[i]) if i < len(widths) else str(c)
            for i, c in enumerate(cells)
        ) + " |"

    sep = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    return "\n".join([fmt(headers), sep] + [fmt(r) for r in rows])


def screenshot(label: str) -> str:
    """Blockquote italic screenshot placeholder — matches PDF style."""
    return f"> *📷 Insert: Screenshot of {label}*\n"


def italic(text: str) -> str:
    if not text:
        return ""
    return f"*{text}*\n"


# ─────────────────────────────────────────────────────────────────────────────
# Widget renderers — match PDF section structure exactly
# ─────────────────────────────────────────────────────────────────────────────

def render_kpi_card_row(w: dict) -> str:
    """
    PDF structure:
      H3: KPI cards — risk summary
      📷 screenshot
      [group_intro paragraph]
      H3: Row 1: The risk landscape   (sub-section if widget has row label)
      H3: Eligible population
      [definition]
      Direction | Interpretation table
      [italic callout]
      ...
      H3: Reading the cards together
      Pattern | Interpretation table
    """
    out = []
    out.append(f"### {w.get('widget_name','')}\n")
    out.append(screenshot(w.get("screenshot_label", "")))
    out.append(f"{w.get('group_intro','')}\n")

    for m in w.get("metrics", []):
        out.append(f"### {m['name']}\n")
        out.append(f"{m.get('definition','')}\n")

        dirs = m.get("direction_table", [])
        if dirs:
            rows = [
                [d.get("direction",""),
                 d.get("interpretation", d.get("operationally signals",""))]
                for d in dirs
            ]
            out.append(md_table(["Direction", "Interpretation"], rows))
            out.append(NL)

        callout = m.get("italic_callout")
        if callout:
            out.append(italic(callout))

    # Reading the cards together
    rt = w.get("reading_together", {})
    if rt:
        out.append(f"### {rt.get('heading', 'Reading the cards together')}\n")
        patterns = rt.get("patterns", [])
        if patterns:
            rows = [[p.get("pattern",""), p.get("interpretation","")] for p in patterns]
            out.append(md_table(["Pattern", "Interpretation"], rows))
            out.append(NL)

    return NL.join(out)


def render_trend_lines(w: dict) -> str:
    """
    PDF structure:
      H3: Trends over time
      📷 screenshot
      [group_intro]
      H3: Members and Eligible Population trends
      [definition]
      Pattern | Interpretation table  (only for charts that have patterns)
      [italic callout]  (only on most important chart)
    """
    out = []
    out.append(f"### {w.get('widget_name','')}\n")
    out.append(screenshot(w.get("screenshot_label", "")))
    out.append(f"{w.get('group_intro','')}\n")

    for chart in w.get("charts", []):
        out.append(f"### {chart.get('name','')}\n")
        out.append(f"{chart.get('definition','')}\n")

        patterns = chart.get("patterns", [])
        if patterns:
            rows = [[p.get("pattern",""), p.get("interpretation","")] for p in patterns]
            out.append(md_table(["Pattern", "Interpretation"], rows))
            out.append(NL)

        callout = chart.get("italic_callout")
        if callout:
            out.append(italic(callout))

    return NL.join(out)


def render_detail_table(w: dict) -> str:
    """
    PDF structure:
      H3: [widget name]
      📷 screenshot
      [group_intro]

      COLUMN_FOCUSED:
        Key columns:
        Column | What to look for table
        Critical patterns:
        Pattern | Interpretation table
        [italic callout]

      SEGMENT_FOCUSED:
        Column / row interpretations:
        Status | Expected behavior | Red flag table
        [italic callout]
    """
    out = []
    out.append(f"### {w.get('widget_name','')}\n")
    out.append(screenshot(w.get("screenshot_label", "")))
    out.append(f"{w.get('group_intro','')}\n")

    if w.get("table_format") == "SEGMENT_FOCUSED":
        segs = w.get("segment_table", [])
        if segs:
            rows = [
                [s.get("segment",""),
                 s.get("expected_behavior",""),
                 s.get("red_flag","")]
                for s in segs
            ]
            out.append(md_table(["Status", "Expected behavior", "Red flag"], rows))
            out.append(NL)
    else:
        cols = w.get("column_table", [])
        if cols:
            out.append("**Key columns:**\n")
            rows = [[c.get("column",""), c.get("what_to_look_for","")] for c in cols]
            out.append(md_table(["Column", "What to look for"], rows))
            out.append(NL)

        patterns = w.get("patterns", [])
        if patterns:
            out.append("**Critical patterns:**\n")
            rows = [[p.get("pattern",""), p.get("interpretation","")] for p in patterns]
            out.append(md_table(["Pattern", "Interpretation"], rows))
            out.append(NL)

    callout = w.get("italic_callout")
    if callout:
        out.append(italic(callout))

    return NL.join(out)


def render_clinical_pair(w: dict) -> str:
    """
    PDF structure:
      H3: Risk factor details and recapture by disease
      📷 screenshot
      [group_intro]
      H3: [bar chart name]
      [definition]
      Pattern | Interpretation table
      H3: [detail table name]
      Column | What to look for table
      [italic callout]
    """
    out = []
    out.append(f"### {w.get('widget_name','')}\n")
    out.append(screenshot(w.get("screenshot_label", "")))
    out.append(f"{w.get('group_intro','')}\n")

    bar = w.get("bar_chart", {})
    if bar:
        out.append(f"### {bar.get('name','')}\n")
        out.append(f"{bar.get('definition','')}\n")
        patterns = bar.get("patterns", [])
        if patterns:
            rows = [[p.get("pattern",""), p.get("interpretation","")] for p in patterns]
            out.append(md_table(["Pattern", "Interpretation"], rows))
            out.append(NL)

    tbl = w.get("detail_table", {})
    if tbl:
        out.append(f"### {tbl.get('name','')}\n")
        cols = tbl.get("column_table", [])
        if cols:
            rows = [[c.get("column",""), c.get("what_to_look_for","")] for c in cols]
            out.append(md_table(["Column", "What to look for"], rows))
            out.append(NL)

    callout = w.get("italic_callout")
    if callout:
        out.append(italic(callout))

    return NL.join(out)


def render_entity_scatter(w: dict) -> str:
    """
    PDF structure:
      H3: Practice/PCP details
      📷 screenshot
      [group_intro]
      [entity table definition]
      Key columns:
      Column | What to look for table
      Reading patterns:
      Pattern | Interpretation table
      H3: PCP distribution scatter
      [definition]
    """
    out = []
    out.append(f"### {w.get('widget_name','')}\n")
    out.append(screenshot(w.get("screenshot_label", "")))
    out.append(f"{w.get('group_intro','')}\n")

    et = w.get("entity_table", {})
    if et:
        out.append(f"{et.get('definition','')}\n")
        out.append("**Key columns:**\n")
        cols = et.get("column_table", [])
        if cols:
            rows = [[c.get("column",""), c.get("what_to_look_for","")] for c in cols]
            out.append(md_table(["Column", "What to look for"], rows))
            out.append(NL)

        rp = et.get("reading_patterns", [])
        if rp:
            out.append("**Reading patterns:**\n")
            rows = [[p.get("pattern",""), p.get("interpretation","")] for p in rp]
            out.append(md_table(["Pattern", "Interpretation"], rows))
            out.append(NL)

    sc = w.get("scatter_plot", {})
    if sc:
        out.append(f"### {sc.get('name','')}\n")
        out.append(f"{sc.get('definition','')}\n")
        pos = sc.get("position_table", [])
        if pos:
            rows = [[p.get("position",""), p.get("interpretation","")] for p in pos]
            out.append(md_table(["Position", "Interpretation"], rows))
            out.append(NL)

    return NL.join(out)


def render_multi_chart(w: dict) -> str:
    """
    PDF structure:
      H3: Gap closure patterns
      📷 screenshot
      [group_intro]
      H3: Gap closure by type of visit
      Segment | Interpretation table
      H3: Gap closure by network status
      ...
    """
    out = []
    out.append(f"### {w.get('widget_name','')}\n")
    out.append(screenshot(w.get("screenshot_label", "")))
    out.append(f"{w.get('group_intro','')}\n")

    for chart in w.get("charts", []):
        out.append(f"### {chart.get('name','')}\n")
        out.append(f"{chart.get('definition','')}\n")
        segs = chart.get("segment_table", [])
        if segs:
            rows = [[s.get("segment",""), s.get("interpretation","")] for s in segs]
            out.append(md_table(["Segment", "Interpretation"], rows))
            out.append(NL)

    return NL.join(out)


def render_action_table(w: dict) -> str:
    """
    PDF structure:
      H3: [widget name]
      📷 screenshot
      [group_intro]
      [bar chart definition if present]
      Column | What to look for table
      [italic callout]
    """
    out = []
    out.append(f"### {w.get('widget_name','')}\n")
    out.append(screenshot(w.get("screenshot_label", "")))
    out.append(f"{w.get('group_intro','')}\n")

    bar = w.get("bar_chart", {})
    if bar:
        out.append(f"**{bar.get('name','')}** — {bar.get('definition','')}\n")

    cols = w.get("column_table", [])
    if cols:
        rows = [[c.get("column",""), c.get("what_to_look_for","")] for c in cols]
        out.append(md_table(["Column", "What to look for"], rows))
        out.append(NL)

    callout = w.get("italic_callout")
    if callout:
        out.append(italic(callout))

    return NL.join(out)


def render_segmentation(w: dict) -> str:
    """
    PDF structure:
      H3: Outreach segmentation
      📷 screenshot
      [group_intro]
      H3: Across PCP visits (rolling 12 months)
      Segment | Interpretation | Outreach action table
      ...
    """
    out = []
    out.append(f"### {w.get('widget_name','')}\n")
    out.append(screenshot(w.get("screenshot_label", "")))
    out.append(f"{w.get('group_intro','')}\n")

    for chart in w.get("charts", []):
        out.append(f"### {chart.get('name','')}\n")
        out.append(f"{chart.get('definition','')}\n")
        segs = chart.get("segment_table", [])
        if segs:
            has_action = any("outreach_action" in s for s in segs)
            if has_action:
                headers = ["Segment", "Interpretation", "Suggested outreach action"]
                rows = [
                    [s.get("segment",""),
                     s.get("interpretation",""),
                     s.get("outreach_action","")]
                    for s in segs
                ]
            else:
                headers = ["Segment", "Interpretation"]
                rows = [[s.get("segment",""), s.get("interpretation","")] for s in segs]
            out.append(md_table(headers, rows))
            out.append(NL)

    return NL.join(out)


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────────────────

RENDERERS = {
    "KPI_CARD_ROW":   render_kpi_card_row,
    "TREND_LINES":    render_trend_lines,
    "DETAIL_TABLE":   render_detail_table,
    "CLINICAL_PAIR":  render_clinical_pair,
    "ENTITY_SCATTER": render_entity_scatter,
    "MULTI_CHART":    render_multi_chart,
    "ACTION_TABLE":   render_action_table,
    "SEGMENTATION":   render_segmentation,
}


def render_widget(content: dict) -> str:
    if not content:
        return ""
    status = content.get("status", "")
    if status in ("NOT_IMPLEMENTED", "ERROR"):
        return (f"### {content.get('widget_name','')}\n\n"
                f"> ⚠️ *Content not yet generated ({status})*\n\n")
    wtype = content.get("widget_type", "")
    renderer = RENDERERS.get(wtype)
    if not renderer:
        return f"### {content.get('widget_name','')}\n\n> ⚠️ *Unknown type: {wtype}*\n\n"
    return renderer(content) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# Layer names
# ─────────────────────────────────────────────────────────────────────────────

LAYER_LABELS = {
    "TOP":    ("Layer 1", "The risk position"),
    "MIDDLE": ("Layer 2", "The diagnosis"),
    "BOTTOM": ("Layer 3", "The action"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Main assembler
# ─────────────────────────────────────────────────────────────────────────────

def assemble(dashboard: str, root: Path) -> str:
    stage3  = root / "output" / "dashboards" / dashboard / "page_wise"

    funnel_map  = load_json(stage3 / "funnel_map.json")
    connector   = load_json(stage3 / "funnel_connector.json")

    if not funnel_map:
        raise FileNotFoundError(f"funnel_map.json not found at {stage3}")
    if not connector:
        raise FileNotFoundError(f"funnel_connector.json not found at {stage3}")

    # load all widget content files
    content_dir   = stage3 / "widget_content"
    widget_lookup = {}   # widget_id -> content dict
    for f in content_dir.glob("*.json"):
        page_data = load_json(f)
        if page_data:
            for w in page_data.get("widgets", []):
                widget_lookup[w["widget_id"]] = w

    # metadata
    dashboard_name = funnel_map.get("dashboard_name", dashboard)
    pages_processed = funnel_map.get("_meta", {}).get("pages_processed", [])
    pages_mirrored  = funnel_map.get("_meta", {}).get("pages_mirrored", [])
    all_page_names  = pages_processed + pages_mirrored
    today           = date.today().strftime("%B %d, %Y")

    # ── Strip time-period suffixes from page display names for rendering ─────
    # "Overview LY" -> "Overview", "Overview LM" -> "Overview"
    # Same logic as funnel_mapper.py get_page_base_name()
    TIME_SUFFIXES = {
        "ly","lm","ytd","mtd","qtd","q1","q2","q3","q4",
        "yoy","mom","qoq","py","cy","prior year","current year",
        "prior month","current month",
    }

    def display_name(page_name: str) -> str:
        """Strip trailing time-period suffix for display."""
        parts = page_name.strip().split()
        if parts and parts[-1].lower() in TIME_SUFFIXES:
            base = " ".join(parts[:-1]).strip()
            return base if base else page_name
        if len(parts) >= 2:
            last_two = " ".join(parts[-2:]).lower()
            if last_two in TIME_SUFFIXES:
                base = " ".join(parts[:-2]).strip()
                return base if base else page_name
        return page_name

    doc = []

    doc.append("**Page Wise Narrative**\n")

    # ── Funnel intro bullets ───────────────────────────────────────────────────
    top_q    = funnel_map.get("funnel_question_top", "")
    mid_q    = funnel_map.get("funnel_question_middle", "")
    bot_q    = funnel_map.get("funnel_question_bottom", "")
    action_q = funnel_map.get("funnel_question_action", "")

    if top_q or mid_q or bot_q:
        doc.append("**The funnel:**\n")
        if top_q:
            doc.append(f"- **Top** -> {top_q}\n")
        if mid_q:
            doc.append(f"- **Middle** -> {mid_q}\n")
        if bot_q:
            doc.append(f"- **Bottom** -> {bot_q}\n")
        if action_q:
            doc.append(f"- **Action** -> {action_q}\n")
        doc.append(NL)

    # ── Pages ─────────────────────────────────────────────────────────────────
    widgets_all = funnel_map.get("widgets", [])

    # Priority ordering: main_page > main > overview > summary > everything else
    _FIRST_KEYWORDS = ["main_page", "main", "overview", "summary"]

    def _page_priority(page_name: str) -> int:
        slug = page_name.lower().replace(" ", "_")
        for i, kw in enumerate(_FIRST_KEYWORDS):
            if slug.startswith(kw):
                return i
        return len(_FIRST_KEYWORDS)

    pages_in_order = sorted(pages_processed, key=_page_priority)

    for page_num, page_name in enumerate(pages_in_order, start=1):
        page_widgets = [
            w for w in widgets_all
            if w.get("page") == page_name
            and not w.get("mirrored_from")
        ]
        if not page_widgets:
            continue

        is_action_page = all(
            w.get("funnel_position") == "ACTION"
            for w in page_widgets
        )

        # use stripped display name for heading
        doc.append(f"## Page {page_num}: {display_name(page_name)}\n")
        doc.append(HR)

        if is_action_page and action_q:
            doc.append(f"{action_q}\n")
            doc.append(NL)

        if is_action_page:
            for wm in sorted(page_widgets, key=lambda x: x.get("reading_order", 99)):
                content = widget_lookup.get(wm["widget_id"], {})
                doc.append(render_widget(content))
                doc.append(HR)
        else:
            current_layer_key = None
            for wm in sorted(page_widgets, key=lambda x: x.get("reading_order", 99)):
                pos = wm.get("funnel_position", "")
                layer_info = LAYER_LABELS.get(pos)

                if layer_info and pos != current_layer_key:
                    current_layer_key = pos
                    layer_num, layer_name = layer_info
                    doc.append(f"## {layer_num}: {layer_name}\n")
                    doc.append(HR)

                content = widget_lookup.get(wm["widget_id"], {})
                doc.append(render_widget(content))
                doc.append(HR)

    # ── Mirrored pages — one-line note each ───────────────────────────────────
    for mirror_page in pages_mirrored:
        source = next(
            (w.get("mirrored_from") for w in widgets_all
             if w.get("page") == mirror_page and w.get("mirrored_from")),
            pages_processed[0] if pages_processed else ""
        )
        page_num = len(pages_in_order) + pages_mirrored.index(mirror_page) + 1
        doc.append(f"## Page {page_num}: {display_name(mirror_page)}\n")
        doc.append(HR)
        doc.append(
            f"> *{display_name(mirror_page)} also shows the same metrics and widget "
            f"structure as the section above, with a different comparison period "
            f"(month-over-month vs year-over-year). "
            f"All interpretation guidance above applies equally here.*\n"
        )
        doc.append(HR)

    # ── How the funnel connects ────────────────────────────────────────────────
    cross_patterns = connector.get("cross_page_patterns", [])

    doc.append("## How the funnel connects\n")
    funnel_table = connector.get("funnel_table", [])
    if funnel_table:
        rows = [
            [r.get("layer",""),
             r.get("section",""),
             r.get("question_it_answers","")]
            for r in funnel_table
        ]
        doc.append(md_table(["Layer", "Section", "Question it answers"], rows))
        doc.append(NL)

    if cross_patterns:
        doc.append("### Reading across pages\n")
        rows = [[p.get("pattern",""), p.get("interpretation","")] for p in cross_patterns]
        doc.append(md_table(["Pattern", "Interpretation"], rows))
        doc.append(NL)

    closing = connector.get("closing_paragraph", "")
    if closing:
        doc.append(f"{closing}\n")

    doc.append(HR)
    doc.append(
        "*Generated by Story Guide Generator | "
        "For metric definitions or SQL queries, query the L5 Knowledge Base*\n"
    )

    return "\n".join(doc)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Assemble final_story_guide.md from stage3 outputs"
    )
    parser.add_argument("--dashboard", default="risk-dash")
    args = parser.parse_args()

    root     = get_project_root()
    out_path = (root / "output" / "dashboards" / args.dashboard
                / "page_wise" / "page_wise_story.md")

    print(f"[assembler] dashboard : {args.dashboard}")
    print(f"[assembler] assembling...")

    content = assemble(args.dashboard, root)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    lines = content.count("\n")
    print(f"[assembler] written   : {out_path}")
    print(f"[assembler] lines     : {lines}")


if __name__ == "__main__":
    main()
