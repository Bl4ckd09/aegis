# Aegis — London Traffic Incident HUD

**An operational HUD that watches London's public traffic-camera network with a
vision-language model, detects and logs road incidents (congestion, accidents, stalled
vehicles, hazards) without identifying any individuals, flags them on a live map, and
cross-references them against TfL's official feed — surfacing conditions the official
feed doesn't yet list.**

Built for **Hack for Impact London (presented by NVIDIA)**. Designed to run **locally on an
NVIDIA DGX Spark** (no cloud, no images leaving the premises); the serving layer is
OpenAI-compatible, so the *identical* NVIDIA model stack also runs on a cloud GPU (e.g.
Modal H100) for failover — switching is one environment variable.

---

## Why it matters

London's Traffic Control Centre has 880+ public JamCams, but no human can watch them all,
and official disruption reports lag the event on the ground. Aegis applies a VL model to
every available camera frame, producing a timestamped, geolocated, source-cited incident
log and a control-room map. Its official-feed cross-reference shows, in real time, how many
live conditions Aegis sees that TfL's feed does **not** yet list ("ahead of the feed"), and
corroborates the ones it does.

## What it does

- **Live map** of every available camera, recoloured by current condition.
- **VL classification** of each frame into a fixed set: `clear · congestion · accident ·
  stalled_vehicle · hazard · obscured`, with a confidence and a one-line description.
- **Incident log** (scrollable, with thumbnails) persisted append-only to `data/incidents.jsonl`.
- **Cross-reference** vs the official TfL disruption feed (GPU spatial join): per incident,
  "✓ in official feed" or "⚡ not in official feed", plus a lead-time when we saw it first.
- **Operator briefing** — a periodic plain-English situational summary from an NVIDIA Nemotron model.

## Responsible use (non-negotiable)

Aegis classifies **road and traffic conditions only**. It performs:

- **no facial recognition**
- **no number-plate reading**
- **no tracking** of any individual or vehicle across frames

The VL prompt explicitly constrains the model to describe road conditions in aggregate and
forbids describing or counting people. This boundary is both the legal/ethical line
(UK GDPR, Open Government Licence terms) and a deliberate design choice.

## The NVIDIA stack

| Role | Model / library | NVIDIA |
|---|---|---|
| Perception (detector) | **Nemotron-Nano-12B-v2-VL** (FP8) on **vLLM** | ✅ |
| Operator briefing | **NVIDIA Nemotron** (Nemotron-3 via llama.cpp, or Nemotron-VL) | ✅ |
| Disruption spatial join | **RAPIDS cuDF / cuPy** (GPU), NumPy CPU fallback | ✅ |
| Compute | **DGX Spark GB10** (local) or **H100** (cloud failover) | ✅ |

**The Spark story:** the GB10 Grace Blackwell superchip with **128 GB of unified memory**
holds many live frames and the full VL-model context at once and runs the model on every
frame locally — no cloud round-trip, no images leaving the premises. Frames are classified
concurrently, so a sweep costs ~`ceil(N / concurrency)` inferences, not N sequential calls.

The detector is **pluggable** behind an OpenAI-compatible interface, so the same code runs
the NVIDIA VLM on vLLM (Spark or cloud), on Modal, or on an NVIDIA NIM — and keeps a proven
Qwen3-VL-via-Ollama fallback. Migrating between them is a single env var (`AEGIS_VL_OPENAI_URL`).

## Architecture

```
Browser HUD (Leaflet map · incident log · lead-time banner · operator briefing)
        │  polls /api/cameras /api/states /api/incidents /api/insight /api/briefing
        ▼
FastAPI backend (backend/)  — no GPU required; orchestrates HTTP + the spatial join
  • tfl.py          JamCam list, frame proxy, road-disruption feed
  • detector.py     async sweep: fetch frame → VL classify (bounded concurrency)
  • vl.py           VL + briefing clients; backends: "ollama" (native) | "openai" (vLLM/llama.cpp/Modal/NIM)
  • store.py        in-memory state + append-only data/incidents.jsonl
  • disruptions.py  official-feed poller + spatial/temporal cross-reference
  • geo.py          RAPIDS cuDF/cuPy nearest-neighbour join (NumPy CPU fallback)
  • briefing.py     periodic control-room briefing (NVIDIA Nemotron)
        │                         │                              │
        ▼                         ▼                              ▼
  TfL JamCams API          TfL Road Disruption API     VLM endpoint (OpenAI-compatible)
  (+ S3 JPEG frames)       (official ground truth)     Nemotron-Nano-VL @ vLLM / Modal / NIM
                                                       (or Qwen3-VL @ Ollama, fallback)
```

## Data sources (all free, Open Government Licence)

- **TfL JamCams** — `GET https://api.tfl.gov.uk/Place/Type/JamCam` (camera list + S3 JPEGs)
- **TfL Road Disruptions** — `GET https://api.tfl.gov.uk/Road/all/Disruption` (ground truth)

An optional free `TFL_APP_KEY` raises rate limits; not required for a demo.

## Run it

The app backend needs **no GPU** (the cuDF join falls back to NumPy), so it can run anywhere;
only the **VLM** needs a GPU. Three deployment modes:

**A — On a GPU box (DGX Spark or cloud GPU VM): serve the NVIDIA VLM with vLLM + run the app**
```bash
bash vllm_serve.sh start        # Nemotron-Nano-VL (FP8) on vLLM, OpenAI API at :8090
AEGIS_VL_BACKEND=openai AEGIS_VL_MODEL=nemotron-nano-vl bash serverctl.sh start
# open http://<host>:8000
```

**B — VLM on Modal (cloud) + app anywhere (e.g. a laptop)**
```bash
modal deploy modal_vllm.py      # -> https://<workspace>--aegis-vllm-serve.modal.run/v1
AEGIS_VL_BACKEND=openai \
  AEGIS_VL_OPENAI_URL=https://<workspace>--aegis-vllm-serve.modal.run/v1 \
  AEGIS_VL_MODEL=nemotron-nano-vl \
  AEGIS_BRIEFING_BACKEND=openai AEGIS_BRIEFING_URL=<same>/v1 AEGIS_BRIEFING_MODEL=nemotron-nano-vl \
  AEGIS_CAMERA_LIMIT=30 bash serverctl.sh start
```

**C — Fallback: Qwen3-VL via Ollama** (the default backend)
```bash
AEGIS_VL_BACKEND=ollama AEGIS_VL_MODEL=qwen3.6 bash serverctl.sh start
```

Helpers: `serverctl.sh {start|stop|restart|status|log}` (app), `vllm_serve.sh {start|stop|status|log}`
(vLLM detector), `sync.sh` (rsync repo to a remote box). `serverctl.sh` uses `setsid` (Linux);
on macOS run `uvicorn backend.main:app` directly. Validate a VLM endpoint with
`python scripts/classify_modal.py <base_url>/v1` (stdlib only).

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `AEGIS_VL_BACKEND` | `ollama` | Detector serving: `ollama` (native `/api/chat`) or `openai` (vLLM / llama.cpp / Modal / NIM) |
| `AEGIS_VL_MODEL` | `qwen3.6` | Model tag / served-model-name |
| `AEGIS_VL_OPENAI_URL` | `http://localhost:8090/v1` | OpenAI-compatible VLM endpoint (when backend = `openai`) |
| `AEGIS_BRIEFING_BACKEND` | `openai` | Briefing serving: `openai` or `ollama` |
| `AEGIS_BRIEFING_URL` | `http://localhost:30000/v1` | OpenAI-compatible text endpoint for briefings |
| `AEGIS_BRIEFING_MODEL` | `nemotron-3-nano-30b` | Briefing model name |
| `AEGIS_CAMERA_LIMIT` | all | Cameras to actively monitor (a subset keeps the demo snappy) |
| `AEGIS_CONCURRENCY` | `8` | Parallel VL calls in flight |
| `AEGIS_POLL_INTERVAL` | `180` | Seconds between camera sweeps (JamCams refresh ~3 min) |
| `AEGIS_BRIEFING_INTERVAL` | `120` | Seconds between briefings |
| `AEGIS_MATCH_RADIUS_M` | `300` | Max distance (m) to match an official disruption |
| `TFL_APP_KEY` | — | Optional; raises TfL rate limits |
| `AEGIS_REPLAY` | `0` | Serve saved snapshot frames for an offline demo |

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | status, detector backend/model, briefing model, spatial backend, scan progress |
| `GET /api/cameras` | monitored camera registry |
| `GET /api/frame/{id}` | live JPEG for a camera |
| `GET /api/states` | camera_id → current category (map colours) |
| `GET /api/incidents` | current non-clear detections (the log) |
| `GET /api/insight` | cross-reference: matched / not-in-feed / best lead time |
| `GET /api/briefing` | latest plain-English operator briefing |
| `GET /api/disruptions` | official TfL disruptions |

## Repository layout

```
backend/        FastAPI app, detector loop, VL/briefing clients, store, cross-reference, geo join
frontend/       Leaflet control-room HUD (index.html, app.js, style.css)
scripts/        smoke + single-frame classify + endpoint validation + nearest-disruption diagnostics
modal_vllm.py   Modal app: Nemotron-Nano-VL (FP8) on vLLM, OpenAI-compatible (cloud failover)
vllm_serve.sh   Serve the NVIDIA VLM on a GPU box via vLLM (incl. DGX Spark CUDA notes)
serverctl.sh    Start/stop/restart the app server
sync.sh         rsync the project to a remote box
```
