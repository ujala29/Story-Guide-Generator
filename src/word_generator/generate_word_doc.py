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

_CATALOG_DROP_COLS = {"Pattern", "Relationships"}

_DAX_NAME_RE = re.compile(
    r'^([A-Za-z][A-Za-z0-9 _\-]+?)\s*=\s*'
    r'(VAR|CALCULATE|DIVIDE|SUM|IF|SWITCH|COUNTROWS|FILTER)',
    re.IGNORECASE
)
_DAX_KEYWORDS = re.compile(
    r'^(VAR\s|RETURN|IF\(|SWITCH\(|CALCULATE\(|DIVIDE\(|SUM\(|'
    r'COUNTROWS\(|FILTER\(|ALL\(|KEEPFILTERS\(|FORMAT\(|ISBLANK\(|UNICHAR\()',
    re.IGNORECASE
)


# ── Helpers ───────────────────────────────────────────────────

def _drop_table_columns(content: str, drop: set) -> str:
    lines = content.splitlines(keepends=True)
    result, drop_indices, in_table = [], set(), False
    for line in lines:
        if not line.strip().startswith('|'):
            in_table, drop_indices = False, set()
            result.append(line)
            continue
        cells = line.strip().split('|')[1:-1]
        if not in_table:
            in_table = True
            drop_indices = {i for i, c in enumerate(cells) if c.strip() in drop}
        filtered = [c for i, c in enumerate(cells) if i not in drop_indices]
        result.append('| ' + ' | '.join(filtered) + ' |\n')
    return ''.join(result)


def _promote_dax_names(content: str) -> str:
    """
    Detect DAX measure name lines inside fenced code blocks and emit a
    ### **Name** heading before the block so it renders as a bold subheading.
    """
    lines = content.splitlines(keepends=True)
    result = []
    in_code = False
    code_lines = []
    fence = ''

    def flush(code_lines):
        if not code_lines:
            return []
        out = []
        for line in code_lines:
            text = line.rstrip('\n')
            if _DAX_NAME_RE.match(text) and not _DAX_KEYWORDS.match(text):
                name = text.split('=')[0].strip()
                out.append(f'\n### **{name}**\n\n')
                break
        out.append(fence + '\n')
        out.extend(code_lines)
        out.append(fence + '\n')
        return out

    for line in lines:
        stripped = line.rstrip('\n')
        if not in_code and stripped.startswith(('```', '~~~')):
            in_code = True
            fence = stripped[:3]
            code_lines = []
            continue
        if in_code and stripped.startswith(fence):
            in_code = False
            result.extend(flush(code_lines))
            code_lines = []
            fence = ''
            continue
        if in_code:
            code_lines.append(line)
        else:
            result.append(line)

    if code_lines:
        result.extend(flush(code_lines))

    return ''.join(result)


def read_file(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    content = re.sub(
        r'^\*\*Widget:\s*(.+?)\*\*\s*$',
        r'## \1',
        content,
        flags=re.MULTILINE,
    )
    content = _promote_dax_names(content)
    return content.rstrip('\n') + '\n\n'


# ── Sorting ───────────────────────────────────────────────────

def detect_visual_type(filename: str) -> str:
    filename = filename.lower()
    for vtype in VISUAL_PRIORITY:
        if vtype in filename:
            return vtype
    return "unknown"


def sort_visuals(files):
    return sorted(files, key=lambda f: (
        VISUAL_PRIORITY.get(detect_visual_type(f.name), 999),
        f.name.lower()
    ))


def sort_pages(page_dirs):
    priority_map = {name: idx for idx, name in enumerate(PAGE_ORDER)}
    return sorted(page_dirs, key=lambda p: (
        priority_map.get(p.name, 999), p.name.lower()
    ))


# ── Title page as raw OpenXML block ──────────────────────────

def _title_page_md(dashboard: str) -> str:
    """Centred bold title page rendered via raw OpenXML — no post-processing."""
    friendly = (
        dashboard.replace("-dash", " Dashboard")
                 .replace("-", " ")
                 .title()
    )
    spacers = '<w:p><w:pPr><w:jc w:val="center"/></w:pPr></w:p>\n' * 10
    title_xml = (
        f'<w:p>'
        f'<w:pPr><w:jc w:val="center"/></w:pPr>'
        f'<w:r>'
        f'<w:rPr>'
        f'<w:b/>'
        f'<w:sz w:val="56"/>'
        f'<w:szCs w:val="56"/>'
        f'<w:color w:val="000000"/>'
        f'</w:rPr>'
        f'<w:t>{friendly}</w:t>'
        f'</w:r>'
        f'</w:p>'
    )
    return f'```{{=openxml}}\n{spacers}{title_xml}\n```' + PAGE_BREAK


# ── Build combined markdown ───────────────────────────────────

def build_combined_md(dashboard: str = "risk-dash") -> tuple[str, int]:
    chunks = []
    story_file_count = 0
    stage3 = BASE_DIR / "output" / "dashboards" / dashboard / "stage3"

    chunks.append(_title_page_md(dashboard))

    overview_path = stage3 / "dashboard_overview.md"
    if overview_path.exists():
        chunks.append(read_file(overview_path))
        print("  + Dashboard Overview")
    else:
        print(f"  ⚠ Not found: {overview_path}")

    chunks.append(PAGE_BREAK)

    filters_path = stage3 / "global_filters.md"
    if filters_path.exists():
        chunks.append("# Global Filters\n\n")
        chunks.append(read_file(filters_path))
        print("  + Global Filters")
    else:
        print(f"  ⚠ Not found: {filters_path}")

    chunks.append(PAGE_BREAK)

    page_wise_path = stage3 / "page_wise_story.md"
    if page_wise_path.exists():
        chunks.append("# Page-Wise Story\n\n")
        chunks.append(read_file(page_wise_path))
        print("  + Page-wise story")
    else:
        print(f"  ⚠ Not found: {page_wise_path}")

    story_root = stage3 / "story_guide"
    if story_root.exists():
        page_dirs = sort_pages([p for p in story_root.iterdir() if p.is_dir()])
        for page_dir in page_dirs:
            chunks.append(PAGE_BREAK)
            chunks.append(f"# {page_dir.name.replace('_', ' ').title()}\n\n")
            chunks.append("## Visual Walkthrough\n\n")
            for vf in sort_visuals(list(page_dir.glob("*.md"))):
                chunks.append(read_file(vf))
                chunks.append("\n\n---\n\n")
                story_file_count += 1

    print(f"  + Story guide files : {story_file_count}")

    catalog_path = OUTPUT_ROOT / "dashboards" / dashboard / "stage2" / "metric_catalog.md"
    if catalog_path.exists():
        chunks.append(PAGE_BREAK)
        chunks.append(f"# Metric Catalog — {dashboard}\n\n")
        chunks.append(_drop_table_columns(read_file(catalog_path), _CATALOG_DROP_COLS))
        print("  + Metric Catalog")
    else:
        print(f"  ⚠ Not found: {catalog_path}")

    faq_path = stage3 / "faq.md"
    if faq_path.exists():
        chunks.append(PAGE_BREAK)
        chunks.append("# FAQ\n\n")
        chunks.append(read_file(faq_path))
        print("  + FAQ")

    glossary_path = stage3 / "glossary.md"
    if glossary_path.exists():
        chunks.append(PAGE_BREAK)
        chunks.append("# Glossary\n\n")
        chunks.append(read_file(glossary_path))
        print("  + Glossary")

    print(f"  Total chunks : {len(chunks)}")
    return "".join(chunks), story_file_count


# ── Minimal post-processing: table row colors only ────────────

def apply_table_row_colors(docx_path: str):
    """
    The only thing markdown/pandoc can't do: alternating row bg colors.
    Opens and saves the docx exactly once.
    """
    doc = Document(docx_path)
    for table in doc.tables:
        for row_idx, row in enumerate(table.rows):
            bg = (
                '2E2E2E' if row_idx == 0
                else ('FFFFFF' if row_idx % 2 == 1 else 'F5F5F5')
            )
            for cell in row.cells:
                tcPr = cell._tc.get_or_add_tcPr()
                for old in tcPr.findall(qn('w:shd')):
                    tcPr.remove(old)
                shd = OxmlElement('w:shd')
                shd.set(qn('w:val'), 'clear')
                shd.set(qn('w:color'), 'auto')
                shd.set(qn('w:fill'), bg)
                tcPr.append(shd)
                for para in cell.paragraphs:
                    for run in para.runs:
                        run.font.color.rgb = (
                            RGBColor(0xFF, 0xFF, 0xFF)
                            if row_idx == 0
                            else RGBColor(0x00, 0x00, 0x00)
                        )
    doc.save(docx_path)
    print(f"  ✓ Table row colors applied ({len(doc.tables)} tables)")


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate Story Guide Word document")
    parser.add_argument("--dashboard", type=str, default="risk-dash",
                        help="Dashboard name (e.g. risk-dash, pac-dash)")
    args = parser.parse_args()

    md, _ = build_combined_md(dashboard=args.dashboard)
    output_path = str(OUTPUT_ROOT / f"{args.dashboard}_story_guide.docx")

    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.md', encoding='utf-8', delete=False
    ) as tmp:
        tmp.write(md)
        tmp_path = tmp.name

    try:
        ref_doc = OUTPUT_ROOT / "reference.docx"
        extra_args = [
            "--standalone",
            "--wrap=none",
            "--columns=120",
            "--toc",           # TOC built by pandoc — free, instant
            "--toc-depth=2",   # H1 and H2
        ]
        if ref_doc.exists():
            extra_args.append(f"--reference-doc={ref_doc}")
            print(f"  Using reference.docx")
        else:
            print("  ⚠ reference.docx not found — run create_reference_doc.py first")

        print("  Converting markdown → docx...")
        pypandoc.convert_file(
            tmp_path, "docx",
            outputfile=output_path,
            extra_args=extra_args
        )

        print("  Applying table row colors...")
        apply_table_row_colors(output_path)

        print(f"\n✅ {output_path}")

    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    main()