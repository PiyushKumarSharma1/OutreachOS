# Business Playbook: $10K → $30K/Month

## Positioning

> "We run a team of AI agents that researches, verifies, and personally reaches 2,000+ of your ideal prospects every month. **10–20 qualified meetings or you don't pay.**"

Not a SaaS subscription (clients hate $36K/yr lock-in — that's why 11x churns 75% at month 3). Not an agency doing manual grunt work. A **performance-priced autonomous system** with owned infrastructure, so our marginal cost per lead is cents, not SaaS seats.

## Offer Stack (per client)

| Component | Price | Notes |
|---|---|---|
| Setup (one-time) | $3,000 | ICP build, domain purchase ×4, DNS (SPF/DKIM/DMARC), inbox creation ×8, 21-day warmup kickoff |
| Retainer | $2,000/mo | System ops, copy iteration, weekly report |
| Performance | $150/booked meeting | Target 12–18 meetings/mo/client |
| **Client all-in** | **~$5,000/mo** | vs $36K+/yr for 11x; vs $625/meeting for AiSDR |

### Revenue Math to Targets

- **$10K/mo**: 3 clients @ ~$3.3K avg (setup amortized + retainer + meetings)
- **$20K/mo**: 6 clients
- **$30K/mo**: 9 clients or 6 clients on higher-meeting performance plans

Cost side at 6 clients: domains+inboxes ~$300/mo, data/verification credits ~$400/mo, LLM ~$150/mo, sending infra ~$200/mo ≈ **$1,050/mo total COGS (~95% gross margin)**.

## Client Acquisition: Eat Your Own Cooking

The system's first campaign targets our own ICP. Run `demo` against real providers:

1. ICP: B2B SaaS founders ($5K+ ACV), agency owners, high-ticket coaches. Titles: Founder, CEO, VP Growth.
2. Trigger signals: recently funded, hiring "SDR" or "demand gen", posting about pipeline problems on LinkedIn.
3. Sequence hook: *"I built 7 AI agents that booked [X] meetings last month for [peer company]. Want me to point them at your ICP? Pay only per meeting."*
4. Volume: 500 sends/day capacity = 15,000/mo. At 2% positive → 300 positive replies → even 10% booking = 30 own meetings/mo. Close 1 in 5 → 6 clients.

### Sales Assets
- Demo: run this repo's `demo` command live on the call — show the waterfall rejecting bad emails, the AI hooks, the pre-call brief. The brief alone closes deals (it proves research depth).
- Case study after client 1: document meetings/mo, reply rate, cost per meeting. Every subsequent close uses it.

## Delivery Runbook (per new client)

**Week 0 — Setup**
1. Buy 4 satellite domains (.com, brand variants: get/go/try). Never their primary domain.
2. Google Workspace, 2 inboxes/domain (8 total). SPF/DKIM/DMARC on all.
3. Start warmup immediately (21-day gate is enforced by code).
4. ICP workshop: industries, titles, headcount band, ONE trigger signal. Narrow until <50K companies match.
5. Load offer + 2 case studies into campaign config.

**Weeks 1–3 — Warmup & Data**
- Hunter builds list (target 2,000 raw). Guardian runs waterfall → expect 85%+ usable.
- Write template copy by hand. Generate 20 AI hooks, review manually before enabling.

**Week 4 — Launch**
- Dispatch: 22/day ramping to 90/day (capacity scales with warmed inboxes).
- Monitor: bounce rate <2% (hard halt above), positive reply rate ≥1%.

**Ongoing**
- Weekly: review `needs_review` flagged leads, iterate opener templates from winning replies, refresh suppression list.
- Monthly report to client: sent, delivered %, replies, positive, meetings, cost-per-meeting trend.

## KPIs That Decide Renewals

| Metric | Red flag | Healthy | Action if red |
|---|---|---|---|
| Bounce rate | >2% | <1% | Halt sends, re-verify list, check domain health |
| Positive reply rate | <1% | 2–5% | Fix ICP or trigger signal before touching copy |
| Meetings/mo | <8 | 12–18 | Add inboxes/domains, tighten targeting |
| Cost/meeting | >$400 | <$250 | Renegotiate plan or prune client |

## Risk Management

- **Domain burn**: rotate satellite pools quarterly; never mix marketing + cold mail.
- **LinkedIn account risk**: only satellite profiles; 20 connections/day cap enforced; client accounts never touched.
- **Churn defense**: monthly strategy call showing cost-per-meeting trend; annual prepay discount (2 months free) offered but never required.
- **Compliance**: CAN-SPAM footer w/ address + opt-out auto-appended; suppression honored instantly; EU leads require opt-in flag in campaign config.
- **Key-person risk**: none — the runbook + event log mean any operator can service any client.

## 90-Day Plan

- **Days 1–14**: live-mode keys wired (Apollo, ZeroBounce, Smartlead), own campaign launched, 500/day.
- **Days 15–45**: first 10 own meetings booked; close 2 pilot clients at $1,500/mo founding-customer rate (discount for testimonial).
- **Days 46–75**: publish case study #1; raise to standard pricing; outbound scaled to 1,000/day; close to 4–5 clients.
- **Days 76–90**: hire VA for CRM hygiene; 6 clients; cross $15K MRR; begin white-label reseller conversations with agencies (they bring clients, we run delivery at 60/40 split).
