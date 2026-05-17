from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class RunRequest(BaseModel):
    dashboard: str
    from_stage: Optional[int] = None
    force: bool = False
    dry_run: bool = False
    skip_verifier: bool = False
    skip_catalog: bool = False
    no_test: bool = False


class RunSummary(BaseModel):
    id: str
    dashboard: str
    status: str           # pending | running | completed | failed
    started_at: str
    finished_at: Optional[str] = None
    return_code: Optional[int] = None
    options: dict


class DashboardInfo(BaseModel):
    name: str
    label: str
    has_output: bool
    semantic_model_name: str = ""
    report_name: str = ""


class DashboardConfig(BaseModel):
    display_name: str
    domain: str
    users: str
    common_pain_points: list[str]


class DashboardRegister(BaseModel):
    name: str
    display_name: str
    domain: str
    users: str
    common_pain_points: list[str]
    semantic_model_name: str
    report_name: str
