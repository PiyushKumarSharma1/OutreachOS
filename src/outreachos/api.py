"""OutreachOS API v2 + Ops Cockpit + Client Portal.

Run: python -m outreachos.api  → http://localhost:8000/dashboard
HTML: /dashboard /campaign/{name} /approvals /portal
JSON API: /api/* (API-key auth for remote callers; localhost trusted)
MCP: python -m outreachos.mcp_server (stdio)
"""
from __future__ import annotations

import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import SETTINGS
from .pool.store import PoolStore
from .orchestration.engine import Engine
from .exports import export_campaign_csv
from .tenancy import TenancyManager
from .webhooks import EventBus
from .compliance import ComplianceManager
from .dashboard.pages import router as pages_router, _recent_events
from .dashboard.portal import router as portal_router

STATIC_DIR = os.path.join(os.path.dirname(__file__), "dashboard", "static")

app = FastAPI(title="OutreachOS", version="0.4.0",
              description="Autonomous AI Outreach OS — cockpit /dashboard · portal /portal · MCP stdio")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(pages_router)
app.include_router(portal_router)

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
OPEN_API_PATHS = {"/api/events/recent", "/api/health", "/health"}


@app.middleware("http")
async def security_and_auth(request: Request, call_next):
    path = request.url.path
    host = (request.client.host if request.client else "") or ""
    is_local = host in LOCAL_HOSTS
    api_key = request.headers.get("X-API-Key", "")

    if path.startswith("/api/") and path not in OPEN_API_PATHS and not is_local:
        auth = TenancyManager(PoolStore(SETTINGS.db_path)).verify(api_key, "read")
        if not auth:
            return JSONResponse({"error": "valid X-API-Key required"},
                                status_code=401,
                                headers={"WWW-Authenticate": "ApiKey"})

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
    client_id: str = ""


class ClientIn(BaseModel):
    name: str
    plan: str = "standard"


class WebhookIn(BaseModel):
    url: str
    events: list[str] = ["*"]
    secret: str | None = None


class SuppressIn(BaseModel):
    email: str
    reason: str = "manual"


def _engine() -> Engine:
    return Engine(PoolStore(SETTINGS.db_path))


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.4.0",
            "provider_mode": SETTINGS.provider_mode, "llm_mode": SETTINGS.llm_mode}


@app.get("/api/events/recent")
def recent_events(limit: int = 18):
    store = PoolStore(SETTINGS.db_path)
    return _recent_events(store, min(limit, 100))


# ---- Tenancy ----

@app.post("/api/clients")
def create_client(c: ClientIn):
    tm = TenancyManager(PoolStore(SETTINGS.db_path))
    client = tm.create_client(c.name, c.plan)
    key = tm.create_api_key(client["id"])
    return {"client": client, "api_key": key}


@app.get("/api/clients/{client_id}/keys")
def list_keys(client_id: str):
    return TenancyManager(PoolStore(SETTINGS.db_path)).list_keys(client_id)


# ---- Campaigns ----

@app.post("/api/campaigns")
def create_campaign(c: CampaignIn):
    eng = _engine()
    camp = eng.create_campaign(c.name, icp=c.icp, offer=c.offer,
                               case_studies=c.case_studies, client_id=c.client_id)
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
    with open(result["path"], newline="", encoding="utf-8") as f:
        content = f.read()
    return StreamingResponse(io.StringIO(content), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


# ---- Infrastructure & deliverability ----

@app.get("/api/infra/inboxes")
def inbox_health():
    eng = _engine()
    return eng.monitor.dashboard()


@app.post("/api/infra/seed")
def infra_seed():
    eng = _engine()
    return {"seeded": eng.infra.seed_defaults()}


# ---- Webhooks ----

@app.post("/api/webhooks")
def create_webhook(w: WebhookIn):
    bus = EventBus(PoolStore(SETTINGS.db_path))
    sub = bus.subscribe(w.url, w.events, w.secret)
    return {"id": sub["id"], "url": sub["url"], "secret": sub["secret"],
            "events": sub["events"]}


@app.get("/api/webhooks/{sub_id}/deliveries")
def webhook_deliveries(sub_id: str):
    bus = EventBus(PoolStore(SETTINGS.db_path))
    return [d for d in bus.delivery_log(100) if d["subscription_id"] == sub_id]


@app.post("/api/webhooks/process")
def webhooks_process(limit: int = 20):
    return EventBus(PoolStore(SETTINGS.db_path)).process_due(min(limit, 100))


# ---- Compliance ----

@app.post("/api/suppressions")
def add_suppression(s: SuppressIn):
    cm = ComplianceManager(PoolStore(SETTINGS.db_path))
    cm.suppress(s.email, s.reason, source="api")
    return {"suppressed": s.email}


@app.get("/api/suppressions")
def list_suppressions():
    cm = ComplianceManager(PoolStore(SETTINGS.db_path))
    return cm.list_suppressions()


@app.get("/u/{token}")
def unsubscribe(token: str, email: str, campaign: str):
    cm = ComplianceManager(PoolStore(SETTINGS.db_path))
    ok = cm.process_unsubscribe(token, email, campaign)
    return JSONResponse({"unsubscribed": ok}, status_code=200 if ok else 400)


# ---- Approvals ----

@app.get("/api/approvals/count")
def approvals_count():
    eng = _engine()
    n = 0
    for c in eng.active_campaigns():
        for l in eng.store.leads(c.id, outreach_state="replied_negative"):
            n += sum(1 for note in l.notes
                     if note.get("type") == "draft_response"
                     and note.get("status") == "needs_human_approval")
    return {"pending": n}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
