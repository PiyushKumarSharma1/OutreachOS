"""FastAPI application entry point for OutreachOS dashboard + portal."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from outreachos.config import SETTINGS
from outreachos.dashboard.pages import router as pages_router
from outreachos.dashboard.portal import router as portal_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("OutreachOS API starting...")
    yield
    # Shutdown
    print("OutreachOS API shutting down...")


app = FastAPI(
    title="OutreachOS",
    description="Autonomous AI Outreach & Lead Generation Agency OS",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
static_dir = Path(__file__).parent / "dashboard" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Routes
app.include_router(pages_router)
app.include_router(portal_router)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.5.0"}


@app.get("/api/export/{name}.csv")
def export_campaign(name: str):
    """Export campaign leads as CSV."""
    from outreachos.pool.store import PoolStore
    from outreachos.orchestration.engine import Engine
    import io
    import csv
    from fastapi.responses import StreamingResponse
    
    engine = Engine(PoolStore(SETTINGS.db_path))
    c = engine.get_campaign(name)
    leads = engine.store.leads(c.id)
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Title", "Company", "Email", "Domain", "Stage", 
                     "Email Status", "Outreach", "Intent Score", "LinkedIn", "Trigger Signal"])
    for l in leads:
        writer.writerow([l.id, l.full_name, l.title, l.company, l.email, l.domain,
                        l.stage, l.email_status, l.outreach_state,
                        l.enrichment.get("intent_score", 0), l.linkedin_url,
                        l.trigger_signal])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={name}.csv"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)