#!/usr/bin/env bash
# Serve the NVIDIA Nemotron-Nano-VL (FP8) detector via vLLM, OpenAI-compatible.
# Runs on hp15. Usage: bash vllm_serve.sh {start|stop|status|log}
set -uo pipefail

VENV="$HOME/vllm-env"
# BF16 avoids the flashinfer FP8 CUTLASS JIT (cuBLAS GEMM + FlashAttention are prebuilt).
MODEL="${VLM_MODEL:-nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16}"
PORT="${VLM_PORT:-8090}"
LOG="$HOME/vllm-nemotron.log"
PIDFILE="$HOME/vllm-nemotron.pid"

is_running(){ [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

case "${1:-start}" in
  start)
    is_running && { echo "already running (pid $(cat "$PIDFILE"))"; exit 0; }
    # flashinfer JIT-compiles FP8 CUTLASS kernels for Blackwell. Use the CONSISTENT system
    # CUDA 13.0 toolkit (nvcc 13.0 matches the 13.0 runtime headers) rather than the mixed
    # pip tree (nvcc 13.3 + cudart 13.0) which fails the cccl version check. $VENV/bin gives ninja.
    export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-13.0}"
    export PATH="$CUDA_HOME/bin:$VENV/bin:$PATH"
    # Conservative memory on the shared GB10: 0.25 of ~119GB (~30GB) for weights+KV.
    # The 12B-v2 hybrid weighs ~24GB; at max-model-len 8192 + one tiny image the KV
    # pool needs only a few GB, so 0.40 (~47GB) over-reserved ~17GB of idle KV. 0.25
    # reclaims it with no throughput loss. --max-model-len kept small to bound KV cache.
    setsid "$VENV/bin/vllm" serve "$MODEL" \
      --port "$PORT" \
      --trust-remote-code \
      --served-model-name nemotron-nano-vl \
      --gpu-memory-utilization "${VLM_GPU_UTIL:-0.25}" \
      --max-model-len "${VLM_MAXLEN:-8192}" \
      --limit-mm-per-prompt '{"image":1}' \
      --enforce-eager \
      > "$LOG" 2>&1 < /dev/null &
    echo $! > "$PIDFILE"
    echo "starting vLLM (pid $(cat "$PIDFILE")) -> http://0.0.0.0:$PORT  (log: $LOG)"
    echo "first start loads ~12GB FP8 weights; watch: bash vllm_serve.sh log"
    ;;
  stop) kill "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null && echo stopped || echo "not running"; rm -f "$PIDFILE";;
  status) is_running && echo "running (pid $(cat "$PIDFILE"))" || echo stopped;;
  log) tail -n "${2:-50}" "$LOG";;
  *) echo "usage: $0 {start|stop|status|log}"; exit 1;;
esac
