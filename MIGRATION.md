# Migrating Ripple to the DGX Spark (hp-15)

Goal: run the **whole stack on hp-15 locally** — FastAPI backend + RAPIDS (cuGraph/cuDF) + the
Nemotron-VL — so it's local, private, on-Spark, with **no Modal dependency**. It's the *same code*;
the GPU path activates automatically when RAPIDS is importable. Migrating off Modal = **unset one env
var** (`AEGIS_RIPPLE_URL`).

## 0. Prereqs
- **hp-15 powered + reachable** — it's been down; physically reboot, then:
  `ssh nvidia@hp-15.local` (pw `nvidiaLTW`) or Tailscale `ssh nvidia@100.109.237.73`.
- Internet on hp-15 (for pip deps; the data downloads can be skipped by copying caches — step 2).
- TfL app key: `27a7ec2b298549a98f5a3d0e07b344ce`.

## 1. Code
```bash
ssh nvidia@hp-15.local
git clone https://github.com/Bl4ckd09/aegis.git ~/aegis   # or: cd ~/aegis && git pull
```

## 2. Data caches — copy from the Mac (skips a ~5-min rebuild)
`data/` is gitignored. Copy the prebuilt caches so hp-15 doesn't re-fetch OSM/TfL/IoD at startup:
```bash
# run on the Mac:
rsync -avz ~/aegis/data/ripple/     nvidia@hp-15.local:~/aegis/data/ripple/      # ~35MB
rsync -avz ~/aegis/data/snapshots/  nvidia@hp-15.local:~/aegis/data/snapshots/   # offline fallback
# IMPORTANT: recompute betweenness on the GPU (the Mac one is CPU-sampled):
ssh nvidia@hp-15.local 'rm -f ~/aegis/data/ripple/centrality.json'
```
graph.graphml / stops.json / pois.json / imd_london.xlsx are platform-independent — fine to copy.
If you skip this, the engine rebuilds on first run (needs internet + `TFL_APP_KEY`, ~5 min).

## 3. Python env + deps
```bash
cd ~/aegis
python3.12 -m venv .venv --system-site-packages   # 3.12 (3.14 broke verifiers earlier); system-site so RAPIDS is visible
.venv/bin/pip install -r requirements.txt          # osmnx pulls networkx/pandas/scipy/shapely/geopandas (aarch64 wheels exist)
```
**RAPIDS (cudf + cugraph):** cuDF already worked on hp-15 (the Aegis spatial join), so it's present.
**cuGraph is the new dependency** — install the RAPIDS build for CUDA 13 / aarch64 (Blackwell). Verify:
```bash
.venv/bin/python -c "import cudf, cugraph; print('RAPIDS OK', cugraph.__version__)"
```

## 4. Serve the VLM locally
```bash
bash vllm_serve.sh start          # Nemotron-Nano-VL FP8 on vLLM @ :8090 (has the Blackwell CUDA_HOME fix)
curl -s localhost:8090/v1/models  # confirm it's up (model load ~minutes)
```

## 5. Launch the backend (local engine, no Modal)
```bash
cd ~/aegis
TFL_APP_KEY=27a7ec2b298549a98f5a3d0e07b344ce \
AEGIS_VL_BACKEND=openai AEGIS_VL_OPENAI_URL=http://localhost:8090/v1 AEGIS_VL_MODEL=nemotron-nano-vl \
AEGIS_BRIEFING_BACKEND=openai AEGIS_BRIEFING_URL=http://localhost:8090/v1 AEGIS_BRIEFING_MODEL=nemotron-nano-vl \
AEGIS_CAMERA_LIMIT=30 \
bash serverctl.sh start
# AEGIS_RIPPLE_URL is UNSET → the LOCAL ripple engine runs (cuGraph on the Spark). That's the whole migration.
```

## 6. Verify
```bash
curl -s localhost:8000/api/ripple/status     # → "backend":"cuGraph (GPU)"   (proves cuGraph on the Spark)
curl -s localhost:8000/api/highstreets       # lifelines populated, chokepoint_disruptions, multi-modal totals
# open http://hp-15.local:8000  (or via Tailscale)
```

## 7. Warm before the demo
- First `/api/highstreets` computes **betweenness on the GPU** (centrality.json deleted in step 2) — warm it once (~1 min).
- vLLM cold-loads the model (~min) — warm it.
- Click one business pin so the cuGraph CUDA init is paid.

## Fallback matrix (a working demo beats a pure-local broken one)
| If… | Then… |
|---|---|
| **cuGraph won't build** on Blackwell/cu13/aarch64 | engine auto-falls back to **networkx (CPU)** — fully works (22k-node graph is small, sub-second); cuDF likely still does the spatial join. Say "cuGraph-ready; cuDF live on the Spark." |
| **vLLM/flashinfer** Blackwell pain | keep the VLM on **Modal H100** — set `AEGIS_VL_OPENAI_URL` to the Modal vLLM URL. Not fully local, but works. |
| **No internet** on hp-15 | copy caches (step 2) + run perception with `AEGIS_REPLAY=1`; cascades work offline once cached. |
| **hp-15 won't come up** | demo from the **Mac as-is**: `AEGIS_RIPPLE_URL`=Modal cuGraph + Modal VLM — the fully-working setup today. |

## Biggest risk = cuGraph on Blackwell
cuDF is proven on hp-15; **cuGraph (cu13/aarch64/Blackwell) is the unknown** — same family of pain as
the vLLM/flashinfer build. If it installs: full local GPU story (cuGraph + cuDF + VLM in 128 GB unified
memory). If not: the networkx fallback keeps everything working — the product is unaffected, only the
"cuGraph *on the Spark*" line softens (you can still show cuGraph on the Modal L4). Prove cuGraph
import (step 3) **early** so you know which story you're telling before demo day.
