"""Live provider adapters. Each activates only when its API key is present.

HTTP calls use stdlib urllib so the core has zero third-party dependencies.
"""
from __future__ import annotations

import json
import os
import urllib.request

from .base import (
    register, LeadSourceProvider, EmailFinderProvider, VerifierProvider,
    CatchAllResolver, SenderProvider,
)


def http_json(url: str, payload: dict | None = None, headers: dict | None = None,
              timeout: int = 30) -> dict:
    data = None
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _key(env: str) -> str:
    return os.getenv(env, "").strip()


@register
class ApolloSource(LeadSourceProvider):
    name = "apollo"
    kinds = ("leadsource",)

    def available(self):
        return bool(_key("APOLLO_API_KEY"))

    def source_leads(self, icp: dict, limit: int) -> list[dict]:
        resp = http_json(
            "https://api.apollo.io/v1/mixed_people/search",
            {
                "api_key": _key("APOLLO_API_KEY"),
                "person_titles": icp.get("titles", []),
                "organization_num_employees_ranges": [f"{icp.get('headcount_min', 10)},{icp.get('headcount_max', 5000)}"],
                "person_locations": icp.get("geos", []),
                "organization_industry_tags": icp.get("industries", []),
                "page": 1,
                "per_page": min(limit, 100),
            },
        )
        people = resp.get("people", [])
        out = []
        for p in people:
            org = p.get("organization") or {}
            out.append({
                "first_name": p.get("first_name", ""),
                "last_name": p.get("last_name", ""),
                "title": p.get("title", ""),
                "company": org.get("name", ""),
                "domain": (org.get("website_url") or "").replace("https://", "").replace("http://", ""),
                "linkedin_url": p.get("linkedin_url", ""),
                "location": p.get("city", "") + ", " + (p.get("state") or p.get("country") or ""),
                "industry": (org.get("industries") or [""])[0] if org.get("industries") else "",
                "headcount": org.get("estimated_num_employees", 0),
                "email": p.get("email", ""),
                "source": self.name,
            })
        return out


@register
class HunterFinder(EmailFinderProvider):
    name = "hunter"
    kinds = ("emailfinder",)

    def available(self):
        return bool(_key("HUNTER_API_KEY"))

    def find_email(self, first_name, last_name, domain):
        url = (f"https://api.hunter.io/v2/email-finder?domain={domain}"
               f"&first_name={first_name}&last_name={last_name}&api_key={_key('HUNTER_API_KEY')}")
        try:
            resp = http_json(url)
            d = resp.get("data", {})
            email = d.get("email")
            score = d.get("score", 0)
            if email and score >= 70:
                return {"email": email, "confidence": round(score / 100, 2)}
        except Exception:
            pass
        return {}


@register
class DropcontactFinder(EmailFinderProvider):
    name = "dropcontact"
    kinds = ("emailfinder",)

    def available(self):
        return bool(_key("DROPCONTACT_API_KEY"))

    def find_email(self, first_name, last_name, domain):
        try:
            resp = http_json("https://api.dropcontact.io/v1/enrich", {
                "key": _key("DROPCONTACT_API_KEY"),
                "first_name": first_name,
                "last_name": last_name,
                "domain": domain,
            })
            d = resp.get("data", {})
            email = d.get("email")
            if email:
                return {"email": email, "confidence": 0.85}
        except Exception:
            pass
        return {}


@register
class ZeroBounceVerifier(VerifierProvider):
    name = "zerobounce"
    kinds = ("verifier",)

    def available(self):
        return bool(_key("ZEROBOUNCE_API_KEY"))

    def verify(self, email):
        url = f"https://api.zerobounce.net/v2/validate?api_key={_key('ZEROBOUNCE_API_KEY')}&email={email}"
        try:
            d = http_json(url)
            status = d.get("status", "unknown")
            mapped = {"valid": "valid", "invalid": "invalid", "catch-all": "catch_all"}.get(status, "unknown")
            return {"status": mapped, "sub_status": d.get("sub_status", "")}
        except Exception:
            return {"status": "unknown"}


@register
class NeverBounceVerifier(VerifierProvider):
    name = "neverbounce"
    kinds = ("verifier",)

    def available(self):
        return bool(_key("NEVERBOUNCE_API_KEY"))

    def verify(self, email):
        try:
            d = http_json("https://api.neverbounce.com/v4/single/check", {
                "key": _key("NEVERBOUNCE_API_KEY"), "email": email,
            })
            result = d.get("result", "unknown")
            mapped = {"valid": "valid", "invalid": "invalid", "catchall": "catch_all"}.get(result, "unknown")
            return {"status": mapped}
        except Exception:
            return {"status": "unknown"}


@register
class ScrubbyCatchAll(CatchAllResolver):
    name = "scrubby"
    kinds = ("catchall",)

    def available(self):
        return bool(_key("SCRUBBY_API_KEY"))

    def resolve(self, email):
        try:
            d = http_json("https://api.scrubby.io/verify", {
                "key": _key("SCRUBBY_API_KEY"), "email": email,
            })
            return {"status": d.get("result", "unknown"), "method": "smtp_ping"}
        except Exception:
            return {"status": "unknown", "method": "smtp_ping"}


@register
class SmartleadSender(SenderProvider):
    name = "smartlead"
    kinds = ("sender",)

    def available(self):
        return bool(_key("SMARTLEAD_API_KEY"))

    def send_batch(self, campaign_id, messages):
        key = _key("SMARTLEAD_API_KEY")
        results = []
        for m in messages:
            try:
                resp = http_json(f"https://server.smartlead.ai/api/v1/campaigns/{campaign_id}/leads?api_key={key}", {
                    "lead_list": [{
                        "first_name": m.get("first_name", ""), "last_name": m.get("last_name", ""),
                        "email": m["to"], "custom_fields": m.get("vars", {}),
                    }],
                })
                results.append({"message_id": str(resp), "status": "queued", "inbox": m.get("inbox", "")})
            except Exception as e:
                results.append({"message_id": "", "status": f"error:{e}", "inbox": m.get("inbox", "")})
        return results

    def fetch_replies(self, campaign_id):
        key = _key("SMARTLEAD_API_KEY")
        try:
            return http_json(f"https://server.smartlead.ai/api/v1/campaigns/{campaign_id}/leads?api_key={key}")
        except Exception:
            return []


@register
class InstantlySender(SenderProvider):
    name = "instantly"
    kinds = ("sender",)

    def available(self):
        return bool(_key("INSTANTLY_API_KEY"))

    def send_batch(self, campaign_id, messages):
        key = _key("INSTANTLY_API_KEY")
        results = []
        for m in messages:
            try:
                resp = http_json("https://api.instantly.ai/api/v1/campaign/lead/add", {
                    "api_key": key,
                    "campaign_id": campaign_id,
                    "first_name": m.get("first_name", ""),
                    "last_name": m.get("last_name", ""),
                    "email": m["to"],
                    "custom_fields": m.get("vars", {}),
                })
                results.append({"message_id": str(resp), "status": "queued", "inbox": m.get("inbox", "")})
            except Exception as e:
                results.append({"message_id": "", "status": f"error:{e}", "inbox": m.get("inbox", "")})
        return results

    def fetch_replies(self, campaign_id):
        key = _key("INSTANTLY_API_KEY")
        try:
            return http_json("https://api.instantly.ai/api/v1/campaign/replies", {
                "api_key": key, "campaign_id": campaign_id,
            })
        except Exception:
            return []


@register
class ClearbitEnrichment:
    name = "clearbit"
    kinds = ("enrichment",)

    def available(self):
        return bool(_key("CLEARBIT_API_KEY"))

    def enrich_person(self, lead: dict) -> dict:
        email = lead.get("email", "")
        if not email:
            return {}
        try:
            resp = http_json(f"https://person.clearbit.com/v2/people/find?email={email}",
                           headers={"Authorization": f"Bearer {_key('CLEARBIT_API_KEY')}"})
            return {
                "clearbit_name": resp.get("name", {}).get("fullName", ""),
                "clearbit_location": resp.get("location", ""),
                "clearbit_twitter": resp.get("twitter", {}).get("handle", ""),
                "clearbit_linkedin": resp.get("linkedin", {}).get("handle", ""),
                "clearbit_bio": resp.get("bio", ""),
                "clearbit_avatar": resp.get("avatar", ""),
            }
        except Exception:
            return {}

    def enrich_company(self, domain: str) -> dict:
        try:
            resp = http_json(f"https://company.clearbit.com/v2/companies/find?domain={domain}",
                           headers={"Authorization": f"Bearer {_key('CLEARBIT_API_KEY')}"})
            return {
                "clearbit_company_name": resp.get("name", ""),
                "clearbit_description": resp.get("description", ""),
                "clearbit_category": resp.get("category", ""),
                "clearbit_tech": resp.get("tech", []),
                "clearbit_metrics": resp.get("metrics", {}),
                "clearbit_employee_count": resp.get("metrics", {}).get("employees", 0),
            }
        except Exception:
            return {}


@register
class PeopleDataLabsEnrichment:
    name = "pdl"
    kinds = ("enrichment",)

    def available(self):
        return bool(_key("PDL_API_KEY"))

    def enrich_person(self, lead: dict) -> dict:
        email = lead.get("email", "")
        if not email:
            return {}
        try:
            resp = http_json("https://api.peopledatalabs.com/v5/person/enrich", {
                "api_key": _key("PDL_API_KEY"),
                "email": email,
                "pretty": True,
            })
            d = resp.get("data", {})
            return {
                "pdl_full_name": d.get("full_name", ""),
                "pdl_job_title": d.get("job_title", ""),
                "pdl_company": d.get("job_company_name", ""),
                "pdl_linkedin": d.get("linkedin_url", ""),
                "pdl_skills": d.get("skills", []),
                "pdl_experience": d.get("experience", []),
            }
        except Exception:
            return {}

    def enrich_company(self, domain: str) -> dict:
        try:
            resp = http_json("https://api.peopledatalabs.com/v5/company/enrich", {
                "api_key": _key("PDL_API_KEY"),
                "website": domain,
                "pretty": True,
            })
            d = resp.get("data", {})
            return {
                "pdl_company_name": d.get("name", ""),
                "pdl_size": d.get("size", ""),
                "pdl_founded": d.get("founded_year", 0),
                "pdl_industry": d.get("industry", ""),
                "pdl_location": d.get("location", ""),
                "pdl_tech": d.get("technologies", []),
            }
        except Exception:
            return {}


@register
class HubSpotSignalProvider:
    name = "hubspot_signals"
    kinds = ("signals",)

    def available(self):
        return bool(_key("HUBSPOT_API_KEY"))

    def signals(self, domain: str) -> list[str]:
        # HubSpot doesn't have direct signal API, but we can check for
        # recent form submissions, page views, etc. via their API
        return []


for _cls in [ApolloSource, HunterFinder, DropcontactFinder, ZeroBounceVerifier,
             NeverBounceVerifier, ScrubbyCatchAll, SmartleadSender, InstantlySender,
             ClearbitEnrichment, PeopleDataLabsEnrichment, HubSpotSignalProvider]:
    register(_cls)
