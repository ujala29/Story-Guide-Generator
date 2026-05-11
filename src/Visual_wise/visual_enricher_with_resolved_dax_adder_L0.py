import json
import re
from pathlib import Path
from collections import defaultdict

def enrich_and_split(
    visuals_path: Path,
    resolved_path: Path,
    out_dir: Path,
) -> dict:
    """
    Enriches visuals with measure chains.
    Saves:
      1. visuals_enriched.json  — all visuals in one file
      2. out_dir/<page>.json    — one file per page
    Returns: { page_name: [visuals] }
    """

    # ── Load ─────────────────────────────────────────────────
    with open(visuals_path, encoding="utf-8") as f:
        visuals = json.load(f)
    with open(resolved_path, encoding="utf-8") as f:
        resolved = json.load(f)

    if isinstance(visuals, list):
        visual_list = visuals
    elif isinstance(visuals, dict) and "visuals" in visuals:
        visual_list = visuals["visuals"]
    else:
        raise ValueError(f"Unexpected visuals.json format in {visuals_path}")

    print(f"Visuals           : {len(visual_list)}")
    print(f"Resolved measures : {len(resolved)}")

    # ── Enrich ───────────────────────────────────────────────
    enriched_list = []
    not_found     = []

    for visual in visual_list:
        measure_chains = []

        for m_ref in visual.get("measures_used", []):
            measure_name = m_ref.split(".", 1)[1] if "." in m_ref else m_ref
            chain = resolved.get(measure_name)
            if chain:
                measure_chains.append(chain)
            else:
                not_found.append(f"{visual.get('title', '?')} → {measure_name}")
                measure_chains.append({
                    "measure_name"    : measure_name,
                    "table"           : "unknown",
                    "dax_summary"     : "Measure definition not found in resolved measures",
                    "business_meaning": "",
                    "depth"           : -1,
                    "depends_on"      : []
                })

        enriched_list.append({**visual, "measure_chains": measure_chains})

    if not_found:
        print(f"\n[WARN] {len(not_found)} measures not found in resolved:")
        for m in not_found:
            print(f"  - {m}")

    # ── Save 1: visuals_enriched.json ────────────────────────
    enriched_path = out_dir.parent / "visuals_enriched.json"
    enriched_path.parent.mkdir(parents=True, exist_ok=True)
    with open(enriched_path, "w", encoding="utf-8") as f:
        json.dump(enriched_list, f, indent=2, ensure_ascii=False)
    print(f"\nSaved enriched    : {enriched_path}")

    # ── Group by page ─────────────────────────────────────────
    grouped = defaultdict(list)
    for v in enriched_list:
        grouped[v.get("page", "unknown")].append(v)

    # ── Save 2: one file per page ─────────────────────────────
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Pages found       : {len(grouped)}")
    print(f"Saving pages to   : {out_dir}\n")

    for page, page_visuals in grouped.items():
        safe_name = re.sub(r'[\\/*?:"<>|]', "", page.strip())
        safe_name = re.sub(r'\s+', "_", safe_name).lower()
        if not safe_name:
            safe_name = "unknown"

        file_path = out_dir / (safe_name + ".json")
        payload   = {
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