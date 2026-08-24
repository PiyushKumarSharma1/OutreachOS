"""Campaign orchestration engine v2 — full subsystem integration.

Pipeline: HUNT(+signals) -> GUARD -> PROFILE(+research subagent)
       -> COPY(+AB variants, +learning bias) -> DISPATCH(+infra health,
       +compliance footer, +sequence engine) -> REPLIES(+intel, +AB outcomes,
       +webhooks) -> PIPELINE(+webhooks) -> LEARN(harvest insights)
"""
from __future__ import annotations

import json

from ..compliance import ComplianceManager
from ..experiments import ABEngine
from ..infrastructure import InfraManager
from ..learning import LearningLoop
from ..pool.models import Campaign, ICP
from ..pool.store import PoolStore
from ..agents import (
    HunterAgent, GuardianAgent, ProfilerAgent, CopywriterAgent,
    SDRAgent, NetworkerAgent, PipelineAgent,
)
from ..agents.subagents import ResearchSubAgent
from ..deliverability import DeliverabilityMonitor
from ..reply_intel import ReplyIntelligence
from ..sequences import SequenceEngine
from ..signals import SignalsEngine
from ..webhooks import EventBus


class Engine:
    def __init__(self, store: PoolStore | None = None):
        self.store = store or PoolStore()
        self.infra = InfraManager(self.store)
        self.monitor = DeliverabilityMonitor(self.store)
        self.compliance = ComplianceManager(self.store)
        self.signals = SignalsEngine(self.store)
        self.ab = ABEngine(self.store)
        self.seq = SequenceEngine(self.store)
        self.learning = LearningLoop(self.store)
        self.bus = EventBus(self.store)
        self._researcher = ResearchSubAgent()

    def create_campaign(self, name: str, icp: dict | None = None, offer: str = "",
                        case_studies: list[dict] | None = None,
                        client_id: str = "") -> Campaign:
        existing = self.store.get_campaign_by_name(name)
        if existing:
            return existing
        c = Campaign(name=name, icp=ICP(**(icp or {})),
                     offer=offer or "a done-for-you growth system",
                     case_studies=case_studies or [], status="active",
                     client_id=client_id)
        self.store.create_campaign(c)
        self.store.log_event("", c.id, "engine", "campaign_created", {"name": name})
        return c

    def get_campaign(self, name_or_id: str) -> Campaign:
        c = self.store.get_campaign_by_name(name_or_id) or self.store.get_campaign(name_or_id)
        if not c:
            raise KeyError(f"campaign '{name_or_id}' not found")
        return c

    def active_campaigns(self) -> list[Campaign]:
        rows = self.store.conn.execute("SELECT data FROM campaigns").fetchall()
        return [Campaign.from_dict(json.loads(r["data"])) for r in rows]

    def campaigns_for_client(self, client_id: str) -> list[Campaign]:
        return [c for c in self.active_campaigns() if c.client_id == client_id]

    def hunt(self, campaign_name: str, limit: int = 100) -> dict:
        campaign = self.get_campaign(campaign_name)
        hunter = HunterAgent(self.store)
        leads = hunter.hunt(campaign, limit)
        scored = 0
        for lead in leads:
            self.signals.score_lead(lead)
            self.store.upsert_lead(lead)
            scored += 1
        self.bus.emit("leads.hunted", {"campaign": campaign.name, "count": len(leads)})
        return {"hunted": len(leads), "signals_scored": scored}

    def qualify(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        guardian = GuardianAgent(self.store)
        targets = [l for l in self.store.leads(campaign.id) if l.stage in ("raw", "hunted")]
        return guardian.run_batch(targets)

    def enrich(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        profiler = ProfilerAgent(self.store)
        targets = [l for l in self.store.leads(campaign.id, email_status="verified") +
                   self.store.leads(campaign.id, email_status="risky_catchall_confirmed")
                   if l.stage == "verified"]
        for lead in targets:
            research = self._researcher.research(lead.to_dict())
            lead.research["findings"] = research["findings"]
            lead.research["research_quality"] = research["research_quality"]
            self.store.upsert_lead(lead)
        return profiler.run_batch(targets)

    def write_copy(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        cw = CopywriterAgent(self.store)
        exp = self.ab.running_for_campaign(campaign.id)
        style_hint = self.learning.recommend_angle_style(campaign.id)
        targets = [l for l in self.store.leads(campaign.id) if l.stage == "profiled"]
        for lead in targets:
            if exp:
                variant = self.ab.assign(exp, lead.id)
                lead.enrichment["ab_variant"] = variant["key"]
                if variant.get("opener_hint"):
                    lead.research["opener_signal"] = variant["opener_hint"]
            if style_hint:
                lead.research["preferred_angle_style"] = style_hint
            self.store.upsert_lead(lead)
        return cw.run_batch(targets)

    def dispatch(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        healthy = self.monitor.healthy_inboxes(self.infra)
        sdr = SDRAgent(self.store, inboxes=healthy or None, compliance=self.compliance)
        net = NetworkerAgent(self.store)
        written = self.store.leads(campaign.id, stage="written")
        written.sort(key=lambda l: -(l.enrichment.get("intent_score") or 0))
        linkedin_pool = [l for l in written if l.linkedin_url]
        exp = self.ab.running_for_campaign(campaign.id)
        for lead in written:
            step = self.seq.next_step(lead)
            if step:
                lead.enrichment["next_sequence_step"] = step["step"]
                lead.enrichment["next_sequence_channel"] = step["channel"]
                self.store.upsert_lead(lead)
        send_res = sdr.dispatch(written)
        if exp:
            for lead in written:
                if lead.outreach_state == "sent":
                    self.ab.record_send(exp["id"], lead.id)
        for lead in written:
            if lead.outreach_state == "sent":
                self.seq.mark_sent(lead, 1)
                self.store.upsert_lead(lead)
        net_res = net.schedule(linkedin_pool)
        if send_res.get("sent"):
            self.bus.emit("email.sent", {"campaign": campaign.name, "count": send_res["sent"]})
        return {"email": send_res, "linkedin": net_res}

    def process_replies(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        sdr = SDRAgent(self.store, compliance=self.compliance)
        intel = ReplyIntelligence(self.store, compliance=self.compliance)
        sim = self.store.conn.execute("SELECT 1").fetchone() and True
        handoffs = []
        from ..config import SETTINGS
        if SETTINGS.provider_mode != "live":
            for lead in self.store.leads(campaign.id, outreach_state="sent"):
                outcome = sdr._simulate_outcome(lead.email)
                if not outcome:
                    continue
                body = sdr._sim_body(outcome)
                if outcome == "replied_positive":
                    res = intel.process(lead, body)
                    if res["route"] == "positive":
                        handoffs.append(lead)
                        self.bus.emit("reply.received", {"campaign": campaign.name,
                                                         "lead": lead.email, "state": "positive"})
                elif outcome == "replied_negative":
                    res = intel.process(lead, body)
                    self.bus.emit("reply.received", {"campaign": campaign.name,
                                                     "lead": lead.email,
                                                     "state": res["route"]})
                else:
                    lead.outreach_state = outcome
                    self.store.upsert_lead(lead)
                    self.store.log_event(lead.id, campaign.id, "sdr", f"reply_{outcome}", {})
        else:
            raw = sdr.sender.fetch_replies(campaign.id)
            by_email = {l.email: l for l in self.store.leads(campaign.id)}
            for r in raw:
                lead = by_email.get(r.get("to_email"))
                if not lead:
                    continue
                res = intel.process(lead, r.get("body", ""))
                if res["route"] == "positive":
                    handoffs.append(lead)
                self.bus.emit("reply.received", {"campaign": campaign.name,
                                                 "lead": lead.email, "state": res["route"]})
        exp = self.ab.running_for_campaign(campaign.id)
        if exp:
            for lead in handoffs:
                self.ab.record_positive(exp["id"], lead.id)
            self.ab.evaluate(exp["id"])
        pipeline = PipelineAgent(self.store)
        briefs = pipeline.process_positive_replies(campaign.id)
        for b in briefs:
            self.bus.emit("meeting.booked", {"campaign": campaign.name,
                                             "lead_id": b["lead_id"],
                                             "prospect": b["prospect"],
                                             "company": b["company"]})
        learn = self.learning.harvest(campaign.id)
        return {"replies": sdr.stats, "booked": len(briefs), "briefs": briefs,
                "learning": learn}

    def full_cycle(self, campaign_name: str, limit: int = 50) -> dict:
        report = {}
        report["hunt"] = self.hunt(campaign_name, limit)
        report["guard"] = self.qualify(campaign_name)
        report["profile"] = self.enrich(campaign_name)
        report["copy"] = self.write_copy(campaign_name)
        report["dispatch"] = self.dispatch(campaign_name)
        report["engage"] = self.process_replies(campaign_name)
        report["stats"] = self.stats(campaign_name)
        self.bus.emit("campaign.cycle_complete",
                      {"campaign": campaign_name, "booked": report["engage"]["booked"]})
        return report

    def stats(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        return self.store.campaign_stats(campaign.id)

    def lead_timeline(self, lead_id: str) -> dict:
        lead = self.store.get_lead(lead_id)
        events = self.store.events_for_lead(lead_id)
        return {
            "lead": lead.to_dict() if lead else None,
            "timeline": [{"agent": e.agent, "action": e.action, "detail": e.detail,
                          "at": e.created_at} for e in events],
        }
