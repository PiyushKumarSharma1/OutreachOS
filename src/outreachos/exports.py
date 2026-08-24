"""Client-facing CSV exports."""
from __future__ import annotations

import csv
from pathlib import Path

from .pool.store import PoolStore


FIELDS = [
    "id", "first_name", "last_name", "title", "company", "domain", "email",
    "email_status", "outreach_state", "stage", "industry", "headcount",
    "location", "source",
]


def export_campaign_csv(store: PoolStore, campaign_name_or_id: str,
                        out_dir: str = "./exports") -> dict:
    engine_store = store
    campaign = (engine_store.get_campaign_by_name(campaign_name_or_id)
                or engine_store.get_campaign(campaign_name_or_id))
    if not campaign:
        return {"error": "campaign not found"}
    leads = engine_store.leads(campaign.id)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"{campaign.name}_{campaign.id[:8]}.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for l in leads:
            writer.writerow(l.to_dict())
    return {"path": str(path), "rows": len(leads)}
