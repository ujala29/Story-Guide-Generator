"""
Centralized output-path registry for Story Guide Generator.

Output folders mirror source-code module names — one folder per pipeline stage:

    output/dashboards/<dashboard>/
    ├── extraction/
    │   ├── extracted_schema.json
    │   └── schema_sections/
    │       ├── measures.json
    │       ├── measures_resolved.json
    │       ├── visuals.json
    │       ├── filters.json
    │       └── relationships.json
    ├── metric_dictionary/
    │   ├── final_measures.json
    │   ├── final_measures_with_llm.json
    │   ├── registry.json
    │   ├── run_report.json
    │   ├── metric_catalog.json / .md / .xlsx
    │   └── scope/
    ├── visual_wise/
    │   ├── enriched_pages/
    │   ├── l0_packets/
    │   ├── l1_packets/
    │   ├── l2_packets/
    │   └── story_guide/
    ├── filter_section/
    │   └── filter_guide/
    │       └── global_filters.md
    ├── dashboard_overview/
    │   └── dashboard_overview.md
    ├── page_wise/
    │   ├── widget_content/
    │   ├── funnel_map.json
    │   ├── funnel_connector.json
    │   └── final_story_guide.md
    └── glossary_faq/
        ├── glossary.md
        └── faq.md

Usage
-----
    from utils.paths import get_paths

    p = get_paths("risk-dash")

    p.measures_resolved          # extraction/schema_sections/measures_resolved.json
    p.final_measures_with_llm    # metric_dictionary/final_measures_with_llm.json
    p.enriched_pages_dir         # visual_wise/enriched_pages/
    p.l0_packets_dir             # visual_wise/l0_packets/
    p.widget_content_dir         # page_wise/widget_content/
    p.final_story_guide_md       # page_wise/final_story_guide.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# utils/ -> src/ -> project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


class DashboardPaths:
    """All output paths for one dashboard, organised by module folder."""

    def __init__(self, dashboard: str, project_root: Optional[Path] = None):
        self.dashboard = dashboard
        self.root      = project_root or _PROJECT_ROOT
        self.base      = self.root / "output" / "dashboards" / dashboard

    # ── Module-level roots ────────────────────────────────────────

    @property
    def extraction_dir(self) -> Path:
        return self.base / "extraction"

    @property
    def metric_dictionary_dir(self) -> Path:
        return self.base / "metric_dictionary"

    @property
    def visual_wise_dir(self) -> Path:
        return self.base / "visual_wise"

    @property
    def filter_section_dir(self) -> Path:
        return self.base / "filter_section"

    @property
    def dashboard_overview_dir(self) -> Path:
        return self.base / "dashboard_overview"

    @property
    def page_wise_dir(self) -> Path:
        return self.base / "page_wise"

    @property
    def glossary_faq_dir(self) -> Path:
        return self.base / "glossary_faq"

    # ── Backward-compat stage aliases ────────────────────────────
    # Existing code that used stage1_dir / stage2_dir / stage3_dir keeps working.

    @property
    def stage1_dir(self) -> Path:
        return self.extraction_dir

    @property
    def stage2_dir(self) -> Path:
        return self.metric_dictionary_dir

    @property
    def stage3_dir(self) -> Path:
        return self.page_wise_dir

    # ── Extraction ────────────────────────────────────────────────

    @property
    def stage1_schema(self) -> Path:
        return self.extraction_dir / "extracted_schema.json"

    @property
    def stage1_sections_dir(self) -> Path:
        return self.extraction_dir / "schema_sections"

    def stage1_section(self, name: str) -> Path:
        fname = name if name.endswith(".json") else f"{name}.json"
        return self.stage1_sections_dir / fname

    @property
    def measures_resolved(self) -> Path:
        return self.stage1_sections_dir / "measures_resolved.json"

    @property
    def visuals(self) -> Path:
        return self.stage1_sections_dir / "visuals.json"

    @property
    def filters(self) -> Path:
        return self.stage1_sections_dir / "filters.json"

    @property
    def relationships(self) -> Path:
        return self.stage1_sections_dir / "relationships.json"

    # ── Metric Dictionary ─────────────────────────────────────────

    @property
    def final_measures(self) -> Path:
        return self.metric_dictionary_dir / "final_measures.json"

    @property
    def final_measures_with_llm(self) -> Path:
        return self.metric_dictionary_dir / "final_measures_with_llm.json"

    @property
    def run_report(self) -> Path:
        return self.metric_dictionary_dir / "run_report.json"

    @property
    def registry(self) -> Path:
        return self.metric_dictionary_dir / "registry.json"

    @property
    def verification_report(self) -> Path:
        return self.metric_dictionary_dir / "verification_report.json"

    @property
    def metric_catalog_registry(self) -> Path:
        return self.metric_dictionary_dir / "metric_catalog_registry.json"

    @property
    def metric_catalog_json(self) -> Path:
        return self.metric_dictionary_dir / "metric_catalog.json"

    @property
    def metric_catalog_md(self) -> Path:
        return self.metric_dictionary_dir / "metric_catalog.md"

    @property
    def metric_catalog_xlsx(self) -> Path:
        return self.metric_dictionary_dir / "metric_catalog.xlsx"

    @property
    def step1_cleaned_measures(self) -> Path:
        return self.metric_dictionary_dir / "step1_cleaned_measures.json"

    # ── Visual Wise ───────────────────────────────────────────────

    @property
    def enriched_pages_dir(self) -> Path:
        return self.visual_wise_dir / "enriched_pages"

    def enriched_page(self, page_name: str) -> Path:
        fname = page_name if page_name.endswith(".json") else f"{page_name}.json"
        return self.enriched_pages_dir / fname

    @property
    def l0_packets_dir(self) -> Path:
        return self.visual_wise_dir / "l0_packets"

    @property
    def l1_packets_dir(self) -> Path:
        return self.visual_wise_dir / "l1_packets"

    @property
    def l2_packets_dir(self) -> Path:
        return self.visual_wise_dir / "l2_packets"

    @property
    def story_guide_dir(self) -> Path:
        return self.visual_wise_dir / "story_guide"

    # ── Filter Section ────────────────────────────────────────────

    @property
    def filter_guide_dir(self) -> Path:
        return self.filter_section_dir / "filter_guide"

    @property
    def filter_guide_md(self) -> Path:
        return self.filter_guide_dir / "global_filters.md"

    # ── Dashboard Overview ────────────────────────────────────────

    @property
    def dashboard_overview_md(self) -> Path:
        return self.dashboard_overview_dir / "dashboard_overview.md"

    # ── Page Wise ─────────────────────────────────────────────────

    @property
    def widget_content_dir(self) -> Path:
        return self.page_wise_dir / "widget_content"

    @property
    def funnel_map(self) -> Path:
        return self.page_wise_dir / "funnel_map.json"

    @property
    def funnel_connector(self) -> Path:
        return self.page_wise_dir / "funnel_connector.json"

    @property
    def final_story_guide_md(self) -> Path:
        return self.page_wise_dir / "final_story_guide.md"

    # ── Glossary & FAQ ────────────────────────────────────────────

    @property
    def glossary_md(self) -> Path:
        return self.glossary_faq_dir / "glossary.md"

    @property
    def faq_md(self) -> Path:
        return self.glossary_faq_dir / "faq.md"

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
            self.metric_dictionary_dir,
            self.enriched_pages_dir,
            self.filter_guide_dir,
            self.dashboard_overview_dir,
            self.l0_packets_dir,
            self.l1_packets_dir,
            self.l2_packets_dir,
            self.story_guide_dir,
            self.widget_content_dir,
            self.glossary_faq_dir,
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
        from utils.paths import get_config

        cfg = get_config()
        cfg.fixes               # prompt/fixes.json
        cfg.system_prompts_dir  # prompt/system_prompt/
        cfg.system_prompt("card.txt")
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
