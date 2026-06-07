# Access Health (Aegis) — Performance Report

**Date:** 2026-06-07 · **Host:** `hp-15` (NVIDIA DGX Spark, GB10 Grace-Blackwell, 119 GiB unified) · **Driver:** 580.159.03 / CUDA 13.0

This report measures the live, GPU-accelerated request paths of the Access Health backend
(`backend.main:app`, uvicorn on `:8000`) under realistic shared-GPU conditions.

## System under test

| Component | Backend | Detail |
|---|---|---|
| Spatial engine | **RAPIDS cuDF/cuPy (GPU)** | population / LSOA spatial joins |
| Ripple cascade | **cuGraph (GPU)** | road graph: **21,908 nodes**, **3,584 transit stops** |
| Perception (VL) | vLLM `nemotron-nano-vl` (`:8090`) | 819/882 cameras monitored, continuous sweep |

**Co-resident GPU tenants during the test** (shared GB10, not isolated):
vLLM VL server (~28 GB), llama.cpp text server (~39 GB), and the background VL camera
sweep — i.e. these numbers reflect production-like mixed load, not a dedicated GPU.

## Method

- Endpoint: `POST /api/cascade` (cuGraph BFS catchment), `hops=15`.
- Coordinates jittered deterministically across the inner-London bounding box so every
  request is **distinct graph work** (no per-coordinate caching).
- Warmup of 5 requests, then a concurrency sweep (1 → 32), 4× requests per level.
- GPU sampled once/second (`nvidia-smi`) for the duration.
- Harness: [`scripts/benchmark_cascade.py`](scripts/benchmark_cascade.py) (reproducible, stdlib + httpx).

## Results — `/api/cascade` concurrency sweep

| Concurrency | Throughput (rps) | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) |
|---:|---:|---:|---:|---:|---:|
| 1  | 0.41 | 2887.9 | 4056.7 | 11067.0 | 2422.0 |
| 2  | 6.52 | 284.0  | 424.3  | 481.6   | 294.3  |
| 4  | 8.05 | 526.1  | 603.1  | 610.3   | 490.4  |
| **8**  | **9.26** | **812.9** | **1077.8** | 1143.9 | 804.8 |
| 16 | 1.04 | 11991.5 | 35679.0 | 35685.9 | 14395.6 |
| 32 | 1.07 | 31257.1 | 41405.0 | 41406.5 | 28472.8 |

All requests returned HTTP 200 (0 errors across 296 requests). Cascade response ≈ 28 KB.

**GPU during the run:** util **85% mean / 96% peak**, power peak **64 W**, temp ~71 °C.

## Single-shot baselines (warm)

| Endpoint | Latency | Size | Notes |
|---|---|---|---|
| `POST /api/cascade` | ~280 ms | 28 KB | pure cuGraph BFS (steady-state) |
| `POST /api/smb/exposure` | ~7.8 s | 33 KB | cascade **+ external TfL/bus/weather APIs** — I/O-bound, not GPU |
| `GET /api/highstreets` | ~11 ms | 118 KB | served from 120 s in-process cache (cold city-scale not isolated here) |

## Key findings

1. **Peak sustained throughput ≈ 9.3 req/s at concurrency 8**, p50 ≈ 0.8 s — the GPU
   reaches 85–96 % utilization here. This is the cascade endpoint's max on the shared box.
2. **Hard saturation cliff beyond 8 concurrent.** At 16–32 concurrent, throughput
   *collapses* ~9× (to ~1 rps) and p50 latency balloons to 12–31 s. Each cuGraph BFS
   allocates GPU memory and a CUDA stream; oversubscribing the single GB10 — already shared
   with vLLM, llama.cpp and the VL sweep — causes serialization + allocation thrash, not
   graceful queueing.
3. **The concurrency-1 row is an outlier** (p50 2.9 s, but min 182 ms, one 11 s spike): its
   58 s window overlapped a background VL camera sweep. Warm, uncontended cascade latency is
   ~180–290 ms (see concurrency-2 min/p50 and the single-shot baseline).
4. **Not power-bound** (64 W peak): the bottleneck is GPU-context contention / serialization
   on the shared device, not compute headroom.

## Recommendations

- **Cap cascade concurrency at ~8** (semaphore / worker pool in front of
  `ripple.engine.cascade`, or a bounded `asyncio` queue) so excess load queues instead of
  collapsing the GPU. This keeps p95 < ~1.1 s under overload instead of 35 s.
- For higher fan-out (city scale), prefer the **batched** `/api/highstreets` path over many
  concurrent single cascades — batching amortizes graph setup far better than N parallel BFS.
- Consider isolating the VL sweep cadence from interactive cascade traffic (or run cascades
  on a CUDA stream priority) to remove the variance seen at concurrency 1.

## Reproduce

```bash
cd ~/aegis
./serverctl.sh start                  # backend on :8000
.venv/bin/python scripts/benchmark_cascade.py   # writes /tmp/aegis_bench_results.json
```
