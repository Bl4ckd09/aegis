"""Official-disruption poller + spatial/temporal cross-reference.

Periodically pulls TfL's Road Disruption feed (the ground truth) and, for every
current VL detection, finds the nearest official disruption within MATCH_RADIUS_M.
Two outcomes drive the headline insight:
  - matched + official updated AFTER we detected  -> positive "lead time" (we saw it first)
  - no match within radius                        -> condition not (yet) in the official feed
"""
from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Optional

from . import config, geo, tfl
from .models import Disruption


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


class DisruptionPoller:
    def __init__(self, state, store) -> None:
        self.state = state
        self.store = store
        self.disruptions: list[Disruption] = []
        self.task: asyncio.Task | None = None
        self._stop = False

    def match_all(self) -> None:
        """Annotate every current incident with its official cross-reference.

        Batched nearest-neighbour spatial join via RAPIDS (GPU) / NumPy (CPU).
        """
        now = datetime.now(timezone.utc)
        incidents = [s for s in self.store.states.values()
                     if s["category"] in config.INCIDENT_CATEGORIES]
        located = [d for d in self.disruptions if d.lat is not None and d.lon is not None]
        if not incidents:
            return

        idxs, dists = ([], [])
        if located:
            idxs, dists = geo.nearest(
                [s["lat"] for s in incidents], [s["lon"] for s in incidents],
                [d.lat for d in located], [d.lon for d in located],
            )

        for i, st in enumerate(incidents):
            d = located[idxs[i]] if idxs else None
            dist = dists[i] if dists else float("inf")
            if d is None or dist > config.MATCH_RADIUS_M:
                # no official record near this detection -> ahead of / absent from feed
                st["matched_disruption_id"] = None
                st["official_logged_at"] = None
                st["lead_time_seconds"] = None
                st["match_distance_m"] = None
                continue

            st["matched_disruption_id"] = d.id
            official = _parse_iso(d.updated_at) or _parse_iso(d.start_at)
            st["official_logged_at"] = official.isoformat() if official else None
            st["match_distance_m"] = round(dist)
            st["match_severity"] = d.severity
            st["match_category"] = d.category

            detected = _parse_iso(st["detected_at"]) or now
            lead = None
            if official is not None:
                delta = (official - detected).total_seconds()
                # positive, bounded delta => we detected before the official update
                if 0 < delta <= config.MATCH_TIME_WINDOW_S:
                    lead = delta
            st["lead_time_seconds"] = lead

    async def run(self) -> None:
        print("[disruptions] poller start")
        last_fetch = -1e9
        loop = asyncio.get_event_loop()
        while not self._stop:
            try:
                # Re-fetch the official feed at the poll interval; re-match frequently
                # against the cached feed so new detections get cross-referenced fast.
                if loop.time() - last_fetch >= config.POLL_INTERVAL_SECONDS:
                    self.disruptions = await tfl.fetch_disruptions(self.state.client)
                    last_fetch = loop.time()
                    print(f"[disruptions] fetched {len(self.disruptions)} official disruptions")
                self.match_all()
            except Exception as e:
                print(f"[disruptions] poll error: {e}")
            await asyncio.sleep(15)

    def start(self) -> None:
        self.task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stop = True
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass

    # --- read for API ---
    def summary(self) -> dict:
        incidents = self.store.incidents()
        matched = [s for s in incidents if s.get("matched_disruption_id")]
        ahead = [s for s in incidents if not s.get("matched_disruption_id")]
        leads = [s for s in incidents if s.get("lead_time_seconds")]
        best = max(leads, key=lambda s: s["lead_time_seconds"], default=None)
        return {
            "official_count": len(self.disruptions),
            "incidents": len(incidents),
            "matched": len(matched),
            "not_in_feed": len(ahead),
            "best_lead": best,
        }
