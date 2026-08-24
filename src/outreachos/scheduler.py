"""Autonomous scheduler: unattended daily campaign cycles with overlap lock."""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

from .pool.store import PoolStore
from .orchestration.engine import Engine


class SchedulerLock:
    def __init__(self, db_path: str):
        self.lock_path = Path(db_path).parent / "scheduler.lock"

    def acquire(self) -> bool:
        if self.lock_path.exists():
            try:
                pid = int(self.lock_path.read_text().strip())
                os.kill(pid, 0)
                return False
            except (ProcessLookupError, ValueError):
                self.lock_path.unlink()
        self.lock_path.write_text(str(os.getpid()))
        return True

    def release(self):
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass


class AutonomousScheduler:
    """Runs the full agent pipeline for active campaigns on a schedule.

    A cycle = qualify -> enrich -> copy -> dispatch -> replies/book.
    Hunt runs only when auto_hunt=True so lists stay deliberate.
    """

    def __init__(self, store: PoolStore | None = None, engine: Engine | None = None):
        self.store = store or PoolStore()
        self.engine = engine or Engine(self.store)

    def run_cycle(self, campaign_names: list[str] | None = None,
                  auto_hunt: bool = False, hunt_limit: int = 25) -> dict:
        campaigns = campaign_names
        if campaigns is None:
            campaigns = [c.name for c in self._active_campaigns()]
        report: dict[str, dict] = {}
        for name in campaigns:
            try:
                report[name] = self._run_one(name, auto_hunt, hunt_limit)
            except Exception as e:
                report[name] = {"error": str(e)}
                self.store.log_event("", "", "scheduler", "cycle_error",
                                     {"campaign": name, "error": str(e)})
        return report

    def _run_one(self, name: str, auto_hunt: bool, hunt_limit: int) -> dict:
        steps: dict = {}
        if auto_hunt:
            steps["hunt"] = self.engine.hunt(name, hunt_limit)
        steps["qualify"] = self.engine.qualify(name)
        steps["enrich"] = self.engine.enrich(name)
        steps["copy"] = self.engine.write_copy(name)
        steps["dispatch"] = self.engine.dispatch(name)
        engage = self.engine.process_replies(name)
        steps["engage"] = {"replies": engage.get("replies", {}), "booked": engage.get("booked", 0)}
        self.store.log_event("", self.engine.get_campaign(name).id, "scheduler",
                             "cycle_complete",
                             {k: v for k, v in steps.items()})
        return steps

    def _active_campaigns(self):
        rows = self.store.conn.execute("SELECT data FROM campaigns").fetchall()
        from .pool.models import Campaign
        return [Campaign.from_dict(json.loads(r["data"])) for r in rows]

    def run_forever(self, interval_hours: float = 24.0, jitter_minutes: int = 30,
                    auto_hunt: bool = False):
        lock = SchedulerLock(self.store.db_path)
        if not lock.acquire():
            raise RuntimeError("scheduler already running")
        try:
            while True:
                self.run_cycle(auto_hunt=auto_hunt)
                sleep_s = interval_hours * 3600 + random.randint(-jitter_minutes * 60, jitter_minutes * 60)
                time.sleep(max(sleep_s, 60))
        finally:
            lock.release()
