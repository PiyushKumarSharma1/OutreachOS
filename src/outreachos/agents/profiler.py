"""PROFILER - deep enrichment + AI research angles (the intelligence layer)."""
from __future__ import annotations

from .base import BaseAgent
from ..llm.client import get_llm


class ProfilerAgent(BaseAgent):
    name = "profiler"

    def __init__(self, store, llm=None, enricher=None):
        super().__init__(store, llm or get_llm())
        self.enricher = enricher

    def process(self, lead) -> str:
        if lead.stage == "dropped":
            return "dropped"

        if self.enricher:
            try:
                person = self.enricher.enrich_person(lead.to_dict())
                if person:
                    lead.enrichment.update({k: v for k, v in person.items() if v})
            except Exception as e:
                self.log(lead, "enrichment_error", {"error": str(e)})

        ctx = {
            "_task": "angles",
            "email": lead.email,
            "company": lead.company,
            "title": lead.title,
            "industry": lead.industry,
            "trigger_signal": lead.trigger_signal,
        }
        result = self.llm.complete_json("Generate 3 distinct outreach angles for this prospect.", ctx)
        angles = [a for a in result.get("angles", []) if isinstance(a, str) and len(a) > 10][:3]
        if not angles:
            self.log(lead, "profiler_failed")
            return lead.stage
        lead.angles = angles
        lead.research["angle_confidence"] = result.get("_confidence", 0.8)
        lead.stage = "profiled"
        self.store.upsert_lead(lead)
        self.log(lead, "profiled", {"n_angles": len(angles)})
        return "profiled"
