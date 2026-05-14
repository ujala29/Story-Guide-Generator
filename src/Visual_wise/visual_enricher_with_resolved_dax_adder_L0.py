import json
import re
from pathlib import Path
from collections import defaultdict

def enrich_and_split(
    visuals_path: Path,
    out_dir: Path,
) -> dict:
    """
    Splits visuals by page and saves per-page JSON files.
    Saves: out_dir/<page>.json — one file per page
    Returns: { page_name: [visuals] }
    """

    with open(visuals_path, encoding="utf-8") as f:
        visuals = json.load(f)

    if isinstance(visuals, list):
        visual_list = visuals
    elif isinstance(visuals, dict) and "visuals" in visuals:
        visual_list = visuals["visuals"]
    else:
        raise ValueError(f"Unexpected visuals.json format in {visuals_path}")

    print(f"Visuals : {len(visual_list)}")

    grouped = defaultdict(list)
    for v in visual_list:
        grouped[v.get("page", "unknown")].append(v)

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Pages found     : {len(grouped)}")
    print(f"Saving pages to : {out_dir}\n")

    for page, page_visuals in grouped.items():
        safe_name = re.sub(r'[\\/*?:"<>|]', "", page.strip())
        safe_name = re.sub(r'\s+', "_", safe_name).lower()
        if not safe_name:
            safe_name = "unknown"

        file_path = out_dir / (safe_name + ".json")
        payload = {
            "page"        : page,
            "visual_count": len(page_visuals),
            "visuals"     : page_visuals,
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        type_counts = {}
        for v in page_visuals:
            t = v.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        type_str = ", ".join(f"{t}({n})" for t, n in type_counts.items())

        print(f"  ✅ [{len(page_visuals):3d} visuals] {file_path.name}")
        print(f"              {type_str}")

    print(f"\nDone. {len(grouped)} page files saved to {out_dir}")
    return dict(grouped)
