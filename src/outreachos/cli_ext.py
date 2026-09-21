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


def cmd_scheduler(args):
    from .orchestration.engine import Engine
    from .scheduler import AutonomousScheduler
    store = PoolStore(SETTINGS.db_path)
    engine = Engine(store)
    scheduler = AutonomousScheduler(store, engine)
    
    if args.run_once:
        campaigns = [args.campaign] if args.campaign else None
        report = scheduler.run_cycle(campaign_names=campaigns, auto_hunt=args.auto_hunt, hunt_limit=args.limit)
        print(json.dumps(report, indent=2))
    elif args.forever:
        try:
            scheduler.run_forever(interval_hours=args.interval, jitter_minutes=args.jitter, auto_hunt=args.auto_hunt)
        except KeyboardInterrupt:
            print("\nScheduler stopped")
        except Exception as e:
            print(f"Scheduler error: {e}")
            return 1
    else:
        print("Use --run-once or --forever")
        return 1
    return 0


def cmd_health(args):
    from .deliverability import DeliverabilityMonitor
    from .infrastructure import InfraManager
    store = PoolStore(SETTINGS.db_path)
    infra = InfraManager(store)
    monitor = DeliverabilityMonitor(store)
    
    print("=== INFRASTRUCTURE ===")
    print(json.dumps(infra.all_inboxes(), indent=2))
    
    print("\n=== DELIVERABILITY CHECK ===")
    print(json.dumps(monitor.check(), indent=2))
    
    print("\n=== DASHBOARD ===")
    print(json.dumps(monitor.dashboard(), indent=2))
    return 0


def cmd_learning(args):
    from .learning import LearningLoop
    store = PoolStore(SETTINGS.db_path)
    learning = LearningLoop(store)
    
    if args.harvest:
        res = learning.harvest(args.campaign)
        print(json.dumps(res, indent=2))
    elif args.best:
        res = learning.best_practices(args.campaign, args.kind, args.top_n)
        print(json.dumps(res, indent=2))
    elif args.summary:
        res = learning.summary(args.campaign)
        print(json.dumps(res, indent=2))
    else:
        print("Use --harvest, --best, or --summary")
        return 1
    return 0


def cmd_webhook_process(args):
    from .webhooks import EventBus
    bus = EventBus(PoolStore(SETTINGS.db_path))
    res = bus.process_due(limit=args.limit)
    print(json.dumps(res, indent=2))
    return 0


def cmd_approvals(args):
    from .orchestration.engine import Engine
    from .pool.store import PoolStore
    store = PoolStore(SETTINGS.db_path)
    engine = Engine(store)
    
    if args.list:
        queue = []
        for c in engine.active_campaigns():
            for l in engine.store.leads(c.id, outreach_state="replied_negative"):
                for n in l.notes:
                    if n.get("type") == "draft_response" and n.get("status") == "needs_human_approval":
                        queue.append({"lead_id": l.id, "lead_name": l.full_name, "campaign": c.name,
                                     "objection": n.get("objection"), "draft": n.get("draft")})
        print(json.dumps(queue, indent=2))
    elif args.approve or args.discard:
        action = "approve" if args.approve else "discard"
        for lead_id in args.lead_ids:
            lead = engine.store.get_lead(lead_id)
            if lead:
                for n in lead.notes:
                    if n.get("type") == "draft_response" and n.get("status") == "needs_human_approval":
                        n["status"] = "approved" if action == "approve" else "discarded"
                lead.notes.append({"agent": "operator", "action": f"draft_{action}d"})
                engine.store.upsert_lead(lead)
                engine.store.log_event(lead.id, lead.campaign_id, "operator", f"draft_{action}d", {})
                if action == "approve":
                    engine.bus.emit("reply.sent", {"lead_id": lead.id, "type": "objection_response"})
        print(f"Drafts {action}d for {len(args.lead_ids)} lead(s)")
    else:
        print("Use --list, --approve <lead_ids>, or --discard <lead_ids>")
        return 1
    return 0


def cmd_portal(args):
    from .dashboard.portal import router
    from fastapi import FastAPI
    import uvicorn
    
    app = FastAPI()
    app.include_router(router)
    
    if args.generate_templates:
        from .dashboard.pages import init_templates
        init_templates()
        print("Portal templates generated")
    else:
        uvicorn.run(app, host=args.host, port=args.port)
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

    sp = sub.add_parser("webhook-process")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_webhook_process)

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

    sp = sub.add_parser("scheduler")
    sp.add_argument("--campaign")
    sp.add_argument("--run-once", action="store_true")
    sp.add_argument("--forever", action="store_true")
    sp.add_argument("--auto-hunt", action="store_true")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--interval", type=float, default=24.0)
    sp.add_argument("--jitter", type=int, default=30)
    sp.set_defaults(func=cmd_scheduler)

    sp = sub.add_parser("health")
    sp.set_defaults(func=cmd_health)

    sp = sub.add_parser("learning")
    sp.add_argument("--campaign", required=True)
    sp.add_argument("--harvest", action="store_true")
    sp.add_argument("--best", action="store_true")
    sp.add_argument("--summary", action="store_true")
    sp.add_argument("--kind", help="angle_style, industry, title_bucket")
    sp.add_argument("--top-n", type=int, default=3)
    sp.set_defaults(func=cmd_learning)

    sp = sub.add_parser("approvals")
    sp.add_argument("--list", action="store_true")
    sp.add_argument("--approve", nargs="+", help="Lead IDs to approve")
    sp.add_argument("--discard", nargs="+", help="Lead IDs to discard")
    sp.set_defaults(func=cmd_approvals)

    sp = sub.add_parser("portal")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8080)
    sp.add_argument("--generate-templates", action="store_true")
    sp.set_defaults(func=cmd_portal)
