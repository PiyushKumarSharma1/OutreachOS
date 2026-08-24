"""Sequence engine v2: conditional multi-step cadences with stop rules.

Step spec:
  {"step": 1, "day_offset": 0, "channel": "email", "stop_on_reply": true}
  {"step": 2, "day_offset": 3, "channel": "email", "condition": "no_reply"}
  {"step": 3, "day_offset": 5, "channel": "linkedin", "condition": "connected"}

Engine responsibilities:
- compute due steps for a lead given first_touch timestamp
- stop-on-reply: any replied_* state halts future steps
- channel routing: email steps -> SDR, linkedin steps -> Networker
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .pool.store import PoolStore

REPLIED_STATES = {"replied_positive", "replied_negative", "ooo_autoreply", "booked"}
TERMINAL_STATES = REPLIED_STATES | {"stopped", "bounced"}


class SequenceEngine:
    def __init__(self, store: PoolStore):
        self.store = store

    @staticmethod
    def default_sequence() -> list[dict]:
        return [
            {"step": 1, "day_offset": 0, "channel": "email", "stop_on_reply": True},
            {"step": 2, "day_offset": 3, "channel": "email", "condition": "no_reply"},
            {"step": 3, "day_offset": 7, "channel": "linkedin", "condition": "no_reply"},
            {"step": 4, "day_offset": 12, "channel": "email", "condition": "no_reply", "type": "breakup"},
        ]

    def plan(self, sequence: list[dict] | None = None) -> list[dict]:
        return sequence or self.default_sequence()

    def first_touch_at(self, lead) -> datetime | None:
        ts = lead.enrichment.get("first_touch_at")
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return None

    def mark_sent(self, lead, step_no: int):
        if not lead.enrichment.get("first_touch_at"):
            lead.enrichment["first_touch_at"] = datetime.now(timezone.utc).isoformat()
        lead.enrichment["last_step_sent"] = step_no

    def due_steps(self, lead, sequence: list[dict] | None = None) -> list[dict]:
        """Steps that should fire now for this lead."""
        if lead.outreach_state in TERMINAL_STATES:
            return []
        start = self.first_touch_at(lead)
        plan = self.plan(sequence)
        last = lead.enrichment.get("last_step_sent", 0)
        now = datetime.now(timezone.utc)
        due = []
        for s in plan:
            if s["step"] <= last:
                continue
            if s.get("condition") == "no_reply" and lead.outreach_state in REPLIED_STATES:
                continue
            if start is None:
                due.append(s) if s["step"] == 1 else None
                continue
            fire_at = start + timedelta(days=s["day_offset"])
            if now >= fire_at:
                due.append(s)
        return due

    def next_step(self, lead, sequence: list[dict] | None = None) -> dict | None:
        due = self.due_steps(lead, sequence)
        return due[0] if due else None

    def progress(self, lead, sequence: list[dict] | None = None) -> dict:
        plan = self.plan(sequence)
        last = lead.enrichment.get("last_step_sent", 0)
        stopped = lead.outreach_state in TERMINAL_STATES
        return {"total": len(plan), "completed": last, "stopped": stopped,
                "state": lead.outreach_state}
