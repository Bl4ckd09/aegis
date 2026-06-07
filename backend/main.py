"""Aegis backend — FastAPI app.

Serves the control-room HUD (static frontend) and the JSON API the HUD polls:
  GET /api/cameras            normalized camera registry
  GET /api/frame/{id}         live JPEG proxy for one camera (supports replay later)
  GET /api/health            service + model + scan status
The detector loop, incident store, disruptions matcher and briefing are wired in
later phases and hang off the shared AppState created in the lifespan below.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, geo, smb, tfl
from .briefing import BriefingGenerator
from .detector import Detector
from .disruptions import DisruptionPoller
from .models import Camera
from .store import IncidentStore

try:  # Ripple's graph stack (osmnx/networkx) may be absent on some boxes — degrade gracefully
    from . import ripple
except Exception as _e:  # pragma: no cover
    ripple = None
    print(f"[startup] Ripple engine unavailable: {_e}")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class AppState:
    def __init__(self) -> None:
        self.client: httpx.AsyncClient | None = None
        self.cameras: list[Camera] = []
        self.camera_by_id: dict[str, Camera] = {}
        self.store = IncidentStore()
        self.detector: Detector | None = None
        self.disruptions: DisruptionPoller | None = None
        self.briefing: BriefingGenerator | None = None

    @property
    def available(self) -> list[Camera]:
        """The camera universe shown on the map (all available, optionally capped by
        CAMERA_LIMIT). The detector classifies a rolling window over this set.
        In replay mode frames come from the snapshot by id, so image_url isn't required."""
        avail = [c for c in self.cameras
                 if c.available and (config.REPLAY_MODE or c.image_url)]
        return avail[: config.CAMERA_LIMIT] if config.CAMERA_LIMIT else avail


state = AppState()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    state.client = httpx.AsyncClient(headers={"User-Agent": "Aegis/1.0 (hackathon)"})
    try:
        state.cameras = await tfl.fetch_cameras(state.client)
    except Exception as e:  # don't crash startup if the network hiccups
        print(f"[startup] camera fetch failed: {e}")
        state.cameras = []
    state.camera_by_id = {c.id: c for c in state.cameras}
    print(f"[startup] cameras={len(state.cameras)} on_map={len(state.available)} "
          f"batch={config.SWEEP_BATCH}/{config.BATCH_INTERVAL_SECONDS}s")
    if config.REPLAY_MODE:
        try:
            seeded = json.loads((config.SNAPSHOT_DIR / "incidents.json").read_text())
            state.store.seed(seeded)
            print(f"[startup] REPLAY: seeded {len(seeded)} incidents from snapshot")
        except OSError as e:
            print(f"[startup] REPLAY: no incidents snapshot ({e})")
    state.detector = Detector(state, state.store)
    state.detector.start()
    state.disruptions = DisruptionPoller(state, state.store)
    state.disruptions.start()
    state.briefing = BriefingGenerator(state, state.store)
    state.briefing.start()
    if config.RIPPLE_URL:  # cascades proxied to a remote GPU engine (e.g. Modal cuGraph)
        print(f"[startup] ripple cascade proxied to {config.RIPPLE_URL}")
    elif ripple is not None:  # load the local road graph + stops in the background (cached → fast)
        asyncio.create_task(asyncio.to_thread(ripple.engine.load))
        print("[startup] ripple cascade engine loading in background...")
    try:
        yield
    finally:
        if state.detector:
            await state.detector.stop()
        if state.disruptions:
            await state.disruptions.stop()
        if state.briefing:
            await state.briefing.stop()
        if state.client:
            await state.client.aclose()


app = FastAPI(title="Aegis", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": config.VL_MODEL,
        "detector_backend": "openai",
        "briefing_model": config.BRIEFING_MODEL,
        "spatial_backend": geo.backend_name(),
        "cameras_total": len(state.cameras),
        "cameras_monitored": len(state.available),
        "scanned": state.store.scanned_count(),
        "sweeps": state.store.sweeps,
        "incidents": len(state.store.incidents()),
        "last_scan_at": state.store.last_scan_at,
        "replay_mode": config.REPLAY_MODE,
    }


@app.get("/api/incidents")
async def incidents():
    """Current non-clear detections, most-recent first (the incident log)."""
    return state.store.incidents()


@app.get("/api/states")
async def states():
    """camera_id -> current category, for recolouring map markers."""
    return state.store.category_map()


@app.get("/api/insight")
async def insight():
    """Headline cross-reference: matches, lead time, and conditions not in the feed."""
    if not state.disruptions:
        return {"official_count": 0, "incidents": 0, "matched": 0, "not_in_feed": 0, "best_lead": None}
    return state.disruptions.summary()


@app.get("/api/briefing")
async def briefing():
    """Latest plain-English operator briefing."""
    if not state.briefing:
        return {"text": "", "generated_at": None}
    return state.briefing.latest()


@app.get("/api/disruptions")
async def disruptions():
    """Official TfL road disruptions (for the map overlay / comparison)."""
    if not state.disruptions:
        return []
    return [
        {"id": d.id, "severity": d.severity, "category": d.category,
         "sub_category": d.sub_category, "status": d.status,
         "lat": d.lat, "lon": d.lon, "comments": d.comments}
        for d in state.disruptions.disruptions if d.lat and d.lon
    ]


class CascadeReq(BaseModel):
    lat: float
    lon: float
    hops: int = 15


async def _cascade(lat: float, lon: float, hops: int) -> dict:
    """The BFS catchment/cascade from a point — remote GPU engine (cuGraph on Modal)
    if AEGIS_RIPPLE_URL is set, else the local engine (cuGraph on the Spark / CPU)."""
    if config.RIPPLE_URL:
        r = await state.client.post(config.RIPPLE_URL,
                                    json={"lat": lat, "lon": lon, "hops": hops}, timeout=300)
        r.raise_for_status()
        return r.json()
    if ripple is None or not ripple.engine.ready:
        raise HTTPException(status_code=503, detail="ripple engine not ready")
    return await asyncio.to_thread(ripple.engine.cascade, lat, lon, hops)


@app.post("/api/cascade")
async def cascade(req: CascadeReq):
    """Ripple a disruption out through the road graph; return the impact footprint."""
    try:
        return await _cascade(req.lat, req.lon, req.hops)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"cascade failed: {e}")


@app.post("/api/smb/exposure")
async def smb_exposure(req: CascadeReq):
    """SMB early-warning: the business's accessibility catchment (BFS) + live signals
    (tube/rail + bus status, nearby road disruptions, weather) → attributed warnings."""
    try:
        catchment = await _cascade(req.lat, req.lon, req.hops)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"catchment failed: {e}")
    disruptions = state.disruptions.disruptions if state.disruptions else []
    return await smb.exposure(state.client, req.lat, req.lon, catchment, disruptions)


_highstreets_cache = {"data": None, "ts": 0.0}


@app.get("/api/highstreets")
async def highstreets():
    """City-scale collective view: batch-cascade today's live disruptions over all
    high-street businesses → access health per high street, deprivation-weighted."""
    now = time.monotonic()
    if _highstreets_cache["data"] and now - _highstreets_cache["ts"] < 120:
        return _highstreets_cache["data"]
    road_disruptions = state.disruptions.disruptions if state.disruptions else []
    road_seeds, transit_seeds, _ = await smb.collective_seeds(state.client, road_disruptions)
    try:
        if config.RIPPLE_URL:
            url = config.RIPPLE_URL.replace("ripple-cascade", "ripple-highstreets")
            r = await state.client.post(url, json={"road_seeds": road_seeds,
                                                   "transit_seeds": transit_seeds,
                                                   "hops_base": 8}, timeout=300)
            r.raise_for_status()
            data = r.json()
        elif ripple is not None and ripple.engine.ready:
            data = await asyncio.to_thread(ripple.engine.highstreets, road_seeds, transit_seeds, 8)
        else:
            raise HTTPException(status_code=503, detail="ripple engine not ready")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"highstreets failed: {e}")
    _highstreets_cache.update(data=data, ts=now)
    return data


@app.get("/api/ripple/status")
async def ripple_status():
    if ripple is None:
        return {"available": False}
    e = ripple.engine
    return {"available": True, "ready": e.ready, "backend": e.engine_backend,
            "bfs_backend": e.bfs_backend,
            "nodes": e.G.number_of_nodes() if e.G else 0, "stops": len(e.stops)}


@app.get("/api/cameras")
async def cameras():
    """Monitored cameras for the map. Frames are loaded via /api/frame/{id}."""
    return [
        {
            "id": c.id,
            "name": c.name,
            "lat": c.lat,
            "lon": c.lon,
            "view": c.view,
            "frame_url": f"/api/frame/{c.id}",
        }
        for c in state.available
    ]


@app.get("/api/frame/{camera_id}")
async def frame(camera_id: str):
    """Proxy a single camera's current JPEG (keeps S3/CORS + offline replay centralized)."""
    cam = state.camera_by_id.get(camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="unknown camera")
    img = await tfl.get_frame(state.client, cam)  # replay-aware (snapshot or live)
    if img is None:
        raise HTTPException(status_code=502, detail="frame fetch failed")
    return Response(content=img, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


# Saved incident thumbnails (frame at detection time).
app.mount("/thumbs", StaticFiles(directory=str(config.THUMB_DIR)), name="thumbs")

# Static HUD (mounted last so /api/* routes win).
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
