"""SELF-SERVE: use OutreachOS to find customers for OutreachOS itself.

Real, keyless pipeline: RemoteOK + HN hiring threads (companies hiring
sales/GTM roles = active pipeline pain = our ICP), website research,
MX validation, personalized drafts, CSV + .eml export, and a pool
campaign so the Outr UI shows the live list.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys

from .pool.store import PoolStore
from .pool.models import Lead
from .providers.real import (
    RemoteOkSource, HNHiringSource, WebsiteResearch,
    MxEmailFinder, _dns_query_mx,
)

SELF_ICP = {
    "industries": ["B2B SaaS", "Software", "Developer Tools", "AI", "FinTech"],
    "titles": ["sales", "SDR", "account executive", "GTM", "growth",
               "business development", "revenue", "sales development"],
    "geos": ["US", "UK", "EU", "Remote"],
    "headcount_min": 5,
    "headcount_max": 5000,
}

OFFER = ("OutreachOS — an AI outbound engine that researches your ICP, verifies "
         "emails, writes personalized sequences and books meetings on autopilot.")

SUBJECTS = [
    "{company}: pipeline while you hire for {role}",
    "idea for {company}'s {role} search",
    "{company} + outbound on autopilot while you hire {role}",
]

BODY = """Hi {company} team,

I saw you're hiring for {role}{where} — that's usually the moment outbound pipeline becomes the bottleneck.

I built OutreachOS: an AI outbound system that finds ICP-fit companies, verifies emails in a waterfall, writes personalized sequences, and books meetings on autopilot (we dogfood it — this email came from it{via}).

{research_line}

Worth a 15-minute look at your pipeline numbers? I'll show you the exact engine.

— Piyush Kumar Sharma
OutreachOS · github.com/PiyushKumarSharma1/OutreachOS
"""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def run(limit: int = 40, out_dir: str = "./agency-customers",
        db_path: str | None = None) -> dict:
    db = db_path or os.getenv("OUTREACHOS_DB", "./outreachos.db")
    store = PoolStore(db)
    os.makedirs(os.path.join(out_dir, "drafts"), exist_ok=True)

    # 1) source from both real feeds
    hn = HNHiringSource().source_leads(SELF_ICP, limit)
    remote = RemoteOkSource().source_leads(SELF_ICP, limit)
    raw = hn + remote

    # 2) dedupe (domain > company name)
    seen: set[str] = set()
    leads: list[dict] = []
    for r in raw:
        key = (r.get("domain") or r.get("company", "").lower())
        if key in seen:
            continue
        seen.add(key)
        leads.append(r)

    # 3) research + email validation
    research = WebsiteResearch()
    finder = MxEmailFinder()
    rows: list[dict] = []
    for lead in leads:
        domain = lead.get("domain", "")
        desc = ""
        tech: list[str] = []
        if domain:
            enriched = research.enrich_company(domain)
            desc = _clean(enriched.get("company_description", ""))[:220]
            tech = enriched.get("tech_detected", [])
        email = lead.get("email_direct") or ""
        email_status = "none"
        if email:
            email_status = "verified" if _dns_query_mx(email.split("@")[1]) else "unknown"
        elif domain:
            found = finder.find_email("", "", domain)  # generic hello@ when MX exists
            email = found.get("email", "")
            email_status = "pattern_generic" if email else "none"
        role = lead.get("trigger_signal", "").replace("hiring ", "").replace("hiring signal on HN (", "").rstrip(")")[:50]
        rows.append({
            "company": lead.get("company", ""),
            "domain": domain,
            "email": email,
            "email_status": email_status,
            "hiring_signal": lead.get("trigger_signal", ""),
            "role": role,
            "location": lead.get("location", ""),
            "source": lead.get("source", ""),
            "source_url": lead.get("source_url", ""),
            "research": desc,
            "tech": ", ".join(tech),
        })

    # 4) personalized drafts (deterministic, honest personalization)
    drafts_dir = os.path.join(out_dir, "drafts")
    for i, row in enumerate(rows):
        research_line = ""
        if row["research"]:
            research_line = f'Quick read on you: "{row["research"][:140]}…" — that positioning writes itself into outbound.'
        subj = SUBJECTS[i % len(SUBJECTS)].format(company=row["company"], role=row["role"] or "sales")
        where = f" ({row['location']})" if row.get("location") and row["location"] not in ("Remote",) else ""
        body = BODY.format(company=row["company"], role=row["role"] or "sales",
                           where=where, research_line=research_line, via="")
        row["subject"] = subj
        row["draft"] = body
        if row["email"]:
            safe = re.sub(r"[^a-z0-9]+", "_", (row["company"].lower() + "_" + row["email"])).strip("_")[:70]
            with open(os.path.join(drafts_dir, f"{safe}.eml"), "w") as fh:
                fh.write(f"To: {row['email']}\nSubject: {subj}\n\n{body}\n")

    # 5) export CSV + summary
    csv_path = os.path.join(out_dir, "leads.csv")
    fields = ["company", "domain", "email", "email_status", "hiring_signal",
              "role", "location", "source", "source_url", "research", "tech", "subject"]
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # 6) push into the pool so Outr UI shows the live list
    from .orchestration.engine import Engine
    engine = Engine(store)
    campaign = store.get_campaign_by_name("self-serve-agency-customers")
    if not campaign:
        campaign = engine.create_campaign(
            "self-serve-agency-customers",
            icp=SELF_ICP,
            offer=OFFER,
            case_studies=[{"industry": "B2B SaaS", "name": "OutreachOS dogfood",
                           "result": "self-sourced customer list", "timeframe": "week 1"}],
        )
    existing = {f"{l.domain}|{l.email}".lower() for l in store.leads(campaign.id)}
    pooled = 0
    for r in rows:
        key = f"{r['domain']}|{r['email']}".lower()
        if key in existing:
            continue
        lead = Lead(
            campaign_id=campaign.id,
            title=r["role"] or "hiring",
            company=r["company"],
            domain=r["domain"],
            email=r["email"],
            email_status="verified" if r["email_status"] == "verified" else "none",
            location=r["location"],
            industry="B2B SaaS",
            source=r["source"],
            trigger_signal=r["hiring_signal"],
        )
        lead.enrichment["self_serve"] = {"research": r["research"], "tech": r["tech"], "source_url": r["source_url"]}
        store.upsert_lead(lead)
        existing.add(key)
        pooled += 1
    engine.run_agent("client_reporter", "self-serve-agency-customers")
    summary = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "total": len(rows),
        "with_email": len([r for r in rows if r["email"]]),
        "verified_or_mx": len([r for r in rows if r["email_status"] in ("verified", "pattern_generic")]),
        "sources": ["remoteok.com", "news.ycombinator.com"],
        "csv": os.path.abspath(csv_path),
        "drafts_dir": os.path.abspath(drafts_dir),
        "rows": rows,
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as fh:
        json.dump(summary, fh, indent=2, default=str)
    store.close()
    return summary


def cmd(args) -> int:
    summary = run(limit=args.limit, out_dir=args.out)
    print(f"\n=== SELF-SERVE CUSTOMER LIST ({summary['total']} companies) ===")
    for r in summary["rows"][:int(args.head)]:
        print(f"- {r['company'][:30]:32} | {r['email'] or '(no email)':34} | {r['email_status']:15} | {r['hiring_signal'][:40]}")
    print(f"\nCSV:     {summary['csv']}")
    print(f"Drafts:  {summary['drafts_dir']}  ({summary['with_email']} emails, {summary['verified_or_mx']} sendable)")
    print("Next: add SMTP_HOST/USER/PASS + LIVE_SEND=1 to actually send (drafts are reviewable .eml files).")
    return 0
