"""OutreachOS API + Ops Cockpit.

Run: python -m outreachos.api  → http://localhost:8000/dashboard
JSON API under /api/*, HTML cockpit under /*.
"""
from __future__ import annotations

import csv
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import SETTINGS
from .pool.store import PoolStore
from .orchestration.engine import Engine
from .exports import export_campaign_csv
from .dashboard.pages import router as pages_router, _recent_events

STATIC_DIR = os.path.join(os.path.dirname(__file__), "dashboard", "static")

app = FastAPI(title="OutreachOS", version="0.2.0",
              description="Autonomous AI Outreach & Lead Generation OS — ops cockpit at /dashboard")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(pages_router)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'"
    )
    return response


class CampaignIn(BaseModel):
    name: str
    icp: dict = {}
    offer: str = ""
    case_studies: list[dict] = []


def _engine() -> Engine:
    return Engine(PoolStore(SETTINGS.db_path))


@app.get("/health")
def health():
    return {"status": "ok", "provider_mode": SETTINGS.provider_mode,
            "llm_mode": SETTINGS.llm_mode}


@app.get("/api/events/recent")
def recent_events(limit: int = 18):
    store = PoolStore(SETTINGS.db_path)
    return _recent_events(store, min(limit, 100))


@app.post("/api/campaigns")
def create_campaign(c: CampaignIn):
    eng = _engine()
    camp = eng.create_campaign(c.name, icp=c.icp, offer=c.offer, case_studies=c.case_studies)
    return {"id": camp.id, "name": camp.name}


@app.get("/api/campaigns/{name}/stats")
def stats(name: str):
    try:
        return _engine().stats(name)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/api/campaigns/{name}/export.csv")
def export_csv(name: str):
    eng = _engine()
    result = export_campaign_csv(eng.store, name, out_dir="./exports")
    if "error" in result:
        raise HTTPException(404, result["error"])
    path = result["path"]
    with open(path, newline="", encoding="utf-8") as f:
        content = f.read()
    buf = io.StringIO(content)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
