# OutreachOS

**Autonomous AI Outreach & Lead Generation Agency OS** — a multi-agent system where 7 primary agents + 2 sub-agents share a Common Pool to find leads, verify emails via waterfall enrichment, write personalized outreach, send across email + LinkedIn, classify replies, handle objections, and book meetings — with a learning loop that improves copy from every outcome.

Built on 2026 operator research: waterfall enrichment (85–95% coverage), catch-all SMTP recovery, strict deliverability gates (<2% bounce, 21-day warmup, 30 sends/inbox/day), one-AI-sentence personalization, and intent-signal prioritization.

## Quickstart (zero API keys needed)

```bash
cd OutreachOS
uv venv .venv && uv pip install pytest --python .venv/bin/python
PYTHONPATH=src .venv/bin/python -m outreachos.cli demo --limit 25
```

## The Full System (v0.4)

**Agents** — Hunter → Guardian → Profiler → Copywriter → SDR → Networker → Pipeline, plus:
- **ResearchSubAgent** — 4-query deep research per lead feeding the Profiler
- **ObjectionSubAgent** — classifies objections (price/timing/authority/competitor) and drafts responses → human-approval queue

**Backend Systems:**
| System | What it does |
|---|---|
| **Tenancy** | Clients + hashed API keys with scopes (read/write/admin) |
| **InfraManager** | Domain/inbox pools, DNS guards, warmup day tracking, rotation |
| **DeliverabilityMonitor** | Per-inbox 24h health from event log; auto-pause >5% bounce, quarantine >8% |
| **SignalsEngine** | Trigger-event detection (funding/hiring/tech/leadership) → intent score → dispatch priority |
| **ABEngine** | Deterministic 50/50 variants, two-proportion z-test, auto-promote winner |
| **SequenceEngine** | Conditional cadences (stop-on-reply, channel routing, breakup steps) |
| **ReplyIntelligence** | Reply routing: positive → book, objection → draft queue, unsubscribe → suppress |
| **LearningLoop** | Harvests win/loss by angle-style/industry/title → Copywriter biases future copy |
| **EventBus** | HMAC-signed webhooks (reply.received, meeting.booked…) with retry backoff |
| **ComplianceManager** | Suppression list, signed unsubscribe links, CAN-SPAM footers |

**MCP Server** — OutreachOS as an MCP server so Claude/any agent can operate it:

```json
{ "mcpServers": { "outreachos": { "command": "python", "args": ["-m", "outreachos.mcp_server"] } } }
```

8 intent-grouped tools: overview, campaign stats, lead search/timeline (read) + run cycle, create campaign, process replies (write-scope gated).

**Client Portal** — white-label reporting: clients log in with their API key at `/portal`, see only their campaigns, booked meetings with pre-call briefs, CSV exports.

**Approval Queue** — `/approvals`: objection drafts await your ✓/✕. Nothing sends without approval.

## CLI

```bash
outreachos init | demo --limit 30
outreachos campaign --name acme --icp '{"industries":["SaaS"],"titles":["VP of Sales"]}'
outreachos hunt|run|dispatch|replies|stats --campaign acme
outreachos client --name "Acme"          # creates client + API key
outreachos infra --seed                  # seed domain/inbox pool
outreachos ab --campaign acme --subject-a "..." --subject-b "..."
outreachos webhook --url https://hooks.dev/x --events meeting.booked
outreachos suppress --email foo@bar.com --reason bounce
```

## Going Live

1. `cp .env.example .env` — add Apollo/Hunter/ZeroBounce/Smartlead/LLM keys
2. `PROVIDER_MODE=live` and/or `LLM_MODE=live`
3. Waterfalls auto-activate when credentialed providers exist

## Docs

- [Market Research](docs/RESEARCH.md) — competitor teardown + patterns integrated
- [Architecture](docs/ARCHITECTURE.md) — blackboard design, state machines, all systems
- [Business Playbook](docs/BUSINESS_PLAYBOOK.md) — pricing, offer, 90-day plan

## Tests

```bash
.venv/bin/python -m pytest tests/ -q     # 47 tests
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
