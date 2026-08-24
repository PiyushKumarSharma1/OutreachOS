import json

from outreachos.config import SETTINGS


def test_full_cycle_end_to_end(engine, campaign):
    report = engine.full_cycle(campaign.name, limit=20)

    assert report["hunt"]["hunted"] > 0
    assert report["guard"]["processed"] > 0
    assert report["stats"]["total_leads"] > 0

    stats = engine.stats(campaign.name)
    assert stats["by_stage"].get("dispatched", 0) + stats["by_outreach_state"].get("sent", 0) > 0

    engaged = engine.store.leads(campaign.id)
    states = {l.outreach_state for l in engaged}
    assert "sent" in states or "replied_positive" in states or "replied_negative" in states or \
        "ooo_autoreply" in states or "queued_linkedin" in states

    booked = [l for l in engaged if l.outreach_state == "booked"]
    for b in booked:
        assert any(n.get("type") == "pre_call_brief" for n in b.notes)


def test_stage_filters_only_verified_reach_profiler(engine, campaign):
    engine.hunt(campaign.name, limit=15)
    engine.qualify(campaign.name)
    profiled_before = [l for l in engine.store.leads(campaign.id) if l.stage == "profiled"]
    assert profiled_before == []

    engine.enrich(campaign.name)
    leads = engine.store.leads(campaign.id)
    for l in leads:
        if l.stage == "profiled":
            assert l.email_status in ("verified", "risky_catchall_confirmed")
        if l.email_status in ("invalid", "risky_catchall") and l.stage != "dropped":
            pass
        else:
            continue


def test_suppression_never_sent(engine, campaign):
    from outreachos.pool.models import Lead
    suppressed = Lead(campaign_id=campaign.id, email="sup@x.io",
                      email_status="suppressed", stage="raw",
                      first_name="Sup", last_name="Press", company="Nope Co",
                      domain="nope.io")
    engine.store.upsert_lead(suppressed)
    res = engine.qualify(campaign.name)
    got = engine.store.get_lead(suppressed.id)
    assert got.stage == "dropped"


def test_sdr_respects_warmup_gate(engine, campaign):
    from outreachos.agents.sdr import SDRAgent
    sdr = SDRAgent(engine.store, inboxes=[
        {"inbox": "cold@newdomain.com", "warmup_days": 2},
    ])
    assert sdr.ready_inboxes() == []


def test_reply_classifier_paths(engine, campaign):
    from outreachos.llm.client import MockLLM
    llm = MockLLM()
    pos = llm.complete_json("", {"_task": "classify_reply", "body": "Sure, let's book a call Thursday"})
    neg = llm.complete_json("", {"_task": "classify_reply", "body": "Not interested, remove me"})
    ooo = llm.complete_json("", {"_task": "classify_reply", "body": "I am out of office until June"})
    unk = llm.complete_json("", {"_task": "classify_reply", "body": "What is the pricing exactly?"})
    assert pos["state"] == "replied_positive"
    assert neg["state"] == "replied_negative"
    assert ooo["state"] == "ooo_autoreply"
    assert unk["state"] == "needs_human"


def test_spam_guard_blocks_spammy_copy():
    from outreachos.utils import spam_score
    score, hits = spam_score("ACT NOW! 100% FREE MONEY guarantee - limited time offer!")
    assert score > 0.3 and hits


def test_stats_shape(engine, campaign):
    s = engine.stats(campaign.name)
    assert {"total_leads", "by_stage", "by_email_status", "by_outreach_state"} <= set(s.keys())
