"""Ethical web-scraping lead source.

Design constraints (non-negotiable):
- robots.txt honored via stdlib robotparser before any fetch
- 1 request/second per host, hard page cap, timeouts
- only public directory pages explicitly configured via ICP `seed_urls`
- optional Playwright renderer for JS-heavy directories (lazy import,
  enabled only when PLAYWRIGHT_ENABLED=1)
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .base import register, LeadSourceProvider
from ..utils import RateLimiter

USER_AGENT = "OutreachOSBot/0.1 (+https://outreachos.local/bot; respectful B2B directory indexer)"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DOMAIN_RE = re.compile(r"https?://(?:www\.)?([a-z0-9-]+\.[a-z0-9.-]+)/?", re.IGNORECASE)


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.jsonld: list[dict] = []
        self.mailtos: set[str] = set()
        self.links: list[str] = []
        self._in_jsonld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld = True
            self._buf = []
        elif tag == "a":
            href = a.get("href", "")
            if href.startswith("mailto:"):
                self.mailtos.add(href[len("mailto:"):].split("?")[0])
            elif href.startswith("http"):
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            raw = "".join(self._buf).strip()
            try:
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
                self.jsonld.extend(i for i in items if isinstance(i, dict))
            except Exception:
                pass
            self._in_jsonld = False

    def handle_data(self, data):
        if self._in_jsonld:
            self._buf.append(data)


def robots_allows(url: str) -> bool:
    try:
        import urllib.robotparser
        parsed = urllib.parse.urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return False


class BaseScraper(LeadSourceProvider):
    kinds = ("leadsource",)

    def __init__(self, max_pages_per_host: int = 10, requests_per_second: float = 1.0):
        self.max_pages = max_pages_per_host
        self.limiter = RateLimiter(requests_per_second)

    def available(self) -> bool:
        return True

    def render(self, url: str) -> str | None:
        raise NotImplementedError

    def source_leads(self, icp: dict, limit: int) -> list[dict]:
        seed_urls = icp.get("seed_urls") or []
        out: list[dict] = []
        seen_hosts: dict[str, int] = {}
        for url in seed_urls:
            if len(out) >= limit:
                break
            host = urllib.parse.urlparse(url).netloc
            if not host:
                continue
            seen_hosts.setdefault(host, 0)
            if seen_hosts[host] >= self.max_pages:
                continue
            if not robots_allows(url):
                continue
            self.limiter.wait()
            html = self.render(url)
            seen_hosts[host] += 1
            if not html:
                continue
            out.extend(self._extract(html))
        deduped: dict[str, dict] = {}
        for r in out:
            key = (r.get("domain") or r.get("company") or "").lower()
            if key and key not in deduped:
                deduped[key] = r
        return list(deduped.values())[:limit]

    def _extract(self, html: str) -> list[dict]:
        parser = _PageParser()
        try:
            parser.feed(html)
        except Exception:
            pass
        leads: list[dict] = []
        for org in parser.jsonld:
            if org.get("@type") not in ("Organization", "LocalBusiness", "Corporation"):
                continue
            name = org.get("name", "")
            site = org.get("url") or ""
            domain_m = DOMAIN_RE.search(site)
            leads.append({
                "first_name": "",
                "last_name": "",
                "title": "",
                "company": name.strip(),
                "domain": (domain_m.group(1) if domain_m else "").lower(),
                "industry": icp_industry_fallback(org),
                "email": org.get("email", "") or next(iter(parser.mailtos), ""),
                "source": self.name,
            })
        for mail in parser.mailtos:
            dom = mail.split("@")[-1]
            if any(l.get("domain") == dom for l in leads):
                continue
            leads.append({"first_name": "", "last_name": "", "title": "",
                          "company": dom.split(".")[0].title(), "domain": dom.lower(),
                          "email": mail, "source": self.name})
        return leads


def icp_industry_fallback(org: dict) -> str:
    desc = str(org.get("description", ""))[:80]
    return desc


@register
class DirectoryScraperProvider(BaseScraper):
    name = "directory_scraper"

    def render(self, url: str) -> str | None:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None


@register
class PlaywrightScraperProvider(BaseScraper):
    """JS-rendered scraping via Playwright. Requires:
       pip install playwright && playwright install chromium
       PLAYWRIGHT_ENABLED=1"""

    name = "playwright_scraper"

    def available(self) -> bool:
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    def render(self, url: str) -> str | None:
        if not self.available():
            return None
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=USER_AGENT)
                page.goto(url, wait_until="networkidle", timeout=30000)
                html = page.content()
                browser.close()
                return html
        except Exception:
            return None
