from outreachos.pool.models import Lead
from outreachos.agents.signal_scout import SignalScoutAgent
from outreachos.agents.meeting_booker import MeetingBookerAgent
from outreachos.agents.icp_refiner import ICPRefinerAgent
from outreachos.agents.deliverability_ops import DeliverabilityOpsAgent
from outreachos.agents.client_reporter import ClientReporterAgent


def _verified_lead(store, campaign, stage="verified", **kw):
    l = Lead(campaign_id=campaign.id, email="p@q.io", email_status="verified",
             stage=stage, first_name="Sam", last_name="Reed",
             company="Testco", title="VP of Sales", industry="SaaS",
             trigger_signal="raised Series A", **kw)
    store.upsert_lead(l)
    return l


def test_signal_scout_refreshes_and_persists_intent(store, campaign):
    lead = _verified_lead(store, campaign)
    scout = SignalScoutAgent(store)
    stats = scout.run(campaign.id)
    got = store.get_lead(lead.id)
    assert "intent_score" in got.enrichment
    assert stats["leads_refreshed"] >= 1
    assert stats["leads_revived"] == 0


def test_signal_scout_revives_dropped_for_timing(store, campaign):
    lead = _verified_lead(store, campaign, stage="dropped",
                          notes=[{"agent": "guardian", "reason": "timing not right"}])
    scout = SignalScoutAgent(store)
    stats = scout.run(campaign.id)
    got = store.get_lead(lead.id)
    assert got.stage == "hunted"
    assert got.outreach_state == "queued_email"
    assert stats["leads_revived"] == 1


def test_meeting_booker_proposes_slots_for_positive_reply(store, campaign):
    lead = _verified_lead(store, campaign, outreach_state="replied_positive")
    booker = MeetingBookerAgent(store)
    stats = booker.run(campaign.id)
    got = store.get_lead(lead.id)
    assert got.outreach_state == "booked"
    assert got.stage == "booked"
    note = next(n for n in got.notes if n.get("type") == "booking_draft")
    assert len(note["slots"]) == 3
    assert stats["meetings_proposed"] == 1


def test_meeting_booker_requeues_ooo_reply(store, campaign):
    lead = _verified_lead(store, campaign, outreach_state="ooo_autoreply")
    booker = MeetingBookerAgent(store)
    stats = booker.run(campaign.id)
    got = store.get_lead(lead.id)
    assert got.outreach_state == "queued_email"
    assert stats["ooo_requeued"] == 1


def test_icp_refiner_records_recommendation(store, campaign):
    _verified_lead(store, campaign, outreach_state="replied_positive")
    refiner = ICPRefinerAgent(store)
    result = refiner.run(campaign.id)
    assert result["stats"]["campaigns_refined"] == 1
    assert isinstance(result["recommendations"], list)


def test_deliverability_ops_audits_without_crashing(store, campaign):
    _verified_lead(store, campaign)
    ops = DeliverabilityOpsAgent(store)
    result = ops.run()
    assert "stats" in result
    assert result["stats"]["inboxes_audited"] >= 0


def test_client_reporter_generates_report(store, campaign):
    _verified_lead(store, campaign, outreach_state="sent")
    reporter = ClientReporterAgent(store)
    result = reporter.run(campaign.id)
    report = result["reports"][0]
    assert report["campaign"] == campaign.name
    assert "leads_total" in report and "reply_rate" in report
    assert result["stats"]["reports_generated"] == 1
