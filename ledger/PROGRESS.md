# STELLA — Progress & Backlog
> NVIDIA Spark Hack London · Track 1: Economic Systems · Updated 2026-06-06

---

## What STELLA Is
On-device AI agent telling London small businesses what government money (rates relief + grants) they're owed but not claiming. Every £ figure is deterministic from gov.uk rules — LLM only drafts the letter.

---

## DONE ✅

### Core Data Pipeline
- **VOA 2026 ingest** (`data/ingest_voa.py`) — parses 2.1M-row asterisk-delimited file, extracts 311,750 London properties
- **Field positions verified** against real file (row counter at [0], BA code at [1], RV at [17], postcode at [14])
- **London BA codes corrected** — all 33 boroughs + City of London (5030)
- **Sector classification** — 20+ rules mapping VOA description text → sector (cafe/retail/pub/hospitality/office/industrial/leisure/other)
- **PUBLIC CONVENIENCE bug fixed** — must appear before PUB rules to avoid misclassification
- **CSV index built** — `data/voa_london_index.csv` (311,750 rows, local, no internet)

### Rules Engine
- **`engines/rules_relief.py`** — deterministic SBRR + pub relief + multiplier calculations
  - Multipliers 2026/27: SB-RHL 38.2p, SB-non-RHL 43.2p, Std-RHL 43p, Std-non-RHL 48p, High 50.8p
  - SBRR: 100% if RV ≤ £12k; tapered 1%/£30 up to £15k; 0% above
  - Pub/live-music 15% relief (pubs only — cafés, restaurants explicitly excluded)
  - Backdated estimate: 6 years
- **`engines/rules_grants.py`** — 10 grant programs with real eligibility rules
  - Inputs: sector, SIC codes, borough, RV, company age, company type
  - Programs: Start Up Loans, UKSPF, London Growth Hub, Innovate UK, R&D Tax Credits, GLA Good Growth Fund, Hospitality Energy Grant, East London Business Place, Creative Enterprise Programme, Net Zero support
  - Sorted: eligible → likely → check
- **8/8 canonical tests pass** (`tests/test_rules_relief.py`)

### Companies House Integration
- **`data/ingest_companies.py`** — name search + profile fetch via CH API (HTTP Basic auth)
- **`data/ingest_companies_local.py`** — bulk CSV ingest → SQLite (`data/ch_index.db`)
  - Reads `BasicCompanyData-YYYYMMDD-*.zip` (5 parts, ~700MB compressed)
  - Builds postcode-indexed SQLite for offline queries
  - `search_by_postcode(postcode)` returns companies instantly from local DB
- **CH API bug fixed** — `location=` parameter works; `registered_postcode=` does not filter

### Agent Pipeline
- **`agent/pipeline.py`** — `run(postcode)` and `run_by_name(name)` → frozen JSON contract
- **`data/postcode_resolver.py`** — postcodes.io with disk cache, degrades offline
- **`data/verify_business.py`** — CLI verification tool, runs engine on all matches at a postcode

### Flask Web Server (`server/app.py`)
Endpoints:
- `GET /` — UI
- `POST /api/lookup` — postcode or name → all VOA properties with findings
- `POST /api/biz-profile` — **two-step**: step 1 auto-selects property (sector + savings logic), step 2 returns full analysis + grants
- `POST /api/companies-at` — companies registered at postcode (local DB first, CH API fallback)
- `POST /api/grants` — grants eligibility (sector + SIC + borough + age + RV)
- `POST /api/draft-email` — LLM claim letter via Ollama

### UI (`server/templates/index.html`)
- **Street Scanner mode** — scan all properties at a postcode, sorted savings-first
- **My Business mode** — name + postcode + sector → auto-selects property → single-business dashboard
  - Companies House profile card (number, SIC codes, age)
  - Relief findings with £ figures and gov.uk source
  - Multi-property checker (SBRR single-occupation rule)
  - Personalised grants panel ranked by eligibility with match reasons
- **Companies panel** — all companies registered at postcode (auto-fetched, collapsible)
- **Confidence badges** explained: high = unambiguous law, medium = likely, check = investigate
- **Email draft modal** — letter pre-filled with UARN, address, findings
- **"Verify RV on gov.uk"** link on every card
- Runs on PORT=5001 (5000 blocked by macOS AirPlay)

### Key Bugs Fixed
| Bug | Fix |
|-----|-----|
| VOA field positions wrong | Verified against real file: RV=[17], postcode=[14], BA=[1] |
| London BA codes shifted | All 33 boroughs re-verified by postcode sampling |
| PUBLIC CONVENIENCE → sector "pub" | Added `("PUBLIC CONVENIENCE","other")` before PUB rules |
| SBRR taper test expectations wrong | Engine correct; tests had wrong multiplier (retail is RHL=0.382) |
| run.py TypeError | Rewrote with `--postcode`/`--name` argparse flags |
| CH API empty postcodes | Fallback to `get_by_number()` per candidate |
| CH `registered_postcode` param broken | Use `location=` parameter instead |
| My Business picked wrong property | Auto-select: 1 sector match → pick it; multiple matches → pick the one with savings; genuine tie → small picker |
| Port 5000 blocked | PORT=5001 |

---

## LEFT TO DO ❌

### Immediate (before demo)
- [ ] **DGX Spark deployment** — copy files, set OLLAMA_HOST, run locally
- [ ] **CH bulk data ingest** — friend downloading `BasicCompanyData-*.zip`; run `python3 data/ingest_companies_local.py BasicCompanyData-*.zip` → builds `ch_index.db`; unlocks SIC codes for all companies → better grant matching
- [ ] **Ollama on DGX Spark** — `curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3.2 && ollama serve` — needed for email draft LLM
- [ ] **Test My Business mode end-to-end** in browser after latest fixes

### Data & Coverage
- [ ] **Scrape `findagrant.gov.uk`** — ~4,000 UK grant schemes; undocumented JSON at `findagrant.gov.uk/api/grants`; build local cache
- [ ] **Expand grants engine** — currently 10 hardcoded programs; target 40-50 real schemes
- [ ] **Turnover / employee intake form** — needed for ~20% of grants that require these (not public from VOA/CH)
- [ ] **SIC code → sector mapping** — improve grant matching when VOA sector is "other" but CH has specific SIC
- [ ] **2026 Revaluation Challenge flag** — if RV dropped from previous list, flag backdated appeal opportunity

### Features
- [ ] **TfL disruption card** — roadworks near business postcode; needs TfL API key (register at api-portal.tfl.gov.uk)
- [ ] **LSOA deprivation index** — cross-reference with IoD 2019 to flag deprived area grants (GLA priority)
- [ ] **Multi-property business analysis** — if a business has 3 sites, analyse all of them
- [ ] **Bulk postcode scan** — upload a CSV of postcodes (e.g. for a BID); export findings as CSV
- [ ] **"Apply now" deep links** — pre-fill grant application URLs where possible

### Quality
- [ ] **Street Scanner: sector override should apply to ALL properties** not just the first
- [ ] **Cache VOA lookup results** — currently re-scans CSV on every request; add in-memory postcode cache
- [ ] **Add tests for grants engine** (`tests/test_rules_grants.py`)
- [ ] **Validate grants against live program status** — some may have closed rounds

---

## Local Data Status

| Source | Status | Location |
|--------|--------|----------|
| VOA 2026 (311,750 London properties) | ✅ Local | `data/voa_london_index.csv` |
| Companies House (name search) | ⚠️ API only | CH API key in env |
| Companies House (bulk, 5M companies) | ❌ Pending | Friend downloading `BasicCompanyData-*.zip` |
| Postcodes.io (LSOA lookup) | ⚠️ Cached | `data/cache/postcodes.json` |
| Grant programs | ❌ Hardcoded | `engines/rules_grants.py` (10 programs) |
| LLM (email drafting) | ❌ Needs Ollama | Set `OLLAMA_HOST=http://<dgx-ip>:11434` |

---

## Run Commands

```bash
# Development (laptop)
PORT=5001 COMPANIES_HOUSE_KEY=cbbf4e3f-b2c0-447f-b45f-fc50e4b65dd5 python3 server/app.py

# After CH bulk download
python3 data/ingest_companies_local.py BasicCompanyData-*.zip

# Full local (DGX Spark, no internet)
PORT=5001 OLLAMA_HOST=http://localhost:11434 python3 server/app.py

# Tests
python3 -m pytest tests/ -v

# CLI verify a business
python3 data/verify_business.py "EC1N 7TE" --sector cafe
```

---

## Gov.uk Sources (for credibility)
- SBRR: `gov.uk/apply-for-business-rate-relief/small-business-rate-relief`
- Multipliers 2026/27: `gov.uk` notification 2/2026
- Pub relief: `gov.uk` publication 1/2026
- Verify any RV: `gov.uk/correct-your-business-rates`
