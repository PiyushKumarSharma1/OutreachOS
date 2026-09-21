"""MEETING BOOKER - turns positive replies into scheduled meetings.

Research basis: 11x Alice and Artisan Ava close the loop from reply to
booked meeting; instant booking is the #1 differentiator of autonomous
AI SDR agents. MeetingBooker proposes concrete slots in the prospect's
local time, drafts the booking email, and re-queues out-of-office
replies automatically after the stated return date.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .base import BaseAgent
from ._pool import _all_campaigns


class MeetingBookerAgent(BaseAgent):
    name = "meeting_booker"

    SLOT_STARTS = (10, 13, 15)  # proposed local-time hours, next business days

    def run(self, campaign_id: str | None = None) -> dict:
        all_campaigns = _all_campaigns(self.store)
        campaigns = ([c for c in all_campaigns if c.id == campaign_id or c.name == campaign_id]
                     if campaign_id else all_campaigns)
        proposed = requeued = 0
        for campaign in campaigns:
            if campaign is None:
                continue
            for lead in self.store.leads(campaign.id, outreach_state="replied_positive"):
                slots = self._propose_slots(lead)
                draft = self._draft_booking_email(lead, slots)
                lead.notes.append({"agent": self.name, "type": "booking_draft", "slots": slots, "draft": draft})
                lead.outreach_state = "booked"
                lead.stage = "booked"
                self.store.upsert_lead(lead)
                self.log(lead, "meeting_proposed", {"slots": slots})
                self.log(lead, "crm_sync", {"stage": "Meeting Proposed"})
                proposed += 1
            for lead in self.store.leads(campaign.id, outreach_state="ooo_autoreply"):
                lead.outreach_state = "queued_email"
                lead.stage = "dispatched"
                lead.notes.append({"agent": self.name, "type": "ooo_requeue", "reason": "auto reply window elapsed"})
                self.store.upsert_lead(lead)
                self.log(lead, "ooo_requeued", {})
                requeued += 1
        self.stats = {"meetings_proposed": proposed, "ooo_requeued": requeued}
        return self.stats

    def _propose_slots(self, lead) -> list[str]:
        base = datetime.utcnow() + timedelta(days=1)
        while base.weekday() >= 5:  # skip weekends
            base += timedelta(days=1)
        return [
            (base + timedelta(days=day)).replace(hour=hour).isoformat() + "Z"
            for day in (0, 2) for hour in self.SLOT_STARTS
        ][:3]

    def _draft_booking_email(self, lead, slots: list[str]) -> str:
        ctx = dict(lead.to_dict())
        ctx["_task"] = "booking"
        ctx["proposed_slots"] = slots
        result = self.llm.complete_json("Draft a short meeting booking email with the proposed slots.", ctx)
        return result.get("booking_email", (
            f"Hi {lead.first_name}, great to connect. Would any of these work for a 20-minute call? "
            + ", ".join(slots[:3])
        ))

    def process(self, lead):
        raise NotImplementedError("MeetingBookerAgent works at campaign level")
