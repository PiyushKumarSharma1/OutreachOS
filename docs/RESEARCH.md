# OutreachOS Market Research (August 2026)

## 1. Category Snapshot: AI SDR Platforms

The AI SDR category matured fast and is now split into three pricing shapes.
22% of sales teams have fully replaced human SDRs with AI; 55% run hybrid workflows.

### Competitor Matrix

| Platform | Model | Entry Price | Contract | Key Strength | Key Weakness |
|---|---|---|---|---|---|
| **11x (Alice)** | Autonomous digital worker | ~$3,750–5,000/mo ($36K+/yr) | Annual | Multilingual scale, brand | Reported 75% 3-month churn; $50–60K year-one TCO |
| **Artisan (Ava)** | Single AI BDR, all-in-one | ~$280 self-serve → $1,500–2,000/mo | Annual | Data layer bundled, warmup built-in | Marketing ships faster than product; long impl |
| **AiSDR** | Volume-based agent | $900/mo + $0.75/msg | Quarterly only | Transparent pricing, reply handling native, unlimited seats | HubSpot-only; $0.75/message dominates above ~1,200 msgs/mo |
| **Regie.ai** | Per-seat AI SEP copilot | $180/user/mo (10-seat min = $21.6K floor) | Annual | Human-in-the-loop, bundles sending infra | Not autonomous; seat-minimum floor |
| **Landbase** | Agentic GTM-1 Omni model | Quote-only | — | 220M+ contact estate | Zero price transparency |
| **Unify** | Signal-based orchestration | ~$1,740/mo | Annual | Intent signal engine | Sources disagree on pricing |
| **Coldreach** | Signal-first research engine | $899/mo | — | Buying-signal monitoring | Narrow scope |
| **Apollo AI** | Assistive inside existing SEP | $49–119/user/mo | Monthly | Cheapest path | Zero-context data, generic outreach |
| **Instantly / Smartlead / Lemlist** | Sending engines only | $37–97/mo | Monthly | Deliverability infra, warmup pools | No intelligence — send but cannot think |

### What Kills These Products (churn analysis)

1. **Annual lock-in** — 11x and Artisan require 12-month commitments; buyers churn at renewal when meeting math fails. Cost-per-meeting decides renewals: a $30K contract at 4 meetings/mo = $625/meeting; at 1/mo = $2,500/meeting.
2. **"AI slop"** — fully AI-written emails are recognizable and get deleted. The winning pattern everywhere: *human-written template + ONE AI-generated research-backed sentence*.
3. **Deliverability decay** — platforms that don't own warmup infrastructure burn domains in weeks under Google/Yahoo/Microsoft bulk-sender rules (<2% bounce hard threshold, SPF/DKIM/DMARC mandatory).
4. **Data waste** — enriching before filtering. Credits spent on non-ICP companies are pure loss.

## 2. Proven Patterns We Integrated

### Waterfall Enrichment (stolen from Clay)
- Cascade providers cheapest-viable-first; pay only on hits.
- Coverage: 85–95% vs 60–75% single-provider. Implemented in `GuardianAgent._find_email`.
- Sanitation phase first: normalize company names (`Acme Corp, Inc.` → `acme corp`), strip URLs to root domains, map titles to seniority buckets. Implemented in `outreachos/utils.py`.

### Verification Waterfall + Catch-All Recovery
- Clay first-party testing: best verifiers hit 99%+ on normal domains (ZeroBounce 99.25%/99.37% quality/coverage), accuracy collapses on catch-alls.
- Third way for catch-alls (don't send blind, don't discard 30% of list): SMTP silent ping recovery recovers ~70% of catch-alls. Implemented via `CatchAllResolver` provider slot (Scrubby adapter included).
- Apollo's "verified" emails still bounce 5–8%; waterfall + verify-before-send keeps bounce <2%.

### Deliverability Math (from operators sending 20M+ emails/month)
- Emails/day ÷ 50 = inboxes needed; ÷100 = domains needed.
- Max 30/inbox/day (we default 30); warm every inbox ≥21 days (we gate on this in `SDRAgent.ready_inboxes`).
- Never send from primary company domain. Satellite domains only (`go`, `try`, `get` prefixes).
- Bounce >2% → providers demote you; >5% → platforms suspend.

### Personalization Discipline
- One AI sentence per email referencing researched signal; rest is static template.
- Prospects with ≥1 trigger signal (funding, hiring, tech-stack change, job change) reply 2–4x more.
- Review 20 AI outputs manually before scaling any new campaign template.

### Realistic Performance Benchmarks
| Metric | Broad volume play | Precision campaign |
|---|---|---|
| Positive reply rate | 0.8–2% | 8–15% |
| Meeting rate | 1 per 100–200 sends | 1 per 25–50 |
| Email coverage w/ waterfall | 85–95% | 95%+ |

## 3. The Gap Our Agency Exploits

**Every platform sells software. Nobody sells outcomes with owned infrastructure.**

- SaaS tools charge regardless of meetings booked (flat/volume/seat).
- Agencies using those tools inherit their costs AND their generic output.
- Enterprise AI SDRs cost clients $36K–100K/year — mid-market can't justify it.
- Our edge: **owned agent stack** (no per-seat license tax) → we can price on performance (per-meeting) while keeping 70%+ gross margin, because our marginal cost per lead is API credits (~$0.05–0.15/lead verified+enriched) not SaaS subscriptions.

## 4. Pricing Benchmarks for Our Offers

| Offer type | Market rate (2026) | Notes |
|---|---|---|
| Lead-gen agency retainer | $3,000–12,000/mo | Typical B2B retainers |
| Setup fee | $2,500–5,000 one-time | Domain buying + DNS + warmup + ICP build |
| Per qualified lead | $15–50 | Volume plays |
| Per booked meeting | $200–500 | Aligns incentives; our target model |
| AI SDR replacement value | $36K–60K/yr | Anchor for ROI framing |

## 5. Target Segments (ranked by willingness to pay)

1. **B2B SaaS ($5K+ ACV)** — outbound math works; personalization matters; they already believe in cold email.
2. **Marketing agencies** — resell our system as white-label; sticky retainers.
3. **High-ticket coaches/consultants ($3K+ offers)** — one client pays for months of service.
4. **Recruiting/staffing firms** — outreach IS their product; volume buyers.
5. **Local B2B services (roofing commercial, IT MSPs)** — high LTV, low sophistication.

## 6. Regulatory & Compliance Watchlist

- CAN-SPAM (US): physical address, working opt-out, honor within 10 days — suppression list enforced in code.
- GDPR (EU): legitimate-interest basis for B2B data; must log source + purpose per lead (our event log does this).
- LinkedIn ToS: automation violates user agreement — use conservative human-like cadence caps (20 connections/day implemented) and accept account risk on satellite profiles, never client profiles.
- Google/Yahoo bulk sender rules (enforced since 2024): one-click unsubscribe for 5K+/day senders, spam-complaint rate <0.3%.
