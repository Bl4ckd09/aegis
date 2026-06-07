"""TfL open-data client: JamCam list, camera frames, road disruptions.

Supports an offline REPLAY mode (config.REPLAY_MODE): cameras, frames and
disruptions are served from a saved snapshot on disk (data/snapshots/) so the
demo runs with zero network — insurance against a flaky venue connection.
Capture a snapshot while live with `python -m scripts.snapshot`.
"""
from __future__ import annotations

import json
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
    """Monitored cameras — from the saved snapshot in replay mode, else live TfL."""
    if config.REPLAY_MODE:
        data = json.loads((config.SNAPSHOT_DIR / "cameras.json").read_text())
        return [
            Camera(id=c["id"], name=c.get("name", c["id"]), lat=c["lat"], lon=c["lon"],
                   view=c.get("view"), available=True, image_url=None)
            for c in data
        ]
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
    """Fetch a single camera JPEG by URL. Returns None on any failure."""
    try:
        r = await client.get(url, timeout=30)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


async def get_frame(client: httpx.AsyncClient, cam: Camera) -> Optional[bytes]:
    """A camera's current JPEG — from the snapshot in replay mode, else live."""
    if config.REPLAY_MODE:
        try:
            return (config.SNAPSHOT_DIR / "frames" / f"{cam.id}.jpg").read_bytes()
        except OSError:
            return None
    if not cam.image_url:
        return None
    return await fetch_image(client, cam.image_url)


async def fetch_disruptions(client: httpx.AsyncClient) -> list[Disruption]:
    """Official road disruptions — from the saved snapshot in replay mode, else live."""
    if config.REPLAY_MODE:
        try:
            data = json.loads((config.SNAPSHOT_DIR / "disruptions.json").read_text())
            return [Disruption(**d) for d in data]
        except OSError:
            return []
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
