# PRD — "LEDGER" *(working name)*
### The on-device agent that tells London's small businesses what they're owed

**NVIDIA Spark Hack — London | Track 1: Economic Systems**
**Team of 3 · 24-hour build · runs 100% local on DGX Spark (GB10 Grace Blackwell)**

---

## The one-liner

> **Every London high-street business is sitting on money it doesn't know it's owed. LEDGER finds it — privately, on-device, in six seconds.**

Alternative framings for different audiences:

- **For judges:** "The NYC winner told businesses what's *true* about them. We tell them what they're *owed*."
- **For a shop owner:** "Type your business name. We'll tell you the rates relief and grants you're probably missing — and draft the email to claim them."
- **For the impact slide:** "£24bn+ goes unclaimed in the UK every year. Most of it because nobody knows it exists. We close that gap one business at a time, without their data ever leaving the room."

---

## 1. What it is

LEDGER is a **private, on-device AI agent** that takes a single London business — by name or postcode — and tells it three things it could not easily find out for itself:

1. **What you're owed.** Business rates relief you qualify for but may not be claiming (Small Business Rate Relief, sector reliefs, the 2026-revaluation challenge wedge), plus government grants matched to your sector and location.
2. **What's about to hit your street.** Roadworks, closures, and disruption near your unit, drawn from London's live operational data — the kind of thing that quietly kills a week's footfall.
3. **What the city's data knows about your block.** Catchment reality — deprivation profile, crime trend, transport access, who actually lives nearby — joined from datasets a business owner would never combine themselves.

The whole thing runs **locally on the DGX Spark**. Business data is ingested and cached *before* runtime; at demo time the ethernet cable comes out and it still works. That isn't a gimmick — it's the product thesis. **The reason a business will trust an AI with its finances is precisely that the data never leaves the device.**

### What it is *not*
- Not a chatbot that retrieves facts and hopes they're right. The money math is a **deterministic rules engine**; the LLM only explains the result in plain English.
- Not a cloud SaaS calculator (Inbest, Policy in Practice, entitledto already own that space — all cloud, all citizen-facing or B2B-embedded).
- Not a clone of the NYC winner (AYA), which surfaced *known facts* about a business. LEDGER surfaces *unknown money and future risk*.

---

## 2. The need (why this exists)

### The headline problem
Billions in government support — relief, grants, reclaimable overpayments — go unclaimed in the UK every year. For benefits alone the figure is **£24.1bn** (Policy in Practice). For business rates the loss is structural and under-measured: **Small Business Rate Relief is one of the most valuable reliefs available, yet many entitled businesses either don't know it exists or never claim it.**

### Why now (the timing wedge that makes this a 2026 product, not an evergreen idea)
The **2026 business rates revaluation came into force on 1 April 2026.** The VOA reassessed **over two million properties**, with rateable values reset to reflect April-2024 market rents. This silently did three things to every London high-street business:

1. **Pushed some over a relief cliff.** Cross the £15,000 line and SBRR vanishes. A business that was getting relief may have lost it overnight — and has grounds to challenge a valuation that's even slightly too high.
2. **Reshuffled the multiplier system.** England moved to a new five-multiplier structure for 2026/27, plus a 1p supplement on all bills, plus London's own GLA 2p Crossrail supplement above £92,000. No owner can reason across that stack.
3. **Introduced new sector reliefs** (e.g. a 15% reduction for qualifying pubs and live-music venues for 2026/27) that are supposed to apply automatically — but automatic reliefs sometimes don't land on the bill, and nobody checks.

This is a **time-boxed window of confusion** affecting every SMB in London *right now*. That's what makes it a hackathon-winning wedge rather than a generic "AI helps business" pitch.

### Why a business can't solve this alone
- The rules are genuinely complex and borough-specific (every London borough runs its own council-tax-support and discretionary-relief variations).
- The information is fragmented across the VOA, gov.uk, the GLA, individual borough sites, and the Find a Grant service.
- There's stigma and friction: small owners don't have a finance team, don't know what to ask, and assume "if I were owed it, someone would've told me." Nobody tells them.

### Why existing tools don't close it
- **Rates advisers / agents** exist but take a cut and target larger commercial properties — the corner café isn't worth their time.
- **Cloud calculators** (where they exist for business rates) require the owner to already know what to look for and to type their data into someone else's server.
- **GOV.UK Chat** (launched ~May 2026, built with Anthropic) is a general signposting assistant — charities have already warned it serves the digitally-fluent and may not move the unclaimed-money needle. It points you at a calculator; it doesn't *find your money and draft the claim*.

**The unclaimed wedge nobody occupies: on-device, proactive, business-facing, money-finding.** Every player found is cloud, passive, or citizen-facing. None run local inference. That's exactly what the DGX Spark is built to demonstrate.

---

## 3. How it fits Track 1 (Economic Systems) — and quietly reaches into Track 3

Track 1's brief: *"help individuals and organisations make better economic decisions, unlock opportunity, and optimise costs."*

LEDGER is a near-perfect literal fit:

| Track 1 phrase | How LEDGER delivers it |
|---|---|
| "better economic decisions" | Tells an owner exactly which reliefs/grants to pursue and what each is worth |
| "unlock opportunity" | Surfaces grants and support the business didn't know existed, matched to its profile |
| "optimise costs" | Finds rates relief that directly reduces the single biggest fixed cost a high-street business carries |

**The structural edge over the NYC winner:** AYA answered Track 1 by *summarising the past* (your inspection grade, your past complaints). LEDGER answers Track 1 by *fusing it with Track 3 (Urban Operations)* — the live operational data of the city (roadworks, disruption, footfall signals) becomes economic intelligence for the business. In the pitch:

> "AYA answered Track 1 by looking backward. We answer Track 1 by plugging the business into the city's real-time nervous system. The same data that runs Urban Operations becomes the business's early-warning system."

That cross-track ambition is something the prior winner didn't reach, and it's the cleanest way to look *additive* rather than *derivative*.

---

## 4. The point of it (the thesis in three sentences)

1. **Local AI is the unlock for financial trust.** A business will let an AI reason over its finances only if the data physically never leaves the device — which is exactly what the Spark hardware makes possible and what cloud tools structurally can't offer.
2. **Determinism is the unlock for financial truth.** Money figures come from an encoded rules engine, never from the model, so the agent never hallucinates a number — the failure mode that would make any finance tool worthless.
3. **Proactivity is the unlock for actual impact.** The proven lever for unclaimed money is reaching out to people who don't know they qualify (a London Pension Credit data campaign drove a 150% claims increase). LEDGER is proactive by design: it tells you before you'd ever think to ask.

---

## 5. Use cases (concrete, demoable)

### Primary — "The reclaim" (your hero demo)
A Hackney café, rateable value £11,500. The owner pays a rates bill and assumes it's correct. LEDGER:
- Pulls the café's RV from the cached VOA 2026 list.
- Runs the deterministic relief engine: RV ≤ £12,000 → up to 100% SBRR → **~£4,968/yr, backdatable up to ~£29,808.**
- Flags that this is very likely unclaimed.
- Drafts the email to Hackney's business rates team, pre-filled with the property reference, ready to send.

**Demo line:** *"This café is owed roughly five grand a year and didn't know. The agent found it, drafted the claim — and watch, I'll unplug the cable, it still works. Their financial data never touched the cloud."*

### Secondary — "The challenge" (the 2026 wedge)
A Camden bookshop, RV £15,800 — just over the cliff. LEDGER flags that the April-2026 revaluation may have pushed it over the £15,000 line and that challenging a slightly-too-high valuation could pull it back under and restore full relief.

### Tertiary — "The street warning" (the Track-3 crossover card)
The same café: LEDGER queries TfL Road Disruption around its postcode → *"Roadworks start on Mare Street Monday, scheduled three weeks — plan a promotion, your walk-in footfall will drop."* One live API call, high perceived intelligence.

### Platform vision (the "where it scales" slide, not built in 24h)
- A borough or BID plugs in as an MCP connector and instantly reaches every business on the platform with targeted, proactive support.
- New support schemes (a charity grant, a council discretionary fund) become connectors, not code changes.
- Per-business persistent memory (via ReadmeDB MCP) means the agent keeps watching and re-checks when rules change.

---

## 6. The three insight engines (what makes it genuinely new)

This is the analytical core — each engine produces an insight a London SMB **cannot get anywhere else**, by joining datasets they'd never join themselves.

### Engine 1 — MONEY ("you're owed this and don't know it") — **BUILD FIRST, NON-NEGOTIABLE**
- **Source:** VOA 2026 rating list (bulk) → rateable value per property; gov.uk relief rules → encoded deterministically; Find a Grant → sector/location-matched grants.
- **Output:** exact relief entitlement, backdating estimate, challenge flags, grant matches, and a drafted claim.
- **Why it's defensible:** deterministic math, traceable to source, impossible for a cloud chatbot to match on privacy. This is the differentiator.

### Engine 2 — FORESIGHT ("here's what's about to hit your street") — **ONE CARD IF TIME**
- **Source:** TfL Road Disruption API (roadworks/closures by location), TfL JamCams (900+ camera stills + 5-sec clips → local VLM for visual triage), LAQN/Breathe London air quality, planning applications.
- **Output:** location-specific operational warnings the owner can act on.
- **Why AYA couldn't do it:** it had no live operational layer. London hands you one free.

### Engine 3 — CROSS-DOMAIN ("what the city's data knows about your block") — **SLIDE, NOT BUILD**
- **Source:** IMD 2025 (deprivation, 7 domains per LSOA), data.police.uk (crime by polygon), LSOA Atlas / Census (catchment demographics, car access, languages), HSDS open layer (high-street boundaries, town-centre class).
- **Output:** catchment-reality insight — e.g. *"40% of your catchment has no car; a delivery option captures spend you're currently losing."*
- **Why it needs the knowledge graph:** the value is in the *joins*, not any single dataset. This is AYA's best idea (a graph built across datasets) pointed at richer London inputs.

---

## 7. Other relevant insights pullable from London's datasets

Beyond the three engines, things the data supports that you can mention as roadmap or weave into cards:

**From the money/rates layer**
- **Empty-property relief** opportunities and transitional relief phasing (bills capped from rising too fast post-revaluation — owners often don't realise they're protected).
- **Discretionary relief** that each borough runs differently — an agent that knows your borough can flag schemes a national tool would miss.
- **Supporting Small Business (SSB) 2026 cap** — protects businesses losing SBRR *because of* the revaluation, capping their increase. Directly relevant to anyone the reval pushed over the cliff.

**From the deprivation / demographic layer (IMD 2025, LSOA Atlas, Census)**
- **Catchment income reality** — is your local customer base getting richer or poorer? Changes pricing and product strategy.
- **No-car households** — high no-car share signals delivery/local-trade opportunity.
- **Language profile** — a high non-English-first-language catchment suggests signage/marketing in other languages captures missed spend.
- **Age profile** — older catchment → different opening hours, product mix, accessibility.

**From the live operational layer (TfL, LAQN)**
- **Footfall proxy via Google Mobility by borough** (open, auto-updating ~every few days) — recovery/decline trend for your area, the legal stand-in for the subscriber-locked HSDS footfall data.
- **Transport accessibility (PTAL / step-free data)** — who can physically reach you; relevant for accessibility grants and customer reach.
- **Air-quality-linked operations** — for nurseries, gyms, outdoor hospitality, pollution forecasts drive operational decisions (move tables indoors, message members).
- **Disruption-as-opportunity** — a competitor's unit under scaffolding or a nearby closure can be *your* promotional window, not just a threat.

**From the business-register layer (Companies House)**
- **Competitor formation signals** — new companies incorporating at nearby addresses in your SIC code = competition arriving before they open.
- **Sector density** — how saturated your immediate area is in your trade.

> **Honesty flag for the team:** the richest footfall/spend data (HSDS, built on BT mobility + Mastercard card spend) is **subscriber-locked to borough and BID officers** — you cannot ship it in the demo. Use the open proxies (Google Mobility, high-street boundaries, town-centre classification) and say so plainly. If a judge asks about deep footfall, the honest answer is the B2B-for-BIDs path, where that access already exists.

---

## 8. Architecture (how it's built)

```
Business name / postcode
        │
        ▼
[ postcodes.io ] ──► LSOA + lat/lng (join glue; optional, degrades offline)
        │
        ▼
[ LOCAL JOIN LAYER ]  ← cached before runtime, no cloud at demo time
   VOA 2026 list · Companies House · IMD 2025 · police · grants
        │
        ▼
┌───────────────────────────────────────────────┐
│  ENGINES (deterministic — no LLM touches math) │
│   • rules_relief.py   (SBRR, sector, reval)    │
│   • rules_grants.py   (Find a Grant matching)  │
│   • foresight.py      (TfL disruption + VLM)   │
│   • crossdomain.py    (IMD + police + census)  │
└───────────────────────────────────────────────┘
        │  structured findings (JSON)
        ▼
[ LOCAL LLM — Nemotron Nano V2 VL 12B, vLLM, NVFP4 ]
   • explains findings in plain English
   • drafts the claim email
   • routes via MCP tools
        │
        ▼
[ MCP CONNECTORS ]  read: TfL, VOA, Find-a-Grant, police
                    act:  draft email, pre-fill grant, ReadmeDB memory
        │
        ▼
[ FRONTEND ]  type name → 6s brief → 3 insight cards → drafted action
```

**The discipline that keeps it honest:** facts and figures come from the data layer and the deterministic engines. The LLM only does language and tool-routing. Every number on a card traces to a source. This is also the accuracy pitch to judges.

**The offline proof:** all cloud calls are *ingestion*, done and cached before the demo. At demo time, unplug → the agent reasons over cached local data with the local model. Thesis intact.

---

## 9. Why this beats the field (positioning)

| | Cloud calculators (Inbest etc.) | GOV.UK Chat | NYC winner (AYA) | **LEDGER** |
|---|---|---|---|---|
| Privacy / on-device | ❌ cloud | ❌ cloud | ✅ local | ✅ **local** |
| Finds money proactively | partial | ❌ signposts | ❌ summarises facts | ✅ **yes** |
| Deterministic (no hallucinated £) | ✅ | ❌ | partial | ✅ **yes** |
| Business-facing | ❌ mostly citizen | both | ✅ | ✅ |
| Drafts the actual claim | ❌ | ❌ | ❌ | ✅ **yes** |
| Live operational foresight | ❌ | ❌ | ❌ | ✅ **yes** |
| Extensible via open connectors | ❌ | ❌ | ❌ hardcoded skills | ✅ **MCP** |

**The sentence that disarms the "derivative" worry:** *"The NYC winner built a brilliant dashboard of what's true about a business. We asked a different question — not what's true about you, but what you're owed and don't know. That question only has a good answer in the UK right now, because the 2026 revaluation just broke everyone's eligibility."*

---

## 10. Scope for 24 hours (what ships vs what's a slide)

**Ships (the demo):**
- Money engine, fully working, tested against ≥3 *real* London businesses with *real* rateable values.
- One end-to-end path: type name → VOA lookup → relief finding → plain-English explanation → drafted reclaim email.
- One Foresight card (TfL Road Disruption by postcode — one live call).
- Local model on Spark, offline proof (cable unplug).
- Clean 3-column frontend; the money number is the visual hero.

**Slides only (where it scales):**
- Cross-domain engine + knowledge graph.
- MCP platform (boroughs/BIDs/charities as connectors).
- Persistent per-business memory + cron monitoring.
- B2B-for-BIDs path with full HSDS footfall access.

**The de-risk rule:** by hour 6, one real business must show one real reclaim on screen. If it isn't there, cut everything else and brute-force that single path. The judge remembers the café that was owed £4,968 and the cable coming out — not unshipped ambition.

---

## 11. Impact numbers (verified, citable)

- **£24.1bn** income-related support unclaimed per year in GB (Policy in Practice) — the macro backdrop.
- **2M+** business properties reassessed in the 2026 revaluation (VOA) — the size of the just-created confusion.
- **SBRR** can reach **100%** relief at RV ≤ £12,000, tapering to £15,000 — and is **backdatable up to ~6 years.**
- **150% increase** in claims from a London data-driven proactive outreach campaign (Pension Credit) — proof proactivity works.
- **£36M+ for 180,000 applicants/yr** (Salad Money) and **£17M for 11,000 people** (Vanquis pilot) — proof the find-and-claim model scales.

---

## 12. Risks (clear-eyed)

- **VOA field parsing.** The bulk list is asterisk-delimited; field indices must be verified against the spec for the actual downloaded file. Highest single technical risk — do it first.
- **Rules-engine accuracy is the whole reputation.** One wrong £ figure kills trust. Encode from gov.uk + borough pages; test against a real bill.
- **Live VLM across 900 cameras in a weekend is unrealistic.** Pre-pull a few JamCam clips; frame the network-scale version as roadmap.
- **HSDS footfall is subscriber-locked.** Don't claim it. Use open proxies and be honest.
- **Cloud memory breaks the offline moment.** If ReadmeDB is hosted, run a local mirror or have the agent degrade gracefully and say so during the unplug.

---

*Built for the NVIDIA Spark Hack, London. Runs on your hardware. The money never leaves the room.*
