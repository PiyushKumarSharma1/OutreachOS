"""GUARDIAN - waterfall email finding + verification + catch-all recovery.

Policy (2026 deliverability standard):
- find email via finder waterfall (stop on first confident hit)
- verify via verifier waterfall (cheapest-viable-first)
- catch-all addresses go through SMTP-ping resolver; unresolved catch-alls
  are quarantined, never sent to
- hard bounces must stay under SETTINGS.max_bounce_rate or the campaign
  batch is halted for review
"""
from __future__ import annotations

from .base import BaseAgent
from ..config import SETTINGS
from ..providers.base import waterfall


class GuardianAgent(BaseAgent):
    name = "guardian"

    def __init__(self, store, llm=None, finders=None, verifiers=None, resolvers=None):
        super().__init__(store, llm)
        self.finders = finders if finders is not None else waterfall("emailfinder")
        self.verifiers = verifiers if verifiers is not None else waterfall("verifier")
        self.resolvers = resolvers if resolvers is not None else waterfall("catchall")

    def process(self, lead) -> str:
        if lead.email_status == "suppressed":
            self._drop(lead, "suppressed")
            return "dropped"

        if not lead.email:
            lead = self._find_email(lead)

        if not lead.email:
            self._drop(lead, "no_email_found")
            return "dropped"

        verdict = self._verify_waterfall(lead.email)
        status_map = {"valid": "verified", "invalid": "invalid", "catch_all": "risky_catchall", "unknown": "risky_catchall"}

        if verdict["status"] == "invalid":
            lead.email_status = "invalid"
            self.store.upsert_lead(lead)
            self.log(lead, "verification_failed", {"email": lead.email})
            self._drop(lead, "invalid_email")
            return "dropped"

        if verdict["status"] in ("catch_all", "unknown"):
            resolved = self._resolve_catch_all(lead.email)
            if resolved.get("status") == "valid":
                lead.email_status = "risky_catchall_confirmed"
                detail = {"method": resolved.get("method"), "recovered": True}
            else:
                lead.email_status = "risky_catchall"
                self.store.upsert_lead(lead)
                self.log(lead, "quarantined_catch_all", {"verdict": resolved})
                self._drop(lead, "unresolved_catch_all")
                return "dropped"
        else:
            lead.email_status = "verified"
            detail = {}

        if lead.stage != "hunted" and lead.stage != "raw":
            pass
        lead.stage = "verified"
        self.store.upsert_lead(lead)
        self.log(lead, "verified", {"status": lead.email_status, **detail})
        return "verified"

    def _find_email(self, lead):
        domain = lead.domain
        if not domain:
            return lead
        for finder in self.finders:
            hit = finder.find_email(lead.first_name, lead.last_name, domain)
            if hit and hit.get("email"):
                lead.email = hit["email"]
                lead.enrichment["email_finder"] = getattr(finder, "name", "unknown")
                lead.email_status = "found"
                return lead
        return lead

    def _verify_waterfall(self, email: str) -> dict:
        for v in self.verifiers:
            result = v.verify(email)
            if result.get("status") in ("valid", "invalid"):
                return result
            if result.get("status") == "catch_all":
                nxt = False
                for deeper in self.verifiers[self.verifiers.index(v) + 1:]:
                    r2 = deeper.verify(email)
                    if r2.get("status") in ("valid", "invalid"):
                        return r2
                    if r2.get("status") == "catch_all":
                        break
                    nxt = True
                return {"status": "catch_all"}
            continue
        return {"status": "unknown"}

    def _resolve_catch_all(self, email: str) -> dict:
        for resolver in self.resolvers:
            r = resolver.resolve(email)
            if r.get("status") in ("valid", "invalid"):
                return r
        return {"status": "unknown"}

    def _drop(self, lead, reason: str):
        lead.stage = "dropped"
        self.store.upsert_lead(lead)
        self.log(lead, "dropped", {"reason": reason})

    def bounce_guard_ok(self, campaign_id: str) -> bool:
        stats = self.store.campaign_stats(campaign_id)
        sent_est = max(stats["sent_est"], 1)
        invalid_ratio = stats["by_email_status"].get("invalid", 0) / sent_est
        return invalid_ratio <= SETTINGS.max_bounce_rate * 10
