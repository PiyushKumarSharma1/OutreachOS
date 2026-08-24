"""Sub-agents: specialized workers invoked by primary agents.

- ResearchSubAgent: multi-query deep research plan per lead (Profiler calls)
- ObjectionSubAgent: objection classification + tailored draft responses
"""
from __future__ import annotations

from ..llm.client import LLMClient, get_llm
from ..utils import stable_seed


class ResearchSubAgent:
    """Deep-research worker. Produces structured findings the Profiler
    turns into angles. Mock mode synthesizes deterministic plausible research
    from the lead's own attributes (zero external calls)."""

    name = "researcher"

    QUERIES = [
        ("company_news", "Recent news or announcements about {company}"),
        ("tech_stack", "Technologies {company} uses or recently adopted"),
        ("pain_points", "Common scaling challenges for {title} teams in {industry}"),
        ("social_activity", "{full_name} recent posts, talks, or interviews"),
    ]

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or get_llm()

    def research(self, lead: dict) -> dict:
        seed = stable_seed("research", lead.get("email", ""), lead.get("company", ""))
        import random
        rng = random.Random(seed)
        findings = {}
        for key, template in self.QUERIES:
            q = template.format(company=lead.get("company", "the company"),
                                title=lead.get("title", "go-to-market"),
                                industry=lead.get("industry", "B2B"),
                                full_name=lead.get("full_name", "the prospect"))
            findings[key] = {
                "query": q,
                "finding": self._synth_finding(key, lead, rng),
                "confidence": round(rng.uniform(0.6, 0.95), 2),
            }
        return {"findings": findings,
                "research_quality": round(sum(f["confidence"] for f in findings.values()) / len(findings), 2)}

    def _synth_finding(self, key: str, lead: dict, rng) -> str:
        company = lead.get("company", "the company")
        industry = lead.get("industry", "B2B")
        bank = {
            "company_news": f"{company} expanded into two new verticals this quarter per their blog",
            "tech_stack": f"{company} runs a modern {industry} stack; recently added analytics tooling",
            "pain_points": f"Teams like {company}'s report manual pipeline work eating 8+ hrs/week",
            "social_activity": f"Active on LinkedIn discussing {industry} growth tactics",
        }
        return bank.get(key, "No notable findings")


class ObjectionSubAgent:
    """Classifies objections in negative/neutral replies and drafts a tailored
    response. DRAFTS ONLY - never auto-sent (policy: human approves)."""

    name = "objection_handler"

    OBJECTION_TYPES = ["price", "timing", "authority", "competitor", "status_quo", "unknown"]

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or get_llm()

    def classify(self, body: str) -> dict:
        ctx = {"_task": "classify_reply", "body": body or ""}
        base = self.llm.complete_json("Classify this reply.", ctx)
        text = (body or "").lower()
        if any(k in text for k in ["too expensive", "budget", "cost", "price", "cheaper"]):
            otype = "price"
        elif any(k in text for k in ["not right now", "next quarter", "later", "busy", "timing"]):
            otype = "timing"
        elif any(k in text for k in ["not my decision", "talk to", "my team handles"]):
            otype = "authority"
        elif any(k in text for k in ["already use", "we work with", "current vendor"]):
            otype = "competitor"
        elif any(k in text for k in ["not interested", "no thanks", "not a fit"]):
            otype = "status_quo"
        else:
            otype = "unknown"
        return {"objection_type": otype, "reply_state": base.get("state", "replied_negative")}

    def draft_response(self, objection_type: str, lead: dict) -> dict:
        drafts = {
            "price": f"Totally understand on budget. Most teams start with the performance-based plan - you only pay on booked meetings, so there's no fixed cost to evaluate. Want the one-pager?",
            "timing": f"Fair - bad timing is real. Want me to circle back in {lead.get('follow_up_window', '6 weeks')}? I'll send one nudge then go quiet.",
            "authority": f"Makes sense - who owns growth experiments at {lead.get('company', 'your company')}? Happy to send something they can skim in 60 seconds instead.",
            "competitor": f"Good to know you've got coverage. Teams usually switch when reply rates dip below ~2%. Happy to do a free deliverability audit of your current setup - no pitch.",
            "status_quo": f"No problem at all. One thing before I go: if pipeline targets increase next quarter, this is exactly the lever that helps. Mind if I check back in a quarter?",
            "unknown": f"Appreciate the honesty. I'll close the loop here - if anything changes, reply to this thread and it comes straight to me.",
        }
        return {"objection_type": objection_type,
                "draft": drafts.get(objection_type, drafts["unknown"]),
                "status": "needs_human_approval"}
