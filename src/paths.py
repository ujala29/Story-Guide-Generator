"""
Centralized output-path registry for Story Guide Generator.

Single source of truth — every stage imports from here instead of
constructing paths inline.

Usage
-----
    from paths import get_paths

    p = get_paths("risk-dash")

    # Stage 1
    p.stage1_dir                   # …/output/dashboards/risk-dash/stage1
    p.stage1_sections_dir          # …/stage1/schema_sections
    p.stage1_section("measures")   # …/schema_sections/measures.json
    p.measures_resolved            # …/schema_sections/measures_resolved.json

    # Stage 2
    p.stage2_dir
    p.final_measures_with_llm      # …/stage2/final_measures_with_llm.json
    p.registry                     # …/stage2/registry.json

    # Stage 3
    p.stage3_dir
    p.enriched_pages_dir           # …/stage3/enriched_pages
    p.l0_packets_dir               # …/stage3/l0_packets
    p.l1_packets_dir               # …/stage3/l1_packets
    p.l2_packets_dir               # …/stage3/l2_packets
    p.story_guide_dir              # …/stage3/story_guide
    p.filter_guide_dir             # …/stage3/filter_guide
    p.dashboard_overview_dir       # …/stage3/dashboard_overview

    # Helpers
    p.ensure(p.stage2_dir)         # mkdir -p
    p.ensure_all()                 # create every expected directory

Output tree produced
--------------------
output/dashboards/<dashboard>/
├── stage1/
│   ├── extracted_schema.json
│   └── schema_sections/
│       └── *.json  (measures, measures_resolved, relationships, visuals, filters, …)
├── stage2/
│   ├── final_measures.json
│   ├── final_measures_with_llm.json
│   ├── run_report.json
│   ├── registry.json
│   ├── verification_report.json
│   ├── metric_catalog.json / .md / .xlsx
│   └── step1_cleaned_measures.json
└── stage3/
    ├── enriched_pages/
    ├── filter_guide/
    ├── dashboard_overview/
    ├── l0_packets/
    ├── l1_packets/
    ├── l2_packets/
    ├── story_guide/
    └── widget_content/
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()


class DashboardPaths:
    """All output paths for one dashboard."""

    def __init__(self, dashboard: str, project_root: Optional[Path] = None):
        self.dashboard = dashboard
        self.root      = project_root or _PROJECT_ROOT
        self.base      = self.root / "output" / "dashboards" / dashboard

    # ── Stage roots ───────────────────────────────────────────────

    @property
    def stage1_dir(self) -> Path:
        return self.base / "stage1"

    @property
    def stage2_dir(self) -> Path:
        return self.base / "stage2"

    @property
    def stage3_dir(self) -> Path:
        return self.base / "stage3"

    # ── Stage 1 ───────────────────────────────────────────────────

    @property
    def stage1_schema(self) -> Path:
        return self.stage1_dir / "extracted_schema.json"

    @property
    def stage1_sections_dir(self) -> Path:
        return self.stage1_dir / "schema_sections"

    def stage1_section(self, name: str) -> Path:
        """e.g. p.stage1_section('measures_resolved') → …/schema_sections/measures_resolved.json"""
        fname = name if name.endswith(".json") else f"{name}.json"
        return self.stage1_sections_dir / fname

    @property
    def measures_resolved(self) -> Path:
        return self.stage1_section("measures_resolved")

    @property
    def visuals(self) -> Path:
        return self.stage1_section("visuals")

    @property
    def filters(self) -> Path:
        return self.stage1_section("filters")

    @property
    def relationships(self) -> Path:
        return self.stage1_section("relationships")

    # ── Stage 2 ───────────────────────────────────────────────────

    @property
    def final_measures(self) -> Path:
        return self.stage2_dir / "final_measures.json"

    @property
    def final_measures_with_llm(self) -> Path:
        return self.stage2_dir / "final_measures_with_llm.json"

    @property
    def run_report(self) -> Path:
        return self.stage2_dir / "run_report.json"

    @property
    def registry(self) -> Path:
        return self.stage2_dir / "registry.json"

    @property
    def verification_report(self) -> Path:
        return self.stage2_dir / "verification_report.json"

    @property
    def metric_catalog_registry(self) -> Path:
        return self.stage2_dir / "metric_catalog_registry.json"

    @property
    def metric_catalog_json(self) -> Path:
        return self.stage2_dir / "metric_catalog.json"

    @property
    def metric_catalog_md(self) -> Path:
        return self.stage2_dir / "metric_catalog.md"

    @property
    def metric_catalog_xlsx(self) -> Path:
        return self.stage2_dir / "metric_catalog.xlsx"

    @property
    def step1_cleaned_measures(self) -> Path:
        return self.stage2_dir / "step1_cleaned_measures.json"

    # ── Stage 3 ───────────────────────────────────────────────────

    @property
    def enriched_pages_dir(self) -> Path:
        return self.stage3_dir / "enriched_pages"

    def enriched_page(self, page_name: str) -> Path:
        fname = page_name if page_name.endswith(".json") else f"{page_name}.json"
        return self.enriched_pages_dir / fname

    @property
    def filter_guide_dir(self) -> Path:
        return self.stage3_dir / "filter_guide"

    @property
    def filter_guide_md(self) -> Path:
        return self.filter_guide_dir / "global_filters.md"

    @property
    def dashboard_overview_dir(self) -> Path:
        return self.stage3_dir / "dashboard_overview"

    @property
    def dashboard_overview_md(self) -> Path:
        return self.dashboard_overview_dir / "dashboard_overview.md"

    @property
    def l0_packets_dir(self) -> Path:
        return self.stage3_dir / "l0_packets"

    @property
    def l1_packets_dir(self) -> Path:
        return self.stage3_dir / "l1_packets"

    @property
    def l2_packets_dir(self) -> Path:
        return self.stage3_dir / "l2_packets"

    @property
    def story_guide_dir(self) -> Path:
        return self.stage3_dir / "story_guide"

    @property
    def funnel_map(self) -> Path:
        return self.stage3_dir / "funnel_map.json"

    @property
    def funnel_connector(self) -> Path:
        return self.stage3_dir / "funnel_connector.json"

    @property
    def widget_content_dir(self) -> Path:
        return self.stage3_dir / "widget_content"

    @property
    def final_story_guide_md(self) -> Path:
        return self.stage3_dir / "final_story_guide.md"

    # ── Helpers ───────────────────────────────────────────────────

    def ensure(self, *paths: Path) -> None:
        """mkdir -p. Paths with a file extension create their parent directory."""
        for p in paths:
            target = p if not p.suffix else p.parent
            target.mkdir(parents=True, exist_ok=True)

    def ensure_all(self) -> None:
        """Create every expected output directory for this dashboard."""
        for d in [
            self.stage1_sections_dir,
            self.stage2_dir,
            self.enriched_pages_dir,
            self.filter_guide_dir,
            self.dashboard_overview_dir,
            self.l0_packets_dir,
            self.l1_packets_dir,
            self.l2_packets_dir,
            self.story_guide_dir,
            self.widget_content_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return f"DashboardPaths({self.dashboard!r}, base={self.base})"


_cache: dict[str, DashboardPaths] = {}


def get_paths(dashboard: str, project_root: Optional[Path] = None) -> DashboardPaths:
    """Return (and cache) DashboardPaths for the given dashboard name."""
    key = f"{dashboard}:{project_root}"
    if key not in _cache:
        _cache[key] = DashboardPaths(dashboard, project_root)
    return _cache[key]


# ── Project-level config / input paths ───────────────────────────────────────

class ConfigPaths:
    """
    Paths to project-level config and prompt files (not dashboard-specific).

    Usage
    -----
        from paths import get_config

        cfg = get_config()
        cfg.fixes               # prompt/fixes.json
        cfg.glossary            # prompt/glossary.json
        cfg.system_prompts_dir  # prompt/system_prompt/
        cfg.system_prompt("card.txt")  # prompt/system_prompt/card.txt
        cfg.prompt_dir          # prompt/  (dashboard sub-dirs live here)
        cfg.pbi_connection      # prompt/pbi_connection_config.json
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.root       = project_root or _PROJECT_ROOT
        self.prompt_dir = self.root / "prompt"

    @property
    def fixes(self) -> Path:
        return self.prompt_dir / "fixes.json"

    @property
    def glossary(self) -> Path:
        return self.prompt_dir / "glossary.json"

    @property
    def system_prompts_dir(self) -> Path:
        return self.prompt_dir / "system_prompt"

    def system_prompt(self, filename: str) -> Path:
        return self.system_prompts_dir / filename

    @property
    def pbi_connection(self) -> Path:
        return self.prompt_dir / "pbi_connection_config.json"

    @property
    def dashboard_config(self) -> Path:
        return self.prompt_dir / "dashboard_config.json"

    def dashboard_prompt_dir(self, dashboard: str) -> Path:
        """e.g. get_config().dashboard_prompt_dir('risk-dash') → prompt/risk-dash/"""
        return self.prompt_dir / dashboard

    def __repr__(self) -> str:
        return f"ConfigPaths(prompt_dir={self.prompt_dir})"


_cfg_cache: dict[str, ConfigPaths] = {}


def get_config(project_root: Optional[Path] = None) -> ConfigPaths:
    """Return (and cache) the project-level ConfigPaths."""
    key = str(project_root)
    if key not in _cfg_cache:
        _cfg_cache[key] = ConfigPaths(project_root)
    return _cfg_cache[key]
