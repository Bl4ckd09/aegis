"""VOA 2026 Rating List parser → London-only index CSV.

Field positions (0-indexed, asterisk-delimited, no header row).
VERIFY against raw file on first run — see Step 1 in the plan / README.

Usage:
    python3 data/ingest_voa.py /path/to/voa-2026.zip              # full London
    python3 data/ingest_voa.py /path/to/voa-2026.zip 50000        # first N rows (test)
    python3 data/ingest_voa.py /path/to/voa-2026.zip --inspect    # show field layout only
"""
from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from pathlib import Path

# ── Field indices (verified against real 2026 compiled epoch file) ────────────
# [00] = sequential row counter (NOT BA code)
# [01] = BA code e.g. "5360" (Hackney), "5990" (Westminster)
# [03] = UARN
# [04] = description code e.g. "CF", "SR", "CW"
# [05] = description text e.g. "CAFE AND PREMISES"
# [06] = SCAT code
# [09] = address line 1
# [10] = address line 2
# [11] = address line 3
# [14] = postcode e.g. "E8 1DY"
# [17] = rateable value (integer £)
IDX_BA_CODE   = 1    # Billing authority code (4 digits), e.g. "5360"
IDX_UARN      = 3    # Unique Address Reference Number
IDX_DESC_CODE = 4    # Primary description code, e.g. "CF", "SR", "PB"
IDX_DESC_TEXT = 5    # e.g. "CAFE AND PREMISES", "SHOP AND PREMISES"
IDX_SCAT      = 6    # SCAT code
IDX_ADDR1     = 9
IDX_ADDR2     = 10
IDX_ADDR3     = 11
IDX_POSTCODE  = 14   # UK postcode
IDX_RV        = 17   # Rateable value (integer £)

MIN_FIELDS = 18

# ── London Billing Authority codes (verified against real VOA 2026 file) ──────
# Codes verified by sampling postcodes per BA code from the actual data.
LONDON_BA: dict[str, str] = {
    "5030": "City of London",
    "5060": "Barking and Dagenham",
    "5090": "Barnet",
    "5120": "Bexley",
    "5150": "Brent",
    "5180": "Bromley",
    "5210": "Camden",
    "5240": "Croydon",
    "5270": "Ealing",
    "5300": "Enfield",
    "5330": "Greenwich",
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

# Description text → sector (first match wins)
# NOTE: longer/more specific strings must come before short ones to avoid false matches
# e.g. "PUBLIC CONVENIENCE" must not match "PUB" — check for "PUBLIC" exclusion via word boundary
SECTOR_RULES: list[tuple[str, str]] = [
    ("PUBLIC CONVENIENCE", "other"),   # must be before "PUB"
    ("PUBLIC HOUSE",       "pub"),
    ("PUB AND",            "pub"),
    ("PUB ",               "pub"),
    ("INN ",               "pub"),
    ("TAVERN",        "pub"),
    ("WINE BAR",      "pub"),
    ("CAFE",          "cafe"),
    ("COFFEE",        "cafe"),
    ("RESTAURANT",    "cafe"),
    ("RETAIL",        "retail"),
    ("SHOP",          "retail"),
    ("STORE",         "retail"),
    ("MARKET",        "retail"),
    ("HOTEL",         "hospitality"),
    ("GUEST HOUSE",   "hospitality"),
    ("BED AND BREAK", "hospitality"),
    ("LEISURE",       "leisure"),
    ("GYM",           "leisure"),
    ("SPORTS",        "leisure"),
    ("THEATRE",       "leisure"),
    ("CINEMA",        "leisure"),
    ("OFFICE",        "office"),
    ("FACTORY",       "industrial"),
    ("WAREHOUSE",     "industrial"),
    ("INDUSTRIAL",    "industrial"),
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


def _inspect(zip_path: str) -> None:
    """Print field layout of first 3 records to stderr for verification."""
    with zipfile.ZipFile(zip_path) as z:
        csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        target = csv_names[0]
        print(f"File in zip: {target}", file=sys.stderr)
        with z.open(target) as raw:
            for i, line in enumerate(io.TextIOWrapper(raw, encoding="latin-1")):
                parts = line.strip().split("*")
                print(f"\n--- Record {i} ({len(parts)} fields) ---")
                for j, p in enumerate(parts):
                    marker = ""
                    if j == IDX_BA_CODE:   marker = " ← BA_CODE (London: 5060–5990)"
                    if j == IDX_UARN:      marker = " ← UARN"
                    if j == IDX_DESC_TEXT: marker = " ← DESC_TEXT"
                    if j == IDX_SCAT:      marker = " ← SCAT"
                    if j == IDX_RV:        marker = " ← RATEABLE_VALUE"
                    if j == IDX_POSTCODE:  marker = " ← POSTCODE"
                    print(f"  [{j:02d}] {repr(p[:70])}{marker}")
                if i >= 2:
                    break


def _validate_sample(rows: list[dict]) -> None:
    if not rows:
        print("WARNING: zero London records — check BA codes and IDX_BA_CODE", file=sys.stderr)
        return

    rvs = [r["rateable_value"] for r in rows]
    bad_rv = sum(1 for v in rvs if not (500 <= v <= 10_000_000))
    if bad_rv / max(len(rvs), 1) > 0.05:
        print(
            f"WARNING: {bad_rv}/{len(rvs)} RVs outside £500–£10M. "
            "IDX_RV may be wrong — re-run with --inspect.",
            file=sys.stderr,
        )

    pcs = [r["postcode"] for r in rows if r["postcode"]]
    if pcs:
        bad_pc = sum(1 for p in pcs if not _POSTCODE_RE.match(p))
        if bad_pc / len(pcs) > 0.10:
            print(
                f"WARNING: {bad_pc}/{len(pcs)} postcodes look malformed. IDX_POSTCODE may be wrong.",
                file=sys.stderr,
            )

    sectors: dict[str, int] = {}
    for r in rows:
        sectors[r["sector"]] = sectors.get(r["sector"], 0) + 1
    print(f"Sector distribution: {sectors}", file=sys.stderr)

    rv_vals = sorted(rvs)
    print(
        f"RV range: £{rv_vals[0]:,.0f}–£{rv_vals[-1]:,.0f}  "
        f"median: £{rv_vals[len(rv_vals)//2]:,.0f}",
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
                    "composite":      False,
                    "address":        address,
                    "postcode":       postcode,
                    "scat":           fields[IDX_SCAT].strip(),
                })

    print(
        f"Parsed {total:,} rows → {len(rows):,} London entries "
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
        print("Usage: python3 data/ingest_voa.py <voa-2026.zip> [max_rows | --inspect]")
        sys.exit(1)
    zip_path = sys.argv[1]
    if "--inspect" in sys.argv:
        _inspect(zip_path)
        return
    max_rows = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None
    rows = parse(zip_path, max_rows)
    out = Path(__file__).parent / "voa_london_index.csv"
    write_index(rows, str(out))


if __name__ == "__main__":
    main()
