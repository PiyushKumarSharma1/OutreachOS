"""Webhook event bus: subscriptions, HMAC-signed delivery, retry with backoff.

Events: leads.hunted, email.sent, reply.received, meeting.booked,
        security.flagged, campaign.cycle_complete
Delivery: POST JSON + X-OutreachOS-Signature (sha256 HMAC of body) +
          X-OutreachOS-Event headers. Retry: 1m, 5m, 30m, 2h, 12h.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.request
from datetime import datetime, timedelta, timezone

from .pool.store import PoolStore
from .utils import new_id

RETRY_SCHEDULE_MIN = [1, 5, 30, 120, 720]
MAX_ATTEMPTS = len(RETRY_SCHEDULE_MIN)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class EventBus:
    def __init__(self, store: PoolStore):
        self.store = store

    def subscribe(self, url: str, events: list[str], secret: str | None = None,
                  client_id: str | None = None) -> dict:
        secret = secret or new_id("whsec")
        sub = {"id": new_id("wh"), "url": url, "secret": secret,
               "events": json.dumps(events), "client_id": client_id or ""}
        self.store.conn.execute(
            "INSERT INTO webhook_subscriptions (id, client_id, url, secret, events, active, created_at) "
            "VALUES (?,?,?,?,?,1,?)",
            (sub["id"], sub["client_id"], url, secret, sub["events"], _iso(_now())))
        self.store.conn.commit()
        return {**sub, "events": events}

    def unsubscribe(self, sub_id: str) -> bool:
        cur = self.store.conn.execute(
            "UPDATE webhook_subscriptions SET active=0 WHERE id=?", (sub_id,))
        self.store.conn.commit()
        return cur.rowcount > 0

    def list_subscriptions(self, active_only: bool = True) -> list[dict]:
        q = "SELECT * FROM webhook_subscriptions"
        if active_only:
            q += " WHERE active=1"
        return [dict(r) for r in self.store.conn.execute(q)]

    def emit(self, event_type: str, payload: dict) -> int:
        """Queue deliveries for all active subscriptions matching the event."""
        queued = 0
        body = json.dumps({"event_type": event_type, "payload": payload,
                           "timestamp": _iso(_now())})
        for sub in self.list_subscriptions(active_only=True):
            events = json.loads(sub["events"])
            if "*" in events or event_type in events:
                self.store.conn.execute(
                    "INSERT INTO webhook_deliveries (id, subscription_id, event_type, payload, "
                    "status, attempts, next_attempt_at, created_at) VALUES (?,?,?,?,?,0,?,?)",
                    (new_id("del"), sub["id"], event_type, body, "pending",
                     _iso(_now()), _iso(_now())))
                queued += 1
        self.store.conn.commit()
        return queued

    @staticmethod
    def sign(secret: str, body: str) -> str:
        return "sha256=" + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()

    def process_due(self, limit: int = 20, poster=None) -> dict:
        """Attempt pending deliveries. poster(url, body, headers) -> (ok, code)."""
        poster = poster or self._post
        now = _iso(_now())
        rows = self.store.conn.execute(
            "SELECT d.*, s.url, s.secret FROM webhook_deliveries d "
            "JOIN webhook_subscriptions s ON s.id = d.subscription_id "
            "WHERE d.status='pending' AND d.next_attempt_at <= ? "
            "ORDER BY d.created_at LIMIT ?", (now, limit)).fetchall()
        sent = failed = 0
        for r in rows:
            body = r["payload"]
            headers = {
                "Content-Type": "application/json",
                "X-OutreachOS-Event": r["event_type"],
                "X-OutreachOS-Signature": self.sign(r["secret"], body),
            }
            ok, code = poster(r["url"], body, headers)
            attempts = r["attempts"] + 1
            if ok:
                self.store.conn.execute(
                    "UPDATE webhook_deliveries SET status='delivered', attempts=?, response_code=? WHERE id=?",
                    (attempts, code, r["id"]))
                sent += 1
            elif attempts >= MAX_ATTEMPTS:
                self.store.conn.execute(
                    "UPDATE webhook_deliveries SET status='failed', attempts=?, response_code=? WHERE id=?",
                    (attempts, code, r["id"]))
                failed += 1
            else:
                delay = RETRY_SCHEDULE_MIN[min(attempts - 1, len(RETRY_SCHEDULE_MIN) - 1)]
                next_at = _now() + timedelta(minutes=delay)
                self.store.conn.execute(
                    "UPDATE webhook_deliveries SET attempts=?, response_code=?, next_attempt_at=? WHERE id=?",
                    (attempts, code, _iso(next_at), r["id"]))
                failed += 1
        self.store.conn.commit()
        return {"attempted": len(rows), "delivered": sent, "retried_or_failed": failed}

    @staticmethod
    def _post(url: str, body: str, headers: dict) -> tuple[bool, int]:
        try:
            req = urllib.request.Request(url, data=body.encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return 200 <= resp.status < 300, resp.status
        except Exception as e:
            code = getattr(e, "code", 0)
            return False, int(code) if code else 0

    def delivery_log(self, limit: int = 50) -> list[dict]:
        rows = self.store.conn.execute(
            "SELECT id, subscription_id, event_type, status, attempts, response_code, created_at "
            "FROM webhook_deliveries ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
