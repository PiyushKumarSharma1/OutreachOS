"""Client-facing portal (white-label reporting) + objection approval queue."""
from __future__ import annotations

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse

from ..config import SETTINGS
from ..pool.store import PoolStore
from ..orchestration.engine import Engine
from ..tenancy import TenancyManager
from .pages import templates, _render, _recent_events

router = APIRouter(include_in_schema=False)

PORTAL_COOKIE = "oos_portal"


def _client_from_request(request: Request) -> dict | None:
    key = request.cookies.get(PORTAL_COOKIE, "")
    if not key:
        return None
    auth = TenancyManager(PoolStore(SETTINGS.db_path)).verify(key, required_scope="read")
    if not auth:
        return None
    return TenancyManager(PoolStore(SETTINGS.db_path)).get_client(auth["client_id"])


@router.get("/portal", response_class=HTMLResponse)
def portal_login(request: Request):
    client = _client_from_request(request)
    if client:
        return RedirectResponse("/portal/dashboard", status_code=302)
    return _render(request, "portal_login.html", error=None)


@router.post("/portal/login")
def portal_do_login(request: Request, api_key: str = Form(...)):
    tm = TenancyManager(PoolStore(SETTINGS.db_path))
    auth = tm.verify(api_key.strip(), required_scope="read")
    if not auth:
        return _render(request, "portal_login.html", error="Invalid API key")
    resp = RedirectResponse("/portal/dashboard", status_code=303)
    resp.set_cookie(PORTAL_COOKIE, api_key.strip(), httponly=True, samesite="lax")
    return resp


@router.get("/portal/logout")
def portal_logout():
    resp = RedirectResponse("/portal", status_code=302)
    resp.delete_cookie(PORTAL_COOKIE)
    return resp


@router.get("/portal/dashboard", response_class=HTMLResponse)
def portal_dashboard(request: Request):
    client = _client_from_request(request)
    if not client:
        return RedirectResponse("/portal", status_code=302)
    engine = Engine(PoolStore(SETTINGS.db_path))
    campaigns = engine.campaigns_for_client(client["id"])
    cards = []
    totals = {"leads": 0, "booked": 0, "sent": 0, "positive": 0}
    meetings = []
    for c in campaigns:
        stats = engine.stats(c.name)
        booked = stats["by_outreach_state"].get("booked", 0)
        totals["leads"] += stats["total_leads"]
        totals["booked"] += booked
        totals["sent"] += stats["sent_est"]
        totals["positive"] += stats["positive_replies"]
        cards.append({"name": c.name, "stats": stats, "booked": booked,
                      "reply_rate_pct": round(stats["reply_rate"] * 100, 1)})
        for l in engine.store.leads(c.id, outreach_state="booked"):
            brief = next((n["brief"] for n in reversed(l.notes)
                          if n.get("type") == "pre_call_brief"), None)
            meetings.append({"campaign": c.name, "prospect": l.full_name,
                             "title": l.title, "company": l.company,
                             "brief": brief})
    return _render(request, "portal_dashboard.html", client=client,
                   campaigns=cards, totals=totals, meetings=meetings)


@router.get("/portal/leads", response_class=HTMLResponse)
def portal_leads(request: Request, stage: str = "", status: str = "",
                 outreach: str = "", q: str = ""):
    client = _client_from_request(request)
    if not client:
        return RedirectResponse("/portal", status_code=302)
    engine = Engine(PoolStore(SETTINGS.db_path))
    campaigns = engine.campaigns_for_client(client["id"])
    all_leads = []
    for c in campaigns:
        all_leads.extend(engine.store.leads(c.id))
    
    if stage:
        all_leads = [l for l in all_leads if l.stage == stage]
    if status:
        all_leads = [l for l in all_leads if l.email_status == status]
    if outreach:
        all_leads = [l for l in all_leads if l.outreach_state == outreach]
    if q:
        ql = q.lower()
        all_leads = [l for l in all_leads if ql in (l.full_name + " " + l.company + " " + l.email + " " + l.title).lower()]
    
    all_leads.sort(key=lambda l: l.updated_at, reverse=True)
    
    from ..pool.models import STAGES, EMAIL_STATUSES, OUTREACH_STATES
    return _render(request, "portal_leads.html", client=client, leads=all_leads[:500],
                   stages=STAGES, statuses=EMAIL_STATUSES, states=OUTREACH_STATES,
                   f_stage=stage, f_status=status, f_outreach=outreach, q=q)


@router.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request):
    engine = Engine(PoolStore(SETTINGS.db_path))
    queue = []
    for c in engine.active_campaigns():
        for l in engine.store.leads(c.id, outreach_state="replied_negative"):
            for n in l.notes:
                if n.get("type") == "draft_response" and n.get("status") == "needs_human_approval":
                    queue.append({"lead": l, "note": n, "campaign": c.name})
    return _render(request, "approvals.html", queue=queue)


@router.post("/approvals/action")
def approvals_action(request: Request, lead_id: str = Form(...), action: str = Form(...)):
    engine = Engine(PoolStore(SETTINGS.db_path))
    lead = engine.store.get_lead(lead_id)
    if lead:
        for n in lead.notes:
            if n.get("type") == "draft_response" and n.get("status") == "needs_human_approval":
                n["status"] = "approved" if action == "approve" else "discarded"
        lead.notes.append({"agent": "operator", "action": f"draft_{action}d"})
        engine.store.upsert_lead(lead)
        engine.store.log_event(lead.id, lead.campaign_id, "operator",
                               f"draft_{action}d", {})
        if action == "approve":
            engine.bus.emit("reply.sent", {"lead_id": lead.id, "type": "objection_response"})
    from urllib.parse import quote
    return RedirectResponse(f"/approvals?msg={quote('Draft ' + action + 'd')}", status_code=303)
