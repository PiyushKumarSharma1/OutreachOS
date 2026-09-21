"""REAL keyless providers: live lead sources, website research, MX email
finding, and an SMTP sender with a draft-mode default.

Keyless by design (2026): hiring-based sourcing is the highest-signal
public data available without paid databases.
- RemoteOK public API: companies actively hiring = buying signal
- HN "Who is hiring?" (Algolia): founder-posted roles with real emails
- Website research: robots-aware homepage fetch for real personalization
- MX check: raw-DNS (stdlib) + SMTP RCPT verification
- SMTP sender: real send when credentials exist; ALWAYS defaults to
  writing reviewable .eml drafts (approval-bound by default).
"""
from __future__ import annotations

import csv
import json
import os
import random
import re
import smtplib
import socket
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.robotparser import RobotFileParser

from .base import (
    register,
    LeadSourceProvider,
    EmailFinderProvider,
    VerifierProvider,
    EnrichmentProvider,
    SenderProvider,
)

UA = "OutreachOS/1.0 (+https://github.com/PiyushKumarSharma1/OutreachOS; contact: Piyush.adm12@gmail.com)"
TIMEOUT = 15
DNS_RESOLVERS = ("8.8.8.8", "1.1.1.1")


def _get_json(url: str, headers: dict | None = None, timeout: int = TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _get_text(url: str, timeout: int = TIMEOUT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")[:200_000]


def _robots_allows(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        rp = RobotFileParser()
        rp.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(UA, url) or rp.can_fetch("*", url)
    except Exception:
        return True  # robots unreachable: treat public page as allowed


def _domain_of(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url if "//" in url else f"https://{url}").netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _match_any(text: str, keywords: list[str]) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in keywords)


def _hn_html_to_text(html: str) -> str:
    return (html or "").replace("<p>", "\n").replace("</p>", "\n").replace("<br>", "\n")


# ---------------------------------------------------------------- sourcing

@register
class RemoteOkSource(LeadSourceProvider):
    """RemoteOK public API — companies hiring right now (keyless)."""
    name = "real_remoteok"
    kinds = ("leadsource",)

    def available(self) -> bool:
        return True  # public API, no credentials required

    def source_leads(self, icp: dict, limit: int) -> list[dict]:
        keywords = icp.get("titles") or ["SDR", "Sales", "Account Executive", "GTM", "Growth", "Business Development"]
        try:
            data = _get_json("https://remoteok.com/api")
        except Exception:
            return []
        jobs = [d for d in data if isinstance(d, dict) and d.get("position")]
        random.Random(int(time.time())).shuffle(jobs)
        out: list[dict] = []
        for job in jobs:
            position = job.get("position", "")
            if not _match_any(position, keywords):
                continue
            company = job.get("company", "").strip()
            if not company:
                continue
            domain = _domain_of(job.get("url", "") or "")
            if not domain:
                domain = re.sub(r"[^a-z0-9]+", "", company.lower()) + ".com"
            out.append({
                "first_name": "", "last_name": "",
                "title": "Hiring: " + position,
                "company": company,
                "domain": domain,
                "email": "",
                "linkedin_url": job.get("url", ""),
                "location": job.get("location", "Remote"),
                "industry": icp.get("industries", ["B2B SaaS"])[0] if icp.get("industries") else "B2B SaaS",
                "headcount": 0,
                "source": "remoteok.com",
                "source_url": job.get("url", "https://remoteok.com"),
                "trigger_signal": f"hiring {position}",
                "email_direct": "",
            })
            if len(out) >= limit:
                break
        return out


@register
class HNHiringSource(LeadSourceProvider):
    """HN 'Ask HN: Who is hiring?' — founder-posted roles with real emails."""
    name = "real_hn_hiring"
    kinds = ("leadsource",)

    def available(self) -> bool:
        return True

    def _latest_thread(self) -> dict | None:
        try:
            q = urllib.parse.quote('"Ask HN: Who is hiring"')
            d = _get_json(f'https://hn.algolia.com/api/v1/search_by_date'
                          f'?query={q}&tags=story&hitsPerPage=1')
            hits = d.get("hits", [])
            return hits[0] if hits else None
        except Exception:
            return None

    def source_leads(self, icp: dict, limit: int) -> list[dict]:
        thread = self._latest_thread()
        if not thread:
            return []
        keywords = icp.get("titles") or ["SDR", "Sales", "Account Executive", "GTM", "Growth", "Business Development"]
        story_id = thread["objectID"]
        out: list[dict] = []
        for kw in keywords[:6]:
            try:
                q = urllib.parse.quote(kw)
                d = _get_json(f"https://hn.algolia.com/api/v1/search?query={q}"
                              f"&tags=comment,story_{story_id}&hitsPerPage=25")
            except Exception:
                continue
            for hit in d.get("hits", []):
                text = _hn_html_to_text(re.sub(r"<[^>]+>", " ", hit.get("comment_text", "") or ""))
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if not lines:
                    continue
                company = ""
                for cand in lines[:3]:
                    cand = cand.split("|")[0].split(" - ")[0].split("·")[0].strip()[:60]
                    cand = re.sub(r"\s*\((YC|acquired|remote|hiring)[^)]*\)", "", cand, flags=re.I).strip()
                    if not cand:
                        continue
                    if _match_any(cand, ["location", "remote only", "remote:", "we are", "hiring at", "apply at", "http", "onsite"]):
                        continue
                    if re.match(r"^(director|manager|engineer|senior|junior|staff|head of|vp|chief|founder)\b", cand, re.I) and " | " not in cand:
                        continue
                    if len(cand) < 2:
                        continue
                    company = cand
                    break
                if not company:
                    continue
                # role: the segment after the company on the same line, or the matched keyword
                head = lines[0]
                role = kw
                segs = [s.strip() for s in head.split("|")]
                if len(segs) > 1 and segs[1]:
                    role = segs[1][:60]
                else:
                    m = re.search(r"(?:hiring|seeking|looking for)\s+(?:an?\s+)?([A-Z][\w\s/&-]{2,50})", text)
                    if m:
                        role = m.group(1).strip()[:60]
                emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]{2,}", text)
                email = emails[0].rstrip(".") if emails else ""
                domain = email.split("@")[1].lower() if email else ""
                out.append({
                    "first_name": "", "last_name": "",
                    "title": "Hiring: " + role,
                    "company": company,
                    "domain": domain,
                    "email": email,
                    "email_direct": email,
                    "linkedin_url": "",
                    "location": "Remote",
                    "industry": "B2B SaaS",
                    "headcount": 0,
                    "source": "news.ycombinator.com",
                    "source_url": f"https://news.ycombinator.com/item?id={hit.get('objectID','')}",
                    "trigger_signal": f"hiring {role}",
                })
                if len(out) >= limit:
                    return out
            time.sleep(0.4)  # polite to Algolia
        return out


# ---------------------------------------------------------------- enrichment

TECH_HINTS = {
    "hubspot": "HubSpot", "intercom": "Intercom", "segment": "Segment",
    "stripe": "Stripe", "calendly": "Calendly", "outreach.io": "Outreach",
    "salesforce": "Salesforce", "marketo": "Marketo", "apollo.io": "Apollo",
    "clearbit": "Clearbit", "clay.com": "Clay", "gtm.js": "Google Tag Manager",
    "cloudflare": "Cloudflare", "posthog": "PostHog", "amplitude": "Amplitude",
}


@register
class WebsiteResearch(EnrichmentProvider):
    """Robots-aware homepage research for real personalization (keyless)."""
    name = "real_website"
    kinds = ("enrichment",)

    def available(self) -> bool:
        return True

    def enrich_company(self, domain: str) -> dict:
        if not domain:
            return {}
        url = f"https://{domain}"
        if not _robots_allows(url):
            return {"research_blocked": "robots.txt disallow"}
        try:
            html = _get_text(url)
        except Exception:
            try:
                html = _get_text(f"https://www.{domain}")
            except Exception:
                return {}
        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()[:120]
        desc = ""
        m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html, re.I | re.S)
        if not m:
            m = re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']', html, re.I | re.S)
        if m:
            desc = re.sub(r"\s+", " ", m.group(1)).strip()[:300]
        if not desc:
            desc = title
        tech = sorted({label for token, label in TECH_HINTS.items() if token in html.lower()})
        return {"company_description": desc, "page_title": title, "tech_detected": tech}


# ---------------------------------------------------------------- email

def _read_name(data: bytes, idx: int, jumps: int = 0) -> tuple[str, int]:
    """Read a DNS name at `idx`, following compression pointers. Returns
    (name, next_index_after_name)."""
    labels: list[str] = []
    while idx < len(data) and jumps < 10:
        b = data[idx]
        if b == 0:
            return ".".join(labels), idx + 1
        if b & 0xC0 == 0xC0:
            if idx + 1 >= len(data):
                break
            ptr = ((b & 0x3F) << 8) | data[idx + 1]
            sub, _ = _read_name(data, ptr, jumps + 1)
            if sub:
                labels.append(sub)
            return ".".join(labels), idx + 2
        if idx + 1 + b > len(data):
            break
        labels.append(data[idx + 1:idx + 1 + b].decode("utf-8", "replace"))
        idx += b + 1
    return ".".join(labels), min(idx + 1, len(data))


def _dns_query_mx(domain: str) -> list[str]:
    """Raw DNS MX lookup using only stdlib sockets (multi-resolver)."""
    qname = b"".join(bytes([len(p)]) + p.encode() for p in domain.split("."))
    packet = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + qname + b"\x00\x00\x0f\x00\x01"
    for resolver in DNS_RESOLVERS:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(5)
            s.sendto(packet, (resolver, 53))
            data, _ = s.recvfrom(1024)
            s.close()
            answers = (data[6] << 8) | data[7]
            if answers == 0:
                continue
            # skip question section
            _, idx = _read_name(data, 12)
            idx += 4  # QTYPE + QCLASS
            mxs: list[str] = []
            for _ in range(answers):
                if idx >= len(data):
                    break
                if data[idx] & 0xC0 == 0xC0:
                    idx += 2
                else:
                    _, idx = _read_name(data, idx)
                if idx + 10 > len(data):
                    break
                rtype = (data[idx] << 8) | data[idx + 1]
                idx += 8  # TYPE + CLASS + TTL
                rdlen = (data[idx] << 8) | data[idx + 1]
                idx += 2
                if rtype == 15 and rdlen >= 3 and idx + rdlen <= len(data):
                    host, _ = _read_name(data, idx + 2)  # skip 2-byte PREFERENCE
                    if host:
                        mxs.append(host)
                idx += rdlen
            if mxs:
                return mxs
        except Exception:
            continue
    return []


@register
class MxEmailFinder(EmailFinderProvider):
    """Pattern candidates validated by real MX records + optional SMTP RCPT."""
    name = "real_mx"
    kinds = ("emailfinder",)

    PATTERNS = ("first@dom", "firstlast@dom", "flast@dom", "first.last@dom")

    def available(self) -> bool:
        return True

    def find_email(self, first_name: str, last_name: str, domain: str) -> dict:
        if not domain:
            return {}
        if not _dns_query_mx(domain):
            return {}
        f = (first_name or "").lower().strip()
        l = (last_name or "").lower().strip()
        if not f:
            return {"email": f"hello@{domain}", "confidence": "pattern_generic"}
        cands = [f"{f}@{domain}", f"{f}{l}@{domain}", f"{f[0]}{l}@{domain}", f"{f}.{l}@{domain}"]
        return {"email": cands[0], "confidence": "pattern_mx", "alternates": cands[1:]}


@register
class MxVerifier(VerifierProvider):
    """SMTP RCPT verification where the server allows it; honest otherwise."""
    name = "real_smtp_verify"
    kinds = ("verifier",)

    def available(self) -> bool:
        return True

    def verify(self, email: str) -> dict:
        domain = email.rsplit("@", 1)[-1].lower()
        mxs = _dns_query_mx(domain)
        if not mxs:
            return {"status": "invalid", "sub_status": "no_mx"}
        try:
            with smtplib.SMTP(timeout=10) as smtp:
                smtp.connect(mxs[0], 25)
                smtp.helo("outreachos.local")
                smtp.mail("verify@outreachos.local")
                code, _ = smtp.rcpt(email)
                smtp.quit()
                if code == 250:
                    return {"status": "valid", "sub_status": "smtp_250"}
                if code in (550, 551, 553):
                    return {"status": "invalid", "sub_status": "smtp_5xx"}
        except Exception:
            pass
        return {"status": "unknown", "sub_status": "mx_present"}


# ---------------------------------------------------------------- sending

@register
class SmtpSender(SenderProvider):
    """Real SMTP sending. Defaults to DRAFT_MODE=1: writes reviewable .eml
    files instead of sending. LIVE_SEND=1 + SMTP creds enables actual send."""
    name = "smtp_sender"
    kinds = ("sender",)

    def __init__(self, drafts_dir: str = "./drafts"):
        self.host = os.getenv("SMTP_HOST", "")
        self.user = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASS", "")
        self.from_addr = os.getenv("SMTP_FROM", self.user)
        self.drafts_dir = drafts_dir

    def available(self) -> bool:
        return bool(self.host and self.user and self.password)

    @property
    def live(self) -> bool:
        return bool(self.available() and os.getenv("LIVE_SEND", "0") == "1")

    def send_batch(self, campaign_id: str, messages: list[dict]) -> list[dict]:
        os.makedirs(self.drafts_dir, exist_ok=True)
        results = []
        for msg in messages:
            eml = EmailMessage()
            eml["Subject"] = msg.get("subject", "")
            eml["From"] = self.from_addr or "draft@outreachos.local"
            eml["To"] = msg.get("to", "")
            eml["Date"] = datetime.now(timezone.utc).isoformat()
            eml.set_content(msg.get("body", ""))
            name = re.sub(r"[^a-z0-9]+", "_", (msg.get("to", "lead").split("@")[0] + "_" + campaign_id)).lower()[:80]
            if self.live:
                try:
                    with smtplib.SMTP(self.host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as smtp:
                        smtp.starttls()
                        smtp.login(self.user, self.password)
                        smtp.send_message(eml)
                    status = "sent"
                except Exception as e:
                    status = f"send_error: {e}"
            else:
                path = os.path.join(self.drafts_dir, f"{name}.eml")
                with open(path, "w") as fh:
                    fh.write(str(eml))
                status = "draft_written"
            results.append({"to": msg.get("to"), "status": status})
            time.sleep(1)  # sending discipline: 1/sec
        return results

    def fetch_replies(self, campaign_id: str) -> list[dict]:
        return []  # reply ingestion happens via IMAP bridge (roadmap)
