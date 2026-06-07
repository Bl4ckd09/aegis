# Aegis — session handoff (resume here)

Context for a Claude Code session running **on hp-15** (low-latency, no SSH). Everything below
is already on this box. Project root: `~/aegis`. HUD: http://localhost:8000

## What Aegis is
Local traffic-incident HUD: TfL JamCams → VL classification → map + incident log + lead-time
cross-reference vs the official TfL disruption feed + operator briefing. Runs entirely on the
DGX Spark. See README.md. Anonymized by design (no faces/plates/tracking).

## Status: working, mid-upgrade
MVP is built and verified end-to-end. Currently swapping the **detector** to an NVIDIA VLM.

NVIDIA stack live (the judging goal — "use as many NVIDIA products as possible"):
- **DGX Spark GB10** (host)
- **Nemotron-3-Nano-30B** drives the operator briefing — via **llama.cpp** at `localhost:30000/v1`
- **RAPIDS cuDF/cuPy** does the GPU spatial join (`backend/geo.py`) — venv built with `--system-site-packages`
- Detector: currently `qwen3.6` (Qwen3-VL 36B) on Ollama (proven). **Migrating to NVIDIA Nemotron-Nano-12B-v2-VL on vLLM** (Option B).

## Option B — where it stands (the active task)
- vLLM 0.22.1 installed in `~/vllm-env` (nightly cu130, torch 2.11.0+cu130, sees GB10).
- FP8 weights cached: `nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8` (in HF cache).
- **CUDA fix applied** (the hard part): flashinfer FP8 JIT failed because pip nvcc was 13.3 vs
  cudart headers 13.0. Fixed by using the system CUDA 13.0 toolkit:
  - `vllm_serve.sh` sets `CUDA_HOME=/usr/local/cuda-13.0` + PATH.
  - the pip nvcc was symlinked to `/usr/local/cuda-13.0/bin/nvcc` (13.0) — matches headers.
  - `python3-dev` installed (Triton JIT needs Python.h).
- Last action: launched `VLM_MODEL=...FP8 bash vllm_serve.sh start`; flashinfer was JIT-compiling
  CUTLASS kernels for sm_121a (first start only, then cached).

### Resume steps
1. Check the vLLM server:
   ```
   bash vllm_serve.sh log 40
   curl -s localhost:8090/v1/models    # ready when this returns the model
   ```
   - If still compiling, wait; if it died, read the log for the root cause.
   - Start/restart if needed: `VLM_MODEL=nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8 bash vllm_serve.sh start`
2. Validate the NVIDIA VLM on real frames (accuracy + latency), compare to qwen3.6:
   ```
   AEGIS_VL_BACKEND=openai AEGIS_VL_OPENAI_URL=http://localhost:8090/v1 \
   AEGIS_VL_MODEL=nemotron-nano-vl .venv/bin/python -m scripts.classify_file data/thumbs/*.jpg
   ```
3. If good, run the app against vLLM:
   ```
   AEGIS_VL_BACKEND=openai AEGIS_VL_OPENAI_URL=http://localhost:8090/v1 \
   AEGIS_VL_MODEL=nemotron-nano-vl AEGIS_CAMERA_LIMIT=30 AEGIS_CONCURRENCY=6 \
   AEGIS_BRIEFING_INTERVAL=45 bash serverctl.sh restart
   ```
   Verify: `curl -s localhost:8000/api/health | jq` → detector_backend=openai.
4. Then **kill Ollama** (user-authorized once perception is off it): `ollama stop qwen3.6`
   (frees ~28GB). Keep it as fallback: `AEGIS_VL_BACKEND=ollama` reloads it.

## Key commands
- App: `bash serverctl.sh {start|stop|restart|status|log}` (uvicorn :8000)
- vLLM detector: `bash vllm_serve.sh {start|stop|status|log}` (:8090)
- Health: `curl -s localhost:8000/api/health | jq`

## Remaining tasks
- Finish Option B validation + flip detector (above).
- HUD polish (#6): minor; add an NVIDIA "powered by" panel.
- Demo prep (#7): offline replay snapshots, finalize README, Spark-story.
- Option A (later, separate, #11): Cosmos-Reason1-7B via NIM (needs NGC key) for max NVIDIA count.

## Notes
- Connectivity from the Mac was via Tailscale (100.109.237.73) after the venue WiFi roamed it to a
  different subnet. On-box you don't need that.
- A teammate's llama.cpp Nemotron server (:30000, ~38GB) is shared — used for the briefing.
- Memory is shared/tight; check `nvidia-smi` before loading models.
