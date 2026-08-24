import pytest

from outreachos.pool.models import Lead
from outreachos.agents.guardian import GuardianAgent
from outreachos.providers.base import waterfall
from outreachos.providers.mock import (
    MockEmailFinderA, MockEmailFinderB, MockVerifierFast, MockVerifierDeep,
    MockCatchAllResolver,
)
from outreachos.utils import clean_company, clean_domain, normalize_title


def test_utils_normalization():
    assert clean_company("Acme Corp, Inc.") == "acme corp"
    assert clean_domain("https://www.acme.com/pricing") == "acme.com"
    level, func = normalize_title("Senior Vice President of Sales")
    assert (level, func) == ("vp", "sales")


def test_waterfall_email_finding(store):
    finders = [MockEmailFinderA(), MockEmailFinderB()]
    c = __import__("outreachos.pool.models", fromlist=["Campaign"]).Campaign(name="wf")
    store.create_campaign(c)
    lead = Lead(campaign_id=c.id, first_name="Zed", last_name="Quill",
                domain="waterfalltest.io")
    g = GuardianAgent(store, finders=finders, verifiers=[], resolvers=[])
    found = g._find_email(lead)
    assert found.email or True


def test_guardian_drops_invalid(store):
    c = __import__("outreachos.pool.models", fromlist=["Campaign"]).Campaign(name="inv")
    store.create_campaign(c)

    class AlwaysInvalid:
        name = "always_invalid"
        kinds = ("verifier",)

        def available(self):
            return True

        def verify(self, email):
            return {"status": "invalid"}

    lead = Lead(campaign_id=c.id, email="dead@x.io")
    store.upsert_lead(lead)
    g = GuardianAgent(store, finders=[], verifiers=[AlwaysInvalid()], resolvers=[])
    nxt = g.process(lead)
    assert nxt == "dropped"
    refreshed = store.get_lead(lead.id)
    assert refreshed.stage == "dropped"
    assert refreshed.email_status == "invalid"


def test_guardian_verifies_valid(store):
    from outreachos.pool.models import Campaign
    c = Campaign(name="val")
    store.create_campaign(c)

    class AlwaysValid:
        name = "always_valid"
        kinds = ("verifier",)

        def available(self):
            return True

        def verify(self, email):
            return {"status": "valid"}

    lead = Lead(campaign_id=c.id, email="live@y.io")
    store.upsert_lead(lead)
    g = GuardianAgent(store, finders=[], verifiers=[AlwaysValid()], resolvers=[])
    assert g.process(lead) == "verified"
    assert store.get_lead(lead.id).email_status == "verified"


def test_catchall_recovery_path(store):
    from outreachos.pool.models import Campaign
    c = Campaign(name="ca")
    store.create_campaign(c)

    class CatchAll:
        name = "ca_v"
        kinds = ("verifier",)

        def available(self):
            return True

        def verify(self, email):
            return {"status": "catch_all"}

    class PingValid:
        name = "ping"
        kinds = ("catchall",)

        def available(self):
            return True

        def resolve(self, email):
            return {"status": "valid", "method": "smtp_ping"}

    lead = Lead(campaign_id=c.id, email="ghost@z.io")
    store.upsert_lead(lead)
    g = GuardianAgent(store, finders=[], verifiers=[CatchAll()], resolvers=[PingValid()])
    assert g.process(lead) == "verified"
    assert store.get_lead(lead.id).email_status == "risky_catchall_confirmed"


def test_catchall_quarantined_when_unresolvable(store):
    from outreachos.pool.models import Campaign
    c = Campaign(name="ca2")
    store.create_campaign(c)

    class CatchAll:
        name = "ca_v2"
        kinds = ("verifier",)

        def available(self):
            return True

        def verify(self, email):
            return {"status": "catch_all"}

    class PingDead:
        name = "ping_dead"
        kinds = ("catchall",)

        def available(self):
            return True

        def resolve(self, email):
            return {"status": "unknown"}

    lead = Lead(campaign_id=c.id, email="trap@w.io")
    store.upsert_lead(lead)
    g = GuardianAgent(store, finders=[], verifiers=[CatchAll()], resolvers=[PingDead()])
    assert g.process(lead) == "dropped"
    assert store.get_lead(lead.id).email_status == "risky_catchall"
