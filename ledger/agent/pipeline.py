"""End-to-end pipeline: postcode or business name → structured relief findings.

JSON contract (frozen — frontend/agent layer builds against this shape):
{
  "query": str,
  "query_type": "postcode" | "name",
  "businesses": [
    {
      "uarn": str,
      "name": str,
      "address": str,
      "postcode": str,
      "borough": str,
      "sector": str,
      "rateable_value": float,
      "gross_annual_bill": float,
      "findings": [
        {
          "headline": str,
          "annual_value": float,
          "backdated_value": float,
          "confidence": "high"|"medium"|"low",
          "rule": str,
          "action": str,
          "explanation": str,
          "source": str
        }
      ],
      "totals": {
        "total_annual_savings": float,
        "total_backdated": float,
        "highest_confidence": "high"|"medium"|"low"|"none"
      }
    }
  ],
  "lsoa": str | null,
  "error": str | null
}

LLM BOUNDARY: this module outputs structured data only. The LLM (agent/llm.py)
consumes this JSON — it never computes or modifies monetary values.
"""
from __future__ import annotations

import csv
import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional

VOA_INDEX = Path(__file__).parent.parent / "data" / "voa_london_index.csv"
_voa_cache: Optional[list[dict]] = None


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
        highest = "high" if "high" in confs else ("medium" if "medium" in confs else ("low" if confs else "none"))

        businesses.append({
            "uarn":             biz.uarn,
            "name":             biz.name,
            "address":          biz.address,
            "postcode":         biz.postcode,
            "borough":          biz.borough,
            "sector":           biz.sector,
            "rateable_value":   rv,
            "gross_annual_bill": round(_gross_bill(rv, sector), 2),
            "findings":         [asdict(f) for f in findings],
            "totals": {
                "total_annual_savings": round(total_annual, 2),
                "total_backdated":      round(total_back, 2),
                "highest_confidence":   highest,
            },
        })

    # Enrich with LSOA — degrades gracefully offline
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
    """Postcode → VOA entries → relief findings. Clean failure if postcode not found."""
    matches = _lookup_postcode(postcode)
    return _build_result(postcode, "postcode", matches, postcode)


def run_by_name(name: str, *, api_key: str | None = None) -> dict:
    """Business name → Companies House → postcode → VOA → relief findings.

    Falls back cleanly if Companies House key missing or no match found.
    Always returns the same JSON shape as run().
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

    # Try each candidate postcode until VOA entries found
    for c in candidates:
        pc = c.get("postcode", "")
        if not pc:
            continue
        matches = _lookup_postcode(pc)
        if matches:
            return _build_result(name, "name", matches, pc)

    return {
        "query":      name,
        "query_type": "name",
        "businesses": [],
        "lsoa":       None,
        "error":      "no_voa_entry_found",
        "candidates": candidates,  # expose for manual postcode confirmation
    }
