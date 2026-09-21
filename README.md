# OutreachOS

**Autonomous AI Outreach & Lead Generation Agency OS** — a multi-agent system where 7 primary agents + 2 sub-agents share a Common Pool to find leads, verify emails via waterfall enrichment, write personalized outreach, send across email + LinkedIn, classify replies, handle objections, and book meetings — with a learning loop that improves copy from every outcome.

Built on 2026 operator research: waterfall enrichment (85–95% coverage), catch-all SMTP recovery, strict deliverability gates (<2% bounce, 21-day warmup, 30 sends/inbox/day), one-AI-sentence personalization, and intent-signal prioritization.

## Quickstart (zero API keys needed)

```bash
cd OutreachOS
uv venv .venv && uv pip install pytest --python .venv/bin/python
PYTHONPATH=src .venv/bin/python -m outreachos.demo --limit 25
```

## The Full System (v0.5)

**Agents (common pool, 14)** — Hunter → Guardian → Profiler → Copywriter → SDR → Networker → Pipeline, plus:
- **SignalScout** — re-scores pool leads with the SignalsEngine, persists fresh trigger signals, revives leads dropped for timing (signal-triggered outreach = 3–5x reply rates per 2026 research)
- **MeetingBooker** — proposes 3 concrete local-time slots + booking email for positive replies; auto-requeues out-of-office replies
- **ICPRefiner** — harvests outcomes per campaign, records keep/drop bucket recommendations on the event ledger
- **DeliverabilityOps** — audits per-inbox 24h health; pauses >5% bounce, quarantines >8%
- **ClientReporter** — weekly retainer-grade client report (replies, meetings, deliverability, learnings)
- Run any of them: `Engine.run_agent(agent_name, campaign_name=None)`; also: ResearchSubAgent (4-query deep research) and ObjectionSubAgent (objection classification) as before, plus:
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

25 intent-grouped tools: overview, campaign stats, lead search/timeline (read) + run cycle, create campaign, process replies, create client, webhooks, experiments, approvals, suppressions, health check, learning insights, experiments, signals, infrastructure, seed (write-scope gated).

**Client Portal** — white-label reporting: clients log in with their API key at `/portal`, see only their campaigns, booked meetings with pre-call briefs, CSV exports.

**Approval Queue** — `/approvals`: objection drafts await your ✓/✕. Nothing sends without approval.

## CLI

```bash
# Core pipeline
outreachos init
outreachos demo --limit 30
outreachos campaign --name acme --icp '{"industries":["SaaS"],"titles":["VP of Sales"]}'
outreachos hunt|run|dispatch|replies|stats --campaign acme

# Client management
outreachos client --name "Acme"          # creates client + API key
outreachos key --client-id <id>          # additional API keys

# Infrastructure
outreachos infra --seed                  # seed domain/inbox pool
outreachos health                        # full infra + deliverability check

# Webhooks
outreachos webhook --url https://hooks.dev/x --events meeting.booked,reply.received
outreachos webhook-process --limit 20    # process pending deliveries

# A/B Experiments
outreachos ab --campaign acme --subject-a "..." --subject-b "..."

# Compliance
outreachos suppress --email foo@bar.com --reason bounce

# Learning
outreachos learning --campaign acme --harvest
outreachos learning --campaign acme --best --kind angle_style --top-n 3
outreachos learning --campaign acme --summary

# Approvals
outreachos approvals --list
outreachos approvals --approve lead_123 lead_456
outreachos approvals --discard lead_789

# Scheduler (unattended daily cycles)
outreachos scheduler --run-once --campaign acme --auto-hunt
outreachos scheduler --forever --auto-hunt --interval 24 --jitter 30

# Client Portal (FastAPI)
outreachos portal --host 0.0.0.0 --port 8080
```

## Going Live

1. `cp .env.example .env` — add Apollo/Hunter/ZeroBounce/Smartlead/LLM keys
2. `PROVIDER_MODE=live` and/or `LLM_MODE=live`
3. Waterfalls auto-activate when credentialed providers exist

## Docs

- [Market Research](docs/RESEARCH.md) — competitor teardown + patterns integrated
- [Competitive Research](docs/COMPETITIVE_RESEARCH.md) — comprehensive 2026 market analysis
- [Architecture](docs/ARCHITECTURE.md) — blackboard design, state machines, all systems
- [Business Playbook](docs/BUSINESS_PLAYBOOK.md) — pricing, offer, 90-day plan

## Tests

```bash
.venv/bin/python -m pytest tests/ -q     # 47 tests
```

## Architecture

```
                     ┌─────────────────────────────────────┐
                     │           COMMON POOL (SQLite)      │
                     │  leads · campaigns · event log      │
                     └──────────┬──────────────────────────┘
                                │ read/write
   ┌───────────┬───────────┬───┴───────┬────────────┬───────────┬───────────┐
   ▼           ▼           ▼           ▼            ▼           ▼           ▼
HUNTER ──▶ GUARDIAN ─▶ PROFILER ─▶ COPYWRITER ─▶ SDR ─┐    NETWORKER  PIPELINE
(source)   (waterfall   (angles +   (template+AI   │      (LinkedIn    (book +
           find+verify) research)   hook)          │       cadence)     brief)
                                                   ▼
                                           reply classifier
                                           positive ──▶ PIPELINE
```

### Pipeline Stages & State Machine

Lead `stage` progression:
`raw → hunted → verified → profiled → written → dispatched → engaged → booked`
Any stage can transition to `dropped` (with reason in event log).

Lead `email_status`: `none → found → verified | risky_catchall_confirmed | risky_catchall(quarantine) | invalid | suppressed`

Lead `outreach_state`: `new → queued_linkedin / sent → replied_positive | replied_negative | ooo_autoreply | bounced → booked | stopped`

### Inter-stage Filters (cost discipline)

| Transition | Filter rule |
|---|---|
| Guardian → Profiler | only `verified` or `risky_catchall_confirmed` (never spend LLM credits on unverified emails) |
| Copywriter → SDR | skip leads flagged `needs_review`; skip non-verified statuses |
| Profiler → Copywriter | require ≥1 generated angle |

## Provider Integrations

| Kind | Providers (waterfall order) |
|---|---|
| **Lead Source** | Apollo (live) → Mock |
| **Email Finder** | Hunter → Dropcontact → Mock A → Mock B |
| **Verifier** | ZeroBounce → NeverBounce → Mock Fast → Mock Deep |
| **Catch-All** | Scrubby → Mock |
| **Enrichment** | Clearbit → People Data Labs → Mock |
| **Signals** | HubSpot → Mock |
| **Sending** | Smartlead → Instantly → Mock |

## Deploy with Docker

```bash
# Development
docker-compose up -d

# Production (add .env with live keys)
docker-compose -f docker-compose.yml up -d --build

# Run scheduler separately
docker-compose run --rm scheduler
```

## MCP Integration (Claude Code)

Add to your Claude Code / opencode config:

```json
{
  "mcpServers": {
    "outreachos": {
      "command": "python",
      "args": ["-m", "outreachos.mcp_server"],
      "env": {
        "OUTREACHOS_DB": "./outreachos.db",
        "OUTREACHOS_MCP_KEY": "your-write-scope-api-key"
      }
    }
  }
}
```

Then in Claude: "Run a full cycle for campaign acme" → calls `outreachos_run_cycle`.

## Design Principles

1. **Pay-on-hit waterfalls** — never trust one data provider
2. **Verify before spend** — no LLM credits touch unverified emails
3. **Deterministic outer loops** — rule-based validation around every AI output
4. **Everything is an event** — replayable, auditable, client-reportable
5. **Mock-first development** — entire system testable with zero external dependencies

## Business Model (from playbook)

| Component | Price | Notes |
|---|---|---|
| Setup (one-time) | $3,000 | ICP build, domain purchase ×4, DNS, inbox creation ×8, 21-day warmup |
| Retainer | $2,000/mo | System ops, copy iteration, weekly report |
| Performance | $150/booked meeting | Target 12–18 meetings/mo/client |
| **Client all-in** | **~$5,000/mo** | vs $36K+/yr for 11x; vs $625/meeting for AiSDR |

Cost side at 6 clients: domains+inboxes ~$300/mo, data/verification credits ~$400/mo, LLM ~$150/mo, sending infra ~$200/mo ≈ **$1,050/mo total COGS (~95% gross margin)**.