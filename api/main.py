from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import dashboards, runs

app = FastAPI(title="Story Guide Generator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboards.router)
app.include_router(runs.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
