"""Sending infrastructure: domain pool, inbox pool, warmup tracking, rotation.

Implements the operator math from RESEARCH.md:
- warm every inbox >= WARMUP_MIN_DAYS before cold sends
- per-inbox daily caps; rotation spreads load
- domains must have DNS configured before inboxes go active
"""
from __future__ import annotations

from datetime import datetime, timezone

from .config import SETTINGS
from .pool.store import PoolStore
from .utils import new_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InfraManager:
    def __init__(self, store: PoolStore):
        self.store = store

    def add_domain(self, name: str, provider: str = "google",
                   dns_configured: bool = False) -> dict:
        dom = {"id": new_id("dom"), "name": name.lower(), "provider": provider,
               "dns_configured": int(dns_configured), "status": "active", "created_at": _now()}
        self.store.conn.execute(
            "INSERT OR IGNORE INTO domains (id, name, provider, status, dns_configured, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (dom["id"], dom["name"], provider, dom["status"], dom["dns_configured"], dom["created_at"]))
        self.store.conn.commit()
        return dom

    def add_inbox(self, email: str, daily_cap: int | None = None,
                  warmup_started: bool = True) -> dict:
        domain = email.split("@")[-1].lower()
        row = self.store.conn.execute("SELECT dns_configured FROM domains WHERE name=?", (domain,)).fetchone()
        if row and not row["dns_configured"]:
            raise ValueError(f"domain {domain} has no DNS configured")
        inbox = {
            "id": new_id("inx"), "email": email.lower(), "domain": domain,
            "warmup_started_at": _now() if warmup_started else "",
            "daily_cap": daily_cap or SETTINGS.daily_send_cap_per_inbox,
            "status": "warming", "created_at": _now(),
        }
        self.store.conn.execute(
            "INSERT OR IGNORE INTO inboxes (id, email, domain, warmup_started_at, daily_cap, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (inbox["id"], inbox["email"], inbox["domain"], inbox["warmup_started_at"],
             inbox["daily_cap"], inbox["status"], inbox["created_at"]))
        self.store.conn.commit()
        return inbox

    def warmup_days(self, inbox_row) -> int:
        started = inbox_row["warmup_started_at"]
        if not started:
            return 0
        try:
            dt = datetime.fromisoformat(started)
            return (datetime.now(timezone.utc) - dt).days
        except Exception:
            return 0

    def ready_inboxes(self) -> list[dict]:
        """Inboxes past warmup gate + active status, with computed warmup_days."""
        out = []
        for r in self.store.conn.execute(
                "SELECT * FROM inboxes WHERE status IN ('active','warming')"):
            days = self.warmup_days(r)
            status = "active" if days >= SETTINGS.warmup_min_days and r["status"] != "paused" else r["status"]
            if status == "active" and r["status"] == "warming":
                self.store.conn.execute("UPDATE inboxes SET status='active' WHERE id=?", (r["id"],))
                self.store.conn.commit()
            if status == "active":
                out.append({"email": r["email"], "inbox": r["email"], "warmup_days": days, "daily_cap": r["daily_cap"]})
        self.store.conn.commit()
        return out

    def all_inboxes(self) -> list[dict]:
        out = []
        for r in self.store.conn.execute("SELECT * FROM inboxes ORDER BY created_at"):
            d = dict(r)
            d["warmup_days"] = self.warmup_days(r)
            out.append(d)
        return out

    def set_status(self, email: str, status: str) -> bool:
        cur = self.store.conn.execute("UPDATE inboxes SET status=? WHERE email=?", (status, email))
        self.store.conn.commit()
        return cur.rowcount > 0

    def seed_defaults(self) -> list[dict]:
        """Seed the default satellite domain/inbox pool (mock infra)."""
        created = []
        for dom in ["growloop1.com", "trygrowloop2.com", "getgrowloop3.com"]:
            self.add_domain(dom, dns_configured=True)
        for email, warm_days_ago in [
            ("ava@growloop1.com", 30), ("sam@growloop1.com", 30),
            ("kai@trygrowloop2.com", 25), ("noor@trygrowloop2.com", 24),
            ("eli@getgrowloop3.com", 22), ("mia@getgrowloop3.com", 22),
        ]:
            inbox = self.add_inbox(email)
            started = datetime.fromisoformat(inbox["warmup_started_at"])
            from datetime import timedelta
            backdated = (started - timedelta(days=warm_days_ago)).isoformat()
            self.store.conn.execute("UPDATE inboxes SET warmup_started_at=? WHERE email=?",
                                    (backdated, email))
            self.store.conn.commit()
            created.append(email)
        return created
