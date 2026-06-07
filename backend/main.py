"""Aegis backend — FastAPI app.

Serves the control-room HUD (static frontend) and the JSON API the HUD polls:
  GET /api/cameras            normalized camera registry
  GET /api/frame/{id}         live JPEG proxy for one camera (supports replay later)
  GET /api/health            service + model + scan status
The detector loop, incident store, disruptions matcher and briefing are wired in
later phases and hang off the shared AppState created in the lifespan below.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles

from . import config, geo, tfl
from .briefing import BriefingGenerator
from .detector import Detector
from .disruptions import DisruptionPoller
from .models import Camera
from .store import IncidentStore

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
    def monitored(self) -> list[Camera]:
        """Available cameras with an image URL, optionally capped for demo responsiveness."""
        avail = [c for c in self.cameras if c.available and c.image_url]
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
    print(f"[startup] cameras={len(state.cameras)} monitored={len(state.monitored)}")
    state.detector = Detector(state, state.store)
    state.detector.start()
    state.disruptions = DisruptionPoller(state, state.store)
    state.disruptions.start()
    state.briefing = BriefingGenerator(state, state.store)
    state.briefing.start()
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
        "detector_backend": config.VL_BACKEND,
        "briefing_model": config.BRIEFING_MODEL if config.BRIEFING_BACKEND == "openai" else config.VL_MODEL,
        "spatial_backend": geo.backend_name(),
        "cameras_total": len(state.cameras),
        "cameras_monitored": len(state.monitored),
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
        for c in state.monitored
    ]


@app.get("/api/frame/{camera_id}")
async def frame(camera_id: str):
    """Proxy a single camera's current JPEG (keeps S3/CORS + offline replay centralized)."""
    cam = state.camera_by_id.get(camera_id)
    if not cam or not cam.image_url:
        raise HTTPException(status_code=404, detail="unknown camera")
    img = await tfl.fetch_image(state.client, cam.image_url)
    if img is None:
        raise HTTPException(status_code=502, detail="frame fetch failed")
    return Response(content=img, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


# Saved incident thumbnails (frame at detection time).
app.mount("/thumbs", StaticFiles(directory=str(config.THUMB_DIR)), name="thumbs")

# Static HUD (mounted last so /api/* routes win).
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
