"""SMB exposure — a live disruption early-warning for a London small business.

The cascade BFS from the business location gives its *accessibility catchment*
(the roads, bus stops, routes and resident population that reach it). We then
overlay live signals on that catchment — TfL **tube/rail line status**, **bus
route status**, nearby **road disruptions**, and **weather** — and turn them into
plain, attributed warnings an owner can act on. No black-box footfall %: every
penalty is a named, real signal.
"""
from __future__ import annotations

import asyncio
import math

from . import config

# Rail-ish modes whose live status matters to a high-street catchment.
RAIL_MODES = "tube,dlr,overground,elizabeth-line"
TFL = "https://api.tfl.gov.uk"


def _key(sep: str) -> str:
    return f"{sep}app_key={config.TFL_APP_KEY}" if config.TFL_APP_KEY else ""


def _haversine_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


async def _tube(client, lat: float, lon: float) -> dict:
    """Rail/tube lines serving stations near the business + their live status."""
    try:
        st = (await client.get(
            f"{TFL}/StopPoint?stopTypes=NaptanMetroStation&lat={lat}&lon={lon}"
            f"&radius=1500{_key('&')}")).json().get("stopPoints", [])
    except Exception:
        st = []
    area_lines = {ln.get("id"): ln.get("name") for s in st for ln in (s.get("lines") or [])}
    if not area_lines:
        return {"lines": [], "disrupted": []}
    try:
        status = (await client.get(f"{TFL}/Line/Mode/{RAIL_MODES}/Status{_key('?')}")).json()
    except Exception:
        status = []
    smap = {l.get("id"): l for l in status}
    lines, disrupted = [], []
    for lid, lname in area_lines.items():
        l = smap.get(lid)
        if not l:
            continue
        ls = (l.get("lineStatuses") or [{}])[0]
        item = {"id": lid, "name": lname or l.get("name"),
                "status": ls.get("statusSeverityDescription", "Unknown"),
                "severity": ls.get("statusSeverity", 10),
                "reason": ls.get("reason")}
        lines.append(item)
        if item["severity"] < 10:   # 10 = Good Service
            disrupted.append(item)
    return {"lines": lines, "disrupted": disrupted}


async def _bus(client, routes: list[str]) -> dict:
    """Live status for the bus routes that serve the catchment."""
    routes = [r for r in routes if r][:25]
    if not routes:
        return {"disrupted": [], "checked": 0}
    try:
        status = (await client.get(f"{TFL}/Line/{','.join(routes)}/Status{_key('?')}")).json()
    except Exception:
        return {"disrupted": [], "checked": len(routes)}
    disrupted = []
    for l in status if isinstance(status, list) else []:
        ls = (l.get("lineStatuses") or [{}])[0]
        if ls.get("statusSeverity", 10) < 10:
            disrupted.append({"id": l.get("id"), "name": l.get("name"),
                              "status": ls.get("statusSeverityDescription"), "reason": ls.get("reason")})
    return {"disrupted": disrupted, "checked": len(routes)}


async def _weather(client, lat: float, lon: float) -> dict:
    """Current conditions + today's rain outlook (Open-Meteo, free, no key)."""
    try:
        d = (await client.get(
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,precipitation,weather_code"
            "&hourly=precipitation_probability&forecast_days=1")).json()
        cur = d.get("current", {}) or {}
        probs = (d.get("hourly", {}) or {}).get("precipitation_probability") or [0]
        return {"temp": cur.get("temperature_2m"), "precip_now": cur.get("precipitation", 0) or 0,
                "rain_prob_today": max(probs) if probs else 0}
    except Exception:
        return {}


def _roads(disruptions, lat: float, lon: float, radius_m: float = 2000.0) -> list[dict]:
    """Official road disruptions within the catchment (nearest first)."""
    out = []
    for d in disruptions or []:
        if d.lat and d.lon:
            dist = _haversine_m(lat, lon, d.lat, d.lon)
            if dist <= radius_m:
                out.append({"severity": d.severity, "category": d.category,
                            "comments": (d.comments or "")[:140], "dist_m": int(dist),
                            "lat": d.lat, "lon": d.lon})
    out.sort(key=lambda x: x["dist_m"])
    return out[:8]


def _cascade_effect(lat: float, lon: float, pts: list[dict], roads: list[dict]) -> dict | None:
    """The nearby disruption that gates the largest share of the catchment, and that share.
    First-order: a catchment node is 'beyond' a disruption if it's farther from the business
    than the disruption is, and nearer the disruption than the business (i.e. in the cone
    past it). We pick the disruption with the biggest such share — the real bottleneck."""
    if not roads or not pts:
        return None
    best = None
    for road in roads:
        dd = _haversine_m(lat, lon, road["lat"], road["lon"])  # business → disruption
        beyond = sum(
            1 for p in pts
            if _haversine_m(lat, lon, p["lat"], p["lon"]) > dd
            and _haversine_m(road["lat"], road["lon"], p["lat"], p["lon"])
            < _haversine_m(lat, lon, p["lat"], p["lon"]))
        pct = round(100 * beyond / len(pts))
        if best is None or pct > best["pct"]:
            best = {"category": road["category"], "dist_m": road["dist_m"], "pct": pct}
    return best if best and best["pct"] >= 3 else None


async def exposure(client, lat: float, lon: float, catchment: dict, disruptions) -> dict:
    """Combine the catchment with live signals into an access-health + warnings view."""
    tube, bus, weather = await asyncio.gather(
        _tube(client, lat, lon),
        _bus(client, catchment.get("routes", [])),
        _weather(client, lat, lon),
    )
    roads = _roads(disruptions, lat, lon)
    cascade_fx = _cascade_effect(lat, lon, catchment.get("ripple_points", []), roads)

    reasons, score = [], 100
    for t in tube["disrupted"]:
        reasons.append({"icon": "🚇", "text": f"{t['name']} line — {t['status']}", "detail": t.get("reason")})
        score -= 12
    for b in bus["disrupted"]:
        reasons.append({"icon": "🚌", "text": f"Bus {b['name']} — {b['status']}", "detail": b.get("reason")})
        score -= 6
    for r in roads:
        reasons.append({"icon": "🚧", "text": f"{r['category']} disruption {r['dist_m']}m away",
                        "detail": r["comments"]})
        score -= 6
    rain = weather.get("rain_prob_today", 0) or 0
    if rain >= 60 or (weather.get("precip_now", 0) or 0) > 0:
        reasons.append({"icon": "🌧", "text": f"Rain likely today ({rain}%)",
                        "detail": "High streets typically see lower footfall in wet weather."})
        score -= 10
    if cascade_fx:  # headline cascade insight — the thing an owner can't see themselves
        reasons.insert(0, {"icon": "🌊",
                           "text": f"~{cascade_fx['pct']}% of your catchment is reached past the "
                                   f"{cascade_fx['category']} disruption {cascade_fx['dist_m']}m away",
                           "detail": "Customers, staff and deliveries from that side face a longer or blocked route."})
    score = max(0, min(100, score))
    if not reasons:
        reasons.append({"icon": "✅", "text": "No live disruptions affecting your catchment", "detail": None})

    return {
        "location": {"lat": lat, "lon": lon},
        "health": score,
        "catchment": {"population": catchment.get("affected_population"),
                      "lsoas": catchment.get("affected_lsoas"),
                      "stops": catchment.get("affected_stops"),
                      "routes": catchment.get("affected_routes"),
                      "nodes": catchment.get("affected_nodes")},
        "tube": tube, "bus": bus, "weather": weather, "roads": roads,
        "cascade_effect": cascade_fx,
        "reasons": reasons,
        "engine": catchment.get("engine"),
        "ripple_points": catchment.get("ripple_points", []),
    }
