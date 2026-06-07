# Ripple — Demo Script & Walkthrough

A tight ~3-minute live demo for **Hack for Impact London (presented by NVIDIA)**.
Everything below reflects what the system actually does — no overclaiming.

---

## TL;DR (the elevator pitch — say this if you only get one sentence)
> "A road closure, a part-suspended tube line, a wet Saturday — each quietly cuts a London corner
> shop's footfall and deliveries, and the owner has no early warning. **Ripple** lets them drop a pin
> on their business and instantly see what's threatening access *right now* — tube, buses, roadworks,
> weather — as plain warnings, plus the bottleneck they can't see: *'28% of your catchment is reached
> past that closure.'* The catchment is a graph search on **NVIDIA RAPIDS cuGraph**, able to run
> **locally on a DGX Spark**."

---

## The signals to land (real output)
- **Whitechapel pin:** access health **low**, and the headline cascade insight —
  **🌊 "~28% of your catchment is reached past the works disruption 411 m away."**
- **Brick Lane pin:** **🚇 District line — Part Closure**, **🚌 buses 242/35/55/78 — Special Service**,
  roadworks within 600 m, weather — every warning a **named, real** signal.
- **Performance:** the catchment (BFS over **21,908** road nodes) computes in **~0.6 s** on **cuGraph (GPU)**.

---

## Pre-demo checklist (do this ~10 min before)
1. **Warm both Modal GPUs:** `curl -s https://<ws>--aegis-ripple-ripple-status.modal.run` → `"backend":"cuGraph (GPU)"`; `curl -s <modal-vllm>/v1/models`. (For safety set `min_containers=1` and redeploy.)
2. **Launch the backend** (README run mode B) with `TFL_APP_KEY` + `AEGIS_RIPPLE_URL` set.
3. **Warm the HUD:** open `http://127.0.0.1:8000` — title reads "RIPPLE", status dot green.
4. **One practice pin** so the cuGraph CUDA init (~one-time 20 s) is paid; pick a pin that shows a strong cascade-effect today (try Whitechapel / Mile End).
5. `curl -s localhost:8000/api/ripple/status` → `ready:true, backend:"cuGraph (GPU)"`.

---

## The 3-minute walkthrough

### 0:00 — The problem
**SAY:** *"Big chains have analysts watching for disruptions. The corner café doesn't — it just sees a
quiet day and doesn't know why. The signals are all public, but nobody joins them to *that shop's*
location. Ripple does."*
**DO:** Map of London; the **"Your business — access health"** panel top-right.

### 0:25 — Drop a pin (the hero moment)
**DO:** Click a business location (e.g. **Whitechapel**). The catchment draws (a blue footprint), and
the panel fills.
**SAY:** *"I dropped a pin on my shop. Ripple worked out my **catchment** — the roads, bus stops and
~17,000 residents that actually feed me — and scored my access health. And the headline:"*
(point at) **🌊 "~28% of your catchment is reached past the works disruption 411 m away."**
*"That's the bottleneck an owner can't see — a quarter of my customers are on the far side of that
closure."*

### 0:55 — The live warnings
**DO:** Read the warnings list.
**SAY:** *"And the live picture, every line a real signal: the **District line is part-closed**, **four
bus routes that serve me are on special service**, roadworks 600 m away, and rain this afternoon. No
black-box footfall guess — just what's actually happening around me, right now."*

### 1:25 — How (the NVIDIA stack + Spark story)
**SAY:** *"That catchment is a graph search over ~22,000 road nodes — on **RAPIDS cuGraph, on an NVIDIA
GPU**, in about **0.6 seconds**. Joins use **cuDF**, tube/bus status is live from TfL, weather from
Open-Meteo. On a **DGX Spark**, the road graph and the vision model live together in **128 GB of
unified memory** — it runs locally, nothing leaves the premises."* (point at **⚡ catchment via
cuGraph (GPU)**.)

### 1:55 — Validation layer (Aegis: click a camera)
**DO:** Click a camera marker → live frame.
**SAY:** *"And when a disruption is live, Ripple can **confirm it with the camera** — an **NVIDIA
Nemotron vision-language model** reads the road, **conditions only, never people**. So the warning
isn't just a feed entry; it's verified."*

### 2:25 — Close
**SAY:** *"So a small-business owner gets an early warning a chain would pay an analyst for — what's
hitting their footfall today and why — built on London's open data and NVIDIA's GPU stack, private
and local on a Spark."*

---

## Likely Q&A
- **"Is this a footfall prediction?"** — No. It's **exposure/early-warning**: every warning is a named,
  real signal (a TfL closure, a route on special service, roadworks, rain). We deliberately don't
  fabricate a footfall % we can't validate. The one modelled number, the cascade-effect %, is a clearly
  first-order graph measure ("share of catchment beyond the disruption").
- **"How is the catchment computed?"** — BFS over the OSM road graph from the business, on cuGraph (GPU);
  bus stops/routes and resident population (IoD2019) attached to the reached area.
- **"Is it really on NVIDIA / the Spark?"** — cuGraph + cuDF run on the GPU now (cloud RAPIDS L4);
  identical code on the Spark — unset one env var, runs on-box in unified memory.
- **"Privacy?"** — Area-level only (LSOA ≈ 1,500 people); cameras read road conditions, never people.

## Fallbacks (if the venue network dies)
- **Catchment:** runs on **CPU (networkx)** with the same output — unset `AEGIS_RIPPLE_URL`; works
  offline once the graph/stops/IMD are cached.
- **Perception:** `AEGIS_REPLAY=1` tab serves saved frames + seeded incidents — a fully offline HUD.
- Live status/weather degrade gracefully (a failed signal just drops out of the warnings list).
- Worst case: narrate from a pre-recorded screen capture (Whitechapel cascade-effect frame).
