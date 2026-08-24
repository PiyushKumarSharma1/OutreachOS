"""Optional REST API. Requires: pip install fastapi uvicorn"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from .config import SETTINGS
from .pool.store import PoolStore
from .orchestration.engine import Engine

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError:
    print("API extras missing. Run: pip install fastapi uvicorn")
    sys.exit(1)


app = FastAPI(title="OutreachOS API", version="0.1.0",
              description="Autonomous AI Outreach & Lead Generation OS")


class CampaignIn(BaseModel):
    name: str
    icp: dict = {}
    offer: str = ""
    case_studies: list[dict] = []


def _engine() -> Engine:
    return Engine(PoolStore(SETTINGS.db_path))


@app.get("/health")
def health():
    return {"status": "ok", "provider_mode": SETTINGS.provider_mode, "llm_mode": SETTINGS.llm_mode}


@app.post("/campaigns")
def create_campaign(c: CampaignIn):
    eng = _engine()
    camp = eng.create_campaign(c.name, icp=c.icp, offer=c.offer, case_studies=c.case_studies)
    return {"id": camp.id, "name": camp.name}


@app.post("/campaigns/{name}/hunt")
def hunt(name: str, limit: int = 50):
    try:
        return _engine().hunt(name, limit)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/campaigns/{name}/run")
def run_pipeline(name: str, limit: int = 50):
    try:
        return _engine().full_cycle(name, limit)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/campaigns/{name}/dispatch")
def dispatch(name: str):
    try:
        return _engine().dispatch(name)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.post("/campaigns/{name}/replies")
def replies(name: str):
    try:
        return _engine().process_replies(name)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/campaigns/{name}/stats")
def stats(name: str):
    try:
        return _engine().stats(name)
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/leads/{lead_id}")
def lead_timeline(lead_id: str):
    tl = _engine().lead_timeline(lead_id)
    if not tl["lead"]:
        raise HTTPException(404, "lead not found")
    return tl


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
