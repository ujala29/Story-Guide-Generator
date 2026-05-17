from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from api.models import DashboardConfig, DashboardInfo, DashboardRegister

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
from utils.config import DASHBOARDS, ROOT

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])

_DASHBOARD_CONFIG_PATH = ROOT / "prompt" / "dashboard_config.json"
_REGISTRY_PATH = ROOT / "prompt" / "dashboards_registry.json"


@router.get("/config")
def get_dashboard_config():
    if not _DASHBOARD_CONFIG_PATH.exists():
        return {}
    return json.loads(_DASHBOARD_CONFIG_PATH.read_text(encoding="utf-8"))


@router.patch("/config/{dashboard}")
def update_dashboard_config(dashboard: str, config: DashboardConfig):
    data: dict = {}
    if _DASHBOARD_CONFIG_PATH.exists():
        data = json.loads(_DASHBOARD_CONFIG_PATH.read_text(encoding="utf-8"))
    data[dashboard] = config.model_dump()
    _DASHBOARD_CONFIG_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"ok": True}


@router.post("/setup")
async def setup_dashboard(
    name: str = Form(...),
    display_name: str = Form(...),
    domain: str = Form(""),
    users: str = Form(""),
    common_pain_points: str = Form("[]"),
    sm_paths: str = Form(...),
    sm_files: List[UploadFile] = File(...),
    rp_paths: str = Form(...),
    rp_files: List[UploadFile] = File(...),
):
    """Upload .SemanticModel and .Report folder contents from user's computer."""
    name = name.strip()
    if not re.match(r"^[a-z0-9-]+$", name):
        raise HTTPException(status_code=400, detail="Dashboard ID must be lowercase letters, numbers, or hyphens")

    sm_path_list: list[str] = json.loads(sm_paths)
    rp_path_list: list[str] = json.loads(rp_paths)

    if not sm_path_list or not rp_path_list:
        raise HTTPException(status_code=400, detail="Both SemanticModel and Report folders are required")

    input_dir = ROOT / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    for upload, rel_path in zip(sm_files, sm_path_list):
        dest = input_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await upload.read())

    for upload, rel_path in zip(rp_files, rp_path_list):
        dest = input_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await upload.read())

    sm_folder = sm_path_list[0].split("/")[0]
    rp_folder = rp_path_list[0].split("/")[0]

    registry: dict = {}
    if _REGISTRY_PATH.exists():
        registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    registry[name] = {
        "semantic_model": f"input/{sm_folder}",
        "report": f"input/{rp_folder}",
    }
    _REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")

    pain_pts: list = json.loads(common_pain_points)
    config_data: dict = {}
    if _DASHBOARD_CONFIG_PATH.exists():
        config_data = json.loads(_DASHBOARD_CONFIG_PATH.read_text(encoding="utf-8"))
    config_data[name] = {
        "display_name": display_name.strip(),
        "domain": domain.strip(),
        "users": users.strip(),
        "common_pain_points": pain_pts,
    }
    _DASHBOARD_CONFIG_PATH.write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {"ok": True, "dashboard": name}


@router.post("/register")
def register_dashboard(req: DashboardRegister):
    """Register a new dashboard from input/ folder contents and save its config."""
    # Validate that input folders exist
    sm_path = ROOT / "input" / req.semantic_model_name
    rp_path = ROOT / "input" / req.report_name
    if not sm_path.exists():
        raise HTTPException(status_code=400, detail=f"SemanticModel folder not found: {req.semantic_model_name}")
    if not rp_path.exists():
        raise HTTPException(status_code=400, detail=f"Report folder not found: {req.report_name}")

    # Save to registry
    registry: dict = {}
    if _REGISTRY_PATH.exists():
        registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    registry[req.name] = {
        "semantic_model": f"input/{req.semantic_model_name}",
        "report": f"input/{req.report_name}",
    }
    _REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")

    # Save dashboard config
    config_data: dict = {}
    if _DASHBOARD_CONFIG_PATH.exists():
        config_data = json.loads(_DASHBOARD_CONFIG_PATH.read_text(encoding="utf-8"))
    config_data[req.name] = {
        "display_name": req.display_name,
        "domain": req.domain,
        "users": req.users,
        "common_pain_points": req.common_pain_points,
    }
    _DASHBOARD_CONFIG_PATH.write_text(
        json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {"ok": True, "dashboard": req.name}


@router.get("", response_model=list[DashboardInfo])
def list_dashboards():
    result = []
    for name, cfg in DASHBOARDS.items():
        docx = ROOT / "output" / f"{name}_story_guide.docx"
        result.append(DashboardInfo(
            name=name,
            label=name.replace("-", " ").title(),
            has_output=docx.exists(),
            semantic_model_name=Path(cfg["semantic_model"]).name,
            report_name=Path(cfg["report"]).name,
        ))
    return result
