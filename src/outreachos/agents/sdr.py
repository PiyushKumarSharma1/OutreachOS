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

    def __init__(self, store, llm=None, sender=None, inboxes=None, compliance=None):
        super().__init__(store, llm)
        self.sender = sender or build("sender")
        self.inboxes = inboxes or DEFAULT_INBOX_POOL
        self.compliance = compliance

    def ready_inboxes(self) -> list[dict]:
        return [i for i in self.inboxes if i.get("warmup_days", 0) >= SETTINGS.warmup_min_days]

    def dispatch(self, leads) -> dict:
        ready = self.ready_inboxes()
        if not ready:
            self.stats = {"queued": 0, "reason": "no_warmed_inboxes"}
            return self.stats
        from ..security.guards import scan_outbound_secrets
        cap = SETTINGS.daily_send_cap_per_inbox
        capacity = len(ready) * cap
        batch = []
        blocked_secrets = 0
        for lead in leads:
            if len(batch) >= capacity:
                break
            if lead.email_status not in ("verified", "risky_catchall_confirmed"):
                continue
            if any(n.get("flag") == "needs_review" for n in lead.notes):
                continue
            step1 = next((e for e in lead.sequence if e.get("step") == 1), None)
            if not step1:
                continue
            sec = scan_outbound_secrets(step1["subject"] + "\n" + step1["body"])
            if not sec["safe"]:
                blocked_secrets += 1
                lead.notes.append({"agent": "security", "flag": "outbound_blocked",
                                   "secrets": sec["secrets"]})
                self.store.upsert_lead(lead)
                self.store.log_event(lead.id, lead.campaign_id, "security",
                                     "outbound_blocked", {"secrets": sec["secrets"]})
                continue
            body = step1["body"]
            if self.compliance:
                body = self.compliance.apply_footer(body, lead.email, lead.campaign_id)
            batch.append((lead, {**step1, "body": body}))

        messages = []
        assignment = {}
        for i, (lead, step1) in enumerate(batch):
            inbox = ready[i % len(ready)]["inbox"]
            assignment[lead.id] = inbox
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
        for lead, _ in batch:
            inbox = assignment.get(lead.id, ready[0]["inbox"])
            lead.outreach_state = "sent"
            lead.stage = "dispatched"
            lead.enrichment["last_inbox"] = inbox
            self.store.upsert_lead(lead)
            self.log(lead, "email_sent", {"inbox": inbox})
            sent_ids.add(lead.email)

        self.stats = {"eligible": len(leads), "sent": len(sent_ids),
                      "capacity": capacity, "blocked_secrets": blocked_secrets}
        return self.stats

    def process_replies(self, campaign_id: str, simulated: bool | None = None) -> dict:
        from ..pool.models import Lead
        from ..security.guards import InjectionGuard
        sim = SETTINGS.provider_mode != "live" if simulated is None else simulated
        guard = InjectionGuard()
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
                safe_body = guard.inspect_reply(r.get("body", ""))["sanitized_body"]
                ctx = {"_task": "classify_reply", "body": safe_body}
                cls = self.llm.complete_json("Classify this reply.", ctx)
                state = r.get("state") or cls.get("state", "needs_human")
                replies.append({"to_email": r.get("to_email"), "state": state,
                                "body": r.get("body", "")})

        by_email = {l.email: l for l in self.store.leads(campaign_id)}
        handoffs = []
        flagged = 0
        for r in replies:
            lead = by_email.get(r["to_email"])
            if not lead:
                continue
            sec = guard.inspect_reply(r.get("body", ""))
            if r["state"] == "replied_positive" and not sec["safe"]:
                flagged += 1
                lead.notes.append({"agent": "security", "flag": "injection_suspected",
                                   "risk_score": sec["risk_score"], "matches": sec["matches"]})
                self.store.upsert_lead(lead)
                self.store.log_event(lead.id, lead.campaign_id, "security",
                                     "injection_flagged",
                                     {"risk_score": sec["risk_score"],
                                      "labels": [m["label"] for m in sec["matches"]]})
                continue
            lead.outreach_state = r["state"]
            if r["state"] == "replied_positive":
                lead.stage = "engaged"
                handoffs.append(lead)
            elif r["state"] == "replied_negative":
                lead.notes.append({"agent": self.name, "action": "suppress"})
            self.store.upsert_lead(lead)
            self.log(lead, f"reply_{r['state']}", {"snippet": (sec["sanitized_body"] or r["body"])[:120]})
        self.stats = {"replies_processed": len(replies) - flagged,
                      "injections_flagged": flagged, "positive_handoffs": len(handoffs)}
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
