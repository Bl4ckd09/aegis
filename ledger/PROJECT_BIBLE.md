# PROJECT BIBLE — "LEDGER"
## The on-device agent that tells London's small businesses what they're owed
### NVIDIA Spark Hack London · Track 1 (Economic Systems) · 24h · 3 people · 100% local on DGX Spark

> This is the single source of truth. Everything verified is cited. Everything assumed is flagged **[ASSUMPTION]**. Everything that can sink the demo is flagged **[RISK]**. Read §13 (limitations) before you start building, not after.

---

## CONTENTS
1. The thesis in one screen
2. AYA teardown — what won NYC, and exactly where we diverge
3. Why we're NOT derivative (the argument that wins the room)
4. The rules to encode — every 2026 number, verified, with sources
5. Every dataset — endpoints, auth, how to call, what it gives
6. The three insight engines (full spec)
7. System architecture
8. DGX Spark setup — modules, models, commands
9. The repo — full module map + what each file does
10. MCP connector layer (our edge)
11. Hour-by-hour 24h plan, split across 3 people
12. The demo script (90 seconds, word for word)
13. **Limitations & risks — read this first**
14. Resource index — every link in one place

---

## 1. THE THESIS IN ONE SCREEN

**One-liner:** *Every London high-street business is sitting on money it doesn't know it's owed. LEDGER finds it — privately, on-device, in six seconds.*

Three questions a business owner cannot answer alone, that LEDGER answers:
1. **What am I owed?** (rates relief + grants — deterministic, no hallucinated £)
2. **What's about to hit my street?** (live TfL disruption near their unit)
3. **What does the city's data know about my block?** (deprivation, crime, catchment)

Three reasons it works:
- **Local = trust.** A business lets AI touch its finances only if data never leaves the device. The Spark makes this real; cloud tools can't.
- **Deterministic = truth.** Money math is an encoded rules engine. The LLM only does language. Never hallucinates a number.
- **Proactive = impact.** The proven lever is telling people before they think to ask (a London Pension Credit data campaign drove a **150% claims increase**).

**The demo moment:** café is owed ~£4,393/yr → agent drafts the claim → **unplug the ethernet → it still works.**

---

## 2. AYA TEARDOWN — what won NYC, and where we diverge

**AYA = "AI for Small Businesses", NYC Spark Hack winner.** Repo: github.com/Ali-Maq/aya-ai-for-small-businesses

### What AYA actually does (the three moves that won)
1. **Pre-join, don't query at runtime.** It indexes ~385 NYC Open Data CSVs locally on 7 keys (zip, BBL, BIN, community district, census tract, address, borough). When you name a business, every fact (health grade, 311 complaints, licences) is *already joined* before the LLM speaks. **This is the anti-hallucination spine — the LLM reasons over a pre-built brief, it doesn't retrieve.**
2. **Knowledge graph as connective tissue.** ~2,668 nodes / 5,344 edges built across those datasets, so it can reason about relationships a single lookup can't see.
3. **Persistent per-business agent.** Each business gets its own workspace with auto-injected identity + standing cron jobs (monitor competitors, watch new 311s). Not a chatbot — a persistent agent. Demo: type "Joe's Pizza" → 6s → grounded brief → 3 GPUs running analyst "hats" in parallel → unplug ethernet → still works.

### AYA's structural ceiling (this is our opening)
AYA answers **"what is already true about this business?"** — your grade, your complaints, your competitors. Useful, but it tells owners things they could in principle look up. **It produces no money and no foresight.** It has no live operational layer and no financial-entitlement engine, because NYC's data and timing didn't hand it one.

### Where we diverge (keep these crisp — they ARE the pitch)
| Dimension | AYA | LEDGER |
|---|---|---|
| Core question | "What's true about me?" | "What am I **owed** and don't know?" |
| Output | Descriptive brief | **Money found + claim drafted** |
| Time orientation | Backward (past records) | Backward **+ forward** (live disruption) |
| Financial engine | None | **Deterministic relief/grant engine** |
| Trigger to act | User asks | **Proactive** (tells you first) |
| Extensibility | 19 hardcoded skills | **Open MCP connectors** |
| What we keep | pre-join locally, 6s brief, KG, offline proof | (all four — they're sound) |

**We steal the skeleton (pre-join + brief + graph + offline). We add three organs AYA can't grow: a money engine, a live-foresight layer, and an MCP connector spine.**

---

## 3. WHY WE'RE NOT DERIVATIVE (the argument that wins the room)

Your friends' worry is legitimate *only if* the hero moment is the brief. It isn't. Three defenses, in order of strength:

1. **Different question, provably.** AYA shows known facts; we show unclaimed money + future risk. A judge who saw AYA watches a café get £4,393 back and registers it as new. That's the test, and we pass it.
2. **A wedge that only exists here, now.** The **2026 business rates revaluation (effective 1 April 2026)** reset **2M+ properties** and is silently breaking SBRR eligibility this quarter. AYA's NYC team had no equivalent. This is a UK-2026-specific opening, not a reskin.
3. **Name AYA out loud, first.** Open with: *"The NYC winner built a brilliant dashboard of what's true about a business. We asked a different question — what you're owed and don't know."* Naming your lineage disarms the objection and signals you studied the field.

**Strongest single anti-derivative move:** walk in with **3 real London businesses** you actually looked up — real rateable values, a real reclaim found. AYA demoed on example businesses. Real shops with real money is a different category of credibility.

---

## 4. THE RULES TO ENCODE — every 2026 number, verified

> All figures England 2026/27, verified June 2026. **City of London differs — flag, never assert.**

### 4.1 The five multipliers (pence per £1 of RV)
Source: **gov.uk notification 2/2026** (official):
| Multiplier | Rate | Applies to |
|---|---|---|
| Small business non-RHL | **43.2p** | RV < £51,000 |
| Small business RHL | **38.2p** | RV < £51,000, retail/hospitality/leisure use |
| Standard non-RHL | **48.0p** | RV £51,000–£499,999 |
| Standard RHL | **43.0p** | RV £51,000–£499,999, RHL use |
| High-value | **50.8p** | RV ≥ £500,000 |

The five-multiplier system replaced the old temporary 40% RHL relief (which ended 31 March 2026) with permanently lower RHL multipliers. RHL = a *use* test on the occupier.

### 4.2 Small Business Rate Relief (SBRR) — the hero rule
A **separate discount applied on top** of the (already lower) small-business multiplier:
- RV **≤ £12,000** → **100%** relief (pay nothing)
- RV **£12,001–£14,999** → **tapered**: official rule is **1% off per £30 over £12,000**. Worked examples (gov.uk): £13,500 → 50%, £14,000 → 33%.
- RV **≥ £15,000** → no SBRR
- **Eligibility:** business occupies **only one property** (with the grace exception below)
- **Grace period:** keep SBRR on the first property for **3 years** after taking a second, for second properties acquired **on/after 27 Nov 2025** (extended from 1 year).
- **Backdating:** relief can often be backdated — owner must contact council.
- **The unclaimed truth (citable):** *"SBRR is one of the most valuable reliefs available, yet many entitled businesses either don't know it exists or haven't claimed it."*

### 4.3 The 2026 revaluation challenge wedge (the timing differentiator)
- Effective **1 April 2026**; draft list published **26 Nov 2025**; **2M+ properties** reassessed; values based on **April 2024** rents.
- If the reval pushed you just **over** £12,000 or £15,000, you may have **grounds to challenge** the valuation and reclaim eligibility (via the Find a Business Rates Valuation / business rates valuation account).

### 4.4 Pub & live music relief 2026/27
- **15%** off, **on top of** other reliefs.
- **Qualify:** pubs, live music venues open to the public.
- **EXCLUDED (do not offer this relief to these):** restaurants, cafés, nightclubs, snack bars, hotels, guesthouses, boarding houses, sporting venues, festival sites, theatres, cinemas, museums, exhibition halls, casinos. *(Engine enforces this — a café must NOT be told it qualifies.)*

### 4.5 Supporting Small Business (SSB) 2026
- Caps the bill increase for those **losing** SBRR/RHL due to the revaluation, at the **higher of £800 or the transitional cap**.
- Automatic; no SBRR applied on top of the £800-capped bill (no double counting).

### 4.6 Transitional relief 2026/27 (upward caps, applied BEFORE other reliefs)
- Small (RV ≤ £20,000): **5%** | Medium (£20,001–£100,000): **15%** | Large (>£100,000): **30%**.

### 4.7 EV charge points
- 10-year 100% relief for separately-assessed EV charge points / EV-only forecourts. (Niche; mention as roadmap.)

### 4.8 [RISK] Things NOT to assert
- The "GLA 2p Crossrail/BRS supplement above £92,000" — this is a Business Rate Supplement feature; **verify per billing authority before stating a £ figure.** The engine flags it, doesn't compute it.
- City of London special arrangements — flag, never compute nationally.

---

## 5. EVERY DATASET — endpoints, auth, how to call

> **CORE** = needed for the working demo. **NICE** = second card if time. **SLIDE** = roadmap only.

### 5.1 VOA 2026 Rating List (bulk) — **CORE — the money spine**
- **What:** every non-domestic property in England/Wales — rateable value, address, property reference, description.
- **Download:** `https://voaratinglists.blob.core.windows.net/html/rlidata.htm` → "2026 non domestic rating list entries" + "summary valuations".
- **Spec:** the data-specification PDF on that page. **Format: ASCII, fields delimited by `*`, records CR/LF separated, `.csv` extension, no field contains `*`.** Cloud setup also exposes APIs over the downloads.
- **How to use:** download 2026 list entries → filter to your target London billing-authority codes → index by postcode + address + property reference. This is the AYA pre-join, pointed at money.
- **[RISK] highest single technical risk:** field column order must be verified against the spec PDF for the actual file. Do this **first** (hour 0–2). Our parser (`ingest_voa.py`) assumes documented positions and is tolerant, but verify.
- **Single-property live check:** GOV.UK **Find a Business Rates Valuation** `https://www.gov.uk/correct-your-business-rates` — to confirm your 3 real businesses on stage.

### 5.2 Companies House API — **CORE — name → entity**
- **What:** SIC codes, registered address, incorporation date, officers, accounts.
- **Auth:** free API key (register an account, instant). REST + JSON.
- **Docs:** `https://developer.company-information.service.gov.uk/`
- **Use:** turn a typed business *name* into a structured entity + SIC to join against VOA and match grants.

### 5.3 GOV.UK Find a Grant — **CORE — the opportunity layer**
- **What:** single government grants service. Filter live grants by sector/location.
- **URL:** `https://www.find-government-grants.service.gov.uk/`
- **Use:** match grants to SIC + postcode; pre-fill application (act connector). Wrap as MCP read connector. **[ASSUMPTION]** public API surface may be limited — for demo, scrape/cache the live grants list rather than relying on a documented API.

### 5.4 TfL Unified API — **CORE for foresight card**
- **Auth:** register at `https://api-portal.tfl.gov.uk/` for `app_id` + `app_key`; append as query params. Open data terms.
- **Base:** `https://api.tfl.gov.uk/` · Swagger: `https://api.tfl.gov.uk/swagger/ui/index.html`
- **Endpoints we use:**
  - **Road Disruption:** `https://api.tfl.gov.uk/Road/All/Disruption` — roadworks/closures with location + dates. *(Easiest high-value foresight card — one call, filter by bounding box around the business postcode.)*
  - **JamCams:** `https://api.tfl.gov.uk/Place/Type/JamCam/` — ~900 cameras, each with lat/lng, a **still image** URL and a **5-second looped video** URL, refreshed every few minutes. Feed to local VLM for "visual triage." **Never call it live CCTV.**
- **[RISK]** Live VLM over 900 cams in 24h is unrealistic. Pre-pull 3–4 clips near your demo businesses; frame network-scale as roadmap.

### 5.5 postcodes.io — **CORE — the join glue**
- **What:** postcode → LSOA code, lat/lng, admin district (borough). Free, **no key**, has a bulk endpoint.
- **URL:** `https://api.postcodes.io/postcodes/{postcode}`
- **Use:** stitches VOA addresses to IMD/police/TfL. Build this layer first. Degrades gracefully offline (money engine doesn't need it).

### 5.6 IMD 2025 — **CORE for cross-domain card**
- **What:** English Indices of Deprivation 2025 — 7 domains per LSOA (income, employment, health, education, crime, housing barriers, living environment). Newest (released Nov 2025).
- **Where:** `https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025` + London Datastore `https://data.london.gov.uk/`
- **Use:** business postcode → LSOA → deprivation profile → catchment reality.

### 5.7 data.police.uk — **CORE — easy, high-impact card**
- **What:** street-level crime + outcomes + stop-and-search. **Free, no key.** JSON REST. Query by lat/lng OR custom polygon.
- **Docs:** `https://data.police.uk/docs/`
- **Use:** "shoplifting in your area up — here's a security grant + neighbours to coordinate with."

### 5.8 London Datastore — **NICE/SLIDE — the breadth**
- **URL:** `https://data.london.gov.uk/` (900+ datasets, JSON API)
- **Key sets:** LSOA Atlas (Pension Credit claimants, child poverty, fuel poverty, car access, PT accessibility), borough council-tax-support variations, high-streets data, planning.
- **HSDS (High Streets Data Service):** **[RISK] subscriber-locked to borough/BID officers** (BT mobility + Mastercard spend). **Do NOT claim to have it.** Open proxies only: high-street boundaries, town-centre classification (CSV), **Google Mobility by borough** (auto-updates ~every few days) as the legal footfall signal.

### 5.9 Supporting live feeds — **SLIDE/NICE**
- **LAQN / Breathe London** air quality: `https://www.londonair.org.uk/LondonAir/API/` — near-real-time pollution (nursery/gym/outdoor café card).
- **National Grid Carbon Intensity:** live + forecast (agentic "when to run" logic).
- **Environment Agency:** flood/river levels.

---

## 6. THE THREE INSIGHT ENGINES (full spec)

### Engine 1 — MONEY ("you're owed this") — **BUILD FIRST, NON-NEGOTIABLE**
- **Inputs:** VOA RV (cached) + sector (from VOA description / Companies House SIC) + borough.
- **Logic:** `rules_relief.py` (deterministic) → SBRR, RHL multiplier check, pub relief (strict), challenge wedge, SSB, City flag. + `rules_grants.py` → Find a Grant matches.
- **Output:** exact £ entitlement, backdating estimate, drafted claim email.
- **Defensibility:** every number traces to gov.uk; LLM never computes.

### Engine 2 — FORESIGHT ("what's about to hit your street") — **ONE CARD IF TIME**
- **Inputs:** business postcode → bounding box. TfL Road Disruption (CORE), JamCam VLM (NICE), LAQN (NICE).
- **Output:** location-specific operational warnings.
- **Why AYA can't:** no live operational layer.

### Engine 3 — CROSS-DOMAIN ("what the city knows about your block") — **SLIDE / 1 CARD IF FLYING**
- **Inputs:** postcode → LSOA → IMD 2025 + police + LSOA Atlas/Census.
- **Output:** catchment reality (income trend, no-car share, crime trend, language profile).
- **Why it needs the graph:** value is in the *joins*. This is AYA's KG idea on richer inputs.

### Extra insights pullable (mention as depth / roadmap)
- Empty-property relief, discretionary borough relief, transitional protection (owners don't know they're capped).
- No-car-household share → delivery opportunity. Language profile → multilingual marketing. Age profile → hours/product mix.
- Companies House: competitor incorporations nearby in your SIC = competition arriving before they open. Sector saturation.
- Disruption-as-opportunity: a competitor's scaffolding / nearby closure = your promo window.

---

## 7. SYSTEM ARCHITECTURE

```
Business name / postcode
   │
   ▼
[postcodes.io] ─► LSOA + lat/lng (join glue; optional, degrades offline)
   │
   ▼
[LOCAL JOIN LAYER]  ← cached BEFORE runtime; no cloud at demo time
   VOA 2026 · Companies House · IMD 2025 · police · grants
   │
   ▼
┌──────────────────────────────────────────────┐
│ ENGINES (deterministic — LLM never does math) │
│  rules_relief.py · rules_grants.py             │
│  foresight.py · crossdomain.py                 │
└──────────────────────────────────────────────┘
   │ structured findings (JSON)
   ▼
[LOCAL LLM — Nemotron Nano V2 VL 12B · vLLM · NVFP4]
   explains findings · drafts claim email · routes via MCP
   │
   ▼
[MCP CONNECTORS]  read: TfL/VOA/Grant/police   act: email/grant/ReadmeDB memory
   │
   ▼
[FRONTEND]  type name → 6s brief → 3 insight cards → drafted action
```

**Discipline:** facts from data layer + engines; LLM only language + routing; every card number traces to source. **Offline proof:** all cloud calls are ingestion, cached pre-demo; unplug → local model + local data.

---

## 8. DGX SPARK SETUP — modules, models, commands

> GB10 Grace Blackwell. Stand this up BEFORE writing app code (Person B, hour 0).

**1. Verify hardware/stack**
```bash
nvidia-smi            # confirm GB10 visible
python3 --version     # use uv or conda for a clean env
```

**2. Local inference — vLLM (OpenAI-compatible endpoint)**
```bash
pip install vllm --break-system-packages
# serve the multimodal model; quantized for GB10
vllm serve nvidia/Nemotron-Nano-VL-12B \
  --quantization nvfp4 \
  --port 8000
# → http://localhost:8000/v1/chat/completions
```
- **Model:** Nemotron Nano V2 VL (12B, multimodal — does language reasoning AND JamCam vision in one). Alt: Gemma multimodal. **[ASSUMPTION]** exact HF model string + NVFP4 flag may differ on the provided image; confirm against the box's model catalog at the event. NVIDIA ships these out-of-the-box on DGX Spark.
- Start with **one** endpoint. Add the AYA-style 3-endpoint parallel "analyst hats" only if time.

**3. VLM pipeline**
- Use NVIDIA's **"Live VLM WebUI"** playbook (stream camera → VLM → analysis) as the reference for `jamcam_analyze.py`. Demo on pre-pulled clips.

**4. Vector store + RAG (relief/grant rule text)**
```bash
pip install chromadb --break-system-packages
```
- Embed gov.uk relief guidance + grant descriptions locally. Math is deterministic; RAG only explains *which* rule and matches grants semantically.

**5. MCP layer**
- Run connectors as local servers the agent calls. **[RISK] ReadmeDB is hosted** → unplugging breaks the memory connector on stage. Run a **local mirror** or have the agent degrade gracefully and say so.

**6. Offline proof rehearsal**
- Confirm: ingest + cache everything → pull cable → full query still returns. Rehearse this specific sequence.

---

## 9. THE REPO — module map

```
spark-london/
├── PROJECT_BIBLE.md            # this file
├── PRD.md                      # the product doc
├── data/
│   ├── ingest_voa.py           # ✅ parse asterisk-delimited 2026 list → index
│   ├── ingest_companies.py     # Companies House → entity + SIC
│   ├── ingest_imd.py           # IMD 2025 by LSOA
│   ├── ingest_police.py        # crime by polygon
│   ├── postcode_resolver.py    # postcodes.io → LSOA/latlng (join glue)
│   └── build_index.py          # multi-key index
├── engines/
│   ├── rules_relief.py         # ✅ DETERMINISTIC relief engine (v2, verified)
│   ├── rules_grants.py         # Find a Grant matching
│   ├── foresight.py            # TfL disruption + JamCam VLM + AQ
│   └── crossdomain.py          # IMD + police + census joins
├── graph/
│   └── build_graph.py          # KG over joined data (AYA's best idea)
├── mcp/
│   ├── tfl_connector.py
│   ├── voa_connector.py
│   ├── findagrant_connector.py
│   ├── police_connector.py
│   └── readmedb_connector.py   # persistent per-business memory (local mirror!)
├── agent/
│   ├── pipeline.py             # ✅ name/postcode → VOA → relief (end-to-end spine)
│   ├── brief_builder.py        # assembles brief (no LLM for facts)
│   ├── insight_cards.py        # fires the 3 card types
│   ├── explain.py              # LLM: JSON findings → plain English + email draft
│   └── orchestrator.py         # LLM reasons over brief + calls MCP tools
├── vlm/
│   └── jamcam_analyze.py       # Nemotron VLM over camera stills/clips
├── server/
│   └── bridge.py               # HTTP gateway → local LLM + MCP + data layer
└── frontend/                   # React+Vite, 3-column: nav | cards | chat
```
✅ = built and tested already (relief engine, VOA parser, pipeline spine).

---

## 10. MCP CONNECTOR LAYER (our edge — your ReadmeDB strength)

AYA hardcoded 19 skills. We make every source + action a connector.
- **Read connectors:** TfL, VOA, Find-a-Grant, Companies House, police, IMD.
- **Act connectors:** draft borough reclaim email (pre-filled property ref); pre-fill Find a Grant; route to Citizens Advice / London Business Hub with context.
- **Memory:** **ReadmeDB MCP** = real versioned per-business store (AYA faked this with scratch files). **Run a local mirror for the offline demo.**
- **Pitch line:** *"AYA had 19 hardcoded skills. We have an open protocol — any borough, BID, or charity plugs in as an MCP and instantly reaches every business. Memory is a real versioned store, not scratch files."*

---

## 11. HOUR-BY-HOUR (24h, 3 people)

**Roles:** A = Data+Truth · B = Spark+Agent · C = Frontend+Demo.

| Hours | A (Data) | B (Spark/Agent) | C (Frontend/Demo) |
|---|---|---|---|
| 0–2 | Download real VOA 2026, verify field indices vs spec, build index for 2–3 boroughs | `nvidia-smi`, vLLM serving Nemotron, hit localhost | Scaffold 3-col UI, mock pipeline JSON |
| 2–6 | Confirm engine matches a REAL bill for 3 real businesses | Wire `explain.py`: JSON → plain English + email draft | Render real cards from `pipeline.run()` |
| 6–10 | **GATE: one real business shows one real reclaim on screen** | Integrate name→agent→data→card loop | Money card as visual hero |
| 10–14 | Add grants matching (`rules_grants.py`) | Add 1 foresight card (TfL Road Disruption) | Email-draft action UI; sleep in shifts |
| 14–18 | Cache everything for offline; cross-domain card if flying | Offline proof working; unplug test passes | Polish hero card; loading→6s brief feel |
| 18–22 | Source list for "real businesses" slide | MCP connector demo (1 real) + local memory mirror | 3 "where it scales" slides |
| 22–24 | Buffer / fix | Buffer / fix | Rehearse 90s demo ×5 |

**The GATE rule (hour 6):** if one real business isn't showing one real reclaim, **stop everything and brute-force that path.** Drop foresight, drop polish. The hero moment is the whole game.

---

## 12. THE DEMO SCRIPT (90 seconds)

1. **(0–10s) Frame the divergence.** "The NYC winner built a dashboard of what's *true* about a business. We asked a different question — what you're *owed* and don't know. In the UK right now that question has a sharp answer, because the April 2026 revaluation just reset every rateable value in the country."
2. **(10–25s) Type a REAL Hackney café.** 6-second grounded brief appears.
3. **(25–45s) The money card lands huge:** "**~£4,393/yr — Small Business Rate Relief this café likely isn't claiming. Backdatable.**" Numbers from a deterministic engine — no hallucination.
4. **(45–60s) Second card:** "Roadworks start on their street Monday — plan a promo." (live TfL)
5. **(60–75s) Agent drafts the reclaim email** live, pre-filled with the property reference.
6. **(75–90s) Unplug the ethernet. Ask one more question. It still answers.** "Their financial data never touched the cloud. That's why a business will trust this — and that's what this hardware is for."

---

## 13. LIMITATIONS & RISKS — READ FIRST

1. **[RISK] VOA field parsing is the #1 technical risk.** Asterisk-delimited, column order must match the spec for the actual file. Do it hour 0–2. If it breaks, the money engine has no data.
2. **[RISK] Rules-engine accuracy = your entire reputation.** One wrong £ kills trust. The engine is verified to June 2026, but **confirm multiplier pence + SBRR taper against gov.uk on build day**, and test against a *real* bill. The café number already moved £4,968→£4,393 once we fixed the RHL multiplier — that's how easily it shifts.
3. **[RISK] HSDS footfall/spend is subscriber-locked to borough/BID officers.** Do NOT claim it. Use Google Mobility + high-street boundaries; say so. If pushed, the honest path is "built for BIDs who already have HSDS."
4. **[RISK] Live VLM over 900 JamCams in 24h is unrealistic.** Pre-pull clips; frame scale as roadmap. JamCams are stills + 5s clips, not live video.
5. **[RISK] Cloud ReadmeDB breaks the unplug moment.** Local mirror or graceful degrade — and narrate it honestly during the demo.
6. **[RISK] Find a Grant has no guaranteed public API.** Cache the live grants list pre-demo; don't depend on a live call.
7. **[ASSUMPTION] Exact Nemotron HF string + NVFP4 flags** may differ on the provided Spark image. Confirm against the box's catalog hour 0.
8. **[RISK] City of London + GLA supplements differ.** Engine flags, never computes. Don't put a City £ figure on screen without local verification.
9. **Scope discipline.** Three engines is the *vision*; the *build* is Money (complete) + one Foresight card. Cross-domain is a slide. Re-deciding this at 4am is how teams die.
10. **Sector inference is fuzzy.** VOA "description" / SIC → RHL classification is approximate. A wrong RHL flag changes the multiplier. For the 3 demo businesses, set sector manually and verify.

---

## 14. RESOURCE INDEX (every link)

**Rules / money**
- SBRR: https://www.gov.uk/apply-for-business-rate-relief/small-business-rate-relief
- 2026 multipliers (official 2/2026): https://www.gov.uk/government/publications/22026-notification-of-non-domestic-rating-multipliers-for-202627/22026-notification-of-non-domestic-rating-multipliers-for-202627
- Pub/live music relief 1/2026: https://www.gov.uk/government/publications/12026-pubs-and-live-music-venues-relief-2026-to-2027/12026-pubs-and-live-music-venues-relief-2026-to-2027
- Qualifying RHL guidance: https://www.gov.uk/guidance/business-rates-multipliers-qualifying-retail-hospitality-or-leisure
- SSB 2026 LA guidance: https://www.gov.uk/government/publications/business-rates-relief-2026-supporting-small-business-relief-local-authority-guidance
- Find a Business Rates Valuation: https://www.gov.uk/correct-your-business-rates
- Business rates valuation account (challenge): https://www.gov.uk/business-rates-valuation-account

**Data**
- VOA bulk rating list: https://voaratinglists.blob.core.windows.net/html/rlidata.htm
- Companies House API: https://developer.company-information.service.gov.uk/
- Find a Grant: https://www.find-government-grants.service.gov.uk/
- TfL portal (key): https://api-portal.tfl.gov.uk/ · base: https://api.tfl.gov.uk/ · swagger: https://api.tfl.gov.uk/swagger/ui/index.html
- TfL Road Disruption: https://api.tfl.gov.uk/Road/All/Disruption
- TfL JamCams: https://api.tfl.gov.uk/Place/Type/JamCam/
- postcodes.io: https://api.postcodes.io/postcodes/{postcode}
- IMD 2025: https://www.gov.uk/government/statistics/english-indices-of-deprivation-2025
- London Datastore: https://data.london.gov.uk/
- data.police.uk: https://data.police.uk/docs/
- LAQN air quality: https://www.londonair.org.uk/LondonAir/API/

**Reference**
- AYA repo: https://github.com/Ali-Maq/aya-ai-for-small-businesses

---

*Built for the NVIDIA Spark Hack, London. Runs on your hardware. The money never leaves the room.*
