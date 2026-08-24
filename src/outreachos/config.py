import os
from dataclasses import dataclass, field


def _bool(v: str) -> bool:
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: os.getenv("OUTREACHOS_DB", "./outreachos.db"))
    provider_mode: str = field(default_factory=lambda: os.getenv("PROVIDER_MODE", "mock"))
    llm_mode: str = field(default_factory=lambda: os.getenv("LLM_MODE", "mock"))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "openai"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    daily_send_cap_per_inbox: int = field(default_factory=lambda: int(os.getenv("DAILY_SEND_CAP_PER_INBOX", "30")))
    warmup_min_days: int = field(default_factory=lambda: int(os.getenv("WARMUP_MIN_DAYS", "21")))
    max_bounce_rate: float = field(default_factory=lambda: float(os.getenv("MAX_BOUNCE_RATE", "0.02")))

    @property
    def live_mode(self) -> bool:
        return self.provider_mode == "live"


SETTINGS = Settings()
