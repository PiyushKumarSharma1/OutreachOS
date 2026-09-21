"""Shared helpers for common-pool agents."""
from __future__ import annotations

import json

from ..pool.models import Campaign


def _all_campaigns(store) -> list[Campaign]:
    rows = store.conn.execute("SELECT data FROM campaigns").fetchall()
    return [Campaign.from_dict(json.loads(r["data"])) for r in rows]
