import json

from outreachos.tenancy import TenancyManager
from outreachos.infrastructure import InfraManager
from outreachos.deliverability import DeliverabilityMonitor
from outreachos.compliance import ComplianceManager
from outreachos.signals import SignalsEngine
from outreachos.experiments import ABEngine, two_proportion_ztest
from outreachos.sequences import SequenceEngine
from outreachos.agents.subagents import ResearchSubAgent, ObjectionSubAgent
from outreachos.reply_intel import ReplyIntelligence
from outreachos.learning import LearningLoop
from outreachos.webhooks import EventBus


def test_tenancy_key_lifecycle(store):
    tm = TenancyManager(store)
    client = tm.create_client("Acme Agency")
    key = tm.create_api_key(client["id"])
    auth = tm.verify(key["raw_key"], "read")
    assert auth and auth["client_id"] == client["id"]
    assert tm.verify(key["raw_key"], "admin") is None
    assert tm.verify("oos_wrong", "read") is None
    assert tm.revoke(key["id"])
    assert tm.verify(key["raw_key"], "read") is None


def test_infra_warmup_gate_and_dns_guard(store):
    infra = InfraManager(store)
    infra.seed_defaults()
    ready = infra.ready_inboxes()
    assert len(ready) >= 5
    infra.add_domain("coldstart.io", dns_configured=False)
    try:
        infra.add_inbox("x@coldstart.io")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_deliverability_auto_pause(store, campaign):
    infra = InfraManager(store)
    infra.seed_defaults()
    monitor = DeliverabilityMonitor(store)
    inbox = infra.ready_inboxes()[0]["email"]
    for _ in range(10):
        store.log_event("", campaign.id, "sdr", "email_sent", {"inbox": inbox})
    for _ in range(2):
        store.log_event("", campaign.id, "sdr", "reply_bounced", {"inbox": inbox})
    res = monitor.check()
    assert res["checked"]
    assert any(a["inbox"] == inbox and a["status"] in ("paused", "quarantined")
               for a in res["actions"])


def test_compliance_suppress_and_unsubscribe(store):
    cm = ComplianceManager(store)
    cm.suppress("bad@x.io", "bounce", "test")
    assert cm.is_suppressed("bad@x.io")
    token = cm.unsubscribe_token("user@y.io", "cmp1")
    assert cm.process_unsubscribe(token, "user@y.io", "cmp1")
    assert not cm.process_unsubscribe("forged", "user@y.io", "cmp1")
    assert cm.is_suppressed("user@y.io")
    body = cm.apply_footer("Hello there", "user@y.io", "cmp1")
    assert "/u/" in body and "Unsubscribe" in body
    assert cm.detect_unsubscribe_request("please unsubscribe me")
    assert not cm.detect_unsubscribe_request("great idea, let's talk")


def test_signals_scoring(store, campaign):
    from outreachos.pool.models import Lead
    eng = SignalsEngine(store)
    lead = Lead(campaign_id=campaign.id, email="s@t.io", company="SigCo",
                domain="sigco.io", first_name="A", last_name="B")
    store.upsert_lead(lead)
    score = eng.score_lead(lead)
    assert 0 <= score <= 100
    refreshed = store.get_lead(lead.id)
    assert refreshed.enrichment.get("intent_score") == score
    top = eng.top_signals(campaign.id)
    assert isinstance(top, list)


def test_ab_significance_and_promotion(store, campaign):
    ab = ABEngine(store)
    assert two_proportion_ztest(50, 100, 5, 100) < 0.001
    assert two_proportion_ztest(10, 100, 10, 100) > 0.9
    exp = ab.create_experiment(campaign.id, "t", [{"key": "A"}, {"key": "B"}],
                               min_sample=5, alpha=0.05)
    leads = [f"lead_{i}" for i in range(40)]
    for i, lid in enumerate(leads):
        v = ab.assign(exp, lid)
        assert v["key"] in ("A", "B")
        assert ab.assign(exp, lid)["key"] == v["key"]
        ab.record_send(exp["id"], lid)
        if v["key"] == "A" and i % 2 == 0:
            ab.record_positive(exp["id"], lid)
    res = ab.evaluate(exp["id"])
    assert res["evaluated"] and res.get("winner") == "A"
    assert ab.winner_config(exp["id"])["key"] == "A"


def test_sequence_engine_rules(store, campaign):
    seq = SequenceEngine(store)
    from outreachos.pool.models import Lead
    lead = Lead(campaign_id=campaign.id, email="q@r.io")
    first = seq.next_step(lead)
    assert first and first["step"] == 1
    seq.mark_sent(lead, 1)
    lead.outreach_state = "replied_positive"
    assert seq.next_step(lead) is None
    lead.outreach_state = "sent"
    lead.enrichment["first_touch_at"] = "2020-01-01T00:00:00+00:00"
    due = seq.due_steps(lead)
    assert [s["step"] for s in due] == [2, 3, 4]


def test_subagents(store, campaign):
    r = ResearchSubAgent().research({"email": "a@b.io", "company": "X", "title": "VP",
                                    "industry": "SaaS", "full_name": "A B"})
    assert len(r["findings"]) == 4 and r["research_quality"] > 0
    o = ObjectionSubAgent()
    assert o.classify("too expensive for us right now")["objection_type"] == "price"
    assert o.classify("not right now, maybe next quarter")["objection_type"] == "timing"
    draft = o.draft_response("price", {"company": "X"})
    assert draft["status"] == "needs_human_approval" and draft["draft"]


def test_reply_intel_unsubscribe_and_objection(store, campaign):
    from outreachos.pool.models import Lead
    cm = ComplianceManager(store)
    intel = ReplyIntelligence(store, compliance=cm)
    lead = Lead(campaign_id=campaign.id, email="u@v.io", first_name="U", last_name="V",
                company="Co", title="VP")
    store.upsert_lead(lead)
    res = intel.process(lead, "please unsubscribe me from this")
    assert res["route"] == "suppressed"
    assert cm.is_suppressed("u@v.io")
    lead2 = Lead(campaign_id=campaign.id, email="n@m.io", first_name="N", last_name="M",
                 company="Co2", title="CTO")
    store.upsert_lead(lead2)
    res2 = intel.process(lead2, "not right now, this quarter is too expensive")
    assert res2["route"] == "objection"
    got = store.get_lead(lead2.id)
    assert any(n.get("type") == "draft_response" for n in got.notes)


def test_learning_loop_harvest(store, campaign):
    from outreachos.pool.models import Lead
    ll = LearningLoop(store)
    for i in range(6):
        l = Lead(campaign_id=campaign.id, email=f"l{i}@x.io", industry="SaaS",
                 title="VP of Sales", first_name="L", last_name=str(i))
        l.angles = ["Signal angle: they just raised", "Value angle: 40% less work"]
        l.outreach_state = "replied_positive" if i % 2 == 0 else "replied_negative"
        store.upsert_lead(l)
    res = ll.harvest(campaign.id)
    assert res["insights_saved"] > 0
    assert ll.recommend_angle_style(campaign.id) is not None
    assert ll.summary(campaign.id)


def test_webhooks_sign_and_retry(store):
    bus = EventBus(store)
    sub = bus.subscribe("http://example.test/hook", ["meeting.booked"], secret="sec123")
    assert bus.emit("meeting.booked", {"lead": "x"}) == 1
    assert bus.emit("other.event", {"lead": "x"}) == 0
    body = json.dumps({"a": 1})
    assert bus.sign("sec123", body).startswith("sha256=")

    calls = []

    def fake_post(url, body, headers):
        calls.append((url, body, headers))
        return False, 500

    res = bus.process_due(poster=fake_post)
    assert res["attempted"] == 1 and res["delivered"] == 0
    url, body, headers = calls[0]
    assert headers["X-OutreachOS-Event"] == "meeting.booked"
    assert headers["X-OutreachOS-Signature"] == bus.sign("sec123", body)
    row = bus.delivery_log()[0]
    assert row["status"] == "pending" and row["attempts"] == 1

    from datetime import datetime, timezone, timedelta
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    store.conn.execute("UPDATE webhook_deliveries SET next_attempt_at=?", (past,))
    store.conn.commit()

    def ok_post(url, payload, headers):
        return True, 200

    res2 = bus.process_due(poster=ok_post)
    assert res2["delivered"] == 1
    assert bus.delivery_log()[0]["status"] == "delivered"
