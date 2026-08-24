"""Additional CLI commands for v0.4 systems (clients, infra, webhooks, AB)."""
from __future__ import annotations

import json

from .config import SETTINGS
from .pool.store import PoolStore
from .tenancy import TenancyManager
from .infrastructure import InfraManager
from .webhooks import EventBus
from .experiments import ABEngine
from .compliance import ComplianceManager


def cmd_client(args):
    tm = TenancyManager(PoolStore(SETTINGS.db_path))
    client = tm.create_client(args.name)
    key = tm.create_api_key(client["id"])
    print(json.dumps({"client": client, "api_key": key}, indent=2))
    return 0


def cmd_key(args):
    tm = TenancyManager(PoolStore(SETTINGS.db_path))
    key = tm.create_api_key(args.client_id)
    print(json.dumps(key, indent=2))
    return 0


def cmd_infra(args):
    eng_store = PoolStore(SETTINGS.db_path)
    infra = InfraManager(eng_store)
    if args.seed:
        print(json.dumps({"seeded": infra.seed_defaults()}, indent=2))
    else:
        print(json.dumps(infra.all_inboxes(), indent=2))
    return 0


def cmd_webhook(args):
    bus = EventBus(PoolStore(SETTINGS.db_path))
    sub = bus.subscribe(args.url, args.events.split(","))
    print(json.dumps(sub, indent=2))
    return 0


def cmd_ab(args):
    store = PoolStore(SETTINGS.db_path)
    engine_store = store
    from .orchestration.engine import Engine
    c = Engine(engine_store).get_campaign(args.campaign)
    exp = ABEngine(store).create_experiment(
        c.id, args.name or "subject-test",
        [{"key": "A", "subject": args.subject_a}, {"key": "B", "subject": args.subject_b}])
    print(json.dumps(exp, indent=2))
    return 0


def cmd_suppress(args):
    cm = ComplianceManager(PoolStore(SETTINGS.db_path))
    cm.suppress(args.email, args.reason or "manual", source="cli")
    print(f"suppressed {args.email}")
    return 0


def register(sub):
    sp = sub.add_parser("client")
    sp.add_argument("--name", required=True)
    sp.set_defaults(func=cmd_client)

    sp = sub.add_parser("key")
    sp.add_argument("--client-id", required=True)
    sp.set_defaults(func=cmd_key)

    sp = sub.add_parser("infra")
    sp.add_argument("--seed", action="store_true")
    sp.set_defaults(func=cmd_infra)

    sp = sub.add_parser("webhook")
    sp.add_argument("--url", required=True)
    sp.add_argument("--events", default="*")
    sp.set_defaults(func=cmd_webhook)

    sp = sub.add_parser("ab")
    sp.add_argument("--campaign", required=True)
    sp.add_argument("--name", default="subject-test")
    sp.add_argument("--subject-a", required=True)
    sp.add_argument("--subject-b", required=True)
    sp.set_defaults(func=cmd_ab)

    sp = sub.add_parser("suppress")
    sp.add_argument("--email", required=True)
    sp.add_argument("--reason", default="manual")
    sp.set_defaults(func=cmd_suppress)
