# Ripple — disruption early-warning for London small businesses (built on Aegis)

**Ripple tells a London small-business owner what's threatening access to their shop *right now*.**
Drop a pin on your business and Ripple computes its **accessibility catchment** with a **GPU graph
BFS (RAPIDS cuGraph)** — the roads, bus stops, routes and residents that feed it — then overlays
**live disruption signals** on that catchment: **TfL tube/rail status, bus-route status, nearby
roadworks, and weather**. The result is an **access-health score** and a list of **plain, attributed
warnings** an owner can act on — including the **cascade-effect** insight they can't see themselves:
*"~28% of your catchment is reached past the works disruption 400 m away."*

Built for **Hack for Impact London (presented by NVIDIA)**. Designed to run **locally on an NVIDIA
DGX Spark** — the road graph and the vision model co-resident in 128 GB of unified memory; every
NVIDIA component is one env var, so the same stack also runs on a cloud RAPIDS GPU + Modal H100.

> Ripple is built on **Aegis**, our camera-perception HUD (documented below) — which doubles as the
> *"validate the disruption with live footage"* layer.

---

## The problem

A road closure, a tube line part-suspended, a burst water main, a wet Saturday — each quietly cuts a
small business's footfall, deliveries and staff commute. Big chains have analysts for this; the corner
café doesn't. The signals are all public (TfL, weather) but **scattered and not joined to *your*
location**. Ripple joins them to your catchment and warns you, in plain language.

## What Ripple does

- **Pick your business** (click the map) → Ripple draws your **accessibility catchment** (BFS over the
  road graph) and the residents/stops/routes that feed it.
- **Access-health score (0–100)** with **attributed warnings**, each a named real signal:
  - 🚇 **tube/rail line status** (TfL) — *"District line — Part Closure"*
  - 🚌 **bus-route status** for the routes serving you — *"Bus 25 — Special Service"*
  - 🚧 **road disruptions** within your catchment, nearest first
  - 🌧 **weather** (Open-Meteo) — rain/cold footfall headwinds
  - 🌊 **cascade effect** — *"~28% of your catchment is reached past the works disruption 411 m away"*
- **No black-box footfall %.** Every penalty is a real, attributed signal — exposure/early-warning,
  not a fabricated prediction.

## How it works

```
your business (map pin)
   → nearest road-graph node
   → BFS outward, k hops                 [RAPIDS cuGraph on GPU · networkx CPU fallback]
   → accessibility catchment (roads + bus stops + routes + resident LSOAs)
   → overlay live signals on the catchment:
        🚇 TfL tube/rail line status     🚌 bus-route status for serving routes
        🚧 road disruptions within it     🌧 weather (Open-Meteo)
        🌊 cascade effect: the nearby disruption that gates the largest share of the catchment
   → access-health score + attributed warnings on the HUD
```

The catchment engine (`backend/ripple.py`) is **dual-path**: **cuGraph/cuDF on a GPU** (DGX Spark or
a cloud RAPIDS GPU), **networkx/pandas CPU fallback** elsewhere — *identical code*. The inner-London
road graph (OSMnx, ~21.9k nodes / 50.5k edges), bus stops (TfL StopPoint) and the LSOA population +
deprivation table (London IoD2019) are built once and cached. The same engine also exposes a
planner-facing cascade (`POST /api/cascade`) — given a *disruption*, who's affected downstream.

## The NVIDIA stack

| Role | Model / library | NVIDIA |
|---|---|---|
| **Catchment graph BFS** | **RAPIDS cuGraph** (GPU) · networkx CPU fallback | ✅ |
| Impact + spatial joins | **RAPIDS cuDF / cuPy** (GPU) · NumPy/pandas fallback | ✅ |
| Perception / footage validation | **Nemotron-Nano-12B-v2-VL** (FP8) on **vLLM** | ✅ |
| Operator briefing | **NVIDIA Nemotron** | ✅ |
| Compute | **DGX Spark GB10** (local) · cloud RAPIDS GPU + **H100** (failover) | ✅ |

**The Spark story:** the GB10 Grace Blackwell superchip's **128 GB unified memory** holds the London
road graph, the demographics, *and* the vision model at once — catchment BFS and vision inference run
locally, no data leaving the premises. Catchments compute in **~0.6 s** over ~22k nodes (cuGraph).

**Portability (one env var each):** the catchment engine runs **locally** or proxies to a remote GPU
(`AEGIS_RIPPLE_URL`); the VL model is OpenAI-compatible (`AEGIS_VL_OPENAI_URL`). On the Spark, both run
on-box (cuGraph + cuDF). On a laptop, point them at a cloud RAPIDS GPU (`modal_ripple.py`) + Modal
H100 (`modal_vllm.py`). **Migrating to the Spark = unset `AEGIS_RIPPLE_URL`** → the same code runs
cuGraph locally. Nothing else changes.

## Responsible use (non-negotiable)

The perception layer classifies **road and traffic conditions only** — **no facial recognition, no
number-plate reading, no tracking**. Ripple's demographics are **area-level** (LSOA, ~1,500 residents),
never individuals. Warnings are sourced from public open data (TfL, OSM, IoD2019, Open-Meteo).

---

## Aegis — the perception / validation layer

Aegis applies a VL model to London's public JamCams, producing a geolocated incident log + a control
map, and cross-references it against TfL's official feed ("ahead of the feed"). For Ripple it's the
live *footage-validation* of a disruption's severity.

- **VL classification** into `clear · congestion · accident · stalled_vehicle · hazard · obscured`,
  describing road conditions only — never people. The ~795-camera network is on the map while a
  **rolling window** is classified (full coverage at bounded GPU cost).
- **Cross-reference** vs the official TfL feed (GPU spatial join); **operator briefing** from Nemotron.

## Architecture

```
Browser HUD (Leaflet map · "your business — access health" panel · briefing · cameras)
   │  POST /api/smb/exposure        GET /api/cameras /api/states /api/incidents /api/briefing
   ▼
FastAPI backend (backend/)
  • smb.py          SMB exposure: catchment + TfL tube/bus status + roadworks + weather → warnings
  • ripple.py       catchment/cascade engine — OSMnx graph, cuGraph BFS (cuDF), bus stops, LSOA data
  • detector.py     async rolling-window camera sweep → VL classify (bounded concurrency)
  • vl.py / disruptions.py / geo.py / briefing.py / store.py / tfl.py / config.py
   │              │                  │                    │                   │
   ▼              ▼                  ▼                    ▼                   ▼
 OSMnx graph   TfL StopPoint     TfL Line status      TfL Road Disruptions  Open-Meteo   VLM endpoint
 + IoD2019     (bus stops)       (tube + bus, live)   (official feed)       (weather)    Nemotron-VL @ vLLM/Modal
   │
   ▼
 catchment engine: local (cuGraph on the Spark) OR modal_ripple.py (cloud RAPIDS L4)
```

## Data sources (all free, Open Government Licence / open data)

- **OSMnx / OpenStreetMap** — drivable road graph
- **TfL StopPoint** — bus stops + routes; **TfL Line status** — live tube/rail + bus disruptions
- **TfL Road Disruptions** — `Road/all/Disruption`; **TfL JamCams** — `Place/Type/JamCam` (+ S3 JPEGs)
- **English Indices of Deprivation 2019 (London)** — LSOA population + deprivation
- **postcodes.io** — reverse-geocode stops → LSOA; **Open-Meteo** — weather (no key)

A free `TFL_APP_KEY` raises rate limits (needed for the bus-stop grid + live status calls).

## Run it

GPUs accelerate the **catchment** (cuGraph) and the **VLM**; everything has a CPU fallback.

**A — On a GPU box (DGX Spark / cloud RAPIDS GPU): everything on-box**
```bash
pip install -r requirements.txt          # + RAPIDS (cudf/cugraph) present on the Spark
bash vllm_serve.sh start                 # Nemotron-Nano-VL (FP8) on vLLM, OpenAI API at :8090
AEGIS_VL_BACKEND=openai AEGIS_VL_MODEL=nemotron-nano-vl TFL_APP_KEY=<key> bash serverctl.sh start
# AEGIS_RIPPLE_URL unset → cuGraph runs locally on the Spark.  open http://<host>:8000
```

**B — Laptop + cloud GPUs (catchment on a Modal RAPIDS L4, VLM on a Modal H100)**
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

### Configuration (key environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `AEGIS_RIPPLE_URL` | — | Proxy the catchment to a remote GPU engine (Modal cuGraph). Unset → local (cuGraph on the Spark) |
| `AEGIS_RIPPLE_RADIUS` / `AEGIS_RIPPLE_HOPS` | `6000` / `15` | Road-graph radius (m) and BFS hop depth |
| `TFL_APP_KEY` | — | TfL key (raises rate limits; needed for stops + live status) |
| `AEGIS_VL_BACKEND` / `AEGIS_VL_MODEL` / `AEGIS_VL_OPENAI_URL` | `ollama` / `qwen3.6` / `…:8090/v1` | Detector serving + model |
| `AEGIS_SWEEP_BATCH` / `AEGIS_BATCH_INTERVAL` | `40` / `12` | Camera rolling-window batch size / interval |

## API

| Endpoint | Returns |
|---|---|
| `POST /api/smb/exposure` `{lat,lon}` | **SMB early-warning**: access-health, attributed warnings (tube/bus/roads/weather/cascade), catchment, engine |
| `POST /api/cascade` `{lat,lon,hops}` | planner cascade: who's affected downstream of a disruption (the engine under SMB) |
| `GET /api/ripple/status` | catchment engine readiness + BFS backend + graph size |
| `GET /api/health` · `/api/cameras` · `/api/frame/{id}` · `/api/states` · `/api/incidents` · `/api/briefing` · `/api/disruptions` | perception layer (Aegis) |

## Repository layout

```
backend/        FastAPI app · smb.py (exposure) · ripple.py (catchment/cascade engine) · detector, VL, geo, store
frontend/       Leaflet HUD — "your business — access health" panel + warnings, camera layer
modal_ripple.py Modal app: catchment engine on a RAPIDS L4 GPU (cuGraph + cuDF)
modal_vllm.py   Modal app: Nemotron-Nano-VL (FP8) on vLLM (cloud failover)
vllm_serve.sh · serverctl.sh · sync.sh   serve VLM / run app / rsync to a remote box
```
