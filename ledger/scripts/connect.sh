#!/usr/bin/env bash
# Forward Spark services to localhost. Run once per session.
set -euo pipefail

HOST="${SPARK_HOST:-hp-15}"

if pgrep -f "ssh.*${HOST}.*-L 11434" >/dev/null 2>&1; then
  echo "Tunnels already running for ${HOST}"
else
  ssh -f -N \
    -L 11434:localhost:11434 \
    -L 11000:localhost:11000 \
    -L 8000:localhost:8000 \
    "${HOST}"
  echo "Tunnels started:"
fi

echo "  Ollama API     → http://localhost:11434"
echo "  DGX Dashboard  → http://localhost:11000"
echo "  vLLM (future)  → http://localhost:8000"
echo "  SSH shell      → ssh ${HOST}"
