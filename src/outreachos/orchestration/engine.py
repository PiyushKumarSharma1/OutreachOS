"""Campaign orchestration engine - wires the agent graph over the Common Pool.

Pipeline: HUNT -> GUARD -> PROFILER -> COPYWRITER -> DISPATCH(SDR || NETWORKER)
          -> REPLIES(SDR classify) -> PIPELINE(book + brief)
Filters between stages prevent wasted spend downstream (verified-only rule).
"""
from __future__ import annotations

import json

from ..pool.models import Campaign, ICP
from ..pool.store import PoolStore
from ..agents import (
    HunterAgent, GuardianAgent, ProfilerAgent, CopywriterAgent,
    SDRAgent, NetworkerAgent, PipelineAgent,
)


class Engine:
    def __init__(self, store: PoolStore | None = None):
        self.store = store or PoolStore()

    def create_campaign(self, name: str, icp: dict | None = None, offer: str = "",
                        case_studies: list[dict] | None = None) -> Campaign:
        existing = self.store.get_campaign_by_name(name)
        if existing:
            return existing
        c = Campaign(name=name,
                     icp=ICP(**(icp or {})),
                     offer=offer or "a done-for-you growth system",
                     case_studies=case_studies or [],
                     status="active")
        self.store.create_campaign(c)
        self.store.log_event("", c.id, "engine", "campaign_created", {"name": name})
        return c

    def get_campaign(self, name_or_id: str) -> Campaign:
        c = self.store.get_campaign_by_name(name_or_id) or self.store.get_campaign(name_or_id)
        if not c:
            raise KeyError(f"campaign '{name_or_id}' not found")
        return c

    def hunt(self, campaign_name: str, limit: int = 100) -> dict:
        campaign = self.get_campaign(campaign_name)
        hunter = HunterAgent(self.store)
        leads = hunter.hunt(campaign, limit)
        return {"hunted": len(leads)}

    def qualify(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        guardian = GuardianAgent(self.store)
        targets = [l for l in self.store.leads(campaign.id) if l.stage in ("raw", "hunted")]
        res = guardian.run_batch(targets)
        return res

    def enrich(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        profiler = ProfilerAgent(self.store)
        targets = self.store.leads(campaign.id, email_status="verified") + \
            self.store.leads(campaign.id, email_status="risky_catchall_confirmed")
        targets = [l for l in targets if l.stage == "verified"]
        return profiler.run_batch(targets)

    def write_copy(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        cw = CopywriterAgent(self.store)
        targets = [l for l in self.store.leads(campaign.id) if l.stage == "profiled"]
        return cw.run_batch(targets)

    def dispatch(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        sdr = SDRAgent(self.store)
        net = NetworkerAgent(self.store)
        written = self.store.leads(campaign.id, stage="written")
        linkedin_pool = [l for l in written if l.linkedin_url]
        send_res = sdr.dispatch(written)
        net_res = net.schedule(linkedin_pool)
        return {"email": send_res, "linkedin": net_res}

    def process_replies(self, campaign_name: str) -> dict:
        campaign = self.get_campaign(campaign_name)
        sdr = SDRAgent(self.store)
        handoffs = sdr.process_replies(campaign.id)
        pipeline = PipelineAgent(self.store)
        briefs = pipeline.process_positive_replies(campaign.id)
        return {"replies": sdr.stats, "booked": len(briefs), "briefs": briefs}

    def full_cycle(self, campaign_name: str, limit: int = 50) -> dict:
        report = {}
        report["hunt"] = self.hunt(campaign_name, limit)
        report["guard"] = self.qualify(campaign_name)
        report["profile"] = self.enrich(campaign_name)
        report["copy"] = self.write_copy(campaign_name)
        report["dispatch"] = self.dispatch(campaign_name)
        report["engage"] = self.process_replies(campaign_name)
        report["stats"] = self.stats(campaign_name)
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
