"""NETWORKER - parallel LinkedIn social-selling cadence.

Cadence: Day1 profile view -> Day2 post like -> Day3 connect w/ note -> Day5 message.
In dry-run mode steps are scheduled and logged; live mode requires a LinkedIn
automation adapter (Playwright bot or PhantomBuster-style API).
"""
from __future__ import annotations

from .base import BaseAgent


CADENCE = [
    {"step": 1, "day_offset": 0, "action": "view_profile"},
    {"step": 2, "day_offset": 1, "action": "like_recent_post"},
    {"step": 3, "day_offset": 2, "action": "connect_with_note"},
    {"step": 4, "day_offset": 5, "action": "send_message"},
]


class NetworkerAgent(BaseAgent):
    name = "networker"
    MAX_CONNECTIONS_PER_DAY = 20

    def __init__(self, store, llm=None, executor=None):
        super().__init__(store, llm)
        self.executor = executor

    def schedule(self, leads) -> dict:
        scheduled = 0
        daily_budget = self.MAX_CONNECTIONS_PER_DAY
        for lead in leads[:daily_budget]:
            if not lead.linkedin_url:
                continue
            note = ""
            if lead.angles:
                note = lead.angles[-1][:280]
            plan = [{"step": s["step"], "day_offset": s["day_offset"], "action": s["action"]}
                    for s in CADENCE]
            if self.executor:
                try:
                    self.executor.execute_step(plan[0], lead.to_dict(), note)
                except Exception as e:
                    self.log(lead, "linkedin_error", {"error": str(e)})
                    continue
            lead.outreach_state = "queued_linkedin" if lead.outreach_state == "new" else lead.outreach_state
            lead.enrichment["linkedin_cadence"] = plan
            self.store.upsert_lead(lead)
            self.log(lead, "linkedin_scheduled", {"steps": len(plan), "note_preview": note[:80]})
            scheduled += 1
        self.stats = {"scheduled": scheduled, "budget_cap": daily_budget}
        return self.stats

    def process(self, lead):
        raise NotImplementedError("NetworkerAgent works at campaign level via schedule()")
