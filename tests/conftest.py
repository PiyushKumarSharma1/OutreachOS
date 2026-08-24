import os
import sys
import tempfile
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from outreachos.pool.store import PoolStore
from outreachos.orchestration.engine import Engine


@pytest.fixture()
def store(tmp_path):
    s = PoolStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture()
def engine(store):
    return Engine(store)


@pytest.fixture()
def campaign(engine):
    return engine.create_campaign(
        "test-campaign",
        icp={"industries": ["SaaS"], "titles": ["VP of Sales"], "headcount_min": 10, "headcount_max": 500},
        offer="AI meetings on autopilot",
        case_studies=[{"industry": "SaaS", "name": "Acme", "result": "2x pipeline", "timeframe": "30 days"}],
    )
