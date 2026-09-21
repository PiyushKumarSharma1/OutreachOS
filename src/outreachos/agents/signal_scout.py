"""SIGNAL SCOUT - continuous trigger-signal watcher for the common pool.

Research basis (2026): signal-triggered outreach delivers 3-5x the reply
rate of cadence-triggered outreach (Common Room / Clay reference stacks).
SignalScout re-scores pool leads with the SignalsEngine, persists fresh
trigger signals, and revives leads dropped for timing back into the
queue so SDR sequences fire on behaviour, not on a static cadence.
"""
from __future__ import annotations

from .base import BaseAgent
from ._pool import _all_campaigns
from ..signals import SignalsEngine


class SignalScoutAgent(BaseAgent):
    name = "signal_scout"

    def __init__(self, store, llm=None, signals=None):
        super().__init__(store, llm)
        self.signals = signals or SignalsEngine(store)

    def run(self, campaign_id: str | None = None) -> dict:
        if campaign_id:
            campaigns = [c for c in _all_campaigns(self.store) if c.id == campaign_id or c.name == campaign_id]
        else:
            campaigns = _all_campaigns(self.store)
        refreshed = revived = 0
        for campaign in campaigns:
            for lead in self.store.leads(campaign.id):
                score = self.signals.score_lead(lead)  # persists signals + trigger_signal
                revived_flag = False
                if lead.stage == "dropped" and any(
                    "timing" in str(n.get("reason", "")) for n in lead.notes
                ):
                    lead.stage = "hunted"
                    lead.outreach_state = "queued_email"
                    revived_flag = True
                    revived += 1
                self.store.upsert_lead(lead)
                self.log(lead, "signal_refresh", {
                    "intent_score": score, "revived": revived_flag,
                    "signals": lead.enrichment.get("signals", []),
                })
                refreshed += 1
        self.stats = {"leads_refreshed": refreshed, "leads_revived": revived}
        return self.stats

    def process(self, lead):
        raise NotImplementedError("SignalScoutAgent works at campaign level")
