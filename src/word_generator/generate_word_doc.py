import argparse
import os
import re
import tempfile
from pathlib import Path

import pypandoc


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
    stage3 = BASE_DIR / "output" / "dashboards" / dashboard / "stage3"

    # 1. Dashboard Overview  (md file has its own heading — no injected title)
    p = stage3 / "dashboard_overview.md"
    if p.exists():
        chunks.append(read_file(p))
        print("  + Dashboard Overview")
    else:
        print(f"  ⚠ not found: {p}")

    # 2. Global Filters
    p = stage3 / "global_filters.md"
    if p.exists():
        chunks.append(PAGE_BREAK)
        chunks.append("# Global Filters\n\n")
        chunks.append(read_file(p))
        print("  + Global Filters")
    else:
        print(f"  ⚠ not found: {p}")

    # 3. Page-Wise Story
    p = stage3 / "page_wise_story.md"
    if p.exists():
        chunks.append(PAGE_BREAK)
        chunks.append("# Page-Wise Story\n\n")
        chunks.append(read_file(p))
        print("  + Page-Wise Story")
    else:
        print(f"  ⚠ not found: {p}")

    # 4. Visual-Wise  (card → trend → bar → table → donut, overview page first)
    story_root = stage3 / "story_guide"
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

    # 5. Metric Catalog — skipped (large table causes pandoc to hang;
    #    available separately at stage2/metric_catalog.md)

    # 6. FAQ
    p = stage3 / "faq.md"
    if p.exists():
        chunks.append(PAGE_BREAK)
        chunks.append("# FAQ\n\n")
        chunks.append(read_file(p))
        print("  + FAQ")
    else:
        print(f"  ⚠ not found: {p}")

    # 7. Glossary
    p = stage3 / "glossary.md"
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
        print(f"\n✅ {output_path}")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    main()
