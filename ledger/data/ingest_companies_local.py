"""Build a local Companies House index from the bulk CSV download.

Source: http://download.companieshouse.gov.uk/en_output.html
File:   BasicCompanyData-YYYYMMDD-1of5.zip  (5 parts, ~700 MB total)

Usage:
    # Point at one or more CSV/ZIP files
    python3 data/ingest_companies_local.py BasicCompanyData-*.zip

    # Or a single extracted CSV
    python3 data/ingest_companies_local.py BasicCompanyData-2026-06-01.csv

Output: data/ch_index.db  (SQLite — queried by postcode in <5ms)

Runtime: ~3 min for all 5M companies on a laptop. Faster on DGX Spark.
"""
from __future__ import annotations

import csv
import io
import sqlite3
import sys
import zipfile
from pathlib import Path

DB_PATH = Path(__file__).parent / "ch_index.db"

# Column names in the CH BasicCompanyData CSV (header row present)
COL_NAME    = "CompanyName"
COL_NUMBER  = "CompanyNumber"
COL_POSTCODE = "RegAddress.PostCode"
COL_STATUS  = "CompanyStatus"
COL_CREATED = "IncorporationDate"
COL_SIC1    = "SICCode.SicText_1"
COL_SIC2    = "SICCode.SicText_2"
COL_ADDR1   = "RegAddress.AddressLine1"
COL_ADDR2   = "RegAddress.AddressLine2"
COL_TOWN    = "RegAddress.PostTown"


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            company_number   TEXT PRIMARY KEY,
            name             TEXT NOT NULL,
            postcode         TEXT NOT NULL,
            status           TEXT,
            date_of_creation TEXT,
            sic1             TEXT,
            sic2             TEXT,
            address          TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_postcode ON companies(postcode)")
    # FTS5 virtual table for fast offline name search
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS companies_fts
        USING fts5(name, company_number UNINDEXED, content='companies', content_rowid='rowid')
    """)
    conn.commit()


def _rebuild_fts(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO companies_fts(companies_fts) VALUES('rebuild')")
    conn.commit()


def _norm_postcode(raw: str) -> str:
    return raw.strip().upper()


def _parse_csv_stream(stream: io.TextIOWrapper, conn: sqlite3.Connection) -> int:
    reader = csv.DictReader(stream)
    # CH bulk CSV has leading spaces on some column names — strip them all
    if reader.fieldnames:
        reader.fieldnames = [f.strip() for f in reader.fieldnames]
    batch: list[tuple] = []
    count = 0
    for row in reader:
        pc = _norm_postcode(row.get(COL_POSTCODE, ""))
        if not pc:
            continue
        addr = ", ".join(filter(None, [
            row.get(COL_ADDR1, "").strip(),
            row.get(COL_ADDR2, "").strip(),
            row.get(COL_TOWN, "").strip(),
        ]))
        batch.append((
            row.get(COL_NUMBER, "").strip(),
            row.get(COL_NAME, "").strip(),
            pc,
            row.get(COL_STATUS, "").strip().lower(),
            row.get(COL_CREATED, "").strip(),
            row.get(COL_SIC1, "").strip(),
            row.get(COL_SIC2, "").strip(),
            addr,
        ))
        count += 1
        if len(batch) >= 50_000:
            conn.executemany(
                "INSERT OR REPLACE INTO companies VALUES (?,?,?,?,?,?,?,?)", batch
            )
            conn.commit()
            batch = []
            print(f"  {count:,} rows…", end="\r", flush=True)
    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO companies VALUES (?,?,?,?,?,?,?,?)", batch
        )
        conn.commit()
    return count


def ingest(paths: list[str]) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    _create_schema(conn)
    total = 0
    for path in paths:
        p = Path(path)
        print(f"Processing {p.name} …")
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]
                if not csv_names:
                    print(f"  No CSV found in {p.name} — skipping")
                    continue
                for csv_name in csv_names:
                    with z.open(csv_name) as raw:
                        n = _parse_csv_stream(
                            io.TextIOWrapper(raw, encoding="utf-8-sig"), conn
                        )
                        total += n
                        print(f"  {csv_name}: {n:,} rows")
        else:
            with open(p, encoding="utf-8-sig") as f:
                n = _parse_csv_stream(f, conn)
                total += n
                print(f"  {n:,} rows")
    print("\nBuilding FTS index for name search…", end=" ", flush=True)
    _rebuild_fts(conn)
    print("done.")
    conn.close()
    db_mb = DB_PATH.stat().st_size / 1_048_576
    print(f"Done. {total:,} companies → {DB_PATH} ({db_mb:.0f} MB)")


def search_by_name_local(name: str, *, limit: int = 10) -> list[dict]:
    """FTS5 name search against local bulk index. Returns [] if DB not built yet."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    # FTS5 match — wrap each token with * for prefix search
    tokens = [t for t in name.strip().split() if len(t) > 1]
    fts_query = " ".join(f'"{t}"*' for t in tokens) if tokens else name
    try:
        rows = conn.execute(
            """SELECT c.* FROM companies c
               JOIN companies_fts fts ON c.rowid = fts.rowid
               WHERE companies_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (fts_query, limit)
        ).fetchall()
    except Exception:
        # FTS table may not exist in older DBs — fall back to LIKE
        rows = conn.execute(
            "SELECT * FROM companies WHERE name LIKE ? LIMIT ?",
            (f"%{name}%", limit)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_by_postcode(postcode: str, *, active_only: bool = False) -> list[dict]:
    """Query local index. Falls back gracefully if DB doesn't exist."""
    if not DB_PATH.exists():
        return []
    pc = _norm_postcode(postcode)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM companies WHERE postcode = ?"
    if active_only:
        q += " AND status = 'active'"
    rows = conn.execute(q, (pc,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 data/ingest_companies_local.py <BasicCompanyData*.zip> [...]")
        print("Download: http://download.companieshouse.gov.uk/en_output.html")
        sys.exit(1)
    ingest(sys.argv[1:])


if __name__ == "__main__":
    main()
