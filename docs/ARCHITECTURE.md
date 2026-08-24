# OutreachOS Architecture

## Design Philosophy

**Blackboard architecture (the "Common Pool")**: every agent is an independent specialist that reads from and writes to a single shared store. No agent talks directly to another. Coordination happens through lead state (`stage`, `email_status`, `outreach_state`) and the append-only event log.

This mirrors LangGraph shared-state semantics without the dependency: deterministic, inspectable, and replayable. Every action on every lead is logged with `(agent, action, detail, timestamp)` — full audit trail for clients and debugging.

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

## Pipeline Stages & State Machine

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

## The Agents

| Agent | File | Responsibility | External deps |
|---|---|---|---|
| Hunter | `agents/hunter.py` | ICP-filtered sourcing, dedupe against pool | LeadSource provider (Apollo adapter) |
| Guardian | `agents/guardian.py` | Waterfall email finding, verification waterfall, catch-all SMTP recovery, suppression enforcement, bounce guard | EmailFinder ×N, Verifier ×N, CatchAllResolver |
| Profiler | `agents/profiler.py` | Enrichment + 3 research angles per lead | Enrichment provider + LLM |
| Copywriter | `agents/copywriter.py` | 3-step sequences: static template + AI hook; spam/length guardrails | LLM |
| SDR | `agents/sdr.py` | Inbox rotation, warmup gating, daily caps, send, reply classification, suppression on negative | Sender provider (Smartlead/Instantly adapters) + LLM classifier |
| Networker | `agents/networker.py` | LinkedIn cadence (view→like→connect→message), 20/day cap | Executor (Playwright bot slot) |
| Pipeline | `agents/pipeline_agent.py` | Positive reply → meeting booking + pre-call brief + CRM sync event | LLM |

## Provider Layer

Every external dependency is behind a `Provider` interface with two implementations:

- **Mock providers** (`providers/mock.py`) — deterministic synthetic data seeded by SHA-256 of inputs. Zero API keys needed; the entire system runs and is fully testable offline.
- **Live providers** (`providers/live.py`) — real HTTP adapters (stdlib urllib, no third-party SDKs): Apollo (sourcing), Hunter (finding), ZeroBounce/NeverBounce (verification), Scrubby (catch-all), Smartlead (sending).

Selection: `PROVIDER_MODE=mock` (default) uses mocks; `PROVIDER_MODE=live` requires matching API keys in env or raises `ProviderError`. Waterfalls are ordered lists — first confident verdict wins, later providers never called (pay-on-hit semantics).

## LLM Layer

`LLMClient.complete_json(instruction, context)` contract:

- **MockLLM** — synthesizes deterministic realistic output from structured context (angles, sequences, reply classification, briefs). Keyword-based classifier implements the same decision boundaries a fine-tuned model would.
- **OpenAICompatLLM** — chat completions with JSON response format; falls back to MockLLM on any error (graceful degradation).

Swap-in point for Claude/Gemini/local models: implement `complete_json`.

## Safety & Compliance Built-In

- Suppression list honored before any processing (`email_status=suppressed` → dropped).
- Unresolved catch-alls quarantined, never sent.
- Warmup gate: inboxes <21 days warm are excluded from rotation.
- Daily cap: 30/inbox default; capacity = warmed_inboxes × cap.
- Spam-score guardrail on all copy (score >0.3 flags `needs_review`, blocks dispatch).
- Negative reply → auto-suppress note.
- Event log = GDPR source/purpose record per lead.

## Scaling Path

1. **Single box** (now): SQLite, sync pipeline. Handles ~10 campaigns × 500 leads/mo.
2. **Queue mode**: swap PoolStore for Postgres; wrap each agent run in a worker (Celery/RQ); engine stages become idempotent tasks keyed by lead state.
3. **Multi-tenant**: add `client_id` to Campaign; per-client inbox pools; per-client sender credentials.
4. **Live LinkedIn**: implement Networker `executor` via Playwright with residential proxies + satellite accounts.

## Testing

20 tests cover: pool CRUD/filters/events/stats, utils normalization, waterfall finding, invalid-drop path, catch-all recovery + quarantine paths, profiler angles, copywriter validation, pipeline booking, full-cycle E2E, stage filters, warmup gate, reply classification boundaries, spam guard.
