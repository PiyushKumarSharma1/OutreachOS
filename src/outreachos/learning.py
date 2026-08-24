"""Learning loop: harvests win/loss outcomes into insights; copywriter consumes.

Closes the self-improvement loop:
  send -> reply -> outcomes -> insights (which angles/subjects win) -> better copy
"""
from __future__ import annotations

from collections import defaultdict

from .pool.store import PoolStore
from .utils import new_id
from datetime import datetime, timezone


class LearningLoop:
    def __init__(self, store: PoolStore):
        self.store = store

    def harvest(self, campaign_id: str) -> dict:
        leads = self.store.leads(campaign_id)
        angle_wins: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        industry_wins: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        title_wins: dict[str, list[int]] = defaultdict(lambda: [0, 0])

        for l in leads:
            won = 1 if l.outreach_state in ("replied_positive", "booked") else 0
            engaged = won or l.outreach_state in ("replied_negative", "sent", "dispatched")
            if not engaged:
                continue
            for i, angle in enumerate(l.angles[:3]):
                style = angle.split(":")[0].strip() if ":" in angle else f"angle_{i}"
                angle_wins[style][0] += won
                angle_wins[style][1] += 1
            if l.industry:
                industry_wins[l.industry][0] += won
                industry_wins[l.industry][1] += 1
            level, func = _title_bucket(l.title)
            title_wins[f"{level}:{func}"][0] += won
            title_wins[f"{level}:{func}"][1] += 1

        saved = 0
        for kind, buckets in (("angle_style", angle_wins),
                              ("industry", industry_wins),
                              ("title_bucket", title_wins)):
            for key, (wins, n) in buckets.items():
                if n < 3:
                    continue
                win_rate = wins / n
                self.store.conn.execute(
                    "INSERT INTO insights (id, campaign_id, kind, key, value, sample_size, win_rate, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (new_id("ins"), campaign_id, kind, key,
                     f"{wins}/{n}", n, round(win_rate, 4),
                     datetime.now(timezone.utc).isoformat()))
                saved += 1
        self.store.conn.commit()
        return {"insights_saved": saved}

    def best_practices(self, campaign_id: str, kind: str | None = None,
                       top_n: int = 3) -> list[dict]:
        q = "SELECT kind, key, value, sample_size, win_rate FROM insights WHERE campaign_id=?"
        args: list = [campaign_id]
        if kind:
            q += " AND kind=?"
            args.append(kind)
        q += " ORDER BY win_rate DESC LIMIT ?"
        args.append(top_n)
        return [dict(r) for r in self.store.conn.execute(q, args)]

    def recommend_angle_style(self, campaign_id: str) -> str | None:
        rows = self.best_practices(campaign_id, kind="angle_style", top_n=1)
        if rows and rows[0]["sample_size"] >= 5:
            return rows[0]["key"]
        return None

    def summary(self, campaign_id: str) -> dict:
        rows = self.store.conn.execute(
            "SELECT kind, key, value, win_rate FROM insights WHERE campaign_id=? "
            "ORDER BY created_at DESC LIMIT 20", (campaign_id,)).fetchall()
        by_kind: dict[str, list] = defaultdict(list)
        for r in rows:
            by_kind[r["kind"]].append({"key": r["key"], "win_rate": r["win_rate"]})
        return {k: sorted(v, key=lambda x: -x["win_rate"])[:3] for k, v in by_kind.items()}


def _title_bucket(title: str) -> tuple[str, str]:
    from .utils import normalize_title
    return normalize_title(title)
