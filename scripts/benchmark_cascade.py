#!/usr/bin/env python3
"""Concurrency-sweep benchmark for the Access Health (Aegis) cuGraph cascade endpoint.
Finds max sustainable throughput + latency percentiles. Coordinates jittered across
inner London so every request is distinct graph work (no per-coord caching)."""
import asyncio, time, statistics, json, sys
import httpx

BASE = "http://127.0.0.1:8000"
HOPS = 15
# inner-London bounding box (covers the 21,908-node graph footprint)
LAT0, LAT1 = 51.48, 51.54
LON0, LON1 = -0.20, -0.05

def coords(n):
    # deterministic spread (no RNG): walk a lattice across the bbox
    out = []
    for i in range(n):
        fx = ((i * 0.6180339887) % 1.0)
        fy = ((i * 0.7548776662) % 1.0)
        out.append((LAT0 + fx * (LAT1 - LAT0), LON0 + fy * (LON1 - LON0)))
    return out

async def one(client, lat, lon):
    t = time.perf_counter()
    r = await client.post(f"{BASE}/api/cascade", json={"lat": lat, "lon": lon, "hops": HOPS}, timeout=120)
    dt = time.perf_counter() - t
    return dt, r.status_code, len(r.content)

async def run_level(concurrency, total):
    cs = coords(total)
    sem = asyncio.Semaphore(concurrency)
    lat_ms, codes = [], []
    async with httpx.AsyncClient() as client:
        async def task(c):
            async with sem:
                dt, code, _ = await one(client, *c)
                lat_ms.append(dt * 1000); codes.append(code)
        wall0 = time.perf_counter()
        await asyncio.gather(*(task(c) for c in cs))
        wall = time.perf_counter() - wall0
    ok = sum(1 for c in codes if c == 200)
    lat_ms.sort()
    def pct(p): return lat_ms[min(len(lat_ms)-1, int(p/100*len(lat_ms)))]
    return {
        "concurrency": concurrency, "requests": total, "ok": ok,
        "wall_s": round(wall, 3),
        "throughput_rps": round(ok / wall, 2),
        "p50_ms": round(statistics.median(lat_ms), 1),
        "p95_ms": round(pct(95), 1),
        "p99_ms": round(pct(99), 1),
        "mean_ms": round(statistics.mean(lat_ms), 1),
        "min_ms": round(lat_ms[0], 1), "max_ms": round(lat_ms[-1], 1),
    }

async def main():
    # warmup (JIT/graph caches)
    async with httpx.AsyncClient() as c:
        for lat, lon in coords(5):
            await one(c, lat, lon)
    results = []
    for conc in [1, 2, 4, 8, 16, 32]:
        total = max(conc * 4, 24)
        res = await run_level(conc, total)
        results.append(res)
        print(json.dumps(res), flush=True)
    json.dump(results, open("/tmp/aegis_bench_results.json", "w"), indent=2)

asyncio.run(main())
