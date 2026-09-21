"""ICP REFINER - closes the learning loop from outcomes back to targeting.

Research basis: "the $/opp ratio improves more from cleaning data and
tightening ICP than from switching platforms" (2026 AI-SDR field study).
ICPRefiner harvests outcome data per campaign, surfaces the buckets
(industry / title / geography / signal) that actually produce positive
replies and the ones producing negative replies, then records a
concrete refinement recommendation on the campaign event ledger so
future hunts converge on the segment that converts.
"""
from __future__ import annotations

from .base import BaseAgent
from ._pool import _all_campaigns
from ..learning import LearningLoop


class ICPRefinerAgent(BaseAgent):
    name = "icp_refiner"

    def __init__(self, store, llm=None):
        super().__init__(store, llm)
        self.loop = LearningLoop(store)

    def run(self, campaign_id: str | None = None) -> dict:
        if campaign_id:
            campaigns = [c for c in _all_campaigns(self.store) if c.id == campaign_id or c.name == campaign_id]
        else:
            campaigns = _all_campaigns(self.store)
        recommendations: list[dict] = []
        for campaign in campaigns:
            harvest = self.loop.harvest(campaign.id)
            buckets = harvest.get("by_bucket") or harvest.get("buckets") or {}
            keep, drop = [], []
            for key, value in buckets.items():
                if not isinstance(value, dict):
                    continue
                positive = value.get("replied_positive", 0)
                negative = value.get("replied_negative", 0)
                if positive > 0:
                    keep.append({"bucket": key, "positive": positive})
                elif negative >= 3:
                    drop.append({"bucket": key, "negative": negative})
            keep.sort(key=lambda item: -item["positive"])
            recommendation = {
                "campaign": campaign.name,
                "keep_buckets": [item["bucket"] for item in keep[:5]],
                "drop_buckets": [item["bucket"] for item in drop[:5]],
                "source": "outcome_harvest",
            }
            self.store.log_event("campaign", campaign.id, self.name,
                                 "icp_refined", recommendation)
            recommendations.append(recommendation)
        self.stats = {"campaigns_refined": len(recommendations)}
        return {"stats": self.stats, "recommendations": recommendations}

    def process(self, lead):
        raise NotImplementedError("ICPRefinerAgent works at campaign level")
