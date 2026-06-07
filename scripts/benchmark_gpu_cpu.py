#!/usr/bin/env python3
"""GPU-vs-CPU benchmark for the Access Health (Aegis) cuGraph engine, plus the
cold city-scale paths. Loads the RippleEngine once and toggles `G_cu` to compare
the SAME graph on GPU (cuGraph) vs CPU (networkx) — a controlled apples-to-apples
measurement. Run with the project venv (RAPIDS via --system-site-packages):

    cd ~/aegis && .venv/bin/python scripts/benchmark_gpu_cpu.py
"""
import time, statistics, json
import networkx as nx

from backend import ripple as R
from backend import config

# This harness compares GPU vs CPU directly, so force the engine to BUILD and KEEP the
# cuGraph graph regardless of the production routing default (auto -> CPU frees G_cu).
config.RIPPLE_BFS_BACKEND = "gpu"

DEFAULT_HOPS = 15

def timeit(fn, n=1):
    ts = []
    for _ in range(n):
        t = time.perf_counter(); fn(); ts.append((time.perf_counter() - t) * 1000)
    return ts

def main():
    out = {}
    t = time.perf_counter()
    e = R.RippleEngine(); e.load()
    out["load_s"] = round(time.perf_counter() - t, 2)
    out["backend"] = e.engine_backend
    n = e.G.number_of_nodes()
    out["nodes"] = n
    has_gpu = e.G_cu is not None
    out["gpu_available"] = has_gpu
    print(f"loaded: {n} nodes, backend={e.engine_backend}, gpu={has_gpu}, load={out['load_s']}s", flush=True)

    # deterministic spread of source nodes across the graph
    all_nodes = list(e.G.nodes())
    srcs = [all_nodes[(i * 2654435761) % len(all_nodes)] for i in range(40)]

    # ---- 1. BFS cascade: GPU vs CPU (same graph) ----
    gpu_cu = e.G_cu
    # warm
    if has_gpu:
        e.G_cu = gpu_cu
        for s in srcs[:5]: e._reach(s, DEFAULT_HOPS)
        gpu = [timeit(lambda s=s: e._reach(s, DEFAULT_HOPS), 3) for s in srcs]
        gpu = [x for sub in gpu for x in sub]
    else:
        gpu = []
    e.G_cu = None  # force CPU networkx path
    for s in srcs[:5]: e._reach(s, DEFAULT_HOPS)
    cpu = [timeit(lambda s=s: e._reach(s, DEFAULT_HOPS), 3) for s in srcs]
    cpu = [x for sub in cpu for x in sub]
    e.G_cu = gpu_cu  # restore

    out["bfs_cascade"] = {
        "hops": DEFAULT_HOPS, "samples": len(cpu),
        "gpu_mean_ms": round(statistics.mean(gpu), 2) if gpu else None,
        "gpu_p50_ms": round(statistics.median(gpu), 2) if gpu else None,
        "cpu_mean_ms": round(statistics.mean(cpu), 2),
        "cpu_p50_ms": round(statistics.median(cpu), 2),
        "speedup_x": round(statistics.mean(cpu) / statistics.mean(gpu), 1) if gpu else None,
    }
    print("bfs_cascade:", json.dumps(out["bfs_cascade"]), flush=True)

    # ---- 2. Betweenness centrality (heavy city-scale analytic), in-memory ----
    cent = {}
    if has_gpu:
        import cugraph
        t = time.perf_counter()
        df = cugraph.betweenness_centrality(e.G_cu, k=min(500, n), normalized=True)
        _ = df["betweenness_centrality"].to_arrow().to_pylist()
        cent["gpu_s"] = round(time.perf_counter() - t, 2)
        cent["gpu_k"] = min(500, n)
    t = time.perf_counter()
    _ = nx.betweenness_centrality(e.UG, k=min(150, n), normalized=True)
    cent["cpu_s"] = round(time.perf_counter() - t, 2)
    cent["cpu_k"] = min(150, n)
    if has_gpu:
        # note: GPU uses more samples (k=500) yet is faster; speedup is conservative
        cent["speedup_x"] = round(cent["cpu_s"] / cent["gpu_s"], 1)
    out["betweenness"] = cent
    print("betweenness:", json.dumps(cent), flush=True)

    # ---- 3. highstreets() cold batch cascade (GPU), varying seed count ----
    stops = e.stops
    hs = {}
    for nseed in [10, 30, 60]:
        seeds = [{"lat": s["lat"], "lon": s["lon"], "weight": 0.8}
                 for s in stops[:: max(1, len(stops) // nseed)]][:nseed]
        ts = timeit(lambda: e.highstreets(seeds, [], 8), 3)
        hs[f"{nseed}_seeds_ms"] = round(statistics.mean(ts), 1)
    out["highstreets_cold"] = hs
    print("highstreets_cold:", json.dumps(hs), flush=True)

    json.dump(out, open("/tmp/aegis_gpu_cpu.json", "w"), indent=2)
    print("WROTE /tmp/aegis_gpu_cpu.json", flush=True)

if __name__ == "__main__":
    main()
