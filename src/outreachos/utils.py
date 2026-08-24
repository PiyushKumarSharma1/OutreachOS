from __future__ import annotations

import hashlib
import re
import time


CORP_SUFFIXES = (
    " inc.", " inc", " incorporated", " llc", " ltd", " limited", " corp",
    " corporation", " co", " company", " gmbh", " s.a.", " plc", " pvt",
)


def clean_company(name: str) -> str:
    n = (name or "").strip().lower()
    for suf in CORP_SUFFIXES:
        if n.endswith(suf):
            n = n[: -len(suf)]
    return re.sub(r"[^\w\s-]", "", n).strip()


def clean_domain(url_or_domain: str) -> str:
    d = (url_or_domain or "").strip().lower()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    d = d.split("/")[0].split("?")[0]
    return d


SENIORITY_MAP = [
    ("chief|cxo|ceo|cto|cmo|cro|cso", "cxo"),
    ("^evp|executive vice", "vp"),
    ("svp|senior vice|^vice president|^vp\\b|head of", "vp"),
    ("director|head", "director"),
    ("manager|lead", "manager"),
]


def normalize_title(title: str) -> tuple[str, str]:
    t = (title or "").strip().lower()
    func = "other"
    for kw in ["sales", "marketing", "growth", "revenue", "engineering", "product", "operations", "hr"]:
        if kw in t:
            func = kw
            break
    for pat, level in SENIORITY_MAP:
        if re.search(pat, t):
            return level, func
    return "ic", func


SPAM_WORDS = {
    "guarantee", "risk free", "act now", "limited time", "free money",
    "no obligation", "100%", "winner", "cash bonus", "click here",
}


def spam_score(text: str) -> tuple[float, list[str]]:
    low = text.lower()
    hits = [w for w in SPAM_WORDS if w in low]
    caps_ratio = sum(1 for c in text if c.isupper()) / max(sum(1 for c in text if c.isalpha()), 1)
    score = len(hits) * 0.2 + max(0.0, caps_ratio - 0.15)
    return round(min(score, 1.0), 2), hits


class RateLimiter:
    def __init__(self, per_second: float = 5.0):
        self.interval = 1.0 / max(per_second, 0.001)
        self._last = 0.0

    def wait(self):
        elapsed = time.monotonic() - self._last
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last = time.monotonic()


def stable_seed(*parts) -> int:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:16], 16)
