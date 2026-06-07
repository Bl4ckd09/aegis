"""Capture an offline-replay snapshot from the running Aegis backend + TfL.

Saves the monitored camera list, each camera's current frame, the official
disruptions feed, and the current incident classifications to data/snapshots/.
Run in the backend venv WHILE the app is live (so frames + classifications are
real), then serve it with no network:

    python -m scripts.snapshot
    AEGIS_REPLAY=1 bash serverctl.sh restart    # (or set AEGIS_REPLAY=1 when launching uvicorn)

Same-machine replay (the venue-network-failure case): thumbnails persist in
data/thumbs/, frames in data/snapshots/frames/.
"""
import asyncio
import json

import httpx

from backend import config, tfl

BASE = "http://127.0.0.1:8000"


async def main():
    frames_dir = config.SNAPSHOT_DIR / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "Aegis/1.0 (snapshot)"}) as client:
        cams = (await client.get(f"{BASE}/api/cameras")).json()
        (config.SNAPSHOT_DIR / "cameras.json").write_text(json.dumps(cams))
        print(f"cameras:     {len(cams)}")

        incidents = (await client.get(f"{BASE}/api/incidents")).json()
        (config.SNAPSHOT_DIR / "incidents.json").write_text(json.dumps(incidents))
        print(f"incidents:   {len(incidents)}")

        ok = 0
        for c in cams:
            try:
                r = await client.get(f"{BASE}/api/frame/{c['id']}")
                if r.status_code == 200:
                    (frames_dir / f"{c['id']}.jpg").write_bytes(r.content)
                    ok += 1
            except Exception:
                pass
        print(f"frames:      {ok}/{len(cams)} saved")

        disr = await tfl.fetch_disruptions(client)  # full objects (with timestamps)
        (config.SNAPSHOT_DIR / "disruptions.json").write_text(
            json.dumps([d.model_dump() for d in disr]))
        print(f"disruptions: {len(disr)}")

    print(f"\nsnapshot -> {config.SNAPSHOT_DIR}")
    print("replay it offline with:  AEGIS_REPLAY=1  (then restart the app)")


if __name__ == "__main__":
    asyncio.run(main())
