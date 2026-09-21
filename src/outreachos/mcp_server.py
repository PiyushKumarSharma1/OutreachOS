"""OutreachOS MCP server — stdio JSON-RPC 2.0.

Lets Claude (or any MCP client) operate the agency directly:
read tools (overview, stats, leads, timelines) + ops tools (run cycles,
create campaigns, process replies) gated behind write scope.

Run: python -m outreachos.mcp_server
Config (Claude Code / opencode):
  { "mcpServers": { "outreachos": { "command": "python",
      "args": ["-m", "outreachos.mcp_server"], "env": {"OUTREACHOS_DB": "..."} } } }

Rules honored (2026 MCP practice):
- stdout carries ONLY JSON-RPC messages; logs go to stderr
- intent-grouped tools, strict JSON Schema inputs
- ops tools require write scope when OUTREACHOS_MCP_KEY is set
"""
from __future__ import annotations

import json
import os
import sys

from .config import SETTINGS
from .pool.store import PoolStore
from .orchestration.engine import Engine
from .tenancy import TenancyManager
from .deliverability import DeliverabilityMonitor
from .infrastructure import InfraManager
from .learning import LearningLoop
from .experiments import ABEngine
from .webhooks import EventBus
from .compliance import ComplianceManager
from .signals import SignalsEngine

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "outreachos", "version": "0.5.0"}


def _tool(name, description, schema, scope="read"):
    return {"name": name, "description": description,
            "inputSchema": schema, "_scope": scope}


TOOLS = [
    # READ TOOLS (no auth required by default)
    _tool("outreachos_overview",
          "Global agency KPIs: campaigns, leads, verified rate, meetings booked, reply rates.",
          {"type": "object", "properties": {}}),
    _tool("outreachos_campaign_stats",
          "Full funnel stats for one campaign: stages, email statuses, outreach states, reply/bounce rates.",
          {"type": "object", "properties": {"campaign": {"type": "string"}}, "required": ["campaign"]}),
    _tool("outreachos_search_leads",
          "Search leads by campaign with optional filters (stage, status, outreach state, text query).",
          {"type": "object",
           "properties": {"campaign": {"type": "string"}, "stage": {"type": "string"},
                          "status": {"type": "string"}, "outreach": {"type": "string"},
                          "q": {"type": "string"}, "limit": {"type": "integer", "default": 20}},
           "required": ["campaign"]}),
    _tool("outreachos_lead_timeline",
          "Complete event timeline for one lead: every agent action with details.",
          {"type": "object", "properties": {"lead_id": {"type": "string"}}, "required": ["lead_id"]}),
    _tool("outreachos_campaigns_list",
          "List all campaigns with basic info.",
          {"type": "object", "properties": {}}),
    _tool("outreachos_health_check",
          "Infrastructure + deliverability health across all inboxes.",
          {"type": "object", "properties": {}}),
    _tool("outreachos_learning_insights",
          "Harvested insights from win/loss outcomes for a campaign.",
          {"type": "object", "properties": {"campaign": {"type": "string"}}, "required": ["campaign"]}),
    _tool("outreachos_experiment_status",
          "A/B experiment status for a campaign.",
          {"type": "object", "properties": {"campaign": {"type": "string"}}, "required": ["campaign"]}),
    _tool("outreachos_signals_summary",
          "Trigger signal distribution for a campaign.",
          {"type": "object", "properties": {"campaign": {"type": "string"}}, "required": ["campaign"]}),
    _tool("outreachos_compliance_suppressions",
          "List suppressed emails.",
          {"type": "object", "properties": {"limit": {"type": "integer", "default": 100}}}),
    _tool("outreachos_webhook_subscriptions",
          "List active webhook subscriptions.",
          {"type": "object", "properties": {}}),
    _tool("outreachos_webhook_deliveries",
          "Recent webhook delivery log.",
          {"type": "object", "properties": {"limit": {"type": "integer", "default": 50}}}),
    _tool("outreachos_approval_queue",
          "Pending objection drafts awaiting human approval.",
          {"type": "object", "properties": {}}),
    
    # WRITE TOOLS (require write scope)
    _tool("outreachos_run_cycle",
          "Run the full autonomous pipeline for a campaign: hunt -> verify -> profile -> copy -> dispatch -> replies -> book.",
          {"type": "object",
           "properties": {"campaign": {"type": "string"}, "limit": {"type": "integer", "default": 25},
                          "auto_hunt": {"type": "boolean", "default": True}},
           "required": ["campaign"]}, scope="write"),
    _tool("outreachos_create_campaign",
          "Create a campaign with ICP targeting, offer, and case studies.",
          {"type": "object",
           "properties": {"name": {"type": "string"}, "offer": {"type": "string"},
                          "industries": {"type": "array", "items": {"type": "string"}},
                          "titles": {"type": "array", "items": {"type": "string"}},
                          "headcount_min": {"type": "integer"}, "headcount_max": {"type": "integer"}},
           "required": ["name"]}, scope="write"),
    _tool("outreachos_process_replies",
          "Classify pending replies, route objections to drafts, book positive ones.",
          {"type": "object", "properties": {"campaign": {"type": "string"}}, "required": ["campaign"]},
          scope="write"),
    _tool("outreachos_create_client",
          "Create a new client with API key.",
          {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
          scope="write"),
    _tool("outreachos_create_webhook",
          "Subscribe to event webhooks.",
          {"type": "object",
           "properties": {"url": {"type": "string"}, "events": {"type": "array", "items": {"type": "string"}},
                          "secret": {"type": "string"}}, "required": ["url"]},
          scope="write"),
    _tool("outreachos_create_experiment",
          "Create an A/B experiment for a campaign.",
          {"type": "object",
           "properties": {"campaign": {"type": "string"}, "name": {"type": "string"},
                          "subject_a": {"type": "string"}, "subject_b": {"type": "string"}},
           "required": ["campaign", "subject_a", "subject_b"]},
          scope="write"),
    _tool("outreachos_approve_draft",
          "Approve an objection response draft.",
          {"type": "object", "properties": {"lead_id": {"type": "string"}}, "required": ["lead_id"]},
          scope="write"),
    _tool("outreachos_discard_draft",
          "Discard an objection response draft.",
          {"type": "object", "properties": {"lead_id": {"type": "string"}}, "required": ["lead_id"]},
          scope="write"),
    _tool("outreachos_suppress_email",
          "Add email to suppression list.",
          {"type": "object", "properties": {"email": {"type": "string"}, "reason": {"type": "string"}},
           "required": ["email"]},
          scope="write"),
    _tool("outreachos_seed_infrastructure",
          "Seed default satellite domains and inboxes.",
          {"type": "object", "properties": {}}, scope="write"),
]


class MCPServer:
    def __init__(self):
        self.engine = None

    def _ensure_engine(self):
        if self.engine is None:
            self.engine = Engine(PoolStore(SETTINGS.db_path))
        return self.engine

    def _authorized(self, scope: str) -> bool:
        key = os.getenv("OUTREACHOS_MCP_KEY", "")
        if not key:
            return True
        auth = TenancyManager(PoolStore(SETTINGS.db_path)).verify(key, required_scope=scope)
        return auth is not None

    def handle(self, msg: dict) -> dict | None:
        method = msg.get("method", "")
        mid = msg.get("id")
        if method == "initialize":
            return self._result(mid, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            })
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            tools = [{k: v for k, v in t.items() if not k.startswith("_")} for t in TOOLS]
            return self._result(mid, {"tools": tools})
        if method == "tools/call":
            return self._call_tool(mid, msg.get("params", {}))
        if method == "ping":
            return self._result(mid, {})
        return self._error(mid, -32601, f"method not found: {method}")

    def _call_tool(self, mid, params):
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if not tool:
            return self._error(mid, -32602, f"unknown tool: {name}")
        if tool["_scope"] == "write" and not self._authorized("write"):
            return self._error(mid, -32003, "write scope required (set valid OUTREACHOS_MCP_KEY)")
        try:
            result = getattr(self, f"_tool_{name}")(args)
            return self._result(mid, {"content": [{"type": "text", "text": json.dumps(result, default=str)}]})
        except KeyError as e:
            return self._error(mid, -32602, str(e))
        except Exception as e:
            return self._error(mid, -32603, f"tool error: {e}")

    # READ TOOL IMPLEMENTATIONS
    def _tool_outreachos_overview(self, args):
        eng = self._ensure_engine()
        campaigns = []
        totals = {"leads": 0, "booked": 0, "sent": 0}
        for c in eng.active_campaigns():
            s = eng.stats(c.name)
            booked = s["by_outreach_state"].get("booked", 0)
            totals["leads"] += s["total_leads"]
            totals["booked"] += booked
            totals["sent"] += s["sent_est"]
            campaigns.append({"name": c.name, "leads": s["total_leads"], "booked": booked,
                              "reply_rate": s["reply_rate"]})
        return {"totals": totals, "campaigns": campaigns}

    def _tool_outreachos_campaign_stats(self, args):
        return self._ensure_engine().stats(args["campaign"])

    def _tool_outreachos_search_leads(self, args):
        eng = self._ensure_engine()
        c = eng.get_campaign(args["campaign"])
        leads = eng.store.leads(c.id, stage=args.get("stage") or None,
                                email_status=args.get("status") or None,
                                outreach_state=args.get("outreach") or None)
        q = (args.get("q") or "").lower()
        if q:
            leads = [l for l in leads if q in (l.full_name + l.company + l.email + l.title).lower()]
        limit = min(int(args.get("limit", 20)), 100)
        return {"count": len(leads), "leads": [
            {"id": l.id, "name": l.full_name, "title": l.title, "company": l.company,
             "email": l.email, "stage": l.stage, "outreach": l.outreach_state,
             "intent_score": l.enrichment.get("intent_score", 0)} for l in leads[:limit]]}

    def _tool_outreachos_lead_timeline(self, args):
        tl = self._ensure_engine().lead_timeline(args["lead_id"])
        if not tl["lead"]:
            raise KeyError("lead not found")
        return tl

    def _tool_outreachos_campaigns_list(self, args):
        eng = self._ensure_engine()
        return {"campaigns": [{"id": c.id, "name": c.name, "status": c.status, "client_id": c.client_id}
                              for c in eng.active_campaigns()]}

    def _tool_outreachos_health_check(self, args):
        store = PoolStore(SETTINGS.db_path)
        infra = InfraManager(store)
        monitor = DeliverabilityMonitor(store)
        health = monitor.check()
        return {
            "infrastructure": infra.all_inboxes(),
            "deliverability_check": health,
            "dashboard": monitor.dashboard(),
        }

    def _tool_outreachos_learning_insights(self, args):
        learning = LearningLoop(PoolStore(SETTINGS.db_path))
        return learning.summary(args["campaign"])

    def _tool_outreachos_experiment_status(self, args):
        ab = ABEngine(PoolStore(SETTINGS.db_path))
        exp = ab.running_for_campaign(self._ensure_engine().get_campaign(args["campaign"]).id)
        if not exp:
            return {"status": "none"}
        return {"experiment": exp, "evaluation": ab.evaluate(exp["id"])}

    def _tool_outreachos_signals_summary(self, args):
        c = self._ensure_engine().get_campaign(args["campaign"])
        signals = SignalsEngine(PoolStore(SETTINGS.db_path))
        return {"top_signals": signals.top_signals(c.id)}

    def _tool_outreachos_compliance_suppressions(self, args):
        cm = ComplianceManager(PoolStore(SETTINGS.db_path))
        return {"suppressions": cm.list_suppressions(limit=args.get("limit", 100))}

    def _tool_outreachos_webhook_subscriptions(self, args):
        bus = EventBus(PoolStore(SETTINGS.db_path))
        return {"subscriptions": bus.list_subscriptions()}

    def _tool_outreachos_webhook_deliveries(self, args):
        bus = EventBus(PoolStore(SETTINGS.db_path))
        return {"deliveries": bus.delivery_log(limit=args.get("limit", 50))}

    def _tool_outreachos_approval_queue(self, args):
        eng = self._ensure_engine()
        queue = []
        for c in eng.active_campaigns():
            for l in eng.store.leads(c.id, outreach_state="replied_negative"):
                for n in l.notes:
                    if n.get("type") == "draft_response" and n.get("status") == "needs_human_approval":
                        queue.append({"lead_id": l.id, "lead_name": l.full_name, "campaign": c.name,
                                     "objection": n.get("objection"), "draft": n.get("draft"),
                                     "note_id": id(n)})
        return {"queue": queue}

    # WRITE TOOL IMPLEMENTATIONS
    def _tool_outreachos_run_cycle(self, args):
        report = self._ensure_engine().full_cycle(args["campaign"], limit=int(args.get("limit", 25)))
        return {"summary": {"hunted": report["hunt"]["hunted"],
                            "verified": report["guard"]["advanced"],
                            "sent": report["dispatch"]["email"].get("sent", 0),
                            "booked": report["engage"]["booked"]},
                "stats": report["stats"]}

    def _tool_outreachos_create_campaign(self, args):
        eng = self._ensure_engine()
        icp = {"industries": args.get("industries", []),
               "titles": args.get("titles", []),
               "headcount_min": args.get("headcount_min", 10),
               "headcount_max": args.get("headcount_max", 5000)}
        c = eng.create_campaign(args["name"], icp=icp, offer=args.get("offer", ""))
        return {"id": c.id, "name": c.name}

    def _tool_outreachos_process_replies(self, args):
        res = self._ensure_engine().process_replies(args["campaign"])
        return {"replies": res.get("replies", {}), "booked": res.get("booked", 0)}

    def _tool_outreachos_create_client(self, args):
        tm = TenancyManager(PoolStore(SETTINGS.db_path))
        client = tm.create_client(args["name"])
        key = tm.create_api_key(client["id"])
        return {"client": client, "api_key": key}

    def _tool_outreachos_create_webhook(self, args):
        bus = EventBus(PoolStore(SETTINGS.db_path))
        sub = bus.subscribe(args["url"], args.get("events", ["*"]), args.get("secret"))
        return sub

    def _tool_outreachos_create_experiment(self, args):
        eng = self._ensure_engine()
        c = eng.get_campaign(args["campaign"])
        exp = ABEngine(eng.store).create_experiment(
            c.id, args.get("name", "subject-test"),
            [{"key": "A", "subject": args["subject_a"]}, {"key": "B", "subject": args["subject_b"]}])
        return exp

    def _tool_outreachos_approve_draft(self, args):
        eng = self._ensure_engine()
        lead = eng.store.get_lead(args["lead_id"])
        if not lead:
            raise KeyError("lead not found")
        for n in lead.notes:
            if n.get("type") == "draft_response" and n.get("status") == "needs_human_approval":
                n["status"] = "approved"
        lead.notes.append({"agent": "operator", "action": "draft_approved"})
        eng.store.upsert_lead(lead)
        eng.store.log_event(lead.id, lead.campaign_id, "operator", "draft_approved", {})
        eng.bus.emit("reply.sent", {"lead_id": lead.id, "type": "objection_response"})
        return {"approved": True, "lead_id": args["lead_id"]}

    def _tool_outreachos_discard_draft(self, args):
        eng = self._ensure_engine()
        lead = eng.store.get_lead(args["lead_id"])
        if not lead:
            raise KeyError("lead not found")
        for n in lead.notes:
            if n.get("type") == "draft_response" and n.get("status") == "needs_human_approval":
                n["status"] = "discarded"
        lead.notes.append({"agent": "operator", "action": "draft_discarded"})
        eng.store.upsert_lead(lead)
        eng.store.log_event(lead.id, lead.campaign_id, "operator", "draft_discarded", {})
        return {"discarded": True, "lead_id": args["lead_id"]}

    def _tool_outreachos_suppress_email(self, args):
        cm = ComplianceManager(PoolStore(SETTINGS.db_path))
        cm.suppress(args["email"], args.get("reason", "manual"), source="mcp")
        return {"suppressed": True, "email": args["email"]}

    def _tool_outreachos_seed_infrastructure(self, args):
        infra = InfraManager(PoolStore(SETTINGS.db_path))
        return {"seeded": infra.seed_defaults()}

    @staticmethod
    def _result(mid, result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    @staticmethod
    def _error(mid, code, message):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    def serve(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = self.handle(msg)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()


def main():
    print("outreachos MCP server starting (stdio)", file=sys.stderr)
    MCPServer().serve()


if __name__ == "__main__":
    main()
