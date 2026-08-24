from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Lead, Campaign, Event


SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads(campaign_id);
CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT,
    campaign_id TEXT,
    agent TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_lead ON events(lead_id);
CREATE INDEX IF NOT EXISTS idx_events_campaign ON events(campaign_id);
"""


class PoolStore:
    """The Common Pool: blackboard store every agent reads from and writes to."""

    def __init__(self, db_path: str = "./outreachos.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def create_campaign(self, c: Campaign) -> Campaign:
        cur = self.conn.execute(
            "INSERT INTO campaigns (id, name, data, created_at) VALUES (?,?,?,?)",
            (c.id, c.name, json.dumps(c.to_dict()), c.created_at),
        )
        self.conn.commit()
        return c

    def get_campaign_by_name(self, name: str) -> Campaign | None:
        row = self.conn.execute("SELECT data FROM campaigns WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        return Campaign.from_dict(json.loads(row["data"]))

    def get_campaign(self, cid: str) -> Campaign | None:
        row = self.conn.execute("SELECT data FROM campaigns WHERE id=?", (cid,)).fetchone()
        if not row:
            return None
        return Campaign.from_dict(json.loads(row["data"]))

    def upsert_lead(self, lead: Lead) -> Lead:
        if not lead.id:
            raise ValueError("Lead.id required")
        self.conn.execute(
            "INSERT INTO leads (id, campaign_id, data, created_at, updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (lead.id, lead.campaign_id, json.dumps(lead.to_dict()), lead.created_at, lead.updated_at),
        )
        self.conn.commit()
        return lead

    def get_lead(self, lead_id: str) -> Lead | None:
        row = self.conn.execute("SELECT data FROM leads WHERE id=?", (lead_id,)).fetchone()
        return Lead.from_dict(json.loads(row["data"])) if row else None

    def leads(self, campaign_id: str, stage: str | None = None,
              email_status: str | None = None, outreach_state: str | None = None) -> list[Lead]:
        q = "SELECT data FROM leads WHERE campaign_id=?"
        args: list = [campaign_id]
        rows = self.conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            l = Lead.from_dict(json.loads(r["data"]))
            if stage and l.stage != stage:
                continue
            if email_status and l.email_status != email_status:
                continue
            if outreach_state and l.outreach_state != outreach_state:
                continue
            out.append(l)
        return out

    def update_lead(self, lead_id: str, **fields) -> Lead | None:
        lead = self.get_lead(lead_id)
        if lead is None:
            return None
        for k, v in fields.items():
            setattr(lead, k, v)
        lead.updated_at = lead.updated_at
        from .models import now_iso
        lead.updated_at = now_iso()
        return self.upsert_lead(lead)

    def log_event(self, lead_id: str, campaign_id: str, agent: str, action: str, detail: dict | None = None) -> Event:
        e = Event(lead_id=lead_id, agent=agent, action=action, detail=detail or {})
        cur = self.conn.execute(
            "INSERT INTO events (lead_id, campaign_id, agent, action, detail, created_at) VALUES (?,?,?,?,?,?)",
            (e.lead_id, campaign_id, e.agent, e.action, json.dumps(e.detail), e.created_at),
        )
        self.conn.commit()
        e.id = cur.lastrowid
        return e

    def events_for_lead(self, lead_id: str) -> list[Event]:
        rows = self.conn.execute(
            "SELECT * FROM events WHERE lead_id=? ORDER BY id ASC", (lead_id,)
        ).fetchall()
        return [Event(lead_id=r["lead_id"], agent=r["agent"], action=r["action"],
                      detail=json.loads(r["detail"]), created_at=r["created_at"], id=r["id"]) for r in rows]

    def campaign_stats(self, campaign_id: str) -> dict:
        leads = self.leads(campaign_id)
        by_stage: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_outreach: dict[str, int] = {}
        for l in leads:
            by_stage[l.stage] = by_stage.get(l.stage, 0) + 1
            by_status[l.email_status] = by_status.get(l.email_status, 0) + 1
            by_outreach[l.outreach_state] = by_outreach.get(l.outreach_state, 0) + 1
        total_sent = by_outreach.get("sent", 0) + sum(
            v for k, v in by_outreach.items() if k.startswith("replied") or k == "booked")
        positive = by_outreach.get("replied_positive", 0) + by_outreach.get("booked", 0)
        invalid = by_status.get("invalid", 0)
        verified = by_status.get("verified", 0) + by_status.get("risky_catchall_confirmed", 0)
        bounce_rate = round(invalid / max(total_sent, 1), 4)
        reply_rate = round((positive + by_outreach.get("replied_negative", 0)) / max(total_sent, 1), 4)
        return {
            "total_leads": len(leads),
            "by_stage": by_stage,
            "by_email_status": by_status,
            "by_outreach_state": by_outreach,
            "sent_est": total_sent,
            "positive_replies": positive,
            "reply_rate": reply_rate,
            "bounce_rate_guard": bounce_rate,
        }
