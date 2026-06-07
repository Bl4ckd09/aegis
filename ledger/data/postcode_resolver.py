"""Postcode → LSOA + lat/lng via postcodes.io. Disk-cached for offline demo.

Cache: data/cache/postcodes.json — populate before unplugging the cable.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
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
        "postcode":  result.get("postcode", ""),
        "lsoa":      result.get("lsoa", ""),
        "latitude":  result.get("latitude"),
        "longitude": result.get("longitude"),
        "borough":   result.get("admin_district", ""),
        "ward":      result.get("admin_ward", ""),
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
