"""Aegis detector VLM on Modal — mirrors the hp-15 (DGX Spark) serving stack so the
work migrates back to the Spark with zero drift.

PARITY with hp-15 (only the endpoint URL + GPU differ):
  - same model:        nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8
  - same engine:       vLLM 0.22.1 (nightly cu130), same install order (torch cu130 -> vllm)
  - same base:         CUDA 13.0 + Ubuntu 24.04 + Python 3.12
  - same API surface:  OpenAI-compatible, served model name 'nemotron-nano-vl', same serve flags
  - GPU:               H100 (Hopper = native FP8, like the Spark's Blackwell — NOT A100/Ampere)

Deploy:   modal deploy modal_vllm.py
Endpoint: https://<workspace>--aegis-vllm-serve.modal.run/v1
Point Aegis at it (backend runs anywhere — Mac/cloud):
  AEGIS_VL_BACKEND=openai AEGIS_VL_MODEL=nemotron-nano-vl \
  AEGIS_VL_OPENAI_URL=https://<workspace>--aegis-vllm-serve.modal.run/v1 \
  bash serverctl.sh restart
Migrate back to the Spark = point AEGIS_VL_OPENAI_URL at http://localhost:8090/v1 and run
bash vllm_serve.sh there (already installed + CUDA-fixed). Same model, same flags, same outputs.
"""
import subprocess

import modal

MODEL = "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8"
SERVED_NAME = "nemotron-nano-vl"   # identical to hp-15's --served-model-name
PORT = 8000

# Mirror the hp-15 install: CUDA 13 / Ubuntu 24.04 / py3.12, torch cu130, then vLLM nightly cu130.
image = (
    modal.Image.from_registry("nvidia/cuda:13.0.0-devel-ubuntu24.04", add_python="3.12")
    .pip_install("torch", extra_index_url="https://download.pytorch.org/whl/cu130")
    .pip_install("vllm==0.22.1", extra_index_url="https://wheels.vllm.ai/nightly/cu130")
    .pip_install("huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

app = modal.App("aegis-vllm")
# Persist the ~12GB FP8 weights across cold starts so only the first run downloads them.
hf_cache = modal.Volume.from_name("aegis-hf-cache", create_if_missing=True)


@app.function(
    image=image,
    gpu="H100",                      # Hopper: native FP8 (same as the Spark's Blackwell)
    volumes={"/root/.cache/huggingface": hf_cache},
    timeout=60 * 60,
    scaledown_window=300,            # stay warm 5 min after last request (avoids re-cold-start)
    # min_containers=1,              # uncomment for an always-on endpoint during the live demo
)
@modal.concurrent(max_inputs=24)     # vLLM continuous-batches concurrent camera frames
@modal.web_server(port=PORT, startup_timeout=15 * 60)  # first start downloads + loads the model
def serve():
    cmd = (
        f"vllm serve {MODEL} --host 0.0.0.0 --port {PORT} "
        f"--served-model-name {SERVED_NAME} --trust-remote-code "
        f"--max-model-len 8192 --limit-mm-per-prompt '{{\"image\":1}}' "
        f"--gpu-memory-utilization 0.90"
    )
    subprocess.Popen(cmd, shell=True)
