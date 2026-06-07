# Data Layer — Setup Guide

## Prerequisites
- Python 3.11+
- ~500MB disk space
- Internet for initial download (offline after)

## Step 1: Download VOA 2026 Rating List (~200MB)

```bash
curl -L "https://voaratinglists.blob.core.windows.net/downloads/uk-englandwales-ndr-2026-listentries-compiled-epoch-0001-baseline-csv.zip" \
     -o /tmp/voa-2026.zip
```

## Step 2: Verify field positions (REQUIRED — do this before full run)

```bash
python3 data/ingest_voa.py /tmp/voa-2026.zip --inspect
```

Check that `[00]` is a 4-digit BA code (e.g. "5360" for Hackney), `IDX_RV` shows a plausible £ integer, and `IDX_POSTCODE` shows a UK postcode. If anything looks off, edit the `IDX_*` constants at the top of `data/ingest_voa.py`.

## Step 3: Build London index

```bash
# Quick test (50k rows, ~10s):
python3 data/ingest_voa.py /tmp/voa-2026.zip 50000

# Full run (~5 min):
python3 data/ingest_voa.py /tmp/voa-2026.zip
# → data/voa_london_index.csv

wc -l data/voa_london_index.csv   # expect 50k–200k lines
```

Warning lines mean field indices are wrong — fix IDX_* and re-run.

## Step 4: Cache postcodes (for offline demo)

```bash
python3 -c "
from data.postcode_resolver import resolve_bulk
resolve_bulk(['E8 1DY', 'EC1A 1BB', 'SW1A 2AA'])  # add your 3 demo postcodes
print('Cached at data/cache/postcodes.json')
"
```

## Step 5: Companies House (optional — name→postcode lookup)

Register free at: https://developer.company-information.service.gov.uk/

```bash
export COMPANIES_HOUSE_KEY=your_key_here
python3 data/ingest_companies.py "Your Business Name"
# Cached at data/cache/companies_house.json
```

## Step 6: Verify demo businesses

```bash
python3 data/verify_business.py "E8 1DY" --name "Demo Café"
```

Cross-check RV at: https://www.gov.uk/correct-your-business-rates

## Offline demo checklist

Before unplugging the cable:
- [ ] `data/voa_london_index.csv` exists, >10,000 lines
- [ ] `data/cache/postcodes.json` has all 3 demo postcodes
- [ ] `data/cache/companies_house.json` has all 3 demo businesses (if using name lookup)
- [ ] `python3 data/verify_business.py <postcode>` runs clean without network

## Data licence

VOA Rating List data © Crown Copyright. Permitted for internal/demo use under VOA terms. Not Open Government Licence — do not relicense or claim it's open.
