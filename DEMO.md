# Ripple — Demo Script & Walkthrough

A tight ~3-minute live demo for **Hack for Impact London (presented by NVIDIA)**.
Everything below reflects what the system actually does — no overclaiming.

---

## TL;DR (the elevator pitch — say this if you only get one sentence)
> "London approves thousands of road closures and diversions a year, each in isolation — nobody
> models what breaks downstream. **Ripple** lets a planner click anywhere on the map and instantly
> see the cascade: the journeys, buses, and — crucially — the **people and the deprived
> neighbourhoods** a disruption will hit. It ripples through London's road graph on **NVIDIA RAPIDS
> cuGraph** in **under a second**, and validates against live camera footage with an **NVIDIA
> vision-language model** — all able to run **locally on a DGX Spark**."

---

## The numbers to land (real output)
- **Planning click — Tower Hamlets:** ~**49,000 residents**, **7** of the affected neighbourhoods
  in England's **most-deprived 20%** · 477 junctions · 74 stops.
- **Contrast — Trafalgar Square:** ~78,000 journeys but only **1** deprived neighbourhood.
  → *Same kind of closure, very different equity impact — and Ripple makes it visible.*
- **Performance:** cascade over a **21,908-node** graph in **~0.6 s** on **cuGraph (GPU)**.

---

## Pre-demo checklist (do this ~10 min before)
1. **Warm both Modal GPUs** (avoid a cold start mid-demo):
   - Cascade: `curl -s https://<ws>--aegis-ripple-ripple-status.modal.run` → `"backend":"cuGraph (GPU)"`.
   - VLM: `curl -s <modal-vllm>/v1/models`. (For safety set `min_containers=1` in `modal_ripple.py` /
     `modal_vllm.py` and redeploy.)
2. **Launch the backend** pointing at both (see README run mode B), with `TFL_APP_KEY` set.
3. **Warm the HUD:** open `http://127.0.0.1:8000`, status dot green, `30/30 scanned`.
4. **Do one practice cascade** (click the map) so the cuGraph CUDA init (~one-time 20s) is paid.
5. **Offline backup tab:** a second run with `AEGIS_REPLAY=1` on port 8001 (perception fallback).
6. `curl -s localhost:8000/api/ripple/status` → `ready:true, backend:"cuGraph (GPU)"`.

---

## The 3-minute walkthrough

### 0:00 — The problem (open on the live HUD)
**SAY:** *"Every road closure in London is approved by one department looking at one dataset. Nobody
models what breaks downstream — the journeys, the buses, the people. The data exists; it's just
never joined up. Ripple joins it, live."*
**DO:** Map of London, cameras as coloured dots; the **Cascade Impact — Planning** panel top-right.

### 0:25 — Planning mode, the hero moment (click a deprived area)
**DO:** Click **East London / Tower Hamlets**. The ripple draws — a red epicentre, blue affected
road nodes — and the panel fills instantly.
**SAY:** *"I just proposed a disruption here. Ripple rippled it through London's road graph and tells
me: ~**49,000 residents** in the affected catchment, and **7** of these neighbourhoods are in
England's most-deprived 20%. 477 junctions, 74 bus stops, 24 routes."*

### 0:55 — The equity contrast (click central London)
**DO:** Click **Trafalgar Square**.
**SAY:** *"Same kind of closure in the centre — 78,000 journeys, but only **one** deprived
neighbourhood. Ripple shows planners not just how big a disruption is, but **who it falls on** — the
equity of the decision, before it's made."*

### 1:25 — How (the NVIDIA stack + Spark story)
**SAY:** *"That cascade is a graph BFS over ~22,000 road nodes — running on **RAPIDS cuGraph on an
NVIDIA GPU**, in about **0.6 seconds**. The impact joins use **cuDF**. On a **DGX Spark**, the road
graph, the demographics, and the vision model all live in **128 GB of unified memory** — the whole
thing runs locally, no data leaves the premises."* (Point at the green **⚡ BFS on cuGraph (GPU)**
line in the panel.)

### 1:50 — Validation layer (Aegis: click a camera)
**DO:** Click an **amber** camera marker → live frame pops up.
**SAY:** *"In live mode Ripple watches TfL's disruption feed and **validates** the model against real
footage: an **NVIDIA Nemotron vision-language model** reads each camera — clear, congestion,
accident — **describing road conditions only, never people**. It even flags conditions **before**
they hit TfL's official feed."* (Point at the **"not yet in the official feed"** banner.)

### 2:20 — Briefing + close
**DO:** Point at the **Operator briefing** (NVIDIA Nemotron) panel.
**SAY:** *"And a plain-English situational briefing, also from an NVIDIA Nemotron model. So: a planner
sees the human cost of a decision before approving it, and a control room sees what's happening — and
what's coming — in real time. Local, private, on NVIDIA hardware."*

---

## Likely Q&A
- **"Is the impact model accurate?"** — It's a first-order reachability model (graph BFS + boarding
  proxy + LSOA population/deprivation), defensible and fast — designed to surface *relative* impact
  and equity, not a full traffic simulation. The architecture takes richer weights (real boardings,
  travel-time edges) directly.
- **"Where does the deprivation data come from?"** — English Indices of Deprivation 2019 at LSOA
  level (≈1,500 residents); **area-level only, never individuals**.
- **"Is it really on NVIDIA / the Spark?"** — cuGraph + cuDF run on the GPU now (cloud RAPIDS L4);
  the code is identical on the Spark — unset one env var and it runs on-box in unified memory.
- **"Privacy?"** — No faces, no plates, no tracking; the VL prompt forbids describing people.

## Fallbacks (if the venue network dies)
- **Cascade:** the engine runs on **CPU (networkx)** with the same numbers — just unset
  `AEGIS_RIPPLE_URL`; the cascade still works offline once the graph/stops/IMD are cached.
- **Perception:** the `AEGIS_REPLAY=1` tab serves saved snapshot frames + seeded incidents — a fully
  offline HUD. The cross-reference + briefing still render.
- Worst case: narrate from a pre-recorded screen capture of the cascade.
