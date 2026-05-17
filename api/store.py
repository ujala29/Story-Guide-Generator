from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RunState:
    id: str
    dashboard: str
    options: dict
    status: str = "pending"          # pending | running | completed | failed
    logs: list[str] = field(default_factory=list)
    new_log_event: asyncio.Event = field(default_factory=asyncio.Event)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: Optional[str] = None
    return_code: Optional[int] = None


_runs: dict[str, RunState] = {}


def create_run(dashboard: str, options: dict) -> RunState:
    run_id = str(uuid.uuid4())[:8]
    run = RunState(id=run_id, dashboard=dashboard, options=options)
    _runs[run_id] = run
    return run


def get_run(run_id: str) -> Optional[RunState]:
    return _runs.get(run_id)


def all_runs() -> list[RunState]:
    return sorted(_runs.values(), key=lambda r: r.started_at, reverse=True)
