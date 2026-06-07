"""Classify one or more local image files with the current VL prompt.

Run on hp15:  .venv/bin/python -m scripts.classify_file data/thumbs/XXX.jpg [...]
"""
import asyncio
import sys

import httpx

from backend import vl


async def main(paths):
    async with httpx.AsyncClient() as client:
        for p in paths:
            try:
                img = open(p, "rb").read()
            except OSError as e:
                print(f"{p}: cannot read ({e})")
                continue
            r = await vl.classify_frame(client, img)
            if r:
                print(f"{p}\n  -> [{r['category']}] conf={r['confidence']}  {r['description']}")
            else:
                print(f"{p}\n  -> (no result)")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
