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
> **locally on a DGX Spark** — and at city scale it shows councils the same thing for **every high
> street at once**, weighted by **deprivation**."

---

## The signals to land (real output)
- **City view (live):** ~**9,500** of 25k high-street businesses access-impaired by **80 road + 1,200+
  tube/bus** disruption points, **~1,500 in the most-deprived high streets**; **10** disruptions on
  critical **chokepoints**; busiest **lifeline junction** supports **410** businesses.
- **Brick Lane pin:** **🚇 District line — Part Closure**, **🚌 buses 242/35/55/78 — Special Service**,
  roadworks within 600 m, weather — every warning a **named, real** signal.
- **Whitechapel pin:** the headline cascade insight — **🌊 "~28% of your catchment is reached past the
  works disruption 411 m away."**
- **Performance:** catchment BFS over **21,908** nodes in **~0.6 s**; the city-scale batch cascade +
  betweenness centrality run on **cuGraph (GPU)**.

---

## Pre-demo checklist (do this ~10 min before)
1. **Warm both Modal GPUs:** `curl -s https://<ws>--aegis-ripple-ripple-status.modal.run` → `"backend":"cuGraph (GPU)"`; `curl -s <modal-vllm>/v1/models`. (For safety set `min_containers=1` and redeploy.)
2. **Launch the backend** (README run mode B) with `TFL_APP_KEY` + `AEGIS_RIPPLE_URL` set.
3. **Warm the HUD:** open `http://127.0.0.1:8000` — title reads "RIPPLE", status dot green.
4. **One practice pin** so the cuGraph CUDA init (~one-time 20 s) is paid; pick a pin that shows a strong cascade-effect today (try Whitechapel / Mile End).
5. `curl -s localhost:8000/api/ripple/status` → `ready:true, backend:"cuGraph (GPU)"`.

---

## The 3-minute walkthrough

### 0:00 — The problem, at city scale (open on the high-street health map)
**SAY:** *"Every road closure, tube outage and roadwork in London quietly cuts small-business
footfall — and no one joins it up. This is **every London high street, right now**: red means
access-impaired. Today, ~**9,500 businesses** are impaired by **80-plus live disruptions** — and
crucially **~1,500 of them are in the most-deprived high streets.**"*
**DO:** The red/green high-street heatmap + the **"London high streets — today"** panel.

### 0:35 — Chokepoints (betweenness centrality)
**DO:** Point at the **◆ cyan** junction markers + the chokepoint line.
**SAY:** *"Ripple also computes the road network's **betweenness centrality** on the GPU — the junctions
the most businesses depend on. These ◆ are London's high-street **lifelines**; the busiest supports
**410 shops**. And **10 of today's disruptions sit right on a critical chokepoint** — outsized impact.
That tells a council exactly which junctions to protect."*

### 1:05 — Drill into one business (the owner's view)
**DO:** Click a shop location (e.g. **Whitechapel**) → catchment draws, panel fills.
**SAY:** *"Now one shop. Ripple worked out its **catchment** — the roads, stops and residents that feed
it — and the live warnings: **District line part-closed**, **bus routes on special service**, roadworks,
rain. Plus the bottleneck an owner can't see:"* (point) **🌊 "~28% of your catchment is reached past
that closure."** *"Every line a real, named signal — no black-box footfall guess."*

### 1:40 — How (the NVIDIA stack + Spark story)
**SAY:** *"The catchment is a cuGraph BFS in ~0.6 s; the city view **batch-cascades all 80+ disruptions
over 28,000 businesses** and runs **betweenness centrality** — real load on the GPU, with **cuDF** joins.
On a **DGX Spark**, the road graph, the demographics and the vision model live together in **128 GB of
unified memory** — local, nothing leaves the premises."* (point at **⚡ via cuGraph (GPU)**.)

### 2:10 — Validation layer (Aegis: click a camera)
**DO:** Click a camera marker → live frame.
**SAY:** *"And a live disruption can be **confirmed with the camera** — an **NVIDIA Nemotron
vision-language model** reads the road, **conditions only, never people**."*

### 2:35 — Close
**SAY:** *"So: a corner-shop owner gets an early warning a chain would pay an analyst for — and a
council gets a live, equity-weighted map of which high streets are suffering and which junctions to
protect. One open-data, NVIDIA-GPU engine, private and local on a Spark."*

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
