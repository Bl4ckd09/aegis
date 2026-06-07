# Aegis — Demo Script & Walkthrough

A tight ~3-minute live demo for **Hack for Impact London (presented by NVIDIA)**.
Everything below reflects what the system actually does — no overclaiming.

---

## TL;DR (the elevator pitch — say this if you only get one sentence)
> "London has **880+ public traffic cameras** that no human can watch at once, and official
> disruption reports lag what's happening on the ground. **Aegis** watches every camera with an
> **NVIDIA vision-language model**, logs road incidents in real time **without identifying anyone**,
> and flags conditions **before they appear in TfL's official feed** — all running on **NVIDIA hardware**."

---

## Pre-demo checklist (do this ~10 min before you present)
1. **Pick where it runs:**
   - **Best — on the DGX Spark (hp-15):** the "local, no images leave the premises" story.
     `bash vllm_serve.sh start` then `AEGIS_VL_BACKEND=openai AEGIS_VL_MODEL=nemotron-nano-vl bash serverctl.sh start`
   - **Failover — Modal H100 (works now):** `AEGIS_VL_BACKEND=openai AEGIS_VL_OPENAI_URL=<modal>/v1 … uvicorn backend.main:app`
2. **Lock the endpoint warm** (avoid a mid-demo cold start): set `min_containers=1` in `modal_vllm.py` → `modal deploy modal_vllm.py`. (Skip if on the Spark.)
3. **Warm the HUD:** open `http://<host>:8000`, confirm the status dot is green and `30/30 scanned`.
4. **Capture a fresh snapshot** (offline backup): `python -m scripts.snapshot`.
5. **Have the offline tab ready** (see Fallbacks): a second run with `AEGIS_REPLAY=1` on port 8001.
6. Confirm health: `curl -s localhost:8000/api/health` → `status:ok`, incidents > 0.

---

## The 3-minute walkthrough

### 0:00 — Hook (open on the live HUD)
**SAY:** *"This is Aegis — a control-room HUD watching London's live traffic-camera network. Every
dot is a real TfL camera; the colour is what an NVIDIA vision-language model sees right now."*
**DO:** Let the map sit — green (clear) and amber (congestion) dots across London.

### 0:20 — Perception (click a congestion marker)
**DO:** Click an **amber** marker → the live camera frame pops up.
**SAY:** *"The model classifies each frame into clear, congestion, accident, stalled vehicle, hazard,
or obscured — with a confidence and a one-line description. Crucially, it describes **road conditions
only** — never people, never number plates."*
**DO:** Point at the incident log entry's description (e.g., *"heavy queuing traffic on a wet carriageway"*).

### 0:50 — The headline insight (point to the banner)
**DO:** Point at the green **lead banner** at the top.
**SAY:** *"Here's the non-obvious part. Aegis is cross-referencing every detection against TfL's
**official** disruption feed. Right now it's surfacing **N live conditions that are NOT yet in the
official feed** — congestion the control room would otherwise be blind to — while corroborating the
ones that are. That's the decision-driving value: we see it first."*

### 1:20 — Operator briefing (point to the briefing card)
**SAY:** *"An NVIDIA Nemotron model writes a plain-English situational briefing for operators — the
same picture a duty officer would summarise, generated automatically."*
**DO:** Read one sentence of the live briefing aloud.

### 1:40 — The NVIDIA stack (point to the "NVIDIA stack" panel)
**SAY:** *"This whole thing is an NVIDIA stack: **Nemotron-Nano-VL** does perception, **Nemotron**
writes the briefing, **RAPIDS cuDF** does the GPU spatial join against the official feed — running on
a **DGX Spark GB10** with 128 GB of unified memory. The Spark holds dozens of live frames and the
full model context at once and classifies them **in parallel, locally — about a second a frame, no
cloud round-trip, no images leaving the building.**"*

### 2:10 — Responsible use (point to the panel)
**SAY:** *"By design, Aegis does **no facial recognition, no number-plate reading, and no tracking**
of any person or vehicle. That boundary is enforced in the model prompt — it's the legal/ethical line
under UK GDPR, and it's deliberate: a traffic tool, not a surveillance tool."*

### 2:30 — Resilience (optional, strong if asked "what if the network dies?")
**SAY:** *"It's built to run locally on the Spark. When our Spark hit a hardware issue mid-build, we
failed over to the **identical** NVIDIA model stack on a cloud H100 by changing **one environment
variable** — and there's an **offline replay mode** that runs the whole HUD from a saved snapshot with
zero network. So a flaky venue connection can't take the demo down."*

### 2:50 — Close
**SAY:** *"Aegis: a control room that sees everything, identifies no one, and warns you first."*

---

## NVIDIA products used (the judging criterion — name them explicitly)
| Layer | NVIDIA product |
|---|---|
| Perception VLM | **NVIDIA Nemotron-Nano-12B-v2-VL** (FP8) |
| Briefing LLM | **NVIDIA Nemotron** |
| Spatial join | **NVIDIA RAPIDS cuDF / cuPy** |
| Serving | **vLLM** on NVIDIA GPUs |
| Compute | **NVIDIA DGX Spark (GB10 Grace Blackwell)** / **H100** |
| *(stretch)* | NVIDIA NIM + TensorRT-LLM + Triton (Cosmos-Reason1 path) |

## Numbers to quote
- **880+** public TfL JamCams · **795** live · **80** official disruptions tracked
- **~1 second per frame** (warm), classified concurrently across the GPU
- Fixed 6-category output; confidence-calibrated; anonymized descriptions

## Fallbacks (if something breaks live)
| If… | Do this |
|---|---|
| Venue network / TfL is down | Switch to the **offline replay** tab (`AEGIS_REPLAY=1`) — full HUD from the snapshot |
| Modal cold-start lag | You pre-locked `min_containers=1`; if not, the first frame takes ~1 min — talk through the architecture meanwhile |
| Spark unreachable | Use the Modal H100 URL (one env var) — identical model + output |
| Map tiles won't load | Markers still render on a blank canvas; the data is the point, not the basemap |

## Anticipated Q&A
- **"Is this surveillance?"** No — it classifies road conditions in aggregate; no faces, plates, or
  cross-frame tracking, enforced in the prompt. It's the opposite of a surveillance framing.
- **"How is it 'ahead of' TfL?"** The official feed is mostly planned roadworks; Aegis detects live
  congestion/incidents the feed doesn't carry, and timestamps when it first saw them.
- **"Accuracy / false positives?"** Conservative prompt — severe categories (accident/hazard) require
  unmistakable evidence; ambiguous frames fall back to congestion/clear. Calibrated confidence.
- **"Does it scale to all 880 cameras?"** Yes — concurrent inference on the GPU; we monitor a subset
  live for demo snappiness; wall-time ≈ ceil(N / concurrency) inferences, not N sequential.
- **"Why the Spark specifically?"** 128 GB unified memory holds many frames + the VL context at once,
  and local inference means sub-second latency with no images leaving the premises.

## One-line submission blurb
> **Aegis** — a locally-run, privacy-preserving operational HUD that applies an NVIDIA vision-language
> model to London's 880+ public traffic cameras, logging road incidents and surfacing live conditions
> before they reach TfL's official feed — on a DGX Spark, identifying no one.
