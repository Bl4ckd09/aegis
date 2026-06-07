# STELLA — Datasets Reference

> All data used, how to get it, what it's used for, and what's still available to add.

---

## Datasets Currently In Use

### 1. VOA 2026 Rating List
| Field | Detail |
|---|---|
| Source | Valuation Office Agency (UK Government) |
| URL | `https://www.gov.uk/guidance/find-a-business-rates-valuation` |
| File | `SCAT_code_and_description_version_4.3.zip` → asterisk-delimited CSV |
| Size | 2.1M properties UK-wide → 311,750 London extracted |
| Local file | `data/voa_london_index.csv` (41MB, committed to repo) |
| License | Open Government Licence v3.0 |
| Updated | April 2026 (revaluation year) |
| Used for | Every rateable value, SBRR calculation, property address, borough |

### 2. Companies House Bulk Data
| Field | Detail |
|---|---|
| Source | Companies House (UK Government) |
| URL | `http://download.companieshouse.gov.uk/en_output.html` |
| File | `BasicCompanyDataAsOneFile-2026-06-01.zip` (493MB compressed) |
| Size | 5,607,936 companies UK-wide |
| Local file | `data/ch_index.db` (1.3GB SQLite — NOT in repo, run ingest) |
| License | Open Government Licence v3.0 |
| Updated | Monthly |
| Used for | Company name lookup, SIC codes, incorporation date, postcode, sector derivation |
| Ingest | `python3 data/ingest_companies_local.py BasicCompanyDataAsOneFile-*.zip` |

### 3. Companies House API (fallback)
| Field | Detail |
|---|---|
| Source | Companies House |
| URL | `https://api.company-information.service.gov.uk` |
| Auth | HTTP Basic — API key as username, blank password |
| Key | `COMPANIES_HOUSE_KEY` env var |
| Used for | Fallback when local DB unavailable; also used for `get_by_number()` full profile |
| Rate limit | 600 req/min |

### 4. London Borough Council Contacts
| Field | Detail |
|---|---|
| Source | Each council's official website (manually verified) |
| Local file | `data/borough_contacts.py` |
| Coverage | All 33 London boroughs + City of London |
| Used for | Direct SBRR application URL, rates team email, phone per borough |

### 5. Postcodes.io (geocoding)
| Field | Detail |
|---|---|
| Source | `postcodes.io` (open source, free) |
| URL | `https://api.postcodes.io` |
| Auth | None — completely free |
| Local cache | `data/cache/postcodes.json` |
| Used for | LSOA code, ward, lat/long from postcode |

---

## Datasets Available to Add (London Open Data)

All free, Open Government Licence, from `data.london.gov.uk`:

### A. Indices of Deprivation 2019
- **URL:** `https://data.london.gov.uk/dataset/indices-of-deprivation-2l15g/`
- **Format:** Excel (3.7MB)
- **STELLA use:** Flag if business is in a deprived LSOA → unlocks additional grants (GLA, UKSPF priority areas)
- **Status:** ❌ Not yet integrated

### B. TfL Live Traffic Disruptions
- **URL:** `https://data.london.gov.uk/dataset/tfl-live-traffic-disruptions-248xn/`
- **Format:** XML feed, updated every 5 min, free
- **STELLA use:** "Roadworks near your postcode affecting footfall" card
- **Status:** ❌ Not yet integrated

### C. Local Units by Employment Size (Borough)
- **URL:** `https://data.london.gov.uk/dataset/local-units-employment-size-borough`
- **Format:** Excel
- **STELLA use:** Show how many businesses of similar size are in your borough → market context
- **Status:** ❌ Not yet integrated

### D. Commercial & Industrial Floorspace by Borough
- **URL:** `https://data.london.gov.uk/dataset/commercial-and-industrial-floorspace-borough/`
- **Format:** Excel
- **STELLA use:** Cross-reference VOA property against sector floorspace trends
- **Status:** ❌ Not yet integrated

### E. Find a Grant (gov.uk)
- **URL:** `https://www.find-government-grants.service.gov.uk/`
- **API:** Undocumented JSON at `/api/grants` — ~4,000 UK schemes
- **STELLA use:** Expand from 10 hardcoded grants to full database
- **Status:** ❌ Not yet integrated

---

## LLM / AI

| Component | Detail |
|---|---|
| Primary | DGX Spark VPS — `http://10.18.216.24:30000/v1/chat/completions` |
| Model | `nemotron` (Nemotron-3-Nano-30B — NVIDIA reasoning model) |
| Fallback | Local Ollama — `http://localhost:11434` |
| Used for | Rates relief claim letters, grant application emails, action step checklists |

---

## Data NOT Used (and why)

| Data | Why not |
|---|---|
| Turnover / revenue | Not public for UK SMEs — would need self-reporting form |
| Employee count | Not public — Companies House only has size band |
| Trading address | CH only has registered address — VOA has property address |
| NNDR ratepayer lists | Councils hold these but don't publish centrally (FOI only) |
| Grant application APIs | Government grant portals have no public submission APIs |

---

## Rebuild Instructions (for DGX Spark / new machine)

```bash
# 1. Clone repo (VOA CSV is included at 41MB)
git clone https://github.com/shahaman098/Stella
cd Stella

# 2. Download CH bulk data (free, no login)
# Go to: http://download.companieshouse.gov.uk/en_output.html
# Download: BasicCompanyDataAsOneFile-YYYY-MM-DD.zip

# 3. Build local company index (~4 min)
python3 data/ingest_companies_local.py BasicCompanyDataAsOneFile-*.zip

# 4. Run
PORT=5001 COMPANIES_HOUSE_KEY=<optional> python3 server/app.py
# LLM auto-connects to DGX at 10.18.216.24:30000
```
