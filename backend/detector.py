"""Async detector loop.

Sweeps the monitored cameras, fetching each frame and classifying it with the
local VL model under a bounded concurrency limit, so wall-time for a sweep is
~ceil(N / concurrency) inferences rather than N sequential calls. After each
sweep it sleeps to pace roughly to the JamCams refresh interval, then repeats.
"""
from __future__ import annotations

import asyncio
import time

from . import config, tfl, vl
from .models import Camera
from .store import IncidentStore


class Detector:
    def __init__(self, state, store: IncidentStore) -> None:
        self.state = state          # AppState (httpx client + cameras)
        self.store = store
        self.sem = asyncio.Semaphore(config.DETECT_CONCURRENCY)
        self.task: asyncio.Task | None = None
        self._stop = False

    async def _classify_one(self, cam: Camera) -> None:
        async with self.sem:
            if self._stop:
                return
            img = await tfl.fetch_image(self.state.client, cam.image_url)
            if not img:
                return
            result = await vl.classify_frame(self.state.client, img)
            if not result:
                return
            # persist the frame as this camera's thumbnail (small JPEG, off the loop)
            try:
                await asyncio.to_thread((config.THUMB_DIR / f"{cam.id}.jpg").write_bytes, img)
            except Exception:
                pass
            self.store.record(cam, result)

    async def _sweep(self) -> None:
        cams = self.state.monitored
        if not cams:
            return
        await asyncio.gather(*(self._classify_one(c) for c in cams), return_exceptions=True)
        self.store.mark_sweep()

    async def run(self) -> None:
        print(f"[detector] start: monitoring {len(self.state.monitored)} cameras, "
              f"concurrency={config.DETECT_CONCURRENCY}, interval={config.POLL_INTERVAL_SECONDS}s")
        while not self._stop:
            t0 = time.monotonic()
            try:
                await self._sweep()
            except Exception as e:
                print(f"[detector] sweep error: {e}")
            elapsed = time.monotonic() - t0
            print(f"[detector] sweep #{self.store.sweeps} done in {elapsed:.0f}s "
                  f"({self.store.scanned_count()} cams, {len(self.store.incidents())} incidents)")
            if self._stop:
                break
            await asyncio.sleep(max(2.0, config.POLL_INTERVAL_SECONDS - elapsed))

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
