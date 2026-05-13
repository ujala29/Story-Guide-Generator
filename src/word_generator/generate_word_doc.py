import argparse
import os
import re
import tempfile
from pathlib import Path

import pypandoc
from docx import Document
from docx.shared import Pt, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
# from docx2pdf import convert


# ── Config ────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).resolve().parent.parent.parent
OUTPUT_ROOT = BASE_DIR / "output"

PAGE_BREAK = '\n\n```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```\n\n'

PAGE_ORDER = [
    "overview_ly",
    "risk_capture_potential",
    "data_availability",
]

VISUAL_PRIORITY = {
    "card": 1, "trend": 2, "line": 2,
    "bar": 3,  "column": 3,
    "table": 4, "matrix": 4,
    "donut": 5, "pie": 5,
}


def style_tables(docx_path: str):
    doc = Document(docx_path)
    for table in doc.tables:
        # full-width
        tbl = table._tbl
        tblPr = tbl.find(qn('w:tblPr'))
        if tblPr is None:
            tblPr = OxmlElement('w:tblPr')
            tbl.insert(0, tblPr)
        for old in tblPr.findall(qn('w:tblW')):
            tblPr.remove(old)
        tblW = OxmlElement('w:tblW')
        tblW.set(qn('w:w'), '5000')
        tblW.set(qn('w:type'), 'pct')
        tblPr.append(tblW)

        # auto-fit columns so no column gets crushed
        for old in tblPr.findall(qn('w:tblLayout')):
            tblPr.remove(old)
        tblLayout = OxmlElement('w:tblLayout')
        tblLayout.set(qn('w:type'), 'autofit')
        tblPr.append(tblLayout)

        for row_idx, row in enumerate(table.rows):
            is_header = row_idx == 0
            bg = '2E2E2E' if is_header else ('FFFFFF' if row_idx % 2 == 1 else 'F5F5F5')
            for cell in row.cells:
                tcPr = cell._tc.get_or_add_tcPr()
                # borders
                for old in tcPr.findall(qn('w:tcBorders')):
                    tcPr.remove(old)
                borders = OxmlElement('w:tcBorders')
                for edge in ('top', 'left', 'bottom', 'right'):
                    el = OxmlElement(f'w:{edge}')
                    el.set(qn('w:val'), 'single')
                    el.set(qn('w:sz'), '4')
                    el.set(qn('w:space'), '0')
                    el.set(qn('w:color'), 'CCCCCC')
                    borders.append(el)
                tcPr.append(borders)
                # background
                for old in tcPr.findall(qn('w:shd')):
                    tcPr.remove(old)
                shd = OxmlElement('w:shd')
                shd.set(qn('w:val'), 'clear')
                shd.set(qn('w:color'), 'auto')
                shd.set(qn('w:fill'), bg)
                tcPr.append(shd)
                # padding
                for old in tcPr.findall(qn('w:tcMar')):
                    tcPr.remove(old)
                tcMar = OxmlElement('w:tcMar')
                for side in ('top', 'left', 'bottom', 'right'):
                    m = OxmlElement(f'w:{side}')
                    m.set(qn('w:w'), str(6 * 20))
                    m.set(qn('w:type'), 'dxa')
                    tcMar.append(m)
                tcPr.append(tcMar)
                # font
                for para in cell.paragraphs:
                    for run in para.runs:
                        run.font.name = 'Calibri'
                        run.font.size = Pt(10)
                        if is_header:
                            run.font.bold = True
                            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                        else:
                            run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    doc.save(docx_path)
    print(f"  ✓ Table styling applied ({len(doc.tables)} tables)")


def read_file(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    content = re.sub(
        r'^\*\*Widget:\s*(.+?)\*\*\s*$',
        r'## \1',
        content,
        flags=re.MULTILINE,
    )
    return content.rstrip('\n') + '\n\n'


def sort_visuals(files):
    def priority(f):
        name = f.name.lower()
        for key, val in VISUAL_PRIORITY.items():
            if key in name:
                return val
        return 999
    return sorted(files, key=lambda f: (priority(f), f.name.lower()))


def sort_pages(page_dirs):
    idx = {name: i for i, name in enumerate(PAGE_ORDER)}
    return sorted(page_dirs, key=lambda p: (idx.get(p.name, 999), p.name.lower()))


# ── Build markdown ────────────────────────────────────────────

def build_combined_md(dashboard: str = "risk-dash") -> str:
    chunks = []
    dash_out = BASE_DIR / "output" / "dashboards" / dashboard
    dashboard_overview_dir = dash_out / "dashboard_overview"
    filter_section_dir     = dash_out / "filter_section"
    page_wise_dir          = dash_out / "page_wise"
    visual_wise_dir        = dash_out / "visual_wise"
    glossary_faq_dir       = dash_out / "glossary_faq"

    # 1. Dashboard Overview  (md file has its own heading — no injected title)
    p = dashboard_overview_dir / "dashboard_overview.md"
    if p.exists():
        chunks.append(read_file(p))
        print("  + Dashboard Overview")
    else:
        print(f"  ⚠ not found: {p}")

    # 2. Global Filters
    p = filter_section_dir / "global_filters.md"
    if p.exists():
        chunks.append(PAGE_BREAK)
        chunks.append("# Global Filters\n\n")
        chunks.append(read_file(p))
        print("  + Global Filters")
    else:
        print(f"  ⚠ not found: {p}")

    # 3. Page-Wise Story
    p = page_wise_dir / "page_wise_story.md"
    if p.exists():
        chunks.append(PAGE_BREAK)
        chunks.append("# Page-Wise Story\n\n")
        chunks.append(read_file(p))
        print("  + Page-Wise Story")
    else:
        print(f"  ⚠ not found: {p}")

    # 4. Visual-Wise  (card -> trend -> bar -> table -> donut, overview page first)
    story_root = visual_wise_dir / "story_guide"
    if story_root.exists():
        count = 0
        for page_dir in sort_pages([d for d in story_root.iterdir() if d.is_dir()]):
            chunks.append(PAGE_BREAK)
            chunks.append(f"# {page_dir.name.replace('_', ' ').title()}\n\n")
            for vf in sort_visuals(list(page_dir.glob("*.md"))):
                chunks.append(read_file(vf))
                chunks.append("\n\n---\n\n")
                count += 1
        print(f"  + Visual files : {count}")
    else:
        print(f"  ⚠ not found: {story_root}")


    # 6. FAQ
    p = glossary_faq_dir / "faq.md"
    if p.exists():
        chunks.append(PAGE_BREAK)
        chunks.append("# FAQ\n\n")
        chunks.append(read_file(p))
        print("  + FAQ")
    else:
        print(f"  ⚠ not found: {p}")

    # 7. Glossary
    p = glossary_faq_dir / "glossary.md"
    if p.exists():
        chunks.append(PAGE_BREAK)
        chunks.append("# Glossary\n\n")
        chunks.append(read_file(p))
        print("  + Glossary")
    else:
        print(f"  ⚠ not found: {p}")

    return "".join(chunks)


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate Story Guide Word document")
    parser.add_argument("--dashboard", default="risk-dash",
                        help="Dashboard name (e.g. risk-dash, pac-dash)")
    args = parser.parse_args()

    md = build_combined_md(dashboard=args.dashboard)
    output_path = str(OUTPUT_ROOT / f"{args.dashboard}_story_guide.docx")

    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.md', encoding='utf-8', delete=False
    ) as tmp:
        tmp.write(md)
        tmp_path = tmp.name

    try:
        extra_args = ["--standalone", "--wrap=none"]
        ref_doc = OUTPUT_ROOT / "reference.docx"
        if ref_doc.exists():
            extra_args.append(f"--reference-doc={ref_doc}")

        print("  Converting...")
        pypandoc.convert_file(tmp_path, "docx", outputfile=output_path, extra_args=extra_args)
        print("  Styling tables...")
        style_tables(output_path)
        print(f"  ✅ Word: {output_path}")

        # pdf_path = output_path.replace(".docx", ".pdf")
        # print("  Converting to PDF...")
        # convert(output_path, pdf_path)
        # print(f"  ✅ PDF : {pdf_path}")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    main()
