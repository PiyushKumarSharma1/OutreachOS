"""Reply intelligence: classification -> routing -> drafting -> learning hooks."""
from __future__ import annotations

from .agents.subagents import ObjectionSubAgent
from .llm.client import LLMClient, get_llm
from .pool.store import PoolStore


class ReplyIntelligence:
    """Processes raw replies into routed outcomes:
    positive -> handoff to pipeline
    objection -> ObjectionSubAgent draft (human approval queue)
    unsubscribe -> compliance suppression
    ooo -> reschedule
    """

    def __init__(self, store: PoolStore, llm: LLMClient | None = None,
                 compliance=None):
        self.store = store
        self.llm = llm or get_llm()
        self.objections = ObjectionSubAgent(self.llm)
        self.compliance = compliance

    def process(self, lead, body: str) -> dict:
        """Full intelligence pass on one reply. Returns routing decision."""
        if self.compliance and self.compliance.detect_unsubscribe_request(body):
            if self.compliance:
                self.compliance.suppress(lead.email, "unsubscribed", source="reply")
            lead.outreach_state = "stopped"
            lead.notes.append({"agent": "compliance", "action": "auto_suppressed"})
            self.store.upsert_lead(lead)
            self.store.log_event(lead.id, lead.campaign_id, "compliance", "suppressed",
                                 {"trigger": "reply_keyword"})
            return {"route": "suppressed"}

        cls = self.objections.classify(body)
        state = cls.get("reply_state", "needs_human")

        if state == "replied_positive":
            lead.outreach_state = "replied_positive"
            lead.stage = "engaged"
            self.store.upsert_lead(lead)
            return {"route": "positive", "state": state}

        if state in ("replied_negative", "needs_human"):
            objection = self.objections.classify(body)
            draft = self.objections.draft_response(objection["objection_type"],
                                                   lead.to_dict())
            lead.outreach_state = "replied_negative"
            lead.notes.append({"agent": "objection_handler", "type": "draft_response",
                               "objection": draft["objection_type"],
                               "draft": draft["draft"], "status": "needs_human_approval"})
            self.store.upsert_lead(lead)
            self.store.log_event(lead.id, lead.campaign_id, "objection_handler",
                                 "draft_prepared",
                                 {"objection": draft["objection_type"]})
            return {"route": "objection", "objection": draft["objection_type"],
                    "draft": draft["draft"]}

        lead.outreach_state = state
        self.store.upsert_lead(lead)
        return {"route": state}
