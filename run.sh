#!/usr/bin/env bash
# Launch the Aegis backend on the Spark. Run this ON hp15 (from ~/aegis).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d .venv ]; then
  echo "Creating venv..."
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi

export AEGIS_DATA_DIR="${AEGIS_DATA_DIR:-$PWD/data}"
HOST="${AEGIS_HOST:-0.0.0.0}"
PORT="${AEGIS_PORT:-8000}"
echo "Aegis -> http://$HOST:$PORT  (model=${AEGIS_VL_MODEL:-qwen3.6}, cameras=${AEGIS_CAMERA_LIMIT:-all})"
exec .venv/bin/uvicorn backend.main:app --host "$HOST" --port "$PORT" "$@"
