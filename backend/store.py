"""In-memory incident store + append-only JSONL persistence.

Tracks the latest classification per camera (drives map colors) and exposes the
current non-clear detections as the incident log. Every incident is also appended
to data/incidents.jsonl so nothing is lost on restart and we have a record to show.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from . import config
from .models import Camera


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IncidentStore:
    def __init__(self) -> None:
        # camera_id -> latest state dict (all scanned cameras, including "clear")
        self.states: dict[str, dict] = {}
        self.classifications = 0          # total VL calls that returned a result
        self.sweeps = 0
        self.last_scan_at: Optional[str] = None

    # --- writes (called from the detector; no awaits => asyncio-safe) ---------
    def record(self, cam: Camera, result: dict) -> dict:
        now = _now_iso()
        category = result["category"]
        st = self.states.get(cam.id, {})
        state = {
            "camera_id": cam.id,
            "common_name": cam.name,
            "lat": cam.lat,
            "lon": cam.lon,
            "category": category,
            "confidence": result["confidence"],
            "description": result["description"],
            "image_thumb_url": f"/thumbs/{cam.id}.jpg",
            "detected_at": now,
            # preserve any cross-reference annotations the matcher added
            "matched_disruption_id": st.get("matched_disruption_id"),
            "official_logged_at": st.get("official_logged_at"),
            "lead_time_seconds": st.get("lead_time_seconds"),
        }
        # if the category changed, the old cross-ref is stale
        if st.get("category") != category:
            state["matched_disruption_id"] = None
            state["official_logged_at"] = None
            state["lead_time_seconds"] = None
        self.states[cam.id] = state
        self.classifications += 1
        self.last_scan_at = now

        if category in config.INCIDENT_CATEGORIES:
            self._append_jsonl(state)
        return state

    def _append_jsonl(self, state: dict) -> None:
        try:
            with config.INCIDENTS_JSONL.open("a") as f:
                f.write(json.dumps(state) + "\n")
        except Exception as e:
            print(f"[store] jsonl append failed: {e}")

    def mark_sweep(self) -> None:
        self.sweeps += 1

    # --- reads ---------------------------------------------------------------
    def incidents(self) -> list[dict]:
        """Current non-clear detections, most-recent first."""
        items = [s for s in self.states.values() if s["category"] in config.INCIDENT_CATEGORIES]
        return sorted(items, key=lambda s: s["detected_at"], reverse=True)

    def category_map(self) -> dict[str, str]:
        """camera_id -> current category, for map recolouring."""
        return {cid: s["category"] for cid, s in self.states.items()}

    def scanned_count(self) -> int:
        return len(self.states)
