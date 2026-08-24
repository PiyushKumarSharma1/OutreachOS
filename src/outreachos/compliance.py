"""Compliance: suppression list, unsubscribe tokens, CAN-SPAM footer injection."""
from __future__ import annotations

import hashlib
import hmac
import os
import re

from .pool.store import PoolStore

UNSUB_SECRET = os.getenv("OUTREACHOS_UNSUB_SECRET", "dev-unsub-secret-change-me")
UNSUB_RE = re.compile(r"\b(unsubscribe|opt.?out|remove me|take me off)\b", re.IGNORECASE)
FOOTER_TEMPLATE = (
    "\n\n---\n{company_name} · {address}\n"
    "You received this one-time business email. "
    "Unsubscribe: {base_url}/u/{token}"
)


class ComplianceManager:
    def __init__(self, store: PoolStore, base_url: str = "https://outreachos.local"):
        self.store = store
        self.base_url = base_url.rstrip("/")
        self.company_name = os.getenv("OUTREACHOS_LEGAL_NAME", "OutreachOS")
        self.address = os.getenv("OUTREACHOS_ADDRESS", "123 Market St, San Francisco, CA")

    def suppress(self, email: str, reason: str, source: str = "manual") -> bool:
        self.store.conn.execute(
            "INSERT OR IGNORE INTO suppressions (email, reason, source, created_at) "
            "VALUES (?,?,?,datetime('now'))",
            (email.lower(), reason, source))
        self.store.conn.commit()
        lead = self.store.conn.execute(
            "SELECT id, data FROM leads WHERE data LIKE ? AND data LIKE ?",
            (f'%"{email.lower()}"%', "%email%")).fetchone()
        if lead:
            from .pool.models import Lead
            l = Lead.from_dict(json_loads(lead["data"]))
            l.email_status = "suppressed"
            l.outreach_state = "stopped"
            self.store.upsert_lead(l)
        return True

    def is_suppressed(self, email: str) -> bool:
        row = self.store.conn.execute(
            "SELECT 1 FROM suppressions WHERE email=?", (email.lower(),)).fetchone()
        return row is not None

    def list_suppressions(self, limit: int = 500) -> list[dict]:
        rows = self.store.conn.execute(
            "SELECT * FROM suppressions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def unsubscribe_token(self, email: str, campaign_id: str) -> str:
        msg = f"{email.lower()}|{campaign_id}".encode()
        return hmac.new(UNSUB_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:24]

    def verify_token(self, token: str, email: str, campaign_id: str) -> bool:
        return hmac.compare_digest(token, self.unsubscribe_token(email, campaign_id))

    def process_unsubscribe(self, token: str, email: str, campaign_id: str) -> bool:
        if not self.verify_token(token, email, campaign_id):
            return False
        self.suppress(email, "unsubscribed", source="link")
        return True

    def apply_footer(self, body: str, email: str, campaign_id: str) -> str:
        if "{unsub_url}" in body or "/u/" in body:
            return body
        token = self.unsubscribe_token(email, campaign_id)
        footer = FOOTER_TEMPLATE.format(
            company_name=self.company_name, address=self.address,
            base_url=self.base_url, token=token)
        return body + footer

    def detect_unsubscribe_request(self, text: str) -> bool:
        return bool(UNSUB_RE.search(text or ""))


def json_loads(s: str) -> dict:
    import json
    return json.loads(s)
