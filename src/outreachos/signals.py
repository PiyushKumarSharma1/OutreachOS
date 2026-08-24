"""Intent signals engine: detects trigger events, scores lead intent.

Signals (mock provider deterministic; live adapters slot in):
- funding: company raised money (weight 35)
- hiring: hiring for relevant role (weight 30)
- tech_change: installed/removed relevant tech (weight 25)
- leadership_change: new exec in buyer role (weight 30)
- content_mention: engaged with relevant content (weight 20)

Intent score = sum of signal weights, capped 100. Dispatch prioritizes
high-intent leads (Clay pattern: signal-rich prospects reply 2-4x).
"""
from __future__ import annotations

import random

from .pool.store import PoolStore
from .utils import stable_seed, new_id
from datetime import datetime, timezone

SIGNAL_WEIGHTS = {
    "funding": 35,
    "hiring": 30,
    "tech_change": 25,
    "leadership_change": 30,
    "content_mention": 20,
}


class SignalsEngine:
    def __init__(self, store: PoolStore, provider=None):
        self.store = store
        self.provider = provider

    def detect(self, lead) -> list[dict]:
        """Returns signal dicts for a lead. Uses provider if set, else mock."""
        if self.provider:
            raw = self.provider.signals(lead.domain)
        else:
            raw = self._mock_signals(lead)
        events = []
        for kind in raw:
            if kind in SIGNAL_WEIGHTS:
                events.append({"kind": kind, "weight": SIGNAL_WEIGHTS[kind],
                               "detail": raw[kind] if isinstance(raw, dict) else ""})
        return events

    def _mock_signals(self, lead) -> list[str]:
        seed = stable_seed("sig", lead.domain, lead.company)
        rng = random.Random(seed)
        pool = list(SIGNAL_WEIGHTS)
        n = rng.choices([0, 1, 2], weights=[0.35, 0.45, 0.2])[0]
        return rng.sample(pool, n)

    def score_lead(self, lead) -> int:
        """Detect, persist signal events, return intent score 0-100."""
        events = self.detect(lead)
        score = min(sum(e["weight"] for e in events), 100)
        for e in events:
            self.store.conn.execute(
                "INSERT OR IGNORE INTO signal_events (id, lead_id, kind, detail, detected_at) "
                "VALUES (?,?,?,?,?)",
                (new_id("sig"), lead.id, e["kind"], e["detail"],
                 datetime.now(timezone.utc).isoformat()))
        if events:
            primary = events[0]["kind"]
            lead.trigger_signal = primary.replace("_", " ")
        lead.enrichment["intent_score"] = score
        lead.enrichment["signals"] = [e["kind"] for e in events]
        self.store.conn.commit()
        self.store.upsert_lead(lead)
        return score

    def top_signals(self, campaign_id: str, limit: int = 10) -> list[dict]:
        rows = self.store.conn.execute(
            """SELECT s.kind, COUNT(*) as n FROM signal_events s
               JOIN leads l ON l.id = s.lead_id
               WHERE l.campaign_id = ? GROUP BY s.kind ORDER BY n DESC LIMIT ?""",
            (campaign_id, limit)).fetchall()
        return [dict(r) for r in rows]
