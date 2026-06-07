# Ripple — real-time causal cascade engine for London (built on Aegis)

**Ripple models the *downstream* impact of a road disruption — before it happens.**
Click anywhere on the map (or let it watch TfL's live disruption feed) and Ripple ripples that
disruption outward through London's road network with a **GPU graph BFS (RAPIDS cuGraph)**, then
quantifies who it hits: road junctions, bus stops, bus routes, daily journeys — and, crucially,
the **population and deprivation** of the neighbourhoods affected. In live mode it validates the
modelled severity against traffic-camera footage with a vision-language model.

Built for **Hack for Impact London (presented by NVIDIA)**. Designed to run **locally on an
NVIDIA DGX Spark** — the road graph, the demographics, and the VL model co-resident in 128 GB of
unified memory; no cloud, no data leaving the premises. Every NVIDIA component is behind one env
var, so the *identical* stack also runs on a cloud RAPIDS GPU + Modal H100 for failover.

> Ripple is built on **Aegis**, our camera-perception HUD (documented below). Under Ripple, Aegis
> becomes the live *"validate the model with footage"* layer.

---

## The problem

London approves thousands of infrastructure decisions a year — road closures, diversions,
roadworks — each in isolation, by one department looking at one dataset. Nobody models what breaks
*downstream*: the journeys rerouted, the buses delayed, the workers in high-deprivation areas who
arrive late. The data to see it **already exists** — it just lives in separate systems that have
never talked to each other. Ripple joins them in real time.

## What Ripple does

- **Planning mode** — click any location on the map and instantly see the forecast cascade impact
  *before* a decision is approved. No forms, no coding — just click.
- **Monitoring mode** — watches TfL's live road-disruption feed and shows each disruption's
  downstream impact as it happens.
- **Impact, per cascade:** affected road junctions · bus stops · bus routes · estimated daily
  journeys · **residents in the affected catchment** · **how many of those neighbourhoods fall in
  England's most-deprived 20%** (the equity headline).
- **Vision validation** (live mode) — classifies the nearest JamCam with the NVIDIA VL model to
  ground the modelled severity against what's actually on the road.
- **Sub-second** cascades over a ~22,000-node graph on cuGraph (GPU).

Example contrast (real output): a disruption at **Trafalgar Square** → 78k journeys, 1 deprived
neighbourhood; the same at **Tower Hamlets** → 49k residents, **7** of the affected neighbourhoods
among London's most deprived. Ripple makes the *equity* of an infrastructure decision visible.

## How it works

```
disruption  (planning-mode click  ·  or live TfL Road Disruption feed)
   → nearest road-graph node
   → BFS outward, k hops                      [RAPIDS cuGraph on GPU · networkx CPU fallback]
   → set of affected road nodes
        ├─ bus stops served  → routes, estimated daily journeys
        └─ LSOAs served      → population + deprivation decile (English IoD 2019)   ← equity
   → (live mode) validate severity via the nearest JamCam + Nemotron-VL
   → ripple footprint + impact numbers on the HUD
```

The cascade engine (`backend/ripple.py`) is **dual-path**, mirroring our cuDF join: **cuGraph/cuDF
on a GPU** (DGX Spark or a cloud RAPIDS GPU) and a **networkx/pandas CPU fallback** elsewhere —
*identical code*. The inner-London road graph (OSMnx, ~21.9k nodes / 50.5k edges), bus stops (TfL
StopPoint), and the LSOA deprivation + population table (London IoD2019) are built once and cached.

## The NVIDIA stack

| Role | Model / library | NVIDIA |
|---|---|---|
| **Cascade graph BFS** | **RAPIDS cuGraph** (GPU) · networkx CPU fallback | ✅ |
| Impact + disruption spatial joins | **RAPIDS cuDF / cuPy** (GPU) · NumPy/pandas fallback | ✅ |
| Perception / validation (detector) | **Nemotron-Nano-12B-v2-VL** (FP8) on **vLLM** | ✅ |
| Operator briefing | **NVIDIA Nemotron** | ✅ |
| Compute | **DGX Spark GB10** (local) · cloud RAPIDS GPU + **H100** (failover) | ✅ |

**The Spark story:** the GB10 Grace Blackwell superchip's **128 GB of unified memory** holds the
full London road graph, the demographics tables, *and* the VL-model context at once — graph BFS and
vision inference run locally, no cloud round-trip, no data leaving the premises. Cascades complete
in **~0.6 s** over ~22k nodes; the camera VL classifies frames concurrently and vLLM reuses ~96% of
vision features across sweeps via its multimodal cache.

**Portability (one env var each):** the VL model is OpenAI-compatible (`AEGIS_VL_OPENAI_URL`); the
cascade engine runs **locally** or proxies to a remote GPU (`AEGIS_RIPPLE_URL`). On the Spark, both
run on-box (cuGraph + cuDF). On a laptop, point them at a cloud RAPIDS GPU (`modal_ripple.py`) +
Modal H100 (`modal_vllm.py`). **Migrating to the Spark = unset `AEGIS_RIPPLE_URL`** → the same
`ripple.py` runs cuGraph locally. Nothing else changes.

## Responsible use (non-negotiable)

The perception layer classifies **road and traffic conditions only** — **no facial recognition, no
number-plate reading, no tracking** of any individual or vehicle across frames. The VL prompt
constrains the model to aggregate road conditions and forbids describing or counting people. This
is the legal/ethical line (UK GDPR, Open Government Licence) and a deliberate design choice. Ripple's
demographics are **area-level** (LSOA, ~1,500 residents) — never individuals.

---

## Aegis — the perception layer

Aegis applies a VL model to London's public JamCams, producing a timestamped, geolocated incident
log and a control-room map, and cross-references it against TfL's official feed to surface
conditions the feed doesn't yet list ("ahead of the feed"). Under Ripple it doubles as the live
footage-validation step.

- **Live map** of every available camera, recoloured by current condition.
- **VL classification** into `clear · congestion · accident · stalled_vehicle · hazard · obscured`,
  with confidence + a one-line description. The whole ~795-camera network is on the map while a
  **rolling window** (`SWEEP_BATCH` cameras every `BATCH_INTERVAL`) is classified — full coverage at
  bounded GPU cost.
- **Incident log** persisted append-only to `data/incidents.jsonl`.
- **Cross-reference** vs the official TfL feed (GPU spatial join): per incident, "✓ in feed" or
  "⚡ not in feed", plus a lead time when we saw it first.
- **Operator briefing** — a periodic plain-English situational summary from an NVIDIA Nemotron model.

## Architecture

```
Browser HUD (Leaflet map · cascade/planning panel · incident log · lead-time banner · briefing)
   │  POST /api/cascade           GET /api/cameras /api/states /api/incidents /api/insight /api/briefing
   ▼
FastAPI backend (backend/)
  • ripple.py       causal cascade engine — OSMnx graph, cuGraph BFS (cuDF), bus stops, LSOA equity
  • detector.py     async rolling-window sweep: fetch frame → VL classify (bounded concurrency)
  • vl.py           VL + briefing clients; backends "ollama" | "openai" (vLLM/llama.cpp/Modal/NIM)
  • disruptions.py  official-feed poller + spatial/temporal cross-reference
  • geo.py          RAPIDS cuDF/cuPy nearest-neighbour join (NumPy CPU fallback)
  • briefing.py     periodic control-room briefing (NVIDIA Nemotron)
  • store.py / tfl.py / config.py
   │                        │                         │                          │
   ▼                        ▼                         ▼                          ▼
 OSMnx road graph      TfL JamCams API          TfL Road Disruptions      VLM endpoint (OpenAI-compatible)
 + TfL StopPoint       (+ S3 JPEG frames)       (official ground truth)   Nemotron-Nano-VL @ vLLM/Modal/NIM
 + London IoD2019                                                          (or Qwen3-VL @ Ollama, fallback)
       │
       ▼
 Ripple GPU engine: local (cuGraph on the Spark) OR modal_ripple.py (cloud RAPIDS L4)
```

## Data sources (all free, Open Government Licence / open data)

- **TfL JamCams** — `GET https://api.tfl.gov.uk/Place/Type/JamCam` (camera list + S3 JPEGs)
- **TfL Road Disruptions** — `GET https://api.tfl.gov.uk/Road/all/Disruption` (ground truth)
- **TfL StopPoint** — bus stops + routes near a point (tiled to cover inner London)
- **OSMnx / OpenStreetMap** — the drivable road graph
- **English Indices of Deprivation 2019 (London)** — LSOA deprivation decile + population
- **postcodes.io** — reverse-geocode bus stops → LSOA

A free `TFL_APP_KEY` raises rate limits (needed for the bus-stop grid).

## Run it

The app backend runs anywhere (CPU fallbacks for both cuGraph and cuDF); GPUs accelerate the
**cascade** (cuGraph) and the **VLM**.

**A — On a GPU box (DGX Spark / cloud RAPIDS GPU): everything on-box**
```bash
pip install -r requirements.txt          # + RAPIDS (cudf/cugraph) present on the Spark
bash vllm_serve.sh start                 # Nemotron-Nano-VL (FP8) on vLLM, OpenAI API at :8090
AEGIS_VL_BACKEND=openai AEGIS_VL_MODEL=nemotron-nano-vl \
  TFL_APP_KEY=<key> bash serverctl.sh start
# AEGIS_RIPPLE_URL is unset → cuGraph runs locally on the Spark.  open http://<host>:8000
```

**B — Laptop + cloud GPUs (cascade on a Modal RAPIDS L4, VLM on a Modal H100)**
```bash
modal deploy modal_ripple.py             # -> https://<ws>--aegis-ripple-ripple-cascade.modal.run
modal deploy modal_vllm.py               # -> https://<ws>--aegis-vllm-serve.modal.run/v1
TFL_APP_KEY=<key> \
  AEGIS_RIPPLE_URL=https://<ws>--aegis-ripple-ripple-cascade.modal.run \
  AEGIS_VL_BACKEND=openai AEGIS_VL_OPENAI_URL=https://<ws>--aegis-vllm-serve.modal.run/v1 \
  AEGIS_VL_MODEL=nemotron-nano-vl \
  AEGIS_BRIEFING_BACKEND=openai AEGIS_BRIEFING_URL=https://<ws>--aegis-vllm-serve.modal.run/v1 \
  AEGIS_BRIEFING_MODEL=nemotron-nano-vl AEGIS_CAMERA_LIMIT=30 \
  .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000   # macOS (no setsid)
```

**C — Fallback: Qwen3-VL via Ollama; cascade on CPU (networkx)** — `AEGIS_VL_BACKEND=ollama AEGIS_VL_MODEL=qwen3.6`.

Helpers: `serverctl.sh {start|stop|restart|status|log}`, `vllm_serve.sh {…}`, `sync.sh` (rsync to a
remote box). Validate a VLM endpoint with `python scripts/classify_modal.py <base_url>/v1` (stdlib).

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `AEGIS_RIPPLE_URL` | — | If set, proxy `/api/cascade` to a remote GPU engine (Modal cuGraph). Unset → local engine (cuGraph on the Spark) |
| `AEGIS_RIPPLE_RADIUS` / `AEGIS_RIPPLE_HOPS` | `6000` / `15` | Road-graph radius (m) and BFS hop depth for a cascade |
| `AEGIS_VL_BACKEND` / `AEGIS_VL_MODEL` | `ollama` / `qwen3.6` | Detector serving + model (`openai` for vLLM/Modal/NIM) |
| `AEGIS_VL_OPENAI_URL` | `http://localhost:8090/v1` | OpenAI-compatible VLM endpoint |
| `AEGIS_BRIEFING_BACKEND` / `_URL` / `_MODEL` | `openai` / `:30000/v1` / `nemotron-3-nano-30b` | Briefing serving + model |
| `AEGIS_CAMERA_LIMIT` | all | Camera universe shown on the map (subset keeps the demo snappy) |
| `AEGIS_SWEEP_BATCH` / `AEGIS_BATCH_INTERVAL` | `40` / `12` | Rolling-window: cameras per batch / seconds between batches |
| `AEGIS_CONCURRENCY` | `8` | Parallel VL calls in flight |
| `TFL_APP_KEY` | — | TfL key (raises rate limits; needed for the bus-stop grid) |
| `AEGIS_REPLAY` | `0` | Serve saved snapshot frames for an offline demo |

## API

| Endpoint | Returns |
|---|---|
| `POST /api/cascade` `{lat,lon,hops}` | **Ripple cascade**: affected junctions/stops/routes/journeys, population, deprived-neighbourhood count, ripple footprint, engine (cuGraph/networkx) |
| `GET /api/ripple/status` | cascade engine readiness + BFS backend + graph size |
| `GET /api/health` | status, detector backend/model, briefing model, spatial backend, scan progress |
| `GET /api/cameras` · `/api/frame/{id}` · `/api/states` | camera registry · live JPEG · category map |
| `GET /api/incidents` · `/api/insight` · `/api/briefing` · `/api/disruptions` | log · cross-reference · briefing · official feed |

## Repository layout

```
backend/        FastAPI app + Ripple cascade engine (ripple.py), detector, VL/briefing, cross-reference, geo join
frontend/       Leaflet HUD (cascade/planning panel, incident log, lead-time banner, briefing)
scripts/        ripple_spike (cascade de-risk) + smoke + single-frame classify + endpoint validation
modal_ripple.py Modal app: Ripple cascade engine on a RAPIDS L4 GPU (cuGraph + cuDF)
modal_vllm.py   Modal app: Nemotron-Nano-VL (FP8) on vLLM, OpenAI-compatible (cloud failover)
vllm_serve.sh   Serve the NVIDIA VLM on a GPU box via vLLM (incl. DGX Spark CUDA notes)
serverctl.sh    Start/stop/restart the app server   ·   sync.sh  rsync the project to a remote box
```
