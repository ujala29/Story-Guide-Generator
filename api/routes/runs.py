from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from api.models import RunRequest, RunSummary
from api.store import RunState, all_runs, create_run, get_run

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from utils.config import ALL_DASHBOARDS

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _run_to_summary(run: RunState) -> RunSummary:
    return RunSummary(
        id=run.id,
        dashboard=run.dashboard,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        return_code=run.return_code,
        options=run.options,
    )


def _is_valid_dashboard(name: str) -> bool:
    """Check hardcoded dashboards AND the dynamic registry."""
    if name in ALL_DASHBOARDS:
        return True
    registry = _PROJECT_ROOT / "prompt" / "dashboards_registry.json"
    if registry.exists():
        try:
            return name in json.loads(registry.read_text(encoding="utf-8"))
        except Exception:
            pass
    return False


def _run_pipeline_sync(run: RunState, cmd: list[str]) -> None:
    """
    Runs the pipeline synchronously in a thread-pool executor.
    Avoids asyncio.create_subprocess_exec which fails on Windows
    when uvicorn uses a SelectorEventLoop (NotImplementedError).
    """
    run.status = "running"
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=str(_PROJECT_ROOT),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        for line in proc.stdout:
            run.logs.append(line.rstrip())
        proc.wait()
        run.return_code = proc.returncode
        run.status = "completed" if proc.returncode == 0 else "failed"
    except Exception as exc:
        run.logs.append(f"[ERROR] {type(exc).__name__}: {exc}")
        run.status = "failed"
    finally:
        run.finished_at = datetime.now(timezone.utc).isoformat()


async def _execute_pipeline(run: RunState) -> None:
    cmd = [sys.executable, str(_PROJECT_ROOT / "main.py"), "--dashboard", run.dashboard]

    opts = run.options
    if opts.get("from_stage"):
        cmd += ["--from-stage", str(opts["from_stage"])]
    if opts.get("force"):
        cmd.append("--force")
    if opts.get("dry_run"):
        cmd.append("--dry-run")
    if opts.get("skip_verifier"):
        cmd.append("--skip-verifier")
    if opts.get("skip_catalog"):
        cmd.append("--skip-catalog")
    if opts.get("no_test"):
        cmd.append("--no-test")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_pipeline_sync, run, cmd)


async def _log_stream(run: RunState) -> AsyncGenerator[str, None]:
    sent = 0
    while True:
        while sent < len(run.logs):
            yield f"data: {run.logs[sent]}\n\n"
            sent += 1

        if run.status in ("completed", "failed"):
            yield "data: [DONE]\n\n"
            break

        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("", response_model=RunSummary, status_code=201)
async def start_run(req: RunRequest, background_tasks: BackgroundTasks):
    if not _is_valid_dashboard(req.dashboard):
        raise HTTPException(status_code=400, detail=f"Unknown dashboard: {req.dashboard}")

    options = req.model_dump(exclude={"dashboard"})
    run = create_run(req.dashboard, options)
    background_tasks.add_task(_execute_pipeline, run)
    return _run_to_summary(run)


@router.get("", response_model=list[RunSummary])
def list_runs():
    return [_run_to_summary(r) for r in all_runs()]


@router.get("/{run_id}", response_model=RunSummary)
def get_run_status(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_summary(run)


@router.get("/{run_id}/logs")
async def stream_logs(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return StreamingResponse(
        _log_stream(run),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{run_id}/download")
def download_output(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "completed":
        raise HTTPException(status_code=400, detail="Run not completed yet")

    docx = _PROJECT_ROOT / "output" / f"{run.dashboard}_story_guide.docx"
    if not docx.exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        path=str(docx),
        filename=f"{run.dashboard}_story_guide.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
