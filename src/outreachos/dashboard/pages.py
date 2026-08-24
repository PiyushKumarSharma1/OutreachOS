"""Server-rendered ops cockpit pages."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import SETTINGS
from ..pool.models import STAGES, EMAIL_STATUSES, OUTREACH_STATES
from ..orchestration.engine import Engine
from ..pool.store import PoolStore

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(include_in_schema=False)

STEPS = [
    {"id": "hunt", "label": "Hunt Leads", "icon": "◈"},
    {"id": "qualify", "label": "Verify Waterfall", "icon": "🛡"},
    {"id": "enrich", "label": "Profile Angles", "icon": "◉"},
    {"id": "copy", "label": "Write Sequences", "icon": "✎"},
    {"id": "dispatch", "label": "Dispatch Email+LI", "icon": "⇨"},
    {"id": "replies", "label": "Process Replies", "icon": "↩"},
]

FUNNEL_ORDER = ["raw", "hunted", "verified", "profiled", "written", "dispatched", "engaged", "booked", "dropped"]


def _ago(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        secs = max((datetime.now(timezone.utc) - dt).total_seconds(), 0)
        if secs < 60: return f"{int(secs)}s"
        if secs < 3600: return f"{int(secs // 60)}m"
        if secs < 86400: return f"{int(secs // 3600)}h"
        return f"{int(secs // 86400)}d"
    except Exception:
        return "—"


def _render(request: Request, name: str, **ctx):
    ctx.setdefault("provider_mode", SETTINGS.provider_mode)
    ctx.setdefault("llm_mode", SETTINGS.llm_mode)
    ctx.setdefault("provider_live", SETTINGS.provider_mode == "live")
    ctx.setdefault("llm_live", SETTINGS.llm_mode == "live")
    ctx["flash"] = request.query_params.get("msg")
    return templates.TemplateResponse(request=request, name=name, context=ctx)


def _recent_events(store: PoolStore, limit: int = 18) -> list[dict]:
    rows = store.conn.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for r in rows:
        detail = r["detail"]
        lead_id = r["lead_id"]
        target = ""
        if lead_id:
            lead = store.get_lead(lead_id)
            if lead:
                target = f"{lead.full_name or 'lead'} · {lead.company}".strip(" ·")
        out.append({"id": r["id"], "agent": r["agent"], "action": r["action"],
                    "target": target, "ago": _ago(r["created_at"])})
    return out


@router.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    engine = Engine(PoolStore(SETTINGS.db_path))
    store = engine.store
    all_leads = []
    cards = []
    total_booked = 0
    total_sent_est = 0
    for c in engine.active_campaigns():
        stats = store.campaign_stats(c.id)
        leads = store.leads(c.id)
        all_leads.extend(leads)
        booked = stats["by_outreach_state"].get("booked", 0)
        total_booked += booked
        sent_est = stats["sent_est"]
        total_sent_est += sent_est
        dispatched = stats["by_stage"].get("dispatched", 0) + booked
        replies_total = sum(v for k, v in stats["by_outreach_state"].items()
                            if k.startswith("replied"))
        cards.append({
            "name": c.name, "id": c.id,
            "industries": ", ".join(c.icp.industries) or "—",
            "stats": stats, "booked": booked,
            "reply_rate_pct": round(stats["reply_rate"] * 100, 1),
            "dispatch_pct": min(round(dispatched / max(len(leads), 1) * 100), 100),
            "_replies": replies_total,
        })
    verified = sum(1 for l in all_leads if l.email_status in ("verified", "risky_catchall_confirmed"))
    kpis = {
        "total_leads": len(all_leads),
        "verified_rate": round(verified / max(len(all_leads), 1) * 100, 1),
        "sent": total_sent_est,
        "booked": total_booked,
        "reply_rate": round(sum(c["_replies"] for c in cards) / max(total_sent_est, 1) * 100, 1),
    }
    return _render(request, "dashboard.html",
                   campaigns=cards, kpis=kpis,
                   events=_recent_events(store))


@router.get("/campaign/{name}", response_class=HTMLResponse)
def campaign_page(request: Request, name: str):
    engine = Engine(PoolStore(SETTINGS.db_path))
    try:
        c = engine.get_campaign(name)
    except KeyError:
        return _render(request, "dashboard.html", campaigns=[], kpis={},
                       events=[], flash="Campaign not found")
    stats = engine.stats(name)
    stage_counts = stats["by_stage"]
    funnel_rows = []
    max_v = max([stage_counts.get(s, 0) for s in FUNNEL_ORDER] + [1])
    for s in FUNNEL_ORDER:
        v = stage_counts.get(s, 0)
        funnel_rows.append({"label": s, "value": v, "pct": round(v / max_v * 100)})
    state_items = sorted(stats["by_outreach_state"].items(), key=lambda kv: -kv[1])
    return _render(request, "campaign.html",
                   c=c,
                   c_name=c.name,
                   steps=STEPS, default_limit=25,
                   funnel_rows=funnel_rows,
                   status_rows=sorted(stats["by_email_status"].items(), key=lambda kv: -kv[1]),
                   outreach_rows=state_items,
                   industries_list=c.icp.industries,
                   titles_list=c.icp.titles[:6],
                   headcount_min=c.icp.headcount_min, headcount_max=c.icp.headcount_max,
                   chart_data={
                       "funnel_labels": [f["label"] for f in funnel_rows],
                       "funnel_values": [f["value"] for f in funnel_rows],
                       "state_labels": [k.replace("_", " ") for k, _ in state_items][:8],
                       "state_values": [v for _, v in state_items][:8],
                   })


@router.post("/campaign/{name}/action")
def campaign_action(request: Request, name: str, step: str = Form(...), limit: int = Form(25)):
    engine = Engine(PoolStore(SETTINGS.db_path))
    msg = f"✓ {step} complete"
    try:
        if step == "hunt":
            res = engine.hunt(name, limit)
            msg = f"✓ Hunted {res['hunted']} new leads"
        elif step == "qualify":
            res = engine.qualify(name)
            msg = f"✓ Guardian: {res['advanced']} verified, {res['dropped']} dropped"
        elif step == "enrich":
            res = engine.enrich(name)
            msg = f"✓ Profiler: {res['advanced']} profiled"
        elif step == "copy":
            res = engine.write_copy(name)
            msg = f"✓ Copywriter: {res['advanced']} sequences written"
        elif step == "dispatch":
            res = engine.dispatch(name)
            msg = f"✓ Dispatched {res['email'].get('sent', 0)} emails · {res['linkedin'].get('scheduled', 0)} LinkedIn cadences"
        elif step == "replies":
            res = engine.process_replies(name)
            msg = f"✓ {res['booked']} meetings booked · {res['briefs'] and len(res['briefs']) or 0} briefs"
        elif step == "cycle":
            report = engine.full_cycle(name, limit=limit)
            msg = f"✓ Full cycle: {report['hunt']['hunted']} hunted → {report['engage']['booked']} booked"
        else:
            msg = f"Unknown step '{step}'"
    except Exception as e:
        msg = f"⚠ {step} failed: {e}"
    from urllib.parse import quote
    return RedirectResponse(f"/campaign/{quote(name)}?msg={quote(msg)}", status_code=303)


@router.get("/campaign/{name}/leads", response_class=HTMLResponse)
def leads_page(request: Request, name: str, stage: str = "", status: str = "",
               outreach: str = "", q: str = ""):
    engine = Engine(PoolStore(SETTINGS.db_path))
    store = engine.store
    c = engine.get_campaign(name)
    leads = store.leads(c.id, stage=stage or None, email_status=status or None,
                        outreach_state=outreach or None)
    if q:
        ql = q.lower()
        leads = [l for l in leads if ql in (l.full_name + " " + l.company + " " + l.email + " " + l.title).lower()]
    leads.sort(key=lambda l: l.updated_at, reverse=True)
    return _render(request, "leads.html", c=c, leads=leads[:500],
                   stages=STAGES, statuses=EMAIL_STATUSES, states=OUTREACH_STATES,
                   f_stage=stage, f_status=status, f_outreach=outreach, q=q)


@router.get("/lead/{lead_id}", response_class=HTMLResponse)
def lead_page(request: Request, lead_id: str):
    engine = Engine(PoolStore(SETTINGS.db_path))
    tl = engine.lead_timeline(lead_id)
    if not tl["lead"]:
        return RedirectResponse("/dashboard", status_code=302)
    lead = tl["lead"]
    for t in tl["timeline"]:
        t["ago"] = _ago(t["at"])
    return _render(request, "lead.html", lead=lead, timeline=tl["timeline"],
                   campaign_name=_campaign_name(engine, lead["campaign_id"]))


def _campaign_name(engine: Engine, cid: str) -> str:
    c = engine.store.get_campaign(cid)
    return c.name if c else ""


@router.get("/activity", response_class=HTMLResponse)
def activity_page(request: Request):
    engine = Engine(PoolStore(SETTINGS.db_path))
    return _render(request, "activity.html", events=_recent_events(engine.store, 40))
