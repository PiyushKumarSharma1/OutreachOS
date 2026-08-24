"""A/B experiment engine with deterministic assignment + significance testing.

- Variants split traffic by stable hash (50/50 default, no drift)
- Outcomes recorded per variant (sent, positives)
- Two-proportion z-test; winner promoted when p < alpha AND min_sample met
"""
from __future__ import annotations

import math

from .pool.store import PoolStore
from .pool.models import new_id
from .utils import stable_seed
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def two_proportion_ztest(s1: int, n1: int, s2: int, n2: int) -> float:
    """Returns two-sided p-value. Pooled standard error."""
    if n1 == 0 or n2 == 0:
        return 1.0
    p1, p2 = s1 / n1, s2 / n2
    p = (s1 + s2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (p1 - p2) / se
    return 2 * (1 - _norm_cdf(abs(z)))


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


class ABEngine:
    def __init__(self, store: PoolStore):
        self.store = store

    def create_experiment(self, campaign_id: str, name: str,
                          variants: list[dict], min_sample: int = 60,
                          alpha: float = 0.05) -> dict:
        exp_id = new_id("exp")
        self.store.conn.execute(
            "INSERT INTO experiments (id, campaign_id, name, metric, status, min_sample, alpha, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (exp_id, campaign_id, name, "positive_reply", "running", min_sample, alpha, _now()))
        for i, v in enumerate(variants):
            key = v.get("key") or chr(65 + i)
            self.store.conn.execute(
                "INSERT INTO variants (id, experiment_id, key, subject, opener_hint, sent, positives) "
                "VALUES (?,?,?,?,?,0,0)",
                (new_id("var"), exp_id, key, v.get("subject", ""), v.get("opener_hint", "")))
        self.store.conn.commit()
        return self.get_experiment(exp_id)

    def get_experiment(self, exp_id: str) -> dict | None:
        row = self.store.conn.execute("SELECT * FROM experiments WHERE id=?", (exp_id,)).fetchone()
        if not row:
            return None
        exp = dict(row)
        exp["variants"] = [dict(r) for r in self.store.conn.execute(
            "SELECT * FROM variants WHERE experiment_id=? ORDER BY key", (exp_id,))]
        return exp

    def running_for_campaign(self, campaign_id: str) -> dict | None:
        row = self.store.conn.execute(
            "SELECT * FROM experiments WHERE campaign_id=? AND status='running' "
            "ORDER BY created_at DESC LIMIT 1", (campaign_id,)).fetchone()
        return self.get_experiment(row["id"]) if row else None

    def assign(self, exp: dict, lead_id: str) -> dict:
        """Deterministic hash assignment. Returns variant dict."""
        existing = self.store.conn.execute(
            "SELECT * FROM assignments WHERE lead_id=?", (lead_id,)).fetchone()
        if existing and existing["experiment_id"] == exp["id"]:
            return next(v for v in exp["variants"] if v["key"] == existing["variant_key"])
        n = len(exp["variants"])
        idx = stable_seed("ab", exp["id"], lead_id) % n
        variant = exp["variants"][idx]
        self.store.conn.execute(
            "INSERT OR REPLACE INTO assignments (lead_id, experiment_id, variant_key, assigned_at) "
            "VALUES (?,?,?,?)", (lead_id, exp["id"], variant["key"], _now()))
        self.store.conn.commit()
        return variant

    def record_send(self, exp_id: str, lead_id: str):
        self.store.conn.execute(
            "UPDATE variants SET sent = sent + 1 WHERE experiment_id=? AND key = "
            "(SELECT variant_key FROM assignments WHERE lead_id=?)", (exp_id, lead_id))
        self.store.conn.commit()

    def record_positive(self, exp_id: str, lead_id: str):
        self.store.conn.execute(
            "UPDATE variants SET positives = positives + 1 WHERE experiment_id=? AND key = "
            "(SELECT variant_key FROM assignments WHERE lead_id=?)", (exp_id, lead_id))
        self.store.conn.commit()

    def evaluate(self, exp_id: str) -> dict:
        """Check significance; promote winner if criteria met."""
        exp = self.get_experiment(exp_id)
        if not exp or exp["status"] != "running" or len(exp["variants"]) != 2:
            return {"evaluated": False, "reason": "not_eligible"}
        a, b = exp["variants"]
        p = two_proportion_ztest(a["positives"], a["sent"], b["positives"], b["sent"])
        result = {"evaluated": True, "p_value": round(p, 4),
                  "a": f"{a['positives']}/{a['sent']}", "b": f"{b['positives']}/{b['sent']}",
                  "min_sample_met": min(a["sent"], b["sent"]) >= exp["min_sample"]}
        if result["min_sample_met"] and p < exp["alpha"]:
            winner = "A" if a["positives"] / a["sent"] >= b["positives"] / b["sent"] else "B"
            self.store.conn.execute(
                "UPDATE experiments SET status='complete', winner=? WHERE id=?", (winner, exp_id))
            self.store.conn.commit()
            result["winner"] = winner
            result["promoted"] = True
        return result

    def winner_config(self, exp_id: str) -> dict | None:
        exp = self.get_experiment(exp_id)
        if exp and exp.get("winner"):
            return next(v for v in exp["variants"] if v["key"] == exp["winner"])
        return None
