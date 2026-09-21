"""CLIENT REPORTER - weekly client-facing performance reports for the agency.

Research basis: agencies charging $10-30K/month retainers win renewals
on reporting clarity (pipeline, replies, meetings, deliverability, A/B
learnings in one digest). ClientReporter assembles a per-campaign
report from the pool: leads processed, sent, replies, meetings,
deliverability health and experiment outcomes — the artifact that
justifies the retainer.
"""
from __future__ import annotations

from .base import BaseAgent
from ._pool import _all_campaigns
from ..deliverability import DeliverabilityMonitor


class ClientReporterAgent(BaseAgent):
    name = "client_reporter"

    def __init__(self, store, llm=None, monitor=None):
        super().__init__(store, llm)
        self.monitor = monitor or DeliverabilityMonitor(store)

    def run(self, campaign_id: str | None = None) -> dict:
        all_campaigns = _all_campaigns(self.store)
        campaigns = ([c for c in all_campaigns if c.id == campaign_id or c.name == campaign_id]
                     if campaign_id else all_campaigns)
        reports: list[dict] = []
        for campaign in campaigns:
            if campaign is None:
                continue
            stats = self.store.campaign_stats(campaign.id)
            leads = self.store.leads(campaign.id)
            sent = int(stats.get("sent_est", stats.get("sent", 0)) or 0)
            by_state = stats.get("by_outreach_state", {})
            positive = int(stats.get("positive_replies", by_state.get("replied_positive", 0)) or 0)
            replies = positive + int(by_state.get("stopped", 0) or 0)  # stop-on-reply counts as a reply
            report = {
                "campaign": campaign.name,
                "campaign_id": campaign.id,
                "leads_total": stats.get("total_leads", len(leads)),
                "sent": sent,
                "replies": replies,
                "positive_replies": positive,
                "meetings_booked": int(by_state.get("booked", 0)),
                "reply_rate": round(float(stats.get("reply_rate", 0)) * 100, 2) if stats.get("reply_rate") and stats.get("reply_rate") < 1 else round((replies / sent) * 100, 2) if sent else 0.0,
                "deliverability": self.monitor.check().get("summary", "no_inbox_data"),
                "top_signals": [l.trigger_signal for l in leads if l.trigger_signal][:5],
            }
            self.store.log_event("system", campaign.id, self.name, "client_report_generated", report)
            reports.append(report)
        self.stats = {"reports_generated": len(reports)}
        return {"stats": self.stats, "reports": reports}

    def process(self, lead):
        raise NotImplementedError("ClientReporterAgent works at system level")
