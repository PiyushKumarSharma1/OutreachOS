"""Deliverability monitor: per-inbox health from the event log, auto-pause.

Health rules (2026 provider thresholds):
- 24h bounce rate > 5%  -> pause inbox (providers start throttling)
- 24h bounce rate > 8%  -> quarantine (manual review required)
- complaint rate > 0.3% -> pause (Google/Yahoo bulk sender rule)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import SETTINGS
from .pool.store import PoolStore


class DeliverabilityMonitor:
    PAUSE_BOUNCE = 0.05
    QUARANTINE_BOUNCE = 0.08
    PAUSE_COMPLAINT = 0.003

    def __init__(self, store: PoolStore):
        self.store = store

    def _window_start(self, hours: int = 24) -> str:
        return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    def inbox_stats(self, inbox: str, hours: int = 24) -> dict:
        since = self._window_start(hours)
        row = self.store.conn.execute(
            """SELECT
                 SUM(CASE WHEN action='email_sent' THEN 1 ELSE 0 END) as sent,
                 SUM(CASE WHEN action='reply_bounced' THEN 1 ELSE 0 END) as bounces,
                 SUM(CASE WHEN action='complaint' THEN 1 ELSE 0 END) as complaints
               FROM events
               WHERE agent='sdr' AND created_at >= ? AND detail LIKE ?""",
            (since, f'%{inbox}%')).fetchone()
        sent = row["sent"] or 0
        bounces = row["bounces"] or 0
        complaints = row["complaints"] or 0
        return {"inbox": inbox, "sent": sent, "bounces": bounces, "complaints": complaints,
                "bounce_rate": round(bounces / sent, 4) if sent else 0.0,
                "complaint_rate": round(complaints / sent, 4) if sent else 0.0}

    def check(self) -> dict:
        """Run health checks across all inboxes; pause/quarantine as needed."""
        actions = []
        for r in self.store.conn.execute("SELECT email, status FROM inboxes"):
            email, status = r["email"], r["status"]
            if status == "quarantined":
                continue
            stats = self.inbox_stats(email)
            new_status = None
            if stats["bounce_rate"] > self.QUARANTINE_BOUNCE:
                new_status = "quarantined"
            elif stats["bounce_rate"] > self.PAUSE_BOUNCE or stats["complaint_rate"] > self.PAUSE_COMPLAINT:
                new_status = "paused"
            if new_status and new_status != status:
                self.store.conn.execute("UPDATE inboxes SET status=? WHERE email=?",
                                        (new_status, email))
                self.store.log_event("", "", "security", "inbox_health_action",
                                     {"inbox": email, "from": status, "to": new_status,
                                      **{k: stats[k] for k in ("sent", "bounces", "bounce_rate")}})
                actions.append({"inbox": email, "status": new_status, **stats})
        self.store.conn.commit()
        return {"checked": True, "actions": actions}

    def healthy_inboxes(self, infra) -> list[dict]:
        """Ready inboxes that also pass current health checks."""
        self.check()
        healthy = []
        for inbox in infra.ready_inboxes():
            row = self.store.conn.execute(
                "SELECT status FROM inboxes WHERE email=?", (inbox["email"],)).fetchone()
            if row and row["status"] == "active":
                healthy.append(inbox)
        return healthy

    def dashboard(self) -> list[dict]:
        out = []
        for r in self.store.conn.execute("SELECT email, status, daily_cap FROM inboxes ORDER BY email"):
            stats = self.inbox_stats(r["email"])
            out.append({**stats, "status": r["status"], "daily_cap": r["daily_cap"]})
        return out
