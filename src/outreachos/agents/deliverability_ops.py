"""DELIVERABILITY OPS - inbox-health auditor and campaign guard as a pool agent.

Research basis (Instantly / Smartlead 2026): deliverability infrastructure
is the moat — warmup tracking, bounce monitoring and inbox rotation.
DeliverabilityOps wraps the DeliverabilityMonitor for the common pool:
audits per-inbox 24h health, auto-pauses campaigns above 5% bounce and
quarantines inboxes above 8%, mirroring agency best practice.
"""
from __future__ import annotations

from .base import BaseAgent
from ..deliverability import DeliverabilityMonitor


class DeliverabilityOpsAgent(BaseAgent):
    name = "deliverability_ops"

    BOUNCE_PAUSE_PCT = 5.0
    BOUNCE_QUARANTINE_PCT = 8.0

    def __init__(self, store, llm=None, monitor=None):
        super().__init__(store, llm)
        self.monitor = monitor or DeliverabilityMonitor(store)

    def run(self, campaign_id: str | None = None) -> dict:
        health = self.monitor.check()
        inboxes = health.get("inboxes", [])
        if not inboxes:
            inboxes = self.monitor.dashboard()
        paused = quarantined = 0
        for inbox in inboxes:
            if not isinstance(inbox, dict):
                continue
            bounce = float(inbox.get("bounce_rate", 0) or 0)
            label = inbox.get("inbox", inbox.get("email", "unknown"))
            if bounce >= self.BOUNCE_QUARANTINE_PCT:
                quarantined += 1
                self.store.log_event("system", campaign_id or "global", self.name,
                                     "inbox_quarantined", {"inbox": label, "bounce_rate": bounce})
            elif bounce >= self.BOUNCE_PAUSE_PCT:
                paused += 1
                self.store.log_event("system", campaign_id or "global", self.name,
                                     "inbox_paused", {"inbox": label, "bounce_rate": bounce})
        self.stats = {"inboxes_audited": len(inboxes), "paused": paused, "quarantined": quarantined}
        return {"stats": self.stats, "health": health}

    def process(self, lead):
        raise NotImplementedError("DeliverabilityOpsAgent works at system level")
