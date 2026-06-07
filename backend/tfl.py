"""TfL open-data client: JamCam list, camera frames, road disruptions."""
from __future__ import annotations

from typing import Optional

import httpx

from . import config
from .models import Camera, Disruption


def _params() -> dict:
    return {"app_key": config.TFL_APP_KEY} if config.TFL_APP_KEY else {}


def _props(cam: dict) -> dict:
    """Flatten a JamCam object's additionalProperties[] into a dict."""
    out = {}
    for p in cam.get("additionalProperties", []) or []:
        key = p.get("key")
        if key is not None:
            out[key] = p.get("value")
    return out


async def fetch_cameras(client: httpx.AsyncClient) -> list[Camera]:
    """GET the JamCam list and normalize into Camera objects."""
    r = await client.get(config.JAMCAM_LIST_URL, params=_params(), timeout=30)
    r.raise_for_status()
    cameras: list[Camera] = []
    for c in r.json():
        props = _props(c)
        lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue
        cameras.append(
            Camera(
                id=c.get("id", ""),
                name=c.get("commonName", c.get("id", "")),
                lat=float(lat),
                lon=float(lon),
                image_url=props.get("imageUrl"),
                view=props.get("view"),
                available=str(props.get("available", "true")).lower() == "true",
            )
        )
    return cameras


async def fetch_image(client: httpx.AsyncClient, url: str) -> Optional[bytes]:
    """Fetch a single camera JPEG. Returns None on any failure."""
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


async def fetch_disruptions(client: httpx.AsyncClient) -> list[Disruption]:
    """GET the official road-disruption feed and normalize."""
    r = await client.get(config.DISRUPTION_URL, params=_params(), timeout=30)
    r.raise_for_status()
    out: list[Disruption] = []
    for d in r.json():
        coords = (d.get("geography") or {}).get("coordinates") or [None, None]
        lon, lat = (coords + [None, None])[:2]
        out.append(
            Disruption(
                id=d.get("id", ""),
                severity=d.get("severity"),
                category=d.get("category"),
                sub_category=d.get("subCategory"),
                status=d.get("status"),
                lat=float(lat) if lat is not None else None,
                lon=float(lon) if lon is not None else None,
                comments=d.get("comments"),
                start_at=d.get("startDateTime"),
                updated_at=d.get("currentUpdateDateTime") or d.get("lastModifiedTime"),
            )
        )
    return out
