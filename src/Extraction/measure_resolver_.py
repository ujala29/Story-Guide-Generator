"""
Step 1: Measure Dependency Resolver
Input : measures[] from extracted_schema.json
Output: per measure -> resolved object with chain_string + exact dax
"""

import json
import sys
from pathlib import Path

# -- Path resolution --
# Script lives at:     L5assistant/pipeline/stage1/measure_resolver_.py
# measures.json is at: L5assistant/output/schema_sections/measures.json
SCRIPT_DIR            = Path(__file__).parent.resolve()
DEFAULT_MEASURES_PATH = SCRIPT_DIR.parent.parent / "output" / "dashboards" / "risk-dash" / "stage1" / "schema_sections" / "measures.json"


# ─────────────────────────────────────────────
# 1. LOAD
# ─────────────────────────────────────────────

def load_measures(path: str) -> dict:
    """Load measures JSON and return a lookup dict: name -> measure_object"""
    with open(path) as f:
        data = json.load(f)

    if isinstance(data, list):
        measures = data
    elif isinstance(data, dict) and "measures" in data:
        measures = data["measures"]
    else:
        raise ValueError("Unrecognized JSON format. Expected list or dict with 'measures' key.")

    return {m["name"]: m for m in measures}


# ─────────────────────────────────────────────
# 2. RECURSIVE CHAIN BUILDER
# ─────────────────────────────────────────────

def build_chain(name: str, lookup: dict, visited: set = None) -> dict:
    if visited is None:
        visited = set()

    if name in visited:
        return {"measure_name": name, "note": "circular reference", "depends_on": []}

    visited = visited | {name}

    measure = lookup.get(name)
    if not measure:
        return {
            "measure_name": name,
            "table": "unknown",
            "dax": "",
            "depth": -1,
            "depends_on": []
        }

    deps = measure.get("depends_on", [])

    return {
        "measure_name": name,
        "table": measure.get("table", ""),
        "dax": measure.get("dax", ""),
        "depth": measure.get("depth", 0),
        "is_leaf": measure.get("is_leaf", True),
        "referenced_columns": measure.get("referenced_columns", []),
        "depends_on": [build_chain(dep, lookup, visited) for dep in deps]
    }


# ─────────────────────────────────────────────
# 4. FLAT CHAIN STRING (for visual packet)
# ─────────────────────────────────────────────

def chain_to_string(chain: dict, indent: int = 0) -> str:
    prefix  = "  " * indent
    name  = chain["measure_name"]
    dax   = chain.get("dax", "")
    cols  = chain.get("referenced_columns", [])
    deps  = chain.get("depends_on", [])
    depth = chain.get("depth", 0)

    lines = []

    if indent == 0:
        lines.append(f"{name}  [depth: {depth}]")
        lines.append(f"  -> {dax}")
    else:
        lines.append(f"{prefix}L-- {name}")
        lines.append(f"{prefix}     -> {dax}")

    if cols and chain.get("is_leaf", True):
        lines.append(f"{prefix}     -> raw columns: {', '.join(cols)}")

    for dep in deps:
        lines.append(chain_to_string(dep, indent + 1))

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 5. MAIN RESOLVER
# ─────────────────────────────────────────────

def resolve_all(measures_path: str) -> dict:
    lookup = load_measures(measures_path)
    resolved = {}
    for name in lookup:
        chain = build_chain(name, lookup)
        resolved[name] = {
            "chain": chain,
            "chain_string": chain_to_string(chain)
        }
    return resolved


# ─────────────────────────────────────────────
# 6. CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":

    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = DEFAULT_MEASURES_PATH

    if not path.exists():
        print(f"ERROR: File not found: {path}")
        print(f"Expected at  : {DEFAULT_MEASURES_PATH}")
        print(f"Or run as    : python {Path(__file__).name} <path_to_measures.json>")
        sys.exit(1)

    print(f"Loading: {path}")
    resolved = resolve_all(str(path))
    print(f"Resolved {len(resolved)} measures")

    # Sample output
    sample_names = [
        "#Members YoY Color",
        "Documented risk MoM Card",
        "Gap to potential risk",
        "Potential risk PY",
    ]

    for name in sample_names:
        if name in resolved:
            print("=" * 60)
            print(resolved[name]["chain_string"])
            print()

    # Save next to measures.json
    out_path = path.parent / "measures_resolved.json"
    with open(out_path, "w") as f:
        json.dump({k: v["chain"] for k, v in resolved.items()}, f, indent=2)
    print(f"\nSaved: {out_path}")