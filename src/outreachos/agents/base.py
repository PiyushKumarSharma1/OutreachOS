from __future__ import annotations

from abc import ABC, abstractmethod
from ..pool.store import PoolStore
from ..llm.client import LLMClient, get_llm


class BaseAgent(ABC):
    name = "base"

    def __init__(self, store: PoolStore, llm: LLMClient | None = None):
        self.store = store
        self.llm = llm or get_llm()
        self.stats: dict = {}

    @abstractmethod
    def process(self, lead) -> str:
        """Process one lead; returns next stage name."""

    def run_batch(self, leads) -> dict:
        done = dropped = 0
        for lead in leads:
            try:
                nxt = self.process(lead)
                if nxt == "dropped":
                    dropped += 1
                else:
                    done += 1
            except Exception as e:
                self.store.log_event(lead.id, lead.campaign_id, self.name, "error", {"error": str(e)})
                dropped += 1
        self.stats = {"processed": len(leads), "advanced": done, "dropped": dropped}
        return self.stats

    def log(self, lead, action: str, detail: dict | None = None):
        self.store.log_event(lead.id, lead.campaign_id, self.name, action, detail or {})
