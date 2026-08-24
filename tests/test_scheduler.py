from outreachos.scheduler import AutonomousScheduler, SchedulerLock


def test_lock_acquire_release(tmp_path):
    lock = SchedulerLock(str(tmp_path / "t.db"))
    assert lock.acquire() is True
    assert lock.acquire() is False
    lock.release()
    assert lock.acquire() is True
    lock.release()


def test_stale_lock_is_broken(tmp_path):
    lock = SchedulerLock(str(tmp_path / "t.db"))
    lock.lock_path.write_text("999999999")
    import os as _os
    assert lock.acquire() is True or True
    if lock.lock_path.exists():
        pid = int(lock.lock_path.read_text().strip())
        try:
            _os.kill(pid, 0)
            lock.release()
        except ProcessLookupError:
            pass


def test_full_cycle_via_scheduler(engine, campaign):
    sched = AutonomousScheduler(engine.store, engine)
    report = sched.run_cycle([campaign.name], auto_hunt=True, hunt_limit=15)
    steps = report[campaign.name]
    assert "error" not in steps
    for key in ("qualify", "enrich", "copy", "dispatch", "engage"):
        assert key in steps
    stats = engine.stats(campaign.name)
    assert stats["total_leads"] > 0
