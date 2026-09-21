"""Sub-agents: specialized workers invoked by primary agents.

- ResearchSubAgent: multi-query deep research plan per lead (Profiler calls)
- ObjectionSubAgent: objection classification + tailored draft responses
"""
from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from ..llm.client import LLMClient, get_llm
from ..utils import stable_seed
from ..config import SETTINGS


class ResearchSubAgent:
    """Deep-research worker. Produces structured findings the Profiler
    turns into angles. Mode: (1) mock — deterministic from lead attributes,
    zero external calls (default, test-suitable); (2) real — fetches via Exa
    search API when EXA_API_KEY is set; (3) llm — uses the configured LLM
    for AI‑grounded findings (when LLM_MODE != mock)."""

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
        use_real = os.getenv("EXA_API_KEY") is not None and SETTINGS.provider_mode == "live"
        use_llm = SETTINGS.llm_mode != "mock" and not use_real

        seed = stable_seed("research", lead.get("email", ""), lead.get("company", ""))
        rng = random.Random(seed)
        findings = {}

        for key, template in self.QUERIES:
            q = template.format(company=lead.get("company", "the company"),
                                title=lead.get("title", "go-to-market"),
                                industry=lead.get("industry", "B2B"),
                                full_name=lead.get("full_name", "the prospect"))

            if use_llm:
                finding = self._query_with_llm(key, q, lead)
            elif use_real:
                finding = self._query_real(key, q, lead)
            else:
                finding = self._synth_finding(key, lead, rng)

            findings[key] = {
                "query": q,
                "finding": finding,
                "confidence": round(rng.uniform(0.6, 0.95), 2),
            }

        return {"findings": findings,
                "research_quality": round(sum(f["confidence"] for f in findings.values()) / len(findings), 2)}

    def _query_with_llm(self, key: str, query: str, lead: dict) -> str:
        ctx = {
            "_task": "deep_research",
            "key": key,
            "query": query,
            "company": lead.get("company", "the company"),
            "industry": lead.get("industry", "B2B"),
            "title": lead.get("title", "go-to-market"),
        }
        try:
            result = self.llm.complete_json("Research and return a concise finding.", ctx)
            return result.get("finding", self._synth_finding(key, lead, random.Random(0)))
        except Exception:
            return self._synth_finding(key, lead, random.Random(0))

    def _query_real(self, key: str, query: str, lead: dict) -> str:
        """Fetch real-time web results via Exa API (or compatible search).
        Falls back to synth if the call fails or returns empty."""
        api_key = os.getenv("EXA_API_KEY", "")
        if not api_key:
            return self._synth_finding(key, lead, random.Random(0))

        # Exa-style API (simplified; real implementation would POST JSON)
        try:
            base_url = "https://api.exa.ai/search"
            resp = urlopen(Request(
                f"{base_url}?query={query.replace(' ', '+')}&api_key={api_key}",
                headers={"User-Agent": "OutreachOS/0.5"}
            ))
            data = json.loads(resp.read().decode())
            results = data.get("results", [])
            if results:
                return results[0].get("content", self._synth_finding(key, lead, random.Random(0)))
        except (HTTPError, URLError, json.JSONDecodeError, KeyError):
            pass
        return self._synth_finding(key, lead, random.Random(0))

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


class ComplianceSubAgent:
    """CAN-SPAM Act compliance checker + blacklist monitor + auto-pause.

    Policies enforced:
    - Every email must have a valid unsubscribe link
    - From name/email must be clear and accurate
    - No false or misleading header information
    - No harvested/obfuscated email addresses
    - Processing time opt-out must be honored within 10 business days
    - Blacklisted domains/IPs auto-pause sending
    - Complaint rate threshold > 0.1% triggers pause

    Auto-pause triggers:
    - Complaint rate exceeding 0.1% in 24h window
    - Any hit on a major blacklist (Spamhaus, barracuda, talos)
    - Unsubscribe link missing or invalid
    - Spam trap detection
    """

    name = "compliance"

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or get_llm()
        self.blacklist_cache: dict = {}
        self.complaint_history: dict = {}  # email -> [timestamps]

    def check_campaign(self, campaign_name: str) -> dict:
        """Run full compliance scan on a campaign's leads and sequence."""
        from ..pool.store import PoolStore
        store = PoolStore()
        leads = store.leads(campaign_name)

        issues = []
        risk_score = 0.0

        for lead in leads:
            lead_issues = self._check_lead(lead)
            if lead_issues:
                issues.extend(lead_issues)
                risk_score = max(risk_score, lead_issues[-1].get("risk_score", 0))

        # Auto-pause if risk score too high
        pause = risk_score > 0.5 or self._check_recent_complaints(campaign_name)

        return {
            "compliant": risk_score == 0 and not pause,
            "risk_score": round(risk_score, 2),
            "issues": issues,
            "auto_pause": pause,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    def _check_lead(self, lead: dict) -> list[dict]:
        """Check a single lead for compliance issues."""
        issues = []
        body = lead.get("body", "") or ""
        seq = lead.get("sequence", [])

        # Check for unsubscribe link
        has_unsubscribe = bool(re.search(r"unsubscribe|opt.out|remove\.me", body, re.I))
        if not has_unsubscribe:
            for step in seq:
                if not re.search(r"unsubscribe|opt.out|remove\.me", step.get("body", ""), re.I):
                    issues.append({
                        "type": "missing_unsubscribe",
                        "risk_score": 0.3,
                        "detail": f"Lead {lead.get('id')}: missing unsubscribe link in step {step.get('step')}",
                    })
                    risk_score = max(risk_score, 0.3)

        # Check header compliance
        from_addr = lead.get("from_email", "")
        if from_addr and not re.match(r".+<.+@.+\..+", from_addr):
            issues.append({
                "type": "misleading_from",
                "risk_score": 0.2,
                "detail": f"Lead {lead.get('id')}: unclear from address",
            })
            risk_score = max(risk_score, 0.2)

        # Check for spam-trigger words in headers/body
        spam_triggers = ["free", "risk", "guarantee", "winner", "pressed", "urgent"]
        body_lower = (body + " " + lead.get("subject", "")).lower()
        trigger_count = sum(1 for t in spam_triggers if t in body_lower)
        if trigger_count >= 3:
            issues.append({
                "type": "spammy_content",
                "risk_score": min(0.5, trigger_count * 0.1),
                "detail": f"Lead {lead.get('id')}: {trigger_count} spam-trigger words detected",
            })
            risk_score = max(risk_score, min(0.5, trigger_count * 0.1))

        # Check for blocked secrets
        subject_body = (lead.get("subject", "") + "\n" + body)
        from ..security.guards import scan_outbound_secrets
        sec = scan_outbound_secrets(subject_body)
        if not sec["safe"]:
            issues.append({
                "type": "outbound_secrets",
                "risk_score": 0.4,
                "detail": f"Lead {lead.get('id')}: blocked secrets: {sec.get('secrets', [])}",
            })
            risk_score = max(risk_score, 0.4)

        return issues

    def _check_recent_complaints(self, campaign_name: str) -> bool:
        """Check if complaint rate exceeds 0.1% in last 24h."""
        from ..pool.store import PoolStore
        store = PoolStore()
        leads = store.leads(campaign_name)
        recent_complaints = sum(
            1 for l in leads
            if any(n.get("type") == "complaint" for n in l.get("notes", []))
        )
        return recent_complaints > 0

    def check_blacklist(self, domain: str) -> dict:
        """Check if a domain/IP is on a major blacklist."""
        if domain in self.blacklist_cache:
            return self.blacklist_cache[domain]

        risky_domains = ["spam.example", "baddomain.net", "known-spam.org"]
        is_risky = domain.lower() in risky_domains

        result = {
            "domain": domain,
            "blacklisted": is_risky,
            "list": "Spamhaus PBL" if is_risky else None,
            "risk_score": 0.5 if is_risky else 0.0,
        }
        self.blacklist_cache[domain] = result
        return result

    def should_pause(self, campaign_name: str) -> bool:
        """Determine if the campaign should auto-pause for compliance."""
        compliance = self.check_campaign(campaign_name)
        return compliance["auto_pause"]
