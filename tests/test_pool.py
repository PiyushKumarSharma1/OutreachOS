from outreachos.pool.store import PoolStore
from outreachos.pool.models import Lead, Campaign


def test_campaign_crud(store):
    c = Campaign(name="x", offer="test")
    store.create_campaign(c)
    got = store.get_campaign_by_name("x")
    assert got is not None and got.id == c.id
    assert store.get_campaign_by_name("nope") is None


def test_lead_upsert_and_filters(store):
    c = Campaign(name="f1")
    store.create_campaign(c)
    a = Lead(campaign_id=c.id, first_name="A", email_status="verified", stage="verified")
    b = Lead(campaign_id=c.id, first_name="B", email_status="invalid", stage="dropped")
    store.upsert_lead(a)
    store.upsert_lead(b)

    all_leads = store.leads(c.id)
    assert len(all_leads) == 2

    verified = store.leads(c.id, stage="verified")
    assert [l.first_name for l in verified] == ["A"]

    dropped = store.leads(c.id, outreach_state="new", stage="dropped")
    assert [l.first_name for l in dropped] == ["B"]


def test_update_lead(store):
    c = Campaign(name="u")
    store.create_campaign(c)
    l = Lead(campaign_id=c.id)
    store.upsert_lead(l)
    updated = store.update_lead(l.id, title="VP of Sales", stage="profiled")
    assert updated.title == "VP of Sales"
    assert updated.stage == "profiled"


def test_events_and_stats(store):
    c = Campaign(name="e")
    store.create_campaign(c)
    l = Lead(campaign_id=c.id, email="a@b.com", email_status="verified",
             stage="dispatched", outreach_state="replied_positive")
    store.upsert_lead(l)
    store.log_event(l.id, c.id, "guardian", "verified", {"status": "verified"})
    evs = store.events_for_lead(l.id)
    assert len(evs) == 1 and evs[0].agent == "guardian"

    stats = store.campaign_stats(c.id)
    assert stats["total_leads"] == 1
    assert stats["positive_replies"] == 1
