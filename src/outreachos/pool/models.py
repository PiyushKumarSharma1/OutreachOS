from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


STAGES = ["raw", "hunted", "verified", "profiled", "written", "dispatched", "engaged", "booked", "dropped"]

EMAIL_STATUSES = [
    "none", "found", "verified", "risky_catchall", "risky_catchall_confirmed",
    "invalid", "suppressed",
]

OUTREACH_STATES = [
    "new", "queued_email", "queued_linkedin", "sent", "replied_positive",
    "replied_negative", "ooo_autoreply", "bounced", "stopped", "booked",
]


@dataclass
class ICP:
    industries: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    geos: list[str] = field(default_factory=list)
    headcount_min: int = 10
    headcount_max: int = 5000
    signals: list[str] = field(default_factory=list)

    def to_dict(self):
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict):
        return cls(**d)


@dataclass
class Campaign:
    id: str = ""
    name: str = ""
    icp: ICP = field(default_factory=ICP)
    offer: str = ""
    case_studies: list[dict] = field(default_factory=list)
    status: str = "draft"
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = new_id("cmp")
        if not self.created_at:
            self.created_at = now_iso()

    def to_dict(self):
        d = self.__dict__.copy()
        d["icp"] = self.icp.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict):
        d = dict(d)
        icp = d.pop("icp", {})
        if isinstance(icp, dict):
            d["icp"] = ICP.from_dict(icp)
        return cls(**d)


@dataclass
class Lead:
    campaign_id: str
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    company: str = ""
    domain: str = ""
    email: str = ""
    email_status: str = "none"
    linkedin_url: str = ""
    location: str = ""
    industry: str = ""
    headcount: int = 0
    source: str = ""
    trigger_signal: str = ""
    enrichment: dict = field(default_factory=dict)
    research: dict = field(default_factory=dict)
    angles: list[str] = field(default_factory=list)
    sequence: list[dict] = field(default_factory=list)
    outreach_state: str = "new"
    stage: str = "raw"
    notes: list[dict] = field(default_factory=list)
    id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = new_id("lead")
        if not self.created_at:
            self.created_at = now_iso()
        if not self.updated_at:
            self.updated_at = self.created_at

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def to_dict(self):
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict):
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Event:
    lead_id: str
    agent: str
    action: str
    detail: dict = field(default_factory=dict)
    created_at: str = ""
    id: int | None = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = now_iso()
