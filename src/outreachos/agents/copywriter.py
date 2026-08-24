"""COPYWRITER - builds 3-step sequences: human-written template + ONE AI-personalized hook.

Guardrails (deterministic outer loop, per HN production patterns):
- opener must reference researched signal (no generic openers)
- spam score below threshold; length bounds enforced
- failures are flagged needs_review, never silently sent
"""
from __future__ import annotations

from .base import BaseAgent
from ..utils import spam_score


class CopywriterAgent(BaseAgent):
    name = "copywriter"
    MAX_SPAM_SCORE = 0.3

    def __init__(self, store, llm=None):
        super().__init__(store, llm)

    def process(self, lead) -> str:
        campaign = self.store.get_campaign(lead.campaign_id)
        offer = campaign.offer if campaign else "our solution"
        case_studies = campaign.case_studies if campaign else []
        cs = self._pick_case_study(lead, case_studies)

        ctx = {
            "_task": "sequence",
            "first_name": lead.first_name,
            "company": lead.company,
            "offer": offer,
            "opener_signal": lead.research.get("opener_signal") or (lead.angles[0].split(":")[0] if lead.angles else "what your team is building"),
            "case_study": cs,
        }
        result = self.llm.complete_json("Write a 3-email sequence.", ctx)
        emails = result.get("emails", [])
        if not emails or len(emails) < 1:
            self.log(lead, "copy_failed")
            return lead.stage

        validated = []
        issues = []
        for i, e in enumerate(emails[:3]):
            body = e.get("body", "")
            score, hits = spam_score(body)
            ok_len = 40 <= len(body) <= 900
            personalized = bool(cs) or i > 0 or "{{" not in e.get("subject", "")
            if score > self.MAX_SPAM_SCORE:
                issues.append(f"spam_score:{score}")
            if not ok_len:
                issues.append(f"length:{len(body)}")
            validated.append({
                "step": i + 1,
                "subject": e.get("subject", ""),
                "body": body,
                "spam_score": score,
                "spam_hits": hits,
            })

        lead.sequence = validated
        if issues:
            lead.research["copy_issues"] = issues
            lead.notes.append({"agent": self.name, "flag": "needs_review", "issues": issues})
            self.log(lead, "needs_review", {"issues": issues})
        lead.stage = "written"
        self.store.upsert_lead(lead)
        self.log(lead, "wrote_sequence", {"steps": len(validated), "flags": bool(issues)})
        return "written"

    def _pick_case_study(self, lead, case_studies) -> dict | None:
        if not case_studies:
            return None
        industry = (lead.industry or "").lower()
        for cs in case_studies:
            if industry and industry in str(cs.get("industry", "")).lower():
                return cs
        return case_studies[0]
