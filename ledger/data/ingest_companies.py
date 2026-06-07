"""Companies House API: business name → candidates with postcode + SIC.

Auth: free API key (HTTP Basic auth, key as username, empty password).
Register: https://developer.company-information.service.gov.uk/
Cache: data/cache/companies_house.json

Usage:
    COMPANIES_HOUSE_KEY=abc123 python3 data/ingest_companies.py "Hackney Coffee"

Note: registered address ≠ trading address. Returns candidates; confirm match.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
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


def _format_address(addr: dict) -> str:
    return ", ".join(filter(None, [
        addr.get("address_line_1", ""),
        addr.get("address_line_2", ""),
        addr.get("locality", ""),
        addr.get("postal_code", ""),
    ]))


def search_by_name(name: str, api_key: str, *, items_per_page: int = 5) -> list[dict]:
    """Return top candidates. Each has postcode, SIC codes, address."""
    cache = _load_cache()
    cache_key = f"search:{name.lower().strip()}"
    if cache_key in cache:
        return cache[cache_key]

    path = f"/search/companies?q={urllib.parse.quote(name)}&items_per_page={items_per_page}"
    try:
        data = _get(path, api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        print(f"Companies House search failed: {exc}", file=sys.stderr)
        return []

    candidates = []
    for item in data.get("items", []):
        addr = item.get("registered_office_address", {})
        postcode = addr.get("postal_code", "").strip().upper()
        company_number = item.get("company_number", "")

        # Search results sometimes omit address — fetch full profile if postcode missing
        if not postcode and company_number:
            profile = get_by_number(company_number, api_key)
            if profile:
                postcode = profile.get("postcode", "")
                addr = {"postal_code": postcode, "address_line_1": profile.get("address", "")}

        candidates.append({
            "company_number": company_number,
            "name":           item.get("title", ""),
            "status":         item.get("company_status", ""),
            "postcode":       postcode,
            "address":        _format_address(addr),
            "sic_codes":      item.get("sic_codes", []),
        })

    cache[cache_key] = candidates
    _save_cache(cache)
    return candidates


def get_by_number(company_number: str, api_key: str) -> dict | None:
    """Fetch full company profile by Companies House number."""
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
        "company_number":   company_number,
        "name":             data.get("company_name", ""),
        "status":           data.get("company_status", ""),
        "postcode":         addr.get("postal_code", "").strip().upper(),
        "address":          _format_address(addr),
        "sic_codes":        data.get("sic_codes", []),
        "date_of_creation": data.get("date_of_creation", ""),
    }
    cache[cache_key] = result
    _save_cache(cache)
    return result


def main() -> None:
    api_key = os.environ.get("COMPANIES_HOUSE_KEY", "")
    if not api_key:
        print("Set COMPANIES_HOUSE_KEY. Free key: https://developer.company-information.service.gov.uk/")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python3 data/ingest_companies.py <business name>")
        sys.exit(1)

    name = " ".join(sys.argv[1:])
    candidates = search_by_name(name, api_key)
    if not candidates:
        print("No results.")
        return

    print(f"\n{len(candidates)} candidate(s) for '{name}':")
    for i, c in enumerate(candidates):
        print(f"\n[{i+1}] {c['name']} ({c['status']})")
        print(f"     Postcode : {c['postcode']}")
        print(f"     Address  : {c['address']}")
        print(f"     SIC      : {', '.join(c['sic_codes'])}")
        print(f"     NOTE: registered address may differ from trading address — confirm before use")


if __name__ == "__main__":
    main()
