#!/usr/bin/env python3
"""Spatial-op micro-benchmark representative of Access Health's catchment math:
haversine distance from a point to ~28k high-street businesses + a radius filter,
GPU (cuPy) vs CPU (NumPy). Characterizes the RAPIDS spatial path on GB10.

    cd ~/aegis && .venv/bin/python scripts/benchmark_spatial.py
"""
import time, json, statistics
import numpy as np
try:
    import cupy as cp
    HAS_GPU = True
except Exception:
    HAS_GPU = False

N = 28000            # ~high-street businesses
ORIGIN = (51.5074, -0.1278)
RADIUS_KM = 1.2

def make_points(xp):
    # deterministic spread across inner London
    i = xp.arange(N)
    lat = 51.45 + (i * 0.6180339887 % 1.0) * 0.12
    lon = -0.25 + (i * 0.7548776662 % 1.0) * 0.30
    return lat.astype(xp.float64), lon.astype(xp.float64)

def haversine(xp, lat, lon, olat, olon):
    R = 6371.0
    p1, p2 = xp.radians(lat), xp.radians(olat)
    dphi = xp.radians(olat - lat); dlmb = xp.radians(olon - lon)
    a = xp.sin(dphi/2)**2 + xp.cos(p1)*xp.cos(p2)*xp.sin(dlmb/2)**2
    return 2*R*xp.arcsin(xp.sqrt(a))

def bench(xp, sync):
    lat, lon = make_points(xp)
    sync()
    ts = []
    for _ in range(50):
        t = time.perf_counter()
        d = haversine(xp, lat, lon, *ORIGIN)
        within = (d <= RADIUS_KM)
        cnt = int(within.sum())
        sync()
        ts.append((time.perf_counter()-t)*1000)
    return round(statistics.median(ts), 3), cnt

out = {"n_points": N, "radius_km": RADIUS_KM}
cpu_ms, cpu_cnt = bench(np, lambda: None)
out["cpu_numpy_ms"] = cpu_ms; out["in_radius"] = cpu_cnt
print(f"  CPU NumPy : {cpu_ms} ms ({cpu_cnt} within {RADIUS_KM}km)")
if HAS_GPU:
    sync = lambda: cp.cuda.Stream.null.synchronize()
    gpu_ms, _ = bench(cp, sync)
    out["gpu_cupy_ms"] = gpu_ms
    out["speedup_x"] = round(cpu_ms / gpu_ms, 1)
    print(f"  GPU cuPy  : {gpu_ms} ms  (speedup {out['speedup_x']}x)")
json.dump(out, open("/tmp/spatial_bench.json", "w"), indent=2)
print("WROTE /tmp/spatial_bench.json")
