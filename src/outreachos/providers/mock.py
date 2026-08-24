from __future__ import annotations

import random

from .base import (
    register, LeadSourceProvider, EmailFinderProvider, VerifierProvider,
    CatchAllResolver, SenderProvider,
)
from ..utils import stable_seed


FIRST = ["Ava", "Liam", "Noah", "Mia", "Ethan", "Zoe", "Lucas", "Emma", "Aiden", "Nora",
         "Raj", "Priya", "Diego", "Sofia", "Kenji", "Yuki", "Omar", "Leila", "Ivan", "Greta"]
LAST = ["Chen", "Patel", "Kim", "Garcia", "Mueller", "Rossi", "Novak", "Silva", "Ahmed",
        "Kowalski", "Tanaka", "Brown", "Davis", "Wilson", "Martinez", "Singh", "Weber"]
TITLES_BY_FUNC = {
    "sales": ["VP of Sales", "Director of Sales", "Head of Revenue", "Chief Revenue Officer", "Sales Manager"],
    "marketing": ["VP of Marketing", "Demand Gen Manager", "Head of Growth", "CMO"],
    "engineering": ["VP Engineering", "CTO", "Engineering Manager"],
}
COMPANY_STEMS = ["brightpath", "quantivo", "lumenlabs", "northbeam", "vertexflow", "orbitally",
                 "stackforge", "datacrane", "heliosync", "copperleaf", "meridianhq", "fluxline"]
TLDS = [".com", ".io", ".ai"]


class MockLeadSource(LeadSourceProvider):
    name = "mock_leadsource"
    kinds = ("leadsource",)

    def available(self):
        return True

    def source_leads(self, icp: dict, limit: int) -> list[dict]:
        industries = icp.get("industries") or ["SaaS"]
        titles = icp.get("titles") or TITLES_BY_FUNC["sales"]
        geos = icp.get("geos") or ["US"]
        out = []
        for i in range(limit):
            seed = stable_seed("hunt", i, tuple(industries), tuple(titles))
            rng = random.Random(seed)
            stem = rng.choice(COMPANY_STEMS) + str(rng.randint(2, 99))
            domain = stem + rng.choice(TLDS)
            fn, ln = rng.choice(FIRST), rng.choice(LAST)
            out.append({
                "first_name": fn,
                "last_name": ln,
                "title": rng.choice(titles),
                "company": stem.replace("_", " ").title(),
                "domain": domain,
                "industry": rng.choice(industries),
                "headcount": rng.randint(icp.get("headcount_min", 10), min(icp.get("headcount_max", 5000), 2000)),
                "location": rng.choice(geos),
                "linkedin_url": f"https://linkedin.com/in/{fn.lower()}-{ln.lower()}-{rng.randint(100, 999)}",
                "source": self.name,
            })
        return out


class MockEmailFinderA(EmailFinderProvider):
    """Primary finder: good hit rate, occasionally no verdict."""

    name = "mock_emailfinder_a"
    kinds = ("emailfinder",)

    def available(self):
        return True

    def find_email(self, first_name, last_name, domain):
        seed = stable_seed("efa", first_name, last_name, domain)
        rng = random.Random(seed)
        if rng.random() < 0.85:
            return {"email": f"{first_name.lower()}.{last_name.lower()}@{domain}", "confidence": round(rng.uniform(0.7, 0.95), 2)}
        return {}


class MockEmailFinderB(EmailFinderProvider):
    """Secondary waterfall layer: different pattern, catches some misses."""

    name = "mock_emailfinder_b"
    kinds = ("emailfinder",)

    def available(self):
        return True

    def find_email(self, first_name, last_name, domain):
        seed = stable_seed("efb", first_name, last_name, domain)
        rng = random.Random(seed)
        if rng.random() < 0.55:
            return {"email": f"{first_name[0].lower()}{last_name.lower()}@{domain}", "confidence": round(rng.uniform(0.6, 0.85), 2)}
        return {}


class MockVerifierFast(VerifierProvider):
    """Layer 1 verification: fast, but returns 'unknown' on a slice."""

    name = "mock_verifier_fast"
    kinds = ("verifier",)

    def available(self):
        return True

    def verify(self, email):
        seed = stable_seed("vf", email)
        rng = random.Random(seed)
        r = rng.random()
        if r < 0.80:
            return {"status": "valid"}
        if r < 0.88:
            return {"status": "invalid"}
        if r < 0.96:
            return {"status": "catch_all"}
        return {"status": "unknown"}


class MockVerifierDeep(VerifierProvider):
    """Waterfall layer 2: resolves most unknowns, flags catch-alls."""

    name = "mock_verifier_deep"
    kinds = ("verifier",)

    def available(self):
        return True

    def verify(self, email):
        seed = stable_seed("vd", email)
        rng = random.Random(seed)
        r = rng.random()
        if r < 0.70:
            return {"status": "valid"}
        if r < 0.78:
            return {"status": "invalid"}
        return {"status": "catch_all"}


class MockCatchAllResolver(CatchAllResolver):
    """SMTP-ping style silent resolution (Scrubby-like)."""

    name = "mock_catchall"
    kinds = ("catchall",)

    def available(self):
        return True

    def resolve(self, email):
        seed = stable_seed("ca", email)
        rng = random.Random(seed)
        if rng.random() < 0.70:
            return {"status": "valid", "method": "smtp_ping"}
        return {"status": "invalid", "method": "smtp_ping"}


REPLY_DISTRIBUTION = {
    "replied_positive": 0.08,
    "replied_negative": 0.05,
    "ooo_autoreply": 0.04,
    "bounced": 0.01,
}


class MockSender(SenderProvider):
    name = "mock_sender"
    kinds = ("sender",)

    def available(self):
        return True

    def send_batch(self, campaign_id, messages):
        results = []
        for m in messages:
            results.append({"message_id": f"msg_{stable_seed('send', campaign_id, m['to']) % 10**10}",
                            "status": "sent", "inbox": m.get("inbox", "sim@outreachos.dev")})
        return results

    def fetch_replies(self, campaign_id):
        return []


def simulate_reply(email: str) -> str | None:
    """Deterministic simulated reply outcome for dry-run/demo mode."""
    seed = stable_seed("reply", email)
    rng = random.Random(seed)
    r = rng.random()
    acc = 0.0
    for state, p in REPLY_DISTRIBUTION.items():
        acc += p
        if r < acc:
            return state
    return None


for _cls in [MockLeadSource, MockEmailFinderA, MockEmailFinderB,
             MockVerifierFast, MockVerifierDeep, MockCatchAllResolver, MockSender]:
    register(_cls)
