"""Smoke test: exercise tfl + vl modules end-to-end against live endpoints.

Run on hp15:  .venv/bin/python -m scripts.smoke
"""
import asyncio
import time

import httpx

from backend import tfl, vl


async def main():
    async with httpx.AsyncClient() as client:
        print("Fetching camera list...")
        cams = await tfl.fetch_cameras(client)
        avail = [c for c in cams if c.available and c.image_url]
        print(f"  cameras={len(cams)}  available_with_image={len(avail)}")
        assert avail, "no available cameras!"

        cam = avail[0]
        print(f"Fetching frame from: {cam.name} ({cam.id})")
        img = await tfl.fetch_image(client, cam.image_url)
        print(f"  frame_bytes={len(img) if img else 0}")
        assert img, "frame download failed!"

        print("Classifying frame with local VL model...")
        t0 = time.time()
        result = await vl.classify_frame(client, img)
        print(f"  latency={time.time() - t0:.1f}s  result={result}")
        assert result and result["category"] in (
            "clear", "congestion", "accident", "stalled_vehicle", "hazard", "obscured"
        ), "VL classification failed!"

        print("Fetching disruptions...")
        disr = await tfl.fetch_disruptions(client)
        located = [d for d in disr if d.lat and d.lon]
        print(f"  disruptions={len(disr)}  with_coords={len(located)}")

        print("\nSMOKE OK ✅")


if __name__ == "__main__":
    asyncio.run(main())
