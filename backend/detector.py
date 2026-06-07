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
        self._cursor = 0            # rolling position into the camera universe

    async def _classify_one(self, cam: Camera) -> None:
        async with self.sem:
            if self._stop:
                return
            img = await tfl.get_frame(self.state.client, cam)
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

    def _next_batch(self, cams: list[Camera]) -> list[Camera]:
        """The next rolling window of SWEEP_BATCH cameras, wrapping around the universe."""
        n = len(cams)
        b = min(config.SWEEP_BATCH, n)
        end = self._cursor + b
        batch = cams[self._cursor:end] + (cams[: end - n] if end > n else [])
        self._cursor = end % n
        return batch

    async def _scan_batch(self, cams: list[Camera]) -> None:
        await asyncio.gather(*(self._classify_one(c) for c in cams), return_exceptions=True)
        self.store.mark_sweep()

    async def run(self) -> None:
        print(f"[detector] start: {len(self.state.available)} cameras on map, rolling "
              f"{config.SWEEP_BATCH}/batch every {config.BATCH_INTERVAL_SECONDS}s, "
              f"concurrency={config.DETECT_CONCURRENCY}")
        while not self._stop:
            cams = self.state.available
            if not cams:
                await asyncio.sleep(5)
                continue
            t0 = time.monotonic()
            batch = self._next_batch(cams)
            try:
                await self._scan_batch(batch)
            except Exception as e:
                print(f"[detector] batch error: {e}")
            elapsed = time.monotonic() - t0
            print(f"[detector] batch #{self.store.sweeps} ({len(batch)} cams) in {elapsed:.0f}s "
                  f"| cursor={self._cursor}/{len(cams)} scanned={self.store.scanned_count()} "
                  f"incidents={len(self.store.incidents())}")
            if self._stop:
                break
            await asyncio.sleep(config.BATCH_INTERVAL_SECONDS)

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
