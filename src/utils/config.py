# src/utils/config.py
#
# Single source of truth for dashboard names and input file paths.
# Add a new dashboard here — nowhere else needs to change.
#
# Usage
# -----
#   from utils.config import DASHBOARDS, ALL_DASHBOARDS, ROOT
#
#   for name, paths in DASHBOARDS.items():
#       run(paths["semantic_model"], paths["report"])

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # utils/ -> src/ -> project root

DASHBOARDS: dict[str, dict] = {
    "risk-dash": {
        "semantic_model": ROOT / "input" / "Risk-Management-v4_Insights_v1.SemanticModel",
        "report":         ROOT / "input" / "Risk-Management-v4_Insights_v1.Report",
    },
    "pac-dash": {
        "semantic_model": ROOT / "input" / "PAC-v4_Insights_v1.SemanticModel",
        "report":         ROOT / "input" / "PAC-v4_Insights_v1.Report",
    },
}

# Load dynamically registered dashboards (created via the UI form)
_REGISTRY_PATH = ROOT / "prompt" / "dashboards_registry.json"
if _REGISTRY_PATH.exists():
    for _name, _cfg in json.loads(_REGISTRY_PATH.read_text(encoding="utf-8")).items():
        if _name not in DASHBOARDS:
            DASHBOARDS[_name] = {
                "semantic_model": ROOT / _cfg["semantic_model"],
                "report":         ROOT / _cfg["report"],
            }

ALL_DASHBOARDS: list[str] = list(DASHBOARDS.keys())
