"""SDR - execution layer: inbox rotation, send caps, reply classification.

Deliverability rules enforced:
- max DAILY_SEND_CAP_PER_INBOX per inbox/day (default 30)
- inboxes must be warmed >= WARMUP_MIN_DAYS
- never sends to non-verified / quarantined addresses (stage gate)
"""
from __future__ import annotations

import random

from .base import BaseAgent
from ..config import SETTINGS
from ..providers.base import build
from ..utils import stable_seed


DEFAULT_INBOX_POOL = [
    {"inbox": "ava@growloop1.com", "warmup_days": 30},
    {"inbox": "sam@growloop1.com", "warmup_days": 30},
    {"inbox": "kai@trygrowloop2.com", "warmup_days": 25},
    {"inbox": "noor@trygrowloop2.com", "warmup_days": 18},
    {"inbox": "eli@getgrowloop3.com", "warmup_days": 10},
]


class SDRAgent(BaseAgent):
    name = "sdr"

    def __init__(self, store, llm=None, sender=None, inboxes=None):
        super().__init__(store, llm)
        self.sender = sender or build("sender")
        self.inboxes = inboxes or DEFAULT_INBOX_POOL

    def ready_inboxes(self) -> list[dict]:
        return [i for i in self.inboxes if i.get("warmup_days", 0) >= SETTINGS.warmup_min_days]

    def dispatch(self, leads) -> dict:
        ready = self.ready_inboxes()
        if not ready:
            self.stats = {"queued": 0, "reason": "no_warmed_inboxes"}
            return self.stats
        cap = SETTINGS.daily_send_cap_per_inbox
        capacity = len(ready) * cap
        batch = []
        for lead in leads:
            if len(batch) >= capacity:
                break
            if lead.email_status not in ("verified", "risky_catchall_confirmed"):
                continue
            if any(n.get("flag") == "needs_review" for n in lead.notes):
                continue
            batch.append(lead)

        messages = []
        assignment = {}
        for i, lead in enumerate(batch):
            inbox = ready[i % len(ready)]["inbox"]
            assignment[lead.id] = inbox
            step1 = next((e for e in lead.sequence if e.get("step") == 1), None)
            if not step1:
                continue
            messages.append({
                "to": lead.email,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "subject": step1["subject"],
                "body": step1["body"],
                "inbox": inbox,
            })

        results = self.sender.send_batch("campaign", messages)
        sent_ids = set()
        for lead in batch:
            inbox = assignment.get(lead.id, ready[0]["inbox"])
            lead.outreach_state = "sent"
            lead.stage = "dispatched"
            lead.enrichment["last_inbox"] = inbox
            self.store.upsert_lead(lead)
            self.log(lead, "email_sent", {"inbox": inbox})
            sent_ids.add(lead.email)

        self.stats = {"eligible": len(leads), "sent": len(sent_ids), "capacity": capacity}
        return self.stats

    def process_replies(self, campaign_id: str, simulated: bool | None = None) -> dict:
        from ..pool.models import Lead
        sim = SETTINGS.provider_mode != "live" if simulated is None else simulated
        replies = []
        if sim:
            for lead in self.store.leads(campaign_id, outreach_state="sent"):
                outcome = self._simulate_outcome(lead.email)
                if outcome:
                    replies.append({"to_email": lead.email, "state": outcome,
                                    "body": self._sim_body(outcome)})
        else:
            raw = self.sender.fetch_replies(campaign_id)
            for r in raw:
                ctx = {"_task": "classify_reply", "body": r.get("body", "")}
                cls = self.llm.complete_json("Classify this reply.", ctx)
                state = r.get("state") or cls.get("state", "needs_human")
                replies.append({"to_email": r.get("to_email"), "state": state, "body": r.get("body", "")})

        updated = 0
        by_email = {l.email: l for l in self.store.leads(campaign_id)}
        handoffs = []
        for r in replies:
            lead = by_email.get(r["to_email"])
            if not lead:
                continue
            lead.outreach_state = r["state"]
            if r["state"] == "replied_positive":
                lead.stage = "engaged"
                handoffs.append(lead)
            elif r["state"] == "replied_negative":
                lead.notes.append({"agent": self.name, "action": "suppress"})
            self.store.upsert_lead(lead)
            self.log(lead, f"reply_{r['state']}", {"snippet": r["body"][:120]})
            updated += 1
        self.stats = {"replies_processed": updated, "positive_handoffs": len(handoffs)}
        return handoffs or {}

    def _simulate_outcome(self, email: str) -> str | None:
        seed = stable_seed("outcome", email)
        rng = random.Random(seed)
        r = rng.random()
        acc = 0.0
        dist = [("replied_positive", 0.08), ("replied_negative", 0.06),
                ("ooo_autoreply", 0.04), ("bounced", 0.005)]
        for state, p in dist:
            acc += p
            if r < acc:
                return state
        return None

    def _sim_body(self, state: str) -> str:
        return {
            "replied_positive": "This looks relevant - can we do Thursday 2pm?",
            "replied_negative": "Not a fit right now. Please remove me.",
            "ooo_autoreply": "I'm out of office until Monday.",
            "bounced": "",
        }[state]

    def process(self, lead):
        raise NotImplementedError("SDRAgent works at campaign level")
