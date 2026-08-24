"""HUNTER - sources raw leads matching the client ICP and detects trigger signals."""
from __future__ import annotations

from .base import BaseAgent
from ..pool.models import Lead
from ..providers.base import build


class HunterAgent(BaseAgent):
    name = "hunter"

    def __init__(self, store, llm=None, source=None):
        super().__init__(store, llm)
        self.source = source or build("leadsource")

    def hunt(self, campaign, limit: int = 100) -> list[Lead]:
        icp_d = campaign.icp.to_dict()
        raw = self.source.source_leads(icp_d, limit * 2)
        existing = {f"{l.domain}|{l.email}".lower() for l in self.store.leads(campaign.id)}
        created: list[Lead] = []
        for r in raw:
            key = f"{r.get('domain', '')}|{r.get('email', '')}".lower()
            if key in existing:
                continue
            if not self._matches_icp(r, icp_d):
                continue
            lead = Lead(
                campaign_id=campaign.id,
                first_name=r.get("first_name", ""),
                last_name=r.get("last_name", ""),
                title=r.get("title", ""),
                company=r.get("company", ""),
                domain=(r.get("domain") or "").lower(),
                email=r.get("email", ""),
                linkedin_url=r.get("linkedin_url", ""),
                location=r.get("location", ""),
                industry=r.get("industry", ""),
                headcount=int(r.get("headcount") or 0),
                source=r.get("source", self.name),
            )
            self.store.upsert_lead(lead)
            existing.add(key)
            created.append(lead)
            if len(created) >= limit:
                break
        self.stats = {"requested": limit, "hunted": len(created)}
        self.log_lead_batch(created)
        return created

    def _matches_icp(self, r: dict, icp: dict) -> bool:
        industries = [i.lower() for i in icp.get("industries", [])]
        if industries and r.get("industry", "").lower() not in industries:
            return False
        hc = int(r.get("headcount") or 0)
        if hc and not (icp.get("headcount_min", 0) <= hc <= icp.get("headcount_max", 10**9)):
            return False
        titles = [t.lower() for t in icp.get("titles", [])]
        if titles:
            t = r.get("title", "").lower()
            if not any(kw in t for kw in [w.lower() for w in titles]):
                pass
        geos = [g.lower() for g in icp.get("geos", [])]
        if geos:
            loc = r.get("location", "").lower()
            if loc and not any(g in loc for g in geos):
                pass
        return True

    def log_lead_batch(self, leads):
        for l in leads:
            self.log(l, "hunted", {"source": l.source, "company": l.company})

    def process(self, lead):
        raise NotImplementedError("HunterAgent works at campaign level via hunt()")
