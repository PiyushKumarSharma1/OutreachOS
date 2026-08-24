"""OutreachOS CLI - run the autonomous outreach pipeline from the terminal."""
from __future__ import annotations

import argparse
import json
import sys

from .config import SETTINGS
from .pool.store import PoolStore
from .orchestration.engine import Engine


DEMO_CAMPAIGN = {
    "name": "demo-agency-growth",
    "icp": {
        "industries": ["SaaS"],
        "titles": ["VP of Sales", "Head of Growth", "Chief Revenue Officer", "Demand Gen Manager"],
        "geos": ["US"],
        "headcount_min": 20,
        "headcount_max": 1000,
    },
    "offer": "an AI outreach system that books 10-20 qualified meetings/month or you don't pay",
    "case_studies": [
        {"industry": "SaaS", "name": "Quantivo", "result": "31 booked meetings in month one",
         "timeframe": "45 days"},
    ],
}


def cmd_init(args):
    store = PoolStore(SETTINGS.db_path)
    print(f"Common Pool initialized at {SETTINGS.db_path}")
    return 0


def cmd_campaign(args):
    store = PoolStore(SETTINGS.db_path)
    engine = Engine(store)
    icp = json.loads(args.icp) if args.icp else {}
    cs = json.loads(args.case_studies) if args.case_studies else []
    c = engine.create_campaign(args.name, icp=icp, offer=args.offer or "", case_studies=cs)
    print(json.dumps({"id": c.id, "name": c.name}, indent=2))
    return 0


def cmd_hunt(args):
    engine = Engine(PoolStore(SETTINGS.db_path))
    res = engine.hunt(args.campaign, args.limit)
    print(json.dumps(res, indent=2))
    return 0


def cmd_run(args):
    engine = Engine(PoolStore(SETTINGS.db_path))
    report = {}
    if not args.stage or args.stage == "full":
        report = engine.full_cycle(args.campaign, limit=args.limit)
    elif args.stage == "qualify":
        report = engine.qualify(args.campaign)
    elif args.stage == "enrich":
        report = engine.enrich(args.campaign)
    elif args.stage == "copy":
        report = engine.write_copy(args.campaign)
    print(json.dumps(report, indent=2, default=str))
    return 0


def cmd_dispatch(args):
    engine = Engine(PoolStore(SETTINGS.db_path))
    res = engine.dispatch(args.campaign)
    print(json.dumps(res, indent=2, default=str))
    return 0


def cmd_replies(args):
    engine = Engine(PoolStore(SETTINGS.db_path))
    res = engine.process_replies(args.campaign)
    print(json.dumps(res, indent=2, default=str))
    return 0


def cmd_stats(args):
    engine = Engine(PoolStore(SETTINGS.db_path))
    print(json.dumps(engine.stats(args.campaign), indent=2))
    return 0


def cmd_lead(args):
    engine = Engine(PoolStore(SETTINGS.db_path))
    tl = engine.lead_timeline(args.lead_id)
    if not tl["lead"]:
        print("lead not found", file=sys.stderr)
        return 1
    print(json.dumps(tl, indent=2, default=str))
    return 0


def cmd_demo(args):
    store = PoolStore(SETTINGS.db_path)
    engine = Engine(store)
    c = engine.create_campaign(
        DEMO_CAMPAIGN["name"], icp=DEMO_CAMPAIGN["icp"],
        offer=DEMO_CAMPAIGN["offer"], case_studies=DEMO_CAMPAIGN["case_studies"])
    print(f"[demo] campaign ready: {c.id}")
    report = engine.full_cycle(c.name, limit=args.limit)
    print(json.dumps(report, indent=2, default=str))
    leads = [l for l in store.leads(c.id) if l.outreach_state == "booked"]
    if leads:
        tl = engine.lead_timeline(leads[0].id)
        print("\n=== SAMPLE BOOKED LEAD TIMELINE ===")
        print(json.dumps(tl, indent=2, default=str))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="outreachos", description="Autonomous AI Outreach OS")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    sp = sub.add_parser("campaign")
    sp.add_argument("--name", required=True)
    sp.add_argument("--icp", help="JSON ICP: industries,titles,geos,headcount_min,headcount_max")
    sp.add_argument("--offer")
    sp.add_argument("--case-studies", dest="case_studies")
    sp.set_defaults(func=cmd_campaign)

    sp = sub.add_parser("hunt")
    sp.add_argument("--campaign", required=True)
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(func=cmd_hunt)

    sp = sub.add_parser("run")
    sp.add_argument("--campaign", required=True)
    sp.add_argument("--stage", choices=["full", "qualify", "enrich", "copy"], default="full")
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("dispatch")
    sp.add_argument("--campaign", required=True)
    sp.set_defaults(func=cmd_dispatch)

    sp = sub.add_parser("replies")
    sp.add_argument("--campaign", required=True)
    sp.set_defaults(func=cmd_replies)

    sp = sub.add_parser("stats")
    sp.add_argument("--campaign", required=True)
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("lead")
    sp.add_argument("lead_id")
    sp.set_defaults(func=cmd_lead)

    sp = sub.add_parser("demo")
    sp.add_argument("--limit", type=int, default=30)
    sp.set_defaults(func=cmd_demo)

    from .cli_ext import register as register_ext
    register_ext(sub)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
