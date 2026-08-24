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


for _cls in [ApolloSource, HunterFinder, ZeroBounceVerifier,
             NeverBounceVerifier, ScrubbyCatchAll, SmartleadSender]:
    register(_cls)
