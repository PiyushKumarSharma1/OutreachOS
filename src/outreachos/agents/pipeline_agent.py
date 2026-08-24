"""PIPELINE - converts positive replies into booked meetings + pre-call briefs.

On a positive reply: drafts the meeting ask, generates a pre-call brief
(everything Profiler learned), marks lead booked, and emits a CRM-sync event.
"""
from __future__ import annotations

from .base import BaseAgent


class PipelineAgent(BaseAgent):
    name = "pipeline"

    def __init__(self, store, llm=None):
        super().__init__(store, llm)

    def process_positive_replies(self, campaign_id: str) -> list[dict]:
        briefs = []
        engaged = self.store.leads(campaign_id, outreach_state="replied_positive")
        for lead in engaged:
            if any(n.get("flag") == "injection_suspected" for n in lead.notes):
                self.store.log_event(lead.id, lead.campaign_id, "security",
                                     "held_for_review", {"reason": "injection_suspected"})
                continue
            brief = self._build_brief(lead)
            lead.notes.append({"agent": self.name, "type": "pre_call_brief", "brief": brief})
            lead.outreach_state = "booked"
            lead.stage = "booked"
            self.store.upsert_lead(lead)
            self.log(lead, "meeting_booked", {"brief_generated": True})
            self.log(lead, "crm_sync", {"stage": "Meeting Booked"})
            briefs.append({"lead_id": lead.id, "prospect": lead.full_name,
                           "company": lead.company, "brief": brief})
        self.stats = {"booked": len(briefs)}
        return briefs

    def _build_brief(self, lead) -> dict:
        ctx = dict(lead.to_dict())
        ctx["_task"] = "brief"
        ctx["full_name"] = lead.full_name
        result = self.llm.complete_json("Generate a pre-call sales brief.", ctx)
        return result.get("pre_call_brief", {
            "prospect": f"{lead.full_name} - {lead.title} @ {lead.company}",
            "context": [f"Trigger: {lead.trigger_signal or 'none'}"],
        })

    def process(self, lead):
        raise NotImplementedError("PipelineAgent works at campaign level")
