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

## GPU vs CPU — controlled comparison (same graph, toggled `G_cu`)

Measured in-process on the *same* loaded 21,908-node graph, switching only the BFS
backend. Harness: [`scripts/benchmark_gpu_cpu.py`](scripts/benchmark_gpu_cpu.py).
(GPU numbers required briefly stopping the VL server to free ~28 GB — the shared GB10
could not host a *second* cuGraph context otherwise, which is itself a memory-pressure
finding.)

| Workload | GPU (cuGraph) | CPU (networkx) | Winner |
|---|---:|---:|---|
| **Single BFS cascade** (`_reach`, hops 15) | 27.6 ms | **0.10 ms** | **CPU ~275× faster** |
| **Betweenness centrality** (global analytic) | **0.62 s** (k=500) | 6.81 s (k=150) | **GPU ~11× faster** (and with 3.3× more samples) |
| **`highstreets()` cold** (batch BFS) | 311 / 874 / 1740 ms | ~27 / 72 / 37 ms | **CPU faster** at this scale |

(`highstreets` columns are 10 / 30 / 60 disruption seeds. GPU cost ≈ 29 ms/seed — one
kernel-launch + device→host transfer per `_reach`; CPU ≈ 0.1 ms/seed.)

### The surprise: at this graph size, GPU BFS is *slower*

The road graph (21,908 nodes / 50,554 edges) is small enough that **cuGraph's per-call
overhead** (kernel launch, cuDF dataframe build, device→host copy ≈ 27 ms) **dwarfs the
actual BFS**, while networkx with an early `cutoff` finishes in ~0.1 ms. GPU only wins on
the **betweenness centrality** — a heavy all-shortest-paths analytic — where it's ~11×
faster *and* samples 3.3× more vertices (k=500 vs 150), i.e. ~37× per normalized sample.

Crucially, betweenness is **computed once at load and cached to disk** — so in steady
state the GPU is doing the *one* job it loses at (per-query BFS) and none of the job it
wins at. **And the per-query GPU BFS is exactly what causes the concurrency-cliff above:**
N concurrent cuGraph contexts oversubscribe the shared device; N concurrent 0.1 ms CPU
BFS would not.

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

## Validation — after routing per-query BFS to CPU (implemented)

Recommendation 1 is now implemented (`AEGIS_RIPPLE_BFS=auto`, default CPU below 200k
nodes; GPU reserved for the betweenness build). Numbers below are a single **clean
consolidated pass** (quieter box; GPU 31 % mean / 23 W during the cascade run — that load
is the *other* tenants, since the cascade no longer touches the GPU):

| Concurrency | Before (GPU BFS) | After (CPU BFS, clean pass) | Δ throughput |
|---:|---|---|---|
| 1  | 0.41 rps · p50 2888 ms | **26.2 rps · p50 42 ms** | 64× |
| 2  | 6.52 rps · p50 284 ms  | 29.2 rps · p50 59 ms   | 4.5× |
| 4  | 8.05 rps · p50 526 ms  | **39.2 rps · p50 99 ms**  | 4.9× |
| 8  | 9.26 rps · p50 813 ms  | 35.2 rps · p50 194 ms  | 3.8× |
| 16 | 1.04 rps · p50 11992 ms | **32.2 rps · p50 486 ms** | 31× |
| 32 | 1.07 rps · p50 31257 ms | **33.0 rps · p50 809 ms** | 31× |

**The saturation cliff is gone.** Throughput now plateaus flat at ~33–39 rps through
concurrency 32 instead of collapsing to ~1 rps; overload p50 drops from 31 s to 0.8 s
(~39×) and single-request latency from 2.9 s to ~42 ms. The cascade no longer touches the
GPU — the ~35 rps ceiling is now the single uvicorn process + `nearest_nodes` KDTree + JSON
serialization (raise with more workers). `/api/ripple/status` reports
`bfs_backend: "networkx (CPU)"`; betweenness still builds on GPU (`backend: "cuGraph (GPU)"`).

A re-run of the controlled GPU-vs-CPU comparison confirms the rationale holds (figures vary
run-to-run with box load/warmup, conclusions do not): per-query BFS GPU 28–52 ms vs CPU
~0.1 ms (CPU 250–500× faster); betweenness GPU 0.6–0.95 s vs CPU 6.8–9.7 s (~10–11×).

## Recommendations

1. ~~**Route per-query BFS (`_reach`) to CPU networkx at this graph size.**~~ **DONE** — see
   Validation above (2.6× peak throughput, ~26× better overload latency, cliff removed). It is ~275× faster per call (0.1 ms vs 27.6 ms) *and* removes the GPU-context
   oversubscription that causes the concurrency cliff. This very likely turns the 9.3 rps
   ceiling + 35 s overload latency into a far higher, flat-latency profile, and frees the
   GPU for the VL perception layer. (Re-validate against the live LSOA-aggregation /
   serialization cost, which is the *other* part of the ~280 ms HTTP latency.)
2. **Keep GPU only for the betweenness centrality build** (~11× faster, the one genuine
   win) — already computed once at load and cached, so this costs nothing in steady state.
3. **The GPU/CPU choice is graph-size-dependent.** cuGraph BFS would overtake CPU on a much
   larger graph (full-resolution all-London, millions of nodes). Make the backend a config
   toggle keyed on node count rather than just RAPIDS availability.
4. If GPU BFS is retained, **cap cascade concurrency at ~8** (semaphore / bounded queue) so
   excess load queues instead of collapsing the device (p95 < ~1.1 s vs 35 s).
5. **Memory:** a second cuGraph context could not be allocated while vLLM + llama.cpp were
   resident — the shared GB10 has no headroom for ad-hoc GPU work. The earlier vLLM
   `0.40 → 0.25` change helped but the text + VL servers still dominate the 119 GiB.

## Reproduce

```bash
cd ~/aegis
./serverctl.sh start                              # backend on :8000
.venv/bin/python scripts/benchmark_cascade.py     # HTTP concurrency sweep
# GPU-vs-CPU + cold city-scale (needs free GPU; stop the VL server first):
bash vllm_serve.sh stop
AEGIS_DATA_DIR="$PWD/data" PYTHONPATH="$PWD" .venv/bin/python scripts/benchmark_gpu_cpu.py
bash vllm_serve.sh start                          # restore VL server (0.25 util)
```

## Machine + use-case benchmark suite (2026-06-07)

A full sweep of the GB10 DGX Spark and every Access Health subsystem, ordered by run
time. Harnesses: `scripts/benchmark_{cascade,gpu_cpu,spatial,vl,briefing}.py` plus ad-hoc
`cupy`/`dd` probes.

### Hardware baseline (GB10) — the headline contention finding

| Metric | Under production load | Idle (services paused) | loss to contention |
|---|---:|---:|---:|
| Memory bandwidth (cuPy triad) | 53 GB/s | **152 GB/s** | −65 % |
| FP16 matmul 8192³ | 21.2 TFLOP/s | **63.1 TFLOP/s** | −66 % |
| FP32 matmul 8192³ | 9.3 TFLOP/s | **19.7 TFLOP/s** | −53 % |

The shared GB10 loses ~⅔ of its compute/bandwidth when VL + llama.cpp + detector run
concurrently. This is the root cause of slow VL decode: the model is memory-bandwidth-bound
and only ~⅓ of bandwidth is free under load.

### Subsystem results

| # | Benchmark | Result |
|---|---|---|
| 1 | Cascade BFS sweep (CPU-routed) | ~19–24 rps flat to c=32, no cliff (under detector load) |
| 2 | API endpoints (`:8000` GETs) | 0–9 ms each (highstreets 9 ms cached, cameras 7 ms) |
| 3 | NVMe disk I/O (3.6 TB) | write **4.0 GB/s**, read **5.8 GB/s** (direct) |
| 5 | Spatial haversine over 28k pts | CPU 0.55 ms vs **GPU 0.125 ms (4.4×)** |
| 6 | Graph BFS / betweenness (idle GPU) | BFS GPU 27.6 ms vs CPU 0.10 ms (CPU ~275×); betweenness GPU 0.67 s vs CPU 6.8 s (10.1×) |
| 7 | VL perception throughput (@0.25, isolated) | plateau **~0.44 img/s** at c≥8; single-image **6.5 s isolated vs ~20 s under load**; TTFT 1.6 s, ~9 tok/s decode |
| 8 | Briefing LLM (Nemotron-3-30B-A3B) | decode **44.5 → 68.5 tok/s** (c=1→4); ~478 tok/briefing, p50 **10.9 s** @ c=1; TTFT 8.8 s (prefill) |

### LLM serving detail

**#7 VL detector** (vLLM `nemotron-nano-vl`, 12B dense, `0.25`, KV concurrency 5.17×):

| Conc | images/s | p50 | tokens/s |
|---:|---:|---:|---:|
| 1 | 0.15 | 6.5 s | 7.3 |
| 2 | 0.25 | 8.0 s | 11.6 |
| 4 | 0.36 | 10.9 s | 17.0 |
| 8 | 0.42 | 16.7 s | 19.6 |
| 16 | 0.44 | 33.6 s | 20.8 |

Each JamCam image is ~3,355 prompt tokens (prefill-dominated) + ~47 output. Throughput
plateaus ~0.44 img/s; aggregate decode caps ~21 tok/s (the ~5-seq KV ceiling at `0.25`).

**#8 briefing** (llama.cpp `Nemotron-3-Nano-30B-A3B`, MoE 3B-active, :30000):

| Conc | briefings/s | p50 | tokens/s |
|---:|---:|---:|---:|
| 1 | 0.09 | 10.9 s | 44.5 |
| 2 | 0.12 | 16.1 s | 55.5 |
| 4 | 0.15 | 23.1 s | 68.5 |

~478 tokens/briefing; TTFT ~8.8 s (30B prefill), decode 44.5 tok/s single-stream.

### Takeaways

- **The box is memory-bandwidth-bound, not compute-bound** for the LLM paths; contention,
  not raw GPU power, is the limiter. Co-residency costs ~⅔ of GPU bandwidth/FLOPS, and that
  shows up directly as VL latency: **6.5 s/image isolated vs ~20 s under load (≈3×)**.
- **MoE beats dense on decode here:** the 30B-A3B briefing model (3B active) decodes at
  **44.5 tok/s** — faster than the 12B *dense* VL model at ~9 tok/s single-stream — because
  decode reads only the active experts, not all weights. Bandwidth, not parameter count, rules.
- **Disk, spatial, and API layers are not bottlenecks** — all sub-10 ms / multi-GB/s.
- Confirms the earlier architectural call: **per-query BFS on CPU** (0.1 ms, no GPU/bandwidth
  contention) is the right default; reserve scarce GPU bandwidth for the LLM serving.
- **Tuning levers for VL throughput** (if needed): the ~5-seq ceiling at `0.25` caps it;
  widening the KV pool (higher gpu-util) or lowering `--max-model-len` raises concurrency,
  but single-image latency stays bandwidth-bound. Isolating the detector sweep from
  interactive load removes the ~3× contention tax.
