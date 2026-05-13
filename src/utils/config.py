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

ALL_DASHBOARDS: list[str] = list(DASHBOARDS.keys())
