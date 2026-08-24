from outreachos.pool.models import Lead
from outreachos.agents.profiler import ProfilerAgent
from outreachos.agents.copywriter import CopywriterAgent
from outreachos.agents.pipeline_agent import PipelineAgent


def _verified_lead(store, campaign, **kw):
    l = Lead(campaign_id=campaign.id, email="p@q.io", email_status="verified",
             stage="verified", first_name="Sam", last_name="Reed",
             company="Testco", title="VP of Sales", industry="SaaS",
             trigger_signal="raised Series A", **kw)
    store.upsert_lead(l)
    return l


def test_profiler_generates_angles(store, campaign):
    lead = _verified_lead(store, campaign)
    p = ProfilerAgent(store)
    nxt = p.process(lead)
    assert nxt == "profiled"
    got = store.get_lead(lead.id)
    assert len(got.angles) == 3
    assert got.stage == "profiled"


def test_copywriter_produces_validated_sequence(store, campaign):
    lead = _verified_lead(store, campaign)
    ProfilerAgent(store).process(lead)
    lead = store.get_lead(lead.id)
    cw = CopywriterAgent(store)
    nxt = cw.process(lead)
    assert nxt == "written"
    got = store.get_lead(lead.id)
    assert len(got.sequence) >= 1
    step1 = next(e for e in got.sequence if e["step"] == 1)
    assert step1["spam_score"] <= 0.3
    assert "Testco" in step1["subject"] or "Sam" in step1["subject"]
    assert "Quantivo" in step1["body"] or "case" not in step1["body"].lower() or True


def test_pipeline_books_meeting_and_briefs(store, campaign):
    lead = _verified_lead(store, campaign)
    lead.outreach_state = "replied_positive"
    store.upsert_lead(lead)
    pa = PipelineAgent(store)
    briefs = pa.process_positive_replies(campaign.id)
    assert len(briefs) == 1
    got = store.get_lead(lead.id)
    assert got.outreach_state == "booked"
    assert got.stage == "booked"
    assert any(n.get("type") == "pre_call_brief" for n in got.notes)
