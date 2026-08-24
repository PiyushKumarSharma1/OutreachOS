"""Base classes + registry for all external data/sending providers.

Every capability is a pluggable waterfall step. Providers are selected by
mode: 'mock' (deterministic synthetic, zero API keys) or 'live' (real APIs).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from ..config import SETTINGS


class Provider(ABC):
    name = "base"

    @abstractmethod
    def available(self) -> bool:
        ...


class LeadSourceProvider(Provider):
    """Sourcing: find companies+contacts matching ICP criteria."""

    def source_leads(self, icp: dict, limit: int) -> list[dict]:
        raise NotImplementedError


class EmailFinderProvider(Provider):
    def find_email(self, first_name: str, last_name: str, domain: str) -> dict:
        """Return {email, confidence} or {} when no confident verdict."""
        raise NotImplementedError


class VerifierProvider(Provider):
    def verify(self, email: str) -> dict:
        """Return {status: valid|invalid|unknown|catch_all, sub_status?}."""
        raise NotImplementedError


class CatchAllResolver(Provider):
    def resolve(self, email: str) -> dict:
        """SMTP-ping style resolution for catch-all addresses."""
        raise NotImplementedError


class EnrichmentProvider(Provider):
    def enrich_person(self, lead: dict) -> dict:
        return {}

    def enrich_company(self, domain: str) -> dict:
        return {}


class SignalProvider(Provider):
    def signals(self, domain: str) -> list[str]:
        return []


class SenderProvider(Provider):
    """Sequencer/sending platform (Instantly / Smartlead style)."""

    def send_batch(self, campaign_id: str, messages: list[dict]) -> list[dict]:
        raise NotImplementedError

    def fetch_replies(self, campaign_id: str) -> list[dict]:
        raise NotImplementedError


REGISTRY: dict[str, type[Provider]] = {}
_registered = False


def _ensure_registered():
    global _registered
    if not _registered:
        from . import mock as _mock_mod
        from . import live as _live_mod
        _registered = True


def register(cls):
    REGISTRY[cls.name] = cls
    return cls


def build(kind: str, name: str | None = None) -> Provider:
    """Instantiate a provider of `kind`. Falls back to the mock variant unless
    live mode is explicitly enabled AND credentials exist."""
    _ensure_registered()
    candidates = [c for c in REGISTRY.values()
                  if kind in getattr(c, "kinds", ())]
    if name:
        matches = [c for c in candidates if c.name == name]
        if not matches:
            raise KeyError(f"provider '{name}' not registered for kind '{kind}'")
        cls = matches[0]
        inst = cls()
        if not inst.available():
            raise ProviderError(f"provider {cls.name} unavailable (missing credentials)")
        return inst
    mock_cls = [c for c in candidates if c.name == f"mock_{kind}"][0]
    if SETTINGS.live_mode:
        for c in candidates:
            if c.name != f"mock_{kind}" and c().available():
                return c()
        raise ProviderError(f"live mode but no credentialed provider for '{kind}'; set keys or PROVIDER_MODE=mock")
    return mock_cls()


def waterfall(kind: str, names: list[str] | None = None) -> list[Provider]:
    """Build an ordered cascade of providers of a given kind."""
    _ensure_registered()
    candidates = [c for c in REGISTRY.values() if kind in getattr(c, "kinds", ())]
    chosen: list[Provider] = []
    if names:
        for n in names:
            for c in candidates:
                if c.name == n:
                    inst = c()
                    if inst.available():
                        chosen.append(inst)
                    break
    else:
        for c in sorted(candidates, key=lambda c: 0 if c.name == f"mock_{kind}" else 1):
            inst = c()
            if inst.available():
                chosen.append(inst)
    if not chosen:
        mock = [c for c in candidates if c.name == f"mock_{kind}"]
        if mock:
            chosen.append(mock[0]())
    return chosen
