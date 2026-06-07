# Aegis — London Traffic Incident HUD

**A locally-run operational HUD that watches London's public traffic-camera network with a
vision-language model, detects and logs road incidents (congestion, accidents, stalled
vehicles, hazards) without identifying any individuals, and flags them on a live map —
often surfacing conditions before they appear in TfL's official disruption feed.**

Built for **Hack for Impact London (presented by NVIDIA)** and runs entirely on a single
**NVIDIA DGX Spark** — no cloud, no images leaving the premises.

---

## Why it matters

London's Traffic Control Centre has 880+ public JamCams, but no human can watch them all,
and official disruption reports lag the event on the ground. Aegis applies a VL model to
every camera frame, producing a timestamped, geolocated, source-cited incident log and a
control-room map. Its official-feed cross-reference shows, in real time, how many live
conditions Aegis sees that the official TfL feed does **not** yet list.

## Responsible use (non-negotiable)

Aegis classifies **road and traffic conditions only**. It performs:

- **no facial recognition**
- **no number-plate reading**
- **no tracking** of any individual or vehicle across frames

The VL prompt explicitly constrains the model to describe road conditions in aggregate and
forbids describing or counting people. All inference is local. This boundary is both the
legal/ethical line (UK GDPR, Open Government Licence terms) and a deliberate design choice.

## The NVIDIA Spark story

The DGX Spark's **GB10 Grace Blackwell** superchip with **128 GB of unified memory** lets
Aegis hold dozens of live camera frames and the full VL-model context simultaneously, and
run a 36B-parameter vision-language model (**Qwen3-VL**, served locally via Ollama) on every
frame — with **no cloud round-trip and no images leaving the premises**. Frames are
classified concurrently across the GPU, so a sweep costs roughly `ceil(N / concurrency)`
inferences rather than N sequential calls. A control room gets local, private, low-latency
situational awareness on commodity-desk hardware.

## Architecture

```
Browser HUD (Leaflet map + incident log + lead-time banner + operator briefing)
        │  polls /api/cameras /api/states /api/incidents /api/insight /api/briefing
        ▼
FastAPI backend (backend/)
  • tfl.py          JamCam list, frame proxy, road-disruption feed
  • detector.py     async sweep: fetch frame → VL classify (bounded concurrency)
  • vl.py           local Qwen3-VL via Ollama (anonymized prompt + JSON schema)
  • store.py        in-memory state + append-only data/incidents.jsonl
  • disruptions.py  official-feed poller + spatial/temporal cross-reference
  • briefing.py     periodic plain-English control-room briefing (local text model)
        │                         │                          │
        ▼                         ▼                          ▼
  TfL JamCams API          TfL Road Disruption API     Qwen3-VL @ localhost:11434
  (+ S3 JPEG frames)       (official ground truth)     (Ollama, OpenAI-compatible)
```

## Data sources (all free, Open Government Licence)

- **TfL JamCams** — `GET https://api.tfl.gov.uk/Place/Type/JamCam` (camera list + S3 JPEGs)
- **TfL Road Disruptions** — `GET https://api.tfl.gov.uk/Road/all/Disruption` (ground truth)

An optional free `TFL_APP_KEY` raises rate limits; not required for a demo.

## Run it

The backend runs on the Spark (where the GPU + Ollama live). From a dev machine:

```bash
./sync.sh                       # rsync this repo to hp15:~/aegis
ssh hp15 'cd ~/aegis && bash serverctl.sh start'   # creates venv, installs deps, launches
# open http://hp-15.local:8000
```

`serverctl.sh {start|stop|restart|status|log}` manages the detached server.

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `AEGIS_VL_MODEL` | `qwen3.6` | Ollama vision model tag |
| `AEGIS_CAMERA_LIMIT` | all | Cameras to actively monitor (subset keeps demo snappy) |
| `AEGIS_CONCURRENCY` | `8` | Parallel VL calls in flight |
| `AEGIS_POLL_INTERVAL` | `180` | Seconds between camera sweeps (JamCams refresh ~3 min) |
| `AEGIS_MATCH_RADIUS_M` | `300` | Max distance to match an official disruption |
| `AEGIS_REPLAY` | `0` | Serve saved snapshot frames for offline demo |

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | model, camera counts, scan progress |
| `GET /api/cameras` | monitored camera registry |
| `GET /api/frame/{id}` | live JPEG for a camera |
| `GET /api/states` | camera_id → current category (map colours) |
| `GET /api/incidents` | current non-clear detections (the log) |
| `GET /api/insight` | cross-reference: matched / not-in-feed / best lead time |
| `GET /api/briefing` | latest plain-English operator briefing |
| `GET /api/disruptions` | official TfL disruptions |
