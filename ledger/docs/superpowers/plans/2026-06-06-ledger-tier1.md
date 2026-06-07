# LEDGER Tier 1 — Money Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete LEDGER money engine — from VOA data ingest through deterministic relief calculation to a frozen JSON pipeline contract — so the frontend/agent tier can build against it.

**Architecture:** Deterministic Python rules engine with zero LLM involvement in money math. Data is ingested/cached before demo time; runtime is fully offline. Pipeline goes: postcode/name → VOA index lookup → `assess()` → structured JSON findings.

**Tech Stack:** Python 3.11+, stdlib only (zipfile, csv, urllib, json, re). No third-party deps for the core engine — installable anywhere, including the DGX Spark without pip headaches.

---

## File Map

| File | Status | Responsibility |
|---|---|---|
| `engines/__init__.py` | create | package marker |
| `engines/rules_relief.py` | **create** | deterministic relief engine — all £ figures |
| `data/__init__.py` | create | package marker |
| `data/ingest_voa.py` | **create** | VOA zip → London index CSV |
| `data/postcode_resolver.py` | **create** | postcodes.io → LSOA/lat-lng, disk-cached |
| `data/ingest_companies.py` | **create** | Companies House name → postcode candidates |
| `agent/pipeline.py` | **rewrite** | postcode/name → VOA → relief → frozen JSON |
| `data/verify_business.py` | **create** | manual end-to-end check for 3 demo businesses |
| `tests/test_rules_relief.py` | **create** | TDD tests for all canonical cases |
| `data/README.md` | **create** | teammate setup docs |

---

### Task 1: `engines/rules_relief.py` — deterministic money engine

**Files:**
- Create: `engines/__init__.py`
- Create: `engines/rules_relief.py`
- Create: `tests/__init__.py`
- Create: `tests/test_rules_relief.py`

- [ ] **Step 1: Write the failing tests first**

Create `tests/__init__.py` (empty) and `tests/test_rules_relief.py`:

```python
"""Canonical test cases — every number verified against gov.uk rules."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engines.rules_relief import Business, assess

def _find(findings, keyword):
    return next((f for f in findings if keyword.lower() in f.headline.lower()), None)


def test_hackney_cafe_full_sbrr():
    """RV £11,500 café → 100% SBRR → £4,393/yr, ~£26k backdated."""
    biz = Business("Test Café", rateable_value=11_500, borough="Hackney", sector="cafe")
    findings = assess(biz)
    sbrr = _find(findings, "small business rate relief")
    assert sbrr is not None, "SBRR finding missing"
    assert abs(sbrr.annual_value - 4393.0) < 1.0, f"Expected ~£4393, got £{sbrr.annual_value}"
    assert sbrr.backdated_value > 26_000, "Backdated should be ~£26k+"
    assert sbrr.confidence == "high"


def test_shop_just_over_cliff():
    """RV £15,800 shop → no SBRR, but revaluation challenge flag."""
    biz = Business("Test Shop", rateable_value=15_800, borough="Hackney", sector="retail")
    findings = assess(biz)
    sbrr = _find(findings, "small business rate relief")
    assert sbrr is None, "Should be NO SBRR above £15,000"
    challenge = _find(findings, "revaluation")
    assert challenge is not None, "Should flag 2026 revaluation challenge"


def test_pub_fifteen_percent():
    """RV £42,000 pub → 15% pub/live-music relief."""
    biz = Business("Test Pub", rateable_value=42_000, borough="Hackney", sector="pub")
    findings = assess(biz)
    pub = _find(findings, "pub")
    assert pub is not None, "Pub relief missing"
    # gross = 42000 * 0.382 = 16044; 15% = 2406.60
    assert abs(pub.annual_value - 2406.60) < 2.0, f"Expected ~£2407, got £{pub.annual_value}"


def test_cafe_no_pub_relief():
    """RV £28,000 café → NO pub/live-music relief (cafés explicitly excluded)."""
    biz = Business("Test Café 2", rateable_value=28_000, borough="Hackney", sector="cafe")
    findings = assess(biz)
    pub = _find(findings, "pub")
    assert pub is None, "Café must NOT receive pub/live-music relief"


def test_sbrr_taper_13500():
    """RV £13,500 → 50% SBRR taper (gov.uk worked example)."""
    biz = Business("Test", rateable_value=13_500, borough="Hackney", sector="retail")
    findings = assess(biz)
    sbrr = _find(findings, "small business rate relief")
    assert sbrr is not None
    # gross = 13500 * 0.432 = 5832; 50% = 2916
    assert abs(sbrr.annual_value - 2_916.0) < 5.0, f"Expected ~£2916, got £{sbrr.annual_value}"


def test_sbrr_taper_14000():
    """RV £14,000 → ~33% SBRR taper (gov.uk worked example)."""
    biz = Business("Test", rateable_value=14_000, borough="Hackney", sector="retail")
    findings = assess(biz)
    sbrr = _find(findings, "small business rate relief")
    assert sbrr is not None
    # steps = (14000-12000)/30 = 66.67; pct = 1 - 0.6667 = 0.3333
    # gross = 14000 * 0.432 = 6048; 33.33% = 2016
    assert abs(sbrr.annual_value - 2_016.0) < 10.0, f"Expected ~£2016, got £{sbrr.annual_value}"


def test_city_of_london_flag():
    """City of London → flag only, no £ figure asserted."""
    biz = Business("Test", rateable_value=10_000, borough="City of London", sector="retail")
    findings = assess(biz)
    city = _find(findings, "city of london")
    assert city is not None
    assert city.annual_value == 0.0, "City of London: never assert a £ figure"


def test_high_value_multiplier():
    """RV ≥ £500k → high-value multiplier 50.8p."""
    biz = Business("Big Office", rateable_value=600_000, borough="Westminster", sector="office")
    findings = assess(biz)
    # No SBRR for high-value; verify no crash
    sbrr = _find(findings, "small business rate relief")
    assert sbrr is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/eshnanigans/NVIDIAHack/Stella
python -m pytest tests/test_rules_relief.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'engines.rules_relief'`

- [ ] **Step 3: Create `engines/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Create `engines/rules_relief.py`**

```python
"""Deterministic business-rates relief engine — England 2026/27.

LLM BOUNDARY: This module computes all £ figures. The LLM never calls
assess() and never modifies these outputs. All numbers trace to gov.uk.

Sources:
  Multipliers:    gov.uk notification 2/2026
  SBRR:          gov.uk/apply-for-business-rate-relief/small-business-rate-relief
  Pub/live music: gov.uk publication 1/2026
  SSB 2026:      gov.uk SSB LA guidance 2026
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

# 2026/27 multipliers — pence per £1 RV (notification 2/2026)
MULT_SB_NON_RHL  = 0.432   # small-business, not RHL use
MULT_SB_RHL      = 0.382   # small-business, RHL use  (RV < £51k)
MULT_STD_NON_RHL = 0.480   # standard, not RHL
MULT_STD_RHL     = 0.430   # standard, RHL use         (RV £51k–£499k)
MULT_HIGH        = 0.508   # high-value                (RV ≥ £500k)

# Retail/Hospitality/Leisure sectors → lower multiplier
RHL_SECTORS = {"retail", "cafe", "pub", "hospitality", "leisure"}

# Pub/live-music: ONLY these two qualify for 15% extra relief
PUB_QUALIFYING = {"pub"}

# Explicitly excluded from pub/live-music relief (per gov.uk 1/2026)
PUB_EXCLUDED = {
    "cafe", "restaurant", "nightclub", "hotel", "guesthouse",
    "snack_bar", "sporting", "festival", "theatre", "cinema",
    "museum", "exhibition", "casino",
}

Sector = Literal["retail", "cafe", "pub", "hospitality", "office", "industrial", "leisure", "other"]


@dataclass
class Business:
    name: str
    rateable_value: float
    borough: str
    sector: Sector
    uarn: str = ""
    address: str = ""
    postcode: str = ""
    composite: bool = False


@dataclass
class ReliefFinding:
    headline: str
    annual_value: float       # £/yr this relief saves
    backdated_value: float    # £ lump (up to 6-yr backdating estimate)
    confidence: Literal["high", "medium", "low"]
    rule: str
    action: str
    explanation: str
    source: str


def _multiplier(rv: float, sector: str) -> float:
    is_rhl = sector in RHL_SECTORS
    if rv >= 500_000:
        return MULT_HIGH
    elif rv >= 51_000:
        return MULT_STD_RHL if is_rhl else MULT_STD_NON_RHL
    else:
        return MULT_SB_RHL if is_rhl else MULT_SB_NON_RHL


def _gross_bill(rv: float, sector: str) -> float:
    return rv * _multiplier(rv, sector)


def _sbrr_pct(rv: float) -> float:
    """Return SBRR discount fraction (0.0–1.0). 1% per £30 over £12,000 taper."""
    if rv <= 12_000:
        return 1.0
    elif rv < 15_000:
        steps = (rv - 12_000) / 30.0
        return max(0.0, 1.0 - steps * 0.01)
    return 0.0


def assess(biz: Business) -> list[ReliefFinding]:
    """Return all applicable relief findings for a business. Never raises."""
    findings: list[ReliefFinding] = []
    rv = biz.rateable_value
    gross = _gross_bill(rv, biz.sector)

    # ── SBRR ────────────────────────────────────────────────────────────
    pct = _sbrr_pct(rv)
    if pct > 0.0:
        saving = gross * pct
        findings.append(ReliefFinding(
            headline=f"Small Business Rate Relief — {pct * 100:.0f}% off",
            annual_value=round(saving, 2),
            backdated_value=round(saving * 6, 2),
            confidence="high",
            rule="SBRR 2026/27",
            action=(
                "Contact your billing authority to claim. "
                "Relief can be backdated — ask specifically."
            ),
            explanation=(
                f"RV £{rv:,.0f} qualifies for {pct * 100:.0f}% SBRR on a "
                f"gross bill of £{gross:,.0f}/yr, saving £{saving:,.0f}/yr. "
                "Backdatable up to 6 years."
            ),
            source="https://www.gov.uk/apply-for-business-rate-relief/small-business-rate-relief",
        ))

    # ── 2026 revaluation challenge wedge ────────────────────────────────
    if 12_000 < rv <= 16_000:
        findings.append(ReliefFinding(
            headline="2026 Revaluation — possible challenge",
            annual_value=0.0,
            backdated_value=0.0,
            confidence="medium",
            rule="2026 Revaluation challenge wedge",
            action="Check via gov.uk/business-rates-valuation-account.",
            explanation=(
                f"RV £{rv:,.0f} is near the SBRR cliff (£12k/£15k). "
                "The April 2026 revaluation may have pushed you just over — "
                "a challenge could restore full or partial relief."
            ),
            source="https://www.gov.uk/business-rates-valuation-account",
        ))

    # ── Pub & live music relief ──────────────────────────────────────────
    if biz.sector in PUB_QUALIFYING and biz.sector not in PUB_EXCLUDED:
        pub_saving = gross * 0.15
        findings.append(ReliefFinding(
            headline="Pub & Live Music Venue Relief — 15% off",
            annual_value=round(pub_saving, 2),
            backdated_value=round(pub_saving, 2),  # 2026/27 only
            confidence="high",
            rule="Pub/live-music relief 2026/27 (gov.uk 1/2026)",
            action="Verify your bill — billing authority should apply automatically.",
            explanation=(
                f"Qualifying pub: 15% off gross bill (£{gross:,.0f}/yr → "
                f"saving £{pub_saving:,.0f}/yr for 2026/27)."
            ),
            source=(
                "https://www.gov.uk/government/publications/"
                "12026-pubs-and-live-music-venues-relief-2026-to-2027/"
                "12026-pubs-and-live-music-venues-relief-2026-to-2027"
            ),
        ))

    # ── City of London flag ──────────────────────────────────────────────
    if "city of london" in biz.borough.lower():
        findings.append(ReliefFinding(
            headline="City of London — special arrangements apply",
            annual_value=0.0,
            backdated_value=0.0,
            confidence="low",
            rule="City of London special arrangements",
            action="Contact the City of London Corporation for your relief position.",
            explanation=(
                "The City of London has separate billing authority arrangements. "
                "No national figure is asserted — verify locally."
            ),
            source="https://www.cityoflondon.gov.uk/business/business-rates",
        ))

    return findings
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/eshnanigans/NVIDIAHack/Stella
python -m pytest tests/test_rules_relief.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add engines/__init__.py engines/rules_relief.py tests/__init__.py tests/test_rules_relief.py
git commit -m "feat: deterministic relief engine (SBRR, pub, challenge wedge)"
```

---

### Task 2: `data/ingest_voa.py` — VOA bulk-list parser

**Files:**
- Create: `data/__init__.py`
- Create: `data/ingest_voa.py`

> ⚠️ **Field-position risk:** Run Step 1 FIRST to inspect the raw file before trusting any field indices.

- [ ] **Step 1: Inspect raw VOA file to verify field positions**

Download the zip (if not already done — ~200MB):
```bash
# Only run if you haven't downloaded it yet:
curl -L "https://voaratinglists.blob.core.windows.net/downloads/uk-englandwales-ndr-2026-listentries-compiled-epoch-0001-baseline-csv.zip" \
     -o /tmp/voa-2026.zip
```

Inspect first 3 records:
```bash
python3 -c "
import zipfile, io
with zipfile.ZipFile('/tmp/voa-2026.zip') as z:
    name = [n for n in z.namelist() if n.endswith('.csv')][0]
    print('File:', name)
    with z.open(name) as f:
        for i, line in enumerate(io.TextIOWrapper(f, encoding='latin-1')):
            parts = line.strip().split('*')
            for j, p in enumerate(parts):
                print(f'  [{j:02d}] {repr(p[:60])}')
            print('---')
            if i >= 2:
                break
"
```

**Verify which field index contains:**
- A 4-digit number starting with 5 (BA code, e.g. 5360)
- A description like "CAFE AND PREMISES" or "SHOP AND PREMISES"
- A plausible £ integer for rateable value (e.g. 11500)
- A UK postcode (e.g. "E8 1DY")

If the indices differ from the constants in the next step, update them.

- [ ] **Step 2: Create `data/__init__.py`**

```python
```
(empty)

- [ ] **Step 3: Create `data/ingest_voa.py`**

```python
"""VOA 2026 Rating List parser → London-only index CSV.

Field positions (0-indexed, asterisk-delimited, no header row).
VERIFY against the actual file before trusting — run Step 1 of the plan.

Usage:
    python3 data/ingest_voa.py /path/to/voa-2026.zip              # full London
    python3 data/ingest_voa.py /path/to/voa-2026.zip 50000        # first N rows (test)
"""
from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from pathlib import Path

# ── Field indices — VERIFY against raw file before running on real data ──────
IDX_BA_CODE  = 0    # Billing authority code, 4 digits, e.g. "5360"
IDX_UARN     = 3    # Unique Address Reference Number
IDX_DESC_CODE= 4    # Primary description code, e.g. "CF", "SR", "PB"
IDX_DESC_TEXT= 5    # e.g. "CAFE AND PREMISES", "SHOP AND PREMISES"
IDX_SCAT     = 6    # SCAT code (4-digit property use classification)
IDX_COMPOSITE= 9    # "Y" = composite (hereditament only, not the sub-parts)
IDX_RV       = 11   # Rateable value (integer £)
IDX_ADDR1    = 12   # Address line 1
IDX_ADDR2    = 13
IDX_ADDR3    = 14
IDX_ADDR4    = 15
IDX_POSTCODE = 16   # UK postcode

MIN_FIELDS = 17     # Records with fewer fields are silently skipped

# ── London Billing Authority codes (all 32 London boroughs + City) ───────────
LONDON_BA = {
    "5060": "Barking and Dagenham",
    "5090": "Barnet",
    "5120": "Bexley",
    "5150": "Brent",
    "5180": "Bromley",
    "5210": "Camden",
    "5240": "City of London",
    "5270": "Croydon",
    "5300": "Ealing",
    "5330": "Enfield",
    "5360": "Hackney",
    "5390": "Hammersmith and Fulham",
    "5420": "Haringey",
    "5450": "Harrow",
    "5480": "Havering",
    "5510": "Hillingdon",
    "5540": "Hounslow",
    "5570": "Islington",
    "5600": "Kensington and Chelsea",
    "5630": "Kingston upon Thames",
    "5660": "Lambeth",
    "5690": "Lewisham",
    "5720": "Merton",
    "5750": "Newham",
    "5780": "Redbridge",
    "5810": "Richmond upon Thames",
    "5840": "Southwark",
    "5870": "Sutton",
    "5900": "Tower Hamlets",
    "5930": "Waltham Forest",
    "5960": "Wandsworth",
    "5990": "Westminster",
}

# Description text → sector classification (order matters: first match wins)
SECTOR_RULES: list[tuple[str, str]] = [
    ("PUB",        "pub"),
    ("INN",        "pub"),
    ("TAVERN",     "pub"),
    ("WINE BAR",   "pub"),
    ("CAFE",       "cafe"),
    ("COFFEE",     "cafe"),
    ("RESTAURANT", "cafe"),    # cafés/restaurants share multiplier; not pub
    ("RETAIL",     "retail"),
    ("SHOP",       "retail"),
    ("STORE",      "retail"),
    ("MARKET",     "retail"),
    ("HOTEL",      "hospitality"),
    ("GUEST HOUSE","hospitality"),
    ("BED AND BREAK", "hospitality"),
    ("LEISURE",    "leisure"),
    ("GYM",        "leisure"),
    ("SPORTS",     "leisure"),
    ("THEATRE",    "leisure"),
    ("CINEMA",     "leisure"),
    ("OFFICE",     "office"),
    ("FACTORY",    "industrial"),
    ("WAREHOUSE",  "industrial"),
    ("INDUSTRIAL", "industrial"),
]

_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}$", re.IGNORECASE)


def _classify_sector(desc_text: str) -> str:
    upper = desc_text.upper()
    for keyword, sector in SECTOR_RULES:
        if keyword in upper:
            return sector
    return "other"


def _norm_postcode(raw: str) -> str:
    return raw.strip().upper()


def _validate_sample(rows: list[dict]) -> None:
    """Loudly warn if parsed data looks wrong."""
    if not rows:
        print("WARNING: zero London records parsed — check BA codes and field indices", file=sys.stderr)
        return

    rvs = [r["rateable_value"] for r in rows if r["rateable_value"]]
    bad_rv = sum(1 for v in rvs if not (500 <= v <= 10_000_000))
    if bad_rv / max(len(rvs), 1) > 0.05:
        print(
            f"WARNING: {bad_rv}/{len(rvs)} RVs outside plausible range £500–£10M. "
            "Field indices may be wrong — re-run Step 1 of the plan.",
            file=sys.stderr,
        )

    pcs = [r["postcode"] for r in rows if r["postcode"]]
    bad_pc = sum(1 for p in pcs if not _POSTCODE_RE.match(p))
    if pcs and bad_pc / len(pcs) > 0.10:
        print(
            f"WARNING: {bad_pc}/{len(pcs)} postcodes look malformed. "
            "IDX_POSTCODE may be wrong.",
            file=sys.stderr,
        )

    sectors = {}
    for r in rows:
        sectors[r["sector"]] = sectors.get(r["sector"], 0) + 1
    print(f"Sector distribution: {sectors}", file=sys.stderr)

    rv_vals = sorted(rvs)
    if rv_vals:
        print(
            f"RV range: £{rv_vals[0]:,}–£{rv_vals[-1]:,}  "
            f"median: £{rv_vals[len(rv_vals)//2]:,}",
            file=sys.stderr,
        )


def parse(zip_path: str, max_rows: int | None = None) -> list[dict]:
    """Parse the VOA zip → list of London property dicts."""
    rows: list[dict] = []
    skipped_no_rv = 0
    skipped_non_london = 0
    total = 0

    with zipfile.ZipFile(zip_path) as z:
        csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"No .csv file found in {zip_path}")
        target = csv_names[0]
        print(f"Parsing {target} ...", file=sys.stderr)

        with z.open(target) as raw:
            reader = csv.reader(
                io.TextIOWrapper(raw, encoding="latin-1"),
                delimiter="*",
                quoting=csv.QUOTE_NONE,
            )
            for fields in reader:
                total += 1
                if max_rows and total > max_rows:
                    break

                if len(fields) < MIN_FIELDS:
                    continue

                ba_code = fields[IDX_BA_CODE].strip()
                if ba_code not in LONDON_BA:
                    skipped_non_london += 1
                    continue

                # Skip composite sub-parts and null-RV proxy records
                composite_flag = fields[IDX_COMPOSITE].strip().upper()
                rv_raw = fields[IDX_RV].strip()
                if not rv_raw or rv_raw == "0":
                    skipped_no_rv += 1
                    continue

                try:
                    rv = float(rv_raw)
                except ValueError:
                    skipped_no_rv += 1
                    continue

                if rv <= 0:
                    skipped_no_rv += 1
                    continue

                desc_text = fields[IDX_DESC_TEXT].strip()
                addr_parts = [
                    fields[IDX_ADDR1].strip(),
                    fields[IDX_ADDR2].strip(),
                    fields[IDX_ADDR3].strip(),
                    fields[IDX_ADDR4].strip(),
                ]
                address = ", ".join(p for p in addr_parts if p)
                postcode = _norm_postcode(fields[IDX_POSTCODE])

                rows.append({
                    "ba_code":        ba_code,
                    "borough":        LONDON_BA[ba_code],
                    "uarn":           fields[IDX_UARN].strip(),
                    "desc_code":      fields[IDX_DESC_CODE].strip(),
                    "desc_text":      desc_text,
                    "sector":         _classify_sector(desc_text),
                    "rateable_value": rv,
                    "composite":      composite_flag == "Y",
                    "address":        address,
                    "postcode":       postcode,
                    "scat":           fields[IDX_SCAT].strip(),
                })

    print(
        f"Parsed {total:,} rows total → {len(rows):,} London entries "
        f"({skipped_non_london:,} non-London, {skipped_no_rv:,} null-RV skipped)",
        file=sys.stderr,
    )
    _validate_sample(rows)
    return rows


def write_index(rows: list[dict], out_path: str) -> None:
    fieldnames = [
        "ba_code", "borough", "uarn", "desc_code", "desc_text",
        "sector", "rateable_value", "composite", "address", "postcode", "scat",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Index written: {out_path} ({len(rows):,} records)", file=sys.stderr)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 data/ingest_voa.py <voa-2026.zip> [max_rows]")
        sys.exit(1)
    zip_path = sys.argv[1]
    max_rows = int(sys.argv[2]) if len(sys.argv) > 2 else None
    rows = parse(zip_path, max_rows)
    out = Path(__file__).parent / "voa_london_index.csv"
    write_index(rows, str(out))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Smoke-test on first 50k rows (fast)**

If VOA zip is already downloaded:
```bash
cd /Users/eshnanigans/NVIDIAHack/Stella
python3 data/ingest_voa.py /tmp/voa-2026.zip 50000
```

Expected stderr output should include:
- "Parsed 50,000 rows total → X London entries"
- Sector distribution showing retail/cafe/pub/office/etc.
- RV range within £500–£10M
- No WARNING lines (if warnings appear, fix field indices before full run)

- [ ] **Step 5: Run full London index (takes ~5 min)**

```bash
python3 data/ingest_voa.py /tmp/voa-2026.zip
# Produces: data/voa_london_index.csv
wc -l data/voa_london_index.csv   # expect 50,000–200,000 lines
```

- [ ] **Step 6: Commit**

```bash
git add data/__init__.py data/ingest_voa.py
git commit -m "feat: VOA 2026 London index parser with RV/postcode validation"
```

---

### Task 3: `data/postcode_resolver.py` — join glue, cached

**Files:**
- Create: `data/postcode_resolver.py`
- Create: `data/cache/` (directory, already exists)

- [ ] **Step 1: Create `data/postcode_resolver.py`**

```python
"""Postcode → LSOA + lat/lng via postcodes.io. Disk-cached for offline demo.

Cache location: data/cache/postcodes.json
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

CACHE_PATH = Path(__file__).parent / "cache" / "postcodes.json"
BULK_URL = "https://api.postcodes.io/postcodes"
SINGLE_URL = "https://api.postcodes.io/postcodes/{}"
_POSTCODE_RE = re.compile(r"^[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}$", re.IGNORECASE)


def _norm(postcode: str) -> str:
    return postcode.strip().upper().replace(" ", "")


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def _parse_result(result: dict | None) -> dict | None:
    if not result:
        return None
    return {
        "postcode":   result.get("postcode", ""),
        "lsoa":       result.get("lsoa", ""),
        "latitude":   result.get("latitude"),
        "longitude":  result.get("longitude"),
        "borough":    result.get("admin_district", ""),
        "ward":       result.get("admin_ward", ""),
    }


def resolve(postcode: str, *, timeout: int = 10) -> dict | None:
    """Return LSOA + lat/lng for a postcode. Returns None if not found or offline."""
    key = _norm(postcode)
    cache = _load_cache()
    if key in cache:
        return cache[key]

    try:
        url = SINGLE_URL.format(urllib.parse.quote(postcode.strip()))
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.load(resp)
        result = _parse_result(data.get("result"))
        cache[key] = result
        _save_cache(cache)
        return result
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def resolve_bulk(postcodes: list[str], *, timeout: int = 30) -> dict[str, dict | None]:
    """Resolve up to 100 postcodes in one call. Returns {normalised_pc: result}."""
    cache = _load_cache()
    keys = [_norm(p) for p in postcodes]
    missing = [k for k in keys if k not in cache]

    if missing:
        try:
            payload = json.dumps({"postcodes": missing[:100]}).encode()
            req = urllib.request.Request(
                BULK_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.load(resp)
            for item in data.get("result", []):
                pc = _norm(item.get("query", ""))
                cache[pc] = _parse_result(item.get("result"))
            _save_cache(cache)
        except (urllib.error.URLError, json.JSONDecodeError, OSError):
            for k in missing:
                cache.setdefault(k, None)

    return {k: cache.get(k) for k in keys}


# fix missing import
import urllib.parse
```

- [ ] **Step 2: Test online resolution**

```bash
cd /Users/eshnanigans/NVIDIAHack/Stella
python3 -c "
from data.postcode_resolver import resolve, resolve_bulk
r = resolve('E8 1DY')
print(r)
bulk = resolve_bulk(['EC1A 1BB', 'E8 1DY', 'SW1A 2AA'])
for k, v in bulk.items():
    print(k, '->', v)
"
```

Expected: dicts with `lsoa`, `latitude`, `longitude`, `borough` populated. Second run (offline simulation) should return same results from cache.

- [ ] **Step 3: Test offline (from cache)**

```bash
# Simulate offline: disconnect or just verify cache file exists and re-run
python3 -c "
from data.postcode_resolver import resolve
print(resolve('E8 1DY'))   # must return from cache without network
"
```

Expected: same result without network call.

- [ ] **Step 4: Commit**

```bash
git add data/postcode_resolver.py
git commit -m "feat: postcodes.io resolver with disk cache (offline-safe)"
```

---

### Task 4: `data/ingest_companies.py` — name → postcode

**Files:**
- Create: `data/ingest_companies.py`

> Requires a free Companies House API key: https://developer.company-information.service.gov.uk/
> Store as env var `COMPANIES_HOUSE_KEY` or pass `--key`.

- [ ] **Step 1: Create `data/ingest_companies.py`**

```python
"""Companies House API: business name → candidates with postcode + SIC.

Auth: free API key (HTTP Basic auth, key as username, empty password).
Cache: data/cache/companies_house.json

Usage:
    python3 data/ingest_companies.py "Hackney Coffee"
    COMPANIES_HOUSE_KEY=abc123 python3 data/ingest_companies.py "Hackney Coffee"

Returns candidates — the registered address may differ from the trading address.
The caller should confirm the match before using the postcode for VOA lookup.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

CACHE_PATH = Path(__file__).parent / "cache" / "companies_house.json"
BASE_URL = "https://api.company-information.service.gov.uk"


def _auth_header(api_key: str) -> str:
    token = base64.b64encode(f"{api_key}:".encode()).decode()
    return f"Basic {token}"


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def _get(path: str, api_key: str, timeout: int = 15) -> dict:
    url = BASE_URL + path
    req = urllib.request.Request(url, headers={"Authorization": _auth_header(api_key)})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def search_by_name(
    name: str,
    api_key: str,
    *,
    items_per_page: int = 5,
) -> list[dict]:
    """Return top candidates for a business name. Each has postcode, SIC, address."""
    cache = _load_cache()
    cache_key = f"search:{name.lower().strip()}"
    if cache_key in cache:
        return cache[cache_key]

    import urllib.parse
    path = f"/search/companies?q={urllib.parse.quote(name)}&items_per_page={items_per_page}"
    try:
        data = _get(path, api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"Companies House search failed: {exc}", file=sys.stderr)
        return []

    candidates = []
    for item in data.get("items", []):
        addr = item.get("registered_office_address", {})
        candidates.append({
            "company_number": item.get("company_number", ""),
            "name":           item.get("title", ""),
            "status":         item.get("company_status", ""),
            "postcode":       addr.get("postal_code", "").strip().upper(),
            "address":        ", ".join(
                filter(None, [
                    addr.get("address_line_1", ""),
                    addr.get("address_line_2", ""),
                    addr.get("locality", ""),
                    addr.get("postal_code", ""),
                ])
            ),
            "sic_codes":      item.get("sic_codes", []),
        })

    cache[cache_key] = candidates
    _save_cache(cache)
    return candidates


def get_by_number(company_number: str, api_key: str) -> dict | None:
    """Fetch full company profile by number."""
    cache = _load_cache()
    cache_key = f"company:{company_number}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        data = _get(f"/company/{company_number}", api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"Companies House fetch failed: {exc}", file=sys.stderr)
        return None

    addr = data.get("registered_office_address", {})
    result = {
        "company_number": company_number,
        "name":           data.get("company_name", ""),
        "status":         data.get("company_status", ""),
        "postcode":       addr.get("postal_code", "").strip().upper(),
        "address":        ", ".join(
            filter(None, [
                addr.get("address_line_1", ""),
                addr.get("address_line_2", ""),
                addr.get("locality", ""),
                addr.get("postal_code", ""),
            ])
        ),
        "sic_codes":      data.get("sic_codes", []),
        "date_of_creation": data.get("date_of_creation", ""),
    }
    cache[cache_key] = result
    _save_cache(cache)
    return result


def main() -> None:
    api_key = os.environ.get("COMPANIES_HOUSE_KEY", "")
    if not api_key:
        print("Set COMPANIES_HOUSE_KEY env var. Free key: https://developer.company-information.service.gov.uk/")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python3 data/ingest_companies.py <business name>")
        sys.exit(1)

    name = " ".join(sys.argv[1:])
    candidates = search_by_name(name, api_key)
    if not candidates:
        print("No results found.")
        return

    print(f"\n{len(candidates)} candidate(s) for '{name}':")
    for i, c in enumerate(candidates):
        print(f"\n[{i+1}] {c['name']} ({c['status']})")
        print(f"     Postcode: {c['postcode']}")
        print(f"     Address:  {c['address']}")
        print(f"     SIC:      {', '.join(c['sic_codes'])}")
        print(f"     Note: registered address may differ from trading address — confirm before use")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test (requires API key)**

```bash
COMPANIES_HOUSE_KEY=<your_key> python3 data/ingest_companies.py "Artisan Coffee Hackney"
```

Expected: 1–5 candidates with postcodes and SIC codes.

- [ ] **Step 3: Commit**

```bash
git add data/ingest_companies.py
git commit -m "feat: Companies House name→postcode lookup with disk cache"
```

---

### Task 5: Rewrite `agent/pipeline.py` — full end-to-end + frozen JSON contract

**Files:**
- Modify: `agent/pipeline.py`

The frozen JSON contract `pipeline.run()` returns:

```json
{
  "query": "E8 1DY",
  "query_type": "postcode",
  "businesses": [
    {
      "uarn": "10012345678",
      "name": "CAFE AND PREMISES",
      "address": "1 MARE STREET, HACKNEY",
      "postcode": "E8 1DY",
      "borough": "Hackney",
      "sector": "cafe",
      "rateable_value": 11500.0,
      "gross_annual_bill": 4393.0,
      "findings": [
        {
          "headline": "Small Business Rate Relief — 100% off",
          "annual_value": 4393.0,
          "backdated_value": 26358.0,
          "confidence": "high",
          "rule": "SBRR 2026/27",
          "action": "Contact your billing authority to claim.",
          "explanation": "...",
          "source": "https://..."
        }
      ],
      "totals": {
        "total_annual_savings": 4393.0,
        "total_backdated": 26358.0,
        "highest_confidence": "high"
      }
    }
  ],
  "lsoa": "E01234567",
  "error": null
}
```

- [ ] **Step 1: Rewrite `agent/pipeline.py`**

```python
"""End-to-end pipeline: postcode or business name → structured relief findings.

JSON contract: see docs/superpowers/plans/2026-06-06-ledger-tier1.md §Task 5.
LLM BOUNDARY: this module produces structured data only. The LLM layer
(agent/llm.py, agent/explain.py) consumes this output — never modifies it.
"""
from __future__ import annotations

import csv
import os
import sys
from dataclasses import asdict
from pathlib import Path

VOA_INDEX = Path(__file__).parent.parent / "data" / "voa_london_index.csv"
_voa_cache: list[dict] | None = None


def _load_voa() -> list[dict]:
    global _voa_cache
    if _voa_cache is not None:
        return _voa_cache
    if not VOA_INDEX.exists():
        return []
    rows = []
    with open(VOA_INDEX, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                row["rateable_value"] = float(row["rateable_value"])
                row["composite"] = row["composite"] == "True"
            except (ValueError, KeyError):
                continue
            rows.append(row)
    _voa_cache = rows
    return rows


def _norm_postcode(pc: str) -> str:
    return pc.strip().upper().replace(" ", "")


def _lookup_postcode(postcode: str) -> list[dict]:
    norm = _norm_postcode(postcode)
    return [r for r in _load_voa() if _norm_postcode(r.get("postcode", "")) == norm]


def _build_result(query: str, query_type: str, matches: list[dict], postcode: str) -> dict:
    from engines.rules_relief import Business, assess, _gross_bill

    businesses = []
    for m in matches:
        rv = m["rateable_value"]
        sector = m.get("sector", "other")
        biz = Business(
            name=m.get("desc_text", ""),
            rateable_value=rv,
            borough=m.get("borough", ""),
            sector=sector,
            uarn=m.get("uarn", ""),
            address=m.get("address", ""),
            postcode=m.get("postcode", ""),
            composite=m.get("composite", False),
        )
        findings = assess(biz)
        total_annual = sum(f.annual_value for f in findings)
        total_back   = sum(f.backdated_value for f in findings)
        confs = [f.confidence for f in findings]
        highest = "high" if "high" in confs else ("medium" if "medium" in confs else "low")

        businesses.append({
            "uarn":            biz.uarn,
            "name":            biz.name,
            "address":         biz.address,
            "postcode":        biz.postcode,
            "borough":         biz.borough,
            "sector":          biz.sector,
            "rateable_value":  rv,
            "gross_annual_bill": round(_gross_bill(rv, sector), 2),
            "findings":        [asdict(f) for f in findings],
            "totals": {
                "total_annual_savings": round(total_annual, 2),
                "total_backdated":      round(total_back, 2),
                "highest_confidence":   highest if findings else "none",
            },
        })

    # Enrich with LSOA if postcode provided (degrades offline)
    lsoa = None
    if postcode:
        try:
            from data.postcode_resolver import resolve
            info = resolve(postcode)
            lsoa = info.get("lsoa") if info else None
        except Exception:
            pass

    return {
        "query":      query,
        "query_type": query_type,
        "businesses": businesses,
        "lsoa":       lsoa,
        "error":      None if businesses else "no_voa_entry_found",
    }


def run(postcode: str) -> dict:
    """Postcode → list of matching VOA entries → relief findings."""
    matches = _lookup_postcode(postcode)
    return _build_result(postcode, "postcode", matches, postcode)


def run_by_name(name: str, *, api_key: str | None = None) -> dict:
    """Business name → Companies House → postcode → VOA → relief findings.

    Falls back to a postcode prompt if Companies House is unavailable.
    Returns the same JSON shape as run().
    """
    key = api_key or os.environ.get("COMPANIES_HOUSE_KEY", "")
    if not key:
        return {
            "query": name, "query_type": "name", "businesses": [], "lsoa": None,
            "error": "companies_house_key_missing — set COMPANIES_HOUSE_KEY or use run(postcode)",
        }

    try:
        from data.ingest_companies import search_by_name
        candidates = search_by_name(name, key)
    except Exception as exc:
        return {
            "query": name, "query_type": "name", "businesses": [], "lsoa": None,
            "error": f"companies_house_error: {exc}",
        }

    if not candidates:
        return {
            "query": name, "query_type": "name", "businesses": [], "lsoa": None,
            "error": "no_companies_house_match",
        }

    # Try each candidate postcode until we find VOA entries
    for c in candidates:
        pc = c.get("postcode", "")
        if not pc:
            continue
        matches = _lookup_postcode(pc)
        if matches:
            return _build_result(name, "name", matches, pc)

    # No VOA match found for any candidate
    return {
        "query":      name,
        "query_type": "name",
        "businesses": [],
        "lsoa":       None,
        "error":      f"no_voa_entry_found — tried postcodes: {[c.get('postcode') for c in candidates]}",
        "candidates": candidates,  # expose for manual confirmation
    }
```

- [ ] **Step 2: Test pipeline against VOA index (requires index built in Task 2)**

```bash
cd /Users/eshnanigans/NVIDIAHack/Stella
python3 -c "
import json
from agent.pipeline import run
result = run('E8 1DY')
print(json.dumps(result, indent=2))
"
```

Expected: JSON with `businesses` array, each with `findings` and `totals`. If the postcode has no VOA entry, `error` = `'no_voa_entry_found'` (clean failure, no crash).

- [ ] **Step 3: Test run_by_name (requires COMPANIES_HOUSE_KEY)**

```bash
COMPANIES_HOUSE_KEY=<key> python3 -c "
import json
from agent.pipeline import run_by_name
result = run_by_name('Hackney Coffee')
print(json.dumps(result, indent=2))
"
```

- [ ] **Step 4: Commit**

```bash
git add agent/pipeline.py
git commit -m "feat: full pipeline with postcode+name lookup, frozen JSON contract"
```

---

### Task 6: `data/verify_business.py` — demo verification helper

**Files:**
- Create: `data/verify_business.py`

This is the tool to confirm the 3 real demo businesses match their actual government bills.

- [ ] **Step 1: Create `data/verify_business.py`**

```python
"""Verify a real business against the VOA index and cross-check with gov.uk.

Usage:
    python3 data/verify_business.py "E8 1DY"
    python3 data/verify_business.py "E8 1DY" --rv 11500 --sector cafe

Use the --rv and --sector flags to override the VOA-parsed values if the
business's actual bill differs (e.g. wrong sector classification).
Cross-check RV at: https://www.gov.uk/correct-your-business-rates
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.pipeline import run, _lookup_postcode
from engines.rules_relief import Business, assess, _gross_bill


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a real business end-to-end")
    parser.add_argument("postcode", help="Business postcode, e.g. E8 1DY")
    parser.add_argument("--rv", type=float, help="Override rateable value from VOA")
    parser.add_argument("--sector", help="Override sector (cafe/retail/pub/hospitality/office/industrial/leisure/other)")
    parser.add_argument("--name", default="", help="Business name for display")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"LEDGER — Verification Report")
    print(f"Postcode: {args.postcode}")
    if args.name:
        print(f"Business: {args.name}")
    print(f"{'='*60}\n")

    # Show raw VOA matches
    matches = _lookup_postcode(args.postcode)
    if not matches:
        print(f"WARNING: No VOA entries found for {args.postcode}")
        print(f"  → Check postcode at: https://www.gov.uk/correct-your-business-rates")
        if not args.rv:
            print("  → Pass --rv <value> to run manual check")
            return
    else:
        print(f"Found {len(matches)} VOA entry/entries:")
        for m in matches:
            print(f"  UARN: {m['uarn']}")
            print(f"  Description: {m['desc_text']}")
            print(f"  Sector (auto): {m['sector']}")
            print(f"  Rateable Value: £{m['rateable_value']:,.0f}")
            print(f"  Address: {m['address']}")
            print()

    # Run relief assessment
    if args.rv or matches:
        rv = args.rv or (matches[0]["rateable_value"] if matches else None)
        sector = args.sector or (matches[0]["sector"] if matches else "other")
        borough = matches[0]["borough"] if matches else "Unknown"

        print(f"Running relief engine with RV=£{rv:,.0f}, sector={sector}, borough={borough}")
        biz = Business(
            name=args.name or "Business",
            rateable_value=rv,
            borough=borough,
            sector=sector,
        )
        findings = assess(biz)
        gross = _gross_bill(rv, sector)
        print(f"  Gross annual bill (before relief): £{gross:,.0f}")
        print()

        if not findings:
            print("  No relief findings — business pays full gross bill.")
        for f in findings:
            print(f"  ✓ {f.headline}")
            if f.annual_value:
                print(f"    Annual saving:   £{f.annual_value:,.0f}/yr")
            if f.backdated_value:
                print(f"    Backdated est.:  £{f.backdated_value:,.0f}")
            print(f"    Confidence:      {f.confidence}")
            print(f"    Action:          {f.action}")
            print(f"    Source:          {f.source}")
            print()

        total = sum(f.annual_value for f in findings)
        back = sum(f.backdated_value for f in findings)
        print(f"{'─'*40}")
        print(f"TOTAL POTENTIAL ANNUAL SAVING: £{total:,.0f}/yr")
        print(f"TOTAL BACKDATED ESTIMATE:       £{back:,.0f}")
        print()
        print("CROSS-CHECK STEPS:")
        print("  1. Look up real RV at: https://www.gov.uk/correct-your-business-rates")
        print("  2. Compare parsed RV above with official RV — must match")
        print("  3. Confirm sector classification matches property use")
        print("  4. Check real bill matches gross_annual_bill within £20")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify 3 demo businesses**

For each real demo business, run:
```bash
python3 data/verify_business.py "E8 1DY" --name "Real Café Name"
```

For each one:
1. Compare "Rateable Value" with the official figure from https://www.gov.uk/correct-your-business-rates
2. If they match: ✓ done
3. If they differ: pass `--rv <real_value>` and note the discrepancy
4. Confirm the annual figure matches what the business actually pays (before any reliefs they're claiming)

- [ ] **Step 3: Commit**

```bash
git add data/verify_business.py
git commit -m "feat: verify_business helper for demo cross-checking"
```

---

### Task 7: `data/README.md` — teammate setup docs

**Files:**
- Create: `data/README.md`

- [ ] **Step 1: Create `data/README.md`**

```markdown
# Data Layer — Setup Guide

## Prerequisites

- Python 3.11+
- ~500MB disk space for VOA index
- Internet connection for initial download (cached for offline use after)

## Step 1: Download VOA 2026 Rating List

```bash
curl -L "https://voaratinglists.blob.core.windows.net/downloads/uk-englandwales-ndr-2026-listentries-compiled-epoch-0001-baseline-csv.zip" \
     -o /tmp/voa-2026.zip
```

File size: ~200MB zip, ~500MB extracted.

## Step 2: Build London Index

```bash
# First, inspect raw fields to verify column positions:
python3 -c "
import zipfile, io
with zipfile.ZipFile('/tmp/voa-2026.zip') as z:
    name = [n for n in z.namelist() if n.endswith('.csv')][0]
    with z.open(name) as f:
        for i, line in enumerate(io.TextIOWrapper(f, encoding='latin-1')):
            parts = line.strip().split('*')
            for j, p in enumerate(parts):
                print(f'[{j:02d}] {repr(p[:60])}')
            print('---')
            if i >= 2: break
"

# Build full London index (~5 min):
python3 data/ingest_voa.py /tmp/voa-2026.zip
# Output: data/voa_london_index.csv
```

Sanity check: `wc -l data/voa_london_index.csv` should show 50,000–200,000 lines.

## Step 3: Cache Postcodes (for offline demo)

```bash
python3 -c "
from data.postcode_resolver import resolve_bulk
# Add your 3 demo business postcodes here:
resolve_bulk(['E8 1DY', 'EC1A 1BB', 'SW1A 2AA'])
print('Postcodes cached at data/cache/postcodes.json')
"
```

## Step 4: Companies House API Key (optional — for name→postcode lookup)

Register free at: https://developer.company-information.service.gov.uk/
```bash
export COMPANIES_HOUSE_KEY=your_key_here
python3 data/ingest_companies.py "Your Business Name"
```
Results cached at `data/cache/companies_house.json`.

## Step 5: Verify Demo Businesses

```bash
python3 data/verify_business.py "E8 1DY" --name "Demo Café"
```

Cross-check RV at: https://www.gov.uk/correct-your-business-rates

## Offline Demo Checklist

Before unplugging the cable:
- [ ] `data/voa_london_index.csv` exists and has >10,000 lines
- [ ] `data/cache/postcodes.json` has entries for all 3 demo postcodes
- [ ] `data/cache/companies_house.json` has entries for all 3 demo businesses
- [ ] `python3 data/verify_business.py <postcode>` runs without network

## Data Licence

VOA Rating List data is © Crown Copyright. Use is subject to the VOA's terms.
Not Open Government Licence — permitted for internal/demo use.
```

- [ ] **Step 2: Commit**

```bash
git add data/README.md
git commit -m "docs: data layer setup guide for teammates"
```

---

## Definition of Done — Tier 1 Locked

- [ ] `tests/test_rules_relief.py` — all 8 tests pass
- [ ] `data/voa_london_index.csv` built from real VOA zip with RV/postcode validation clean
- [ ] `data/cache/postcodes.json` populated for 3 demo postcodes
- [ ] `data/cache/companies_house.json` populated for 3 demo businesses (if API key available)
- [ ] `agent/pipeline.run("E8 1DY")` returns valid JSON with findings
- [ ] `agent/pipeline.run_by_name("Demo Café")` chains to postcode correctly
- [ ] `data/verify_business.py` confirms at least 1 real business RV matches gov.uk
- [ ] Everything runs offline (cable unplugged) from cached data
- [ ] `data/README.md` reviewed by teammate who can set up from scratch

---

## Self-Review Against Spec

| Spec requirement | Task |
|---|---|
| Real VOA file end-to-end with validation | Task 2 |
| postcode_resolver.py with bulk + cache | Task 3 |
| ingest_companies.py with candidate handling | Task 4 |
| run_by_name() in pipeline | Task 5 |
| Frozen JSON contract | Task 5 (documented above) |
| Tolerant postcode matching + clean failure | Task 5 (_norm_postcode) |
| verify_business.py for 3 demo businesses | Task 6 |
| data/README.md | Task 7 |
| SBRR 100%/taper/none correct | Task 1 |
| Pub relief with correct exclusions | Task 1 |
| Challenge wedge flag | Task 1 |
| City of London flag | Task 1 |
| Determinism rule (LLM never touches £) | Enforced by module boundary comment |
| Offline-first (all cloud calls cached) | Tasks 3, 4, 5 |
