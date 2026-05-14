import json
from collections import Counter
from pathlib import Path

path = Path("output/dashboards/pac-dash/visual_wise/enriched_pages/main_page_ly.json")
data = json.loads(path.read_text(encoding="utf-8"))

visuals = data.get("visuals", [])
type_counts = Counter(v.get("type", "unknown") for v in visuals)

print(f"\nPage : {data.get('page')}")
print(f"Total visuals: {len(visuals)}\n")
print(f"{'Visual Type':<35} {'Count':>5}")
print("-" * 42)
for vtype, count in type_counts.most_common():
    print(f"{vtype:<35} {count:>5}")

# Detailed list for card-related types
CARD_KEYWORDS = {"card", "kpi", "yoy"}
card_types = [t for t in type_counts if any(k in t.lower() for k in CARD_KEYWORDS)]

if card_types:
    print(f"\n--- Card-like visuals detail ---")
    for vtype in card_types:
        entries = [v for v in visuals if v.get("type") == vtype]
        print(f"\n[{vtype}] ({len(entries)} visuals)")
        for v in entries:
            print(f"  id={v['id'][:12]}  title={v.get('title','')!r}  measures={v.get('measures_used', [])}")
