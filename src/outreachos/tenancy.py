"""Multi-tenancy: clients and API keys with hashed storage + scope checks."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

from .pool.store import PoolStore
from .utils import new_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class TenancyManager:
    SCOPES = {"read", "write", "admin"}

    def __init__(self, store: PoolStore):
        self.store = store

    def create_client(self, name: str, plan: str = "standard") -> dict:
        slug = name.lower().replace(" ", "-")
        client = {"id": new_id("cli"), "name": name, "slug": slug,
                  "plan": plan, "created_at": _now()}
        self.store.conn.execute(
            "INSERT INTO clients (id, name, slug, plan, created_at) VALUES (?,?,?,?,?)",
            (client["id"], name, slug, plan, client["created_at"]))
        self.store.conn.commit()
        return client

    def get_client(self, client_id: str) -> dict | None:
        row = self.store.conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        return dict(row) if row else None

    def list_clients(self) -> list[dict]:
        return [dict(r) for r in self.store.conn.execute("SELECT * FROM clients ORDER BY created_at")]

    def create_api_key(self, client_id: str, scopes: set[str] | None = None) -> dict:
        raw = "oos_" + secrets.token_urlsafe(32)
        prefix = raw[:12]
        rec = {
            "id": new_id("key"), "client_id": client_id,
            "key_hash": _hash_key(raw), "prefix": prefix,
            "scopes": ",".join(sorted((scopes or {"read", "write"}) & self.SCOPES)),
            "created_at": _now(), "revoked": 0,
        }
        self.store.conn.execute(
            "INSERT INTO api_keys (id, client_id, key_hash, prefix, scopes, created_at, revoked) "
            "VALUES (?,?,?,?,?,?,?)",
            (rec["id"], rec["client_id"], rec["key_hash"], rec["prefix"], rec["scopes"],
             rec["created_at"], 0))
        self.store.conn.commit()
        return {"id": rec["id"], "client_id": client_id, "prefix": prefix,
                "scopes": rec["scopes"], "raw_key": raw}

    def verify(self, raw_key: str, required_scope: str = "read") -> dict | None:
        """Returns {client_id, scopes, key_id} when valid + authorized, else None."""
        if not raw_key:
            return None
        row = self.store.conn.execute(
            "SELECT * FROM api_keys WHERE key_hash=? AND revoked=0", (_hash_key(raw_key),)
        ).fetchone()
        if not row:
            return None
        scopes = set(row["scopes"].split(","))
        if required_scope not in scopes and "admin" not in scopes:
            return None
        self.store.conn.execute("UPDATE api_keys SET last_used_at=? WHERE id=?",
                                (_now(), row["id"]))
        self.store.conn.commit()
        return {"client_id": row["client_id"], "scopes": sorted(scopes), "key_id": row["id"]}

    def revoke(self, key_id: str) -> bool:
        cur = self.store.conn.execute("UPDATE api_keys SET revoked=1 WHERE id=?", (key_id,))
        self.store.conn.commit()
        return cur.rowcount > 0

    def list_keys(self, client_id: str) -> list[dict]:
        rows = self.store.conn.execute(
            "SELECT id, prefix, scopes, created_at, last_used_at, revoked FROM api_keys "
            "WHERE client_id=? ORDER BY created_at", (client_id,)).fetchall()
        return [dict(r) for r in rows]
