# OutreachOS

**Autonomous AI Outreach & Lead Generation Agency OS** — a multi-agent system where 7 specialized agents share a Common Pool to find leads, verify emails via waterfall enrichment, write personalized outreach, send across email + LinkedIn, classify replies, and book meetings. Zero human intervention in the loop.

Built on 2026 operator research: waterfall enrichment (85–95% coverage vs 60% single-provider), catch-all SMTP recovery, strict deliverability gates (<2% bounce, 21-day warmup, 30 sends/inbox/day), and the one-AI-sentence personalization pattern that beats fully-generated spam.

## Quickstart (zero API keys needed)

```bash
cd OutreachOS
uv venv .venv && uv pip install pytest --python .venv/bin/python
PYTHONPATH=src .venv/bin/python -m outreachos.cli demo --limit 25
```

The demo runs the full pipeline on synthetic data:

```
hunt: 25 leads sourced → guard: 22 verified, 3 dropped by waterfall
profile: 22 × 3 research angles → copy: 22 validated sequences
dispatch: 22 emails + 20 LinkedIn cadences
engage: 6 replies classified → 2 meetings BOOKED with pre-call briefs
```

## The Agent Roster

| Agent | Job |
|---|---|
| 🕵️ Hunter | Sources ICP-matched leads, dedupes against pool |
| 🛡️ Guardian | Waterfall email finding → verification → SMTP catch-all recovery; quarantines what it can't confirm |
| 🧠 Profiler | Enrichment + 3 research angles per lead |
| ✍️ Copywriter | Human template + AI hook; spam/length guardrails; flags for review |
| 📨 SDR | Inbox rotation, warmup gating, daily caps, sending, reply classification |
| 🤝 Networker | LinkedIn cadence: view → like → connect → message (20/day cap) |
| 🎯 Pipeline | Positive reply → booked meeting + pre-call sales brief + CRM sync |

All agents coordinate through the **Common Pool** (SQLite blackboard + append-only event log). No direct agent-to-agent calls — full audit trail of every action.

## CLI

```bash
outreachos init                                  # create DB
outreachos campaign --name acme --icp '{"industries":["SaaS"],"titles":["VP of Sales"]}' \
                   --offer "AI meetings or you don't pay"
outreachos hunt --campaign acme --limit 100      # stage: source
outreachos run --campaign acme --stage qualify   # guardian waterfall
outreachos run --campaign acme --stage enrich    # profiler angles
outreachos run --campaign acme --stage copy      # sequences
outreachos dispatch --campaign acme              # SDR + Networker
outreachos replies --campaign acme               # classify + book
outreachos stats --campaign acme                 # funnel dashboard
outreachos lead lead_xxxx                        # full event timeline
```

## Going Live

1. `cp .env.example .env` and add keys: `APOLLO_API_KEY`, `HUNTER_API_KEY`, `ZEROBOUNCE_API_KEY`, `SMARTLEAD_API_KEY` (+ optional `OPENAI_API_KEY` for real LLM hooks)
2. Set `PROVIDER_MODE=live` and/or `LLM_MODE=live`
3. Waterfalls activate automatically: mock providers step aside when credentialed ones exist

## REST API

```bash
pip install fastapi uvicorn
python -m outreachos.api        # http://localhost:8000/docs
# POST /campaigns/{name}/run · GET /campaigns/{name}/stats · GET /leads/{id}
```

Docker: `docker compose up`

## Tests

```bash
.venv/bin/python -m pytest tests/ -q     # 20 tests
```

## Docs

- [Market Research & Competitor Analysis](docs/RESEARCH.md) — 11x/Artisan/AiSDR/Regie pricing, churn post-mortems, patterns we stole
- [Architecture](docs/ARCHITECTURE.md) — blackboard design, state machines, provider layer, scaling path
- [Business Playbook](docs/BUSINESS_PLAYBOOK.md) — pricing, offer stack, client acquisition, delivery runbook, KPIs, 90-day plan

## Design Principles

1. **Pay-on-hit waterfalls** — never trust one data provider
2. **Verify before spend** — no LLM credits touch unverified emails
3. **Deterministic outer loops** — rule-based validation around every AI output
4. **Everything is an event** — replayable, auditable, client-reportable
5. **Mock-first development** — entire system testable with zero external dependencies
