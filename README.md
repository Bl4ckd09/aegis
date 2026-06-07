# Access Health — disruption early-warning for London small businesses

**Access Health tells a London small-business owner what's threatening access to their shop *right
now*.** Drop a pin on your business and it computes your **accessibility catchment** with a **GPU graph
BFS (RAPIDS cuGraph)** — the roads, bus stops, routes and residents that feed it — then overlays **live
disruption signals** on that catchment: **TfL tube/rail status, bus-route status, nearby roadworks, and
weather**. The result is an **access-health score** and a list of **plain, attributed warnings** an owner
can act on — including the **cascade-effect** insight they can't see themselves:
*"~28% of your catchment is reached past the works disruption 411 m away."*

At **city scale**, it batch-cascades **all of today's live disruptions** (road + tube + bus,
severity-weighted) over **~25k high-street businesses** on the GPU to produce a live **high-street
access-health map** — which neighbourhoods are impaired, **weighted by deprivation** — plus the
**chokepoint "lifeline" junctions** (RAPIDS cuGraph **betweenness centrality**) the most businesses
depend on. A warning tool for one owner; a **public-good instrument** for councils and BIDs.

Built for **Hack for Impact London (presented by NVIDIA)**. Designed to run **locally on an NVIDIA DGX
Spark** — the road graph and the vision model co-resident in 128 GB of unified memory; every NVIDIA
component is one env var, so the same stack also runs on a cloud RAPIDS GPU + Modal H100.

> ### The three names
> - **Access Health** — the product / the HUD an owner uses (this app's brand).
> - **Ripple** — the catchment + cascade **engine** (`backend/ripple.py`) underneath it.
> - **Aegis** — the **camera-perception** layer (and the FastAPI backend package, `backend/`), which
>   doubles as the *"validate the disruption with live footage"* layer and gives the repo/app its title.

---

## Part of a two-app suite for London SMBs

This repo ships **both halves** of the same idea — *what a small business can't see but a GPU can join
for it* — cross-linked in the UI:

| App | Question it answers | Lives in | Default port |
|---|---|---|---|
| **Access Health** (this README) | *"What's threatening access to my shop **right now**?"* — transport/weather disruption | repo root (`backend/`, `frontend/`) | `:8000` |
| **STELLA — Financial Health** | *"What government money am I **owed** and not claiming?"* — business-rates relief + grants | [`ledger/`](ledger/) | `:5000` |

The HUD's header links across to the sibling app (host-relative `//<host>:5000`), so over an SSH tunnel
or a public IP with both ports open the two feel like one product. STELLA is documented separately in
[`ledger/PROGRESS.md`](ledger/PROGRESS.md), [`ledger/PRD.md`](ledger/PRD.md) and
[`ledger/PROJECT_BIBLE.md`](ledger/PROJECT_BIBLE.md).

---

## The problem

A road closure, a tube line part-suspended, a burst water main, a wet Saturday — each quietly cuts a
small business's footfall, deliveries and staff commute. Big chains have analysts for this; the corner
café doesn't. The signals are all public (TfL, weather) but **scattered and not joined to *your*
location**. Access Health joins them to your catchment and warns you, in plain language.

## What it does

- **Pick your business** (click the map) → it draws your **accessibility catchment** (BFS over the road
  graph) and the residents/stops/routes that feed it.
- **Access-health score (0–100)** with **attributed warnings**, each a named real signal:
  - 🚇 **tube/rail line status** (TfL) — *"District line — Part Closure"*
  - 🚌 **bus-route status** for the routes serving you — *"Bus 25 — Special Service"*
  - 🚧 **road disruptions** within your catchment, nearest first
  - 🌧 **weather** (Open-Meteo) — rain/cold footfall headwinds
  - 🌊 **cascade effect** — *"~28% of your catchment is reached past the works disruption 411 m away"*
- **No black-box footfall %.** Every penalty is a real, attributed signal — exposure/early-warning,
  not a fabricated prediction.

**At city scale (the collective, public-good view):**
- **Batch-cascades today's live disruptions** — road (full BFS ripple, radius scaled by severity) +
  disrupted tube/rail/bus lines (their stops/stations) — over ~25k businesses on the GPU.
- **High-street access-health map**, deprivation-weighted: which high streets are impaired, ranked,
  with the count of affected businesses in the **most-deprived 20%**.
- **Betweenness centrality** (cuGraph) → **"lifeline" junctions** the most businesses depend on (which
  to protect), and flags how many of today's disruptions sit on a critical chokepoint.

## How it works

**Per business (the pin):**

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

The catchment engine (`backend/ripple.py`) is **dual-path**: **cuGraph/cuDF on a GPU** (DGX Spark or a
cloud RAPIDS GPU), **networkx/pandas CPU fallback** elsewhere — *identical code*. The inner-London road
graph (OSMnx, ~21.9k nodes / ~50.5k edges), bus stops (TfL StopPoint) and the LSOA population +
deprivation table (London IoD2019) are built once and cached. The same engine also exposes a
planner-facing cascade (`POST /api/cascade`) — given a *disruption*, who's affected downstream.

**City scale (the collective view, `GET /api/highstreets`):**

```
today's live disruptions                          betweenness centrality (cuGraph, once)
  road  → BFS cascade (severity-scaled radius)        → chokepoint percentile per junction
  tube/bus (disrupted lines → stops/stations)         → "lifeline" junctions ranked by
        → local node impairment                          businesses depending on them
            │                                                     │
            └──────────────► severity-weighted node impairment ◄──┘
                              → aggregate ~25k businesses by LSOA high street
                              → access health + deprived-affected count + chokepoint flags
```

Both run on the same GPU engine; the city-scale pass is where the batch BFS + betweenness genuinely load
the GPU. Heavy data is cached, so the per-call cost is the live disruptions only (the result is also
cached server-side for 120 s).

## The NVIDIA stack

| Role | Model / library | NVIDIA |
|---|---|---|
| **Catchment + city-scale batch cascade (BFS)** | **RAPIDS cuGraph** (GPU) · networkx CPU fallback | ✅ |
| **Chokepoint analytics** | **RAPIDS cuGraph betweenness centrality** (GPU) | ✅ |
| Impact + spatial joins | **RAPIDS cuDF / cuPy** (GPU, `backend/geo.py`) · NumPy/pandas fallback | ✅ |
| Perception / footage validation | **Nemotron-Nano-12B-v2-VL** (FP8) on **vLLM** · `qwen3.6` on Ollama as fallback | ✅ |
| Operator briefing | **Nemotron-3-Nano-30B** on llama.cpp (OpenAI API `:30000`) | ✅ |
| Compute | **DGX Spark GB10** (local) · cloud RAPIDS L4 + **H100** (failover) | ✅ |

**Detector serving (pluggable).** Out of the box the detector is `qwen3.6` (Qwen3-VL) on **Ollama** —
the proven fallback (`AEGIS_VL_BACKEND=ollama`). The NVIDIA path serves
**`nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL`** on **vLLM** (OpenAI-compatible, `:8090`, served as
`nemotron-nano-vl`) via `vllm_serve.sh`; flip to it with `AEGIS_VL_BACKEND=openai`. Same code, same
prompts, same six-category output.

**The Spark story:** the GB10 Grace Blackwell superchip's **128 GB unified memory** holds the London road
graph, the demographics, *and* the vision model at once — catchment BFS and vision inference run locally,
no data leaving the premises. Catchments compute in **~0.6 s** over ~21.9k nodes (cuGraph).

**Portability (one env var each):** the catchment engine runs **locally** or proxies to a remote GPU
(`AEGIS_RIPPLE_URL`); the VL model is OpenAI-compatible (`AEGIS_VL_OPENAI_URL`). On the Spark, both run
on-box (cuGraph + cuDF). On a laptop, point them at a cloud RAPIDS L4 (`modal_ripple.py`) + Modal H100
(`modal_vllm.py`). **Migrating to the Spark = unset `AEGIS_RIPPLE_URL`** → the same code runs cuGraph
locally. Nothing else changes. See [`MIGRATION.md`](MIGRATION.md).

## Responsible use (non-negotiable)

The perception layer classifies **road and traffic conditions only** — **no facial recognition, no
number-plate reading, no tracking**. Demographics are **area-level** (LSOA, ~1,500 residents), never
individuals. Warnings are sourced from public open data (TfL, OSM, IoD2019, Open-Meteo).

---

## Aegis — the perception / validation layer

Aegis applies a VL model to London's public JamCams, producing a geolocated incident log + a control map,
and cross-references it against TfL's official feed ("ahead of the feed"). For Access Health it's the live
*footage-validation* of a disruption's severity.

- **VL classification** into `clear · congestion · accident · stalled_vehicle · hazard · obscured`,
  describing road conditions only — never people. The ~795-camera network is on the map while a **rolling
  window** is classified (`SWEEP_BATCH` cameras every `BATCH_INTERVAL` s) — full coverage at bounded GPU
  cost.
- **Cross-reference** vs the official TfL feed (GPU spatial join) for a lead-time "insight"; **operator
  briefing** generated by Nemotron-3-Nano-30B.

## Architecture

```
Browser HUD (Leaflet map · "your business — access health" panel · briefing · cameras · → Financial Health)
   │  POST /api/smb/exposure   POST /api/cascade   GET /api/highstreets
   │  GET /api/cameras /api/states /api/incidents /api/insight /api/briefing /api/disruptions /api/health
   ▼
FastAPI backend (backend/)
  • main.py         app + routes + AppState (cameras, detector, disruptions, briefing, ripple)
  • smb.py          SMB exposure: catchment + TfL tube/bus status + roadworks + weather → warnings; collective seeds
  • ripple.py       catchment/cascade/highstreets engine — OSMnx graph, cuGraph BFS (cuDF), bus stops, LSOA data
  • detector.py     async rolling-window camera sweep → VL classify (bounded concurrency)
  • vl.py · disruptions.py · geo.py · briefing.py · store.py · tfl.py · models.py · config.py
   │              │                  │                    │                   │
   ▼              ▼                  ▼                    ▼                   ▼
 OSMnx graph   TfL StopPoint     TfL Line status      TfL Road Disruptions  Open-Meteo   VLM endpoint
 + IoD2019     (bus stops)       (tube + bus, live)   (official feed)       (weather)    Nemotron-VL @ vLLM/Modal
   │
   ▼
 catchment engine: local (cuGraph on the Spark / CPU fallback) OR modal_ripple.py (cloud RAPIDS L4)
```

## Data sources (all free, Open Government Licence / open data)

- **OSMnx / OpenStreetMap** — drivable road graph
- **TfL StopPoint** — bus stops + routes; **TfL Line status** — live tube/rail + bus disruptions
- **TfL Road Disruptions** — `Road/all/Disruption`; **TfL JamCams** — `Place/Type/JamCam` (+ S3 JPEGs)
- **English Indices of Deprivation 2019 (London)** — LSOA population + deprivation
- **postcodes.io** — reverse-geocode stops → LSOA; **Open-Meteo** — weather (no key)

A free `TFL_APP_KEY` raises rate limits (needed for the bus-stop grid + live status calls).

## Run it

GPUs accelerate the **catchment** (cuGraph) and the **VLM**; everything has a CPU/Ollama fallback. Python
deps are in `requirements.txt` (FastAPI, uvicorn, httpx, pydantic, osmnx, scikit-learn, openpyxl); RAPIDS
`cudf`/`cugraph` are **system packages** on the GPU box, picked up via a `--system-site-packages` venv.

**A — On a GPU box (DGX Spark / cloud RAPIDS GPU): everything on-box**
```bash
bash vllm_serve.sh start                 # Nemotron-Nano-VL (FP8) on vLLM, OpenAI API at :8090
# operator briefing uses Nemotron-3-Nano-30B on llama.cpp at :30000 (shared) — optional
AEGIS_VL_BACKEND=openai AEGIS_VL_MODEL=nemotron-nano-vl \
  AEGIS_VL_OPENAI_URL=http://localhost:8090/v1 TFL_APP_KEY=<key> \
  bash serverctl.sh start                # setsid uvicorn :8000, survives the SSH session
# AEGIS_RIPPLE_URL unset → cuGraph runs locally on the Spark.  open http://<host>:8000
bash serverctl.sh status|log|restart|stop
```
`run.sh` is the simpler foreground equivalent (`./run.sh`); `serverctl.sh` is the detached daemon.

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

Offline demo: set `AEGIS_REPLAY=1` to seed incidents from a cached snapshot if the venue network dies.
A full live walkthrough is in [`DEMO.md`](DEMO.md).

### Configuration (key environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `AEGIS_RIPPLE_URL` | — | Proxy the catchment to a remote GPU engine (Modal cuGraph). Unset → local (cuGraph on the Spark / CPU) |
| `AEGIS_RIPPLE_RADIUS` / `AEGIS_RIPPLE_HOPS` | `6000` / `15` | Road-graph radius (m) and BFS hop depth |
| `TFL_APP_KEY` | — | TfL key (raises rate limits; needed for stops + live status) |
| `AEGIS_VL_BACKEND` / `AEGIS_VL_MODEL` / `AEGIS_VL_OPENAI_URL` | `ollama` / `qwen3.6` / `…:8090/v1` | Detector serving + model (set `openai` + `nemotron-nano-vl` for the NVIDIA path) |
| `AEGIS_BRIEFING_BACKEND` / `AEGIS_BRIEFING_URL` / `AEGIS_BRIEFING_MODEL` | `openai` / `…:30000/v1` / `nemotron-3-nano-30b` | Operator-briefing serving + model |
| `AEGIS_SWEEP_BATCH` / `AEGIS_BATCH_INTERVAL` | `40` / `12` | Camera rolling-window batch size / interval (s) |
| `AEGIS_CAMERA_LIMIT` / `AEGIS_CONCURRENCY` | all / `8` | Cap the camera universe / parallel VL calls in flight |
| `AEGIS_REPLAY` | `0` | `1` = offline replay from a snapshot |

## API

| Endpoint | Returns |
|---|---|
| `POST /api/smb/exposure` `{lat,lon,hops}` | **SMB early-warning**: access-health, attributed warnings (tube/bus/roads/weather/cascade), catchment, engine |
| `GET /api/highstreets` | **city-scale collective view**: per-high-street access health (deprivation-weighted), worst-hit ranking, betweenness chokepoint "lifelines", multi-modal totals (cached 120 s) |
| `POST /api/cascade` `{lat,lon,hops}` | planner cascade: who's affected downstream of a disruption (the engine under SMB exposure) |
| `GET /api/ripple/status` | catchment engine readiness + BFS backend + graph/stop counts |
| `GET /api/insight` | cross-reference headline: official count, matched, conditions **not** in the feed, best lead time |
| `GET /api/health` | service + detector/briefing model + spatial backend + scan/sweep/incident counters |
| `GET /api/cameras` · `/api/frame/{id}` · `/api/states` · `/api/incidents` · `/api/briefing` · `/api/disruptions` | perception layer (Aegis): camera registry, live JPEG proxy, marker states, incident log, briefing text, official road disruptions |

## Repository layout

```
backend/        FastAPI app · main.py (routes) · smb.py (exposure) · ripple.py (catchment/cascade/highstreets engine)
                · detector.py · vl.py · disruptions.py · geo.py (cuDF spatial join) · briefing.py · store.py · tfl.py · config.py
frontend/       Leaflet HUD — "your business — access health" panel + warnings, camera layer, → Financial Health link
ledger/         STELLA — the sibling "Financial Health" app (business-rates relief + grants); its own Flask server on :5000
scripts/        offline/eval helpers — classify_file/classify_modal, snapshot, ripple_spike, nearest, smoke
modal_ripple.py Modal app: catchment engine on a RAPIDS L4 GPU (cuGraph + cuDF)
modal_vllm.py   Modal app: Nemotron-Nano-12B-v2-VL (FP8) on vLLM, H100 (cloud failover)
vllm_serve.sh · serverctl.sh · run.sh · sync.sh   serve the VLM / run the app (daemon or foreground) / rsync to hp15
DEMO.md · MIGRATION.md · HANDOFF.md               demo script · Spark migration checklist · session handoff
```
