#!/usr/bin/env bash
# Push local changes to the Spark.
set -euo pipefail

HOST="${SPARK_HOST:-hp-15}"
REMOTE_DIR="${SPARK_DIR:-~/ledger}"

rsync -avz --delete \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '.venv' \
  --exclude 'data/cache' \
  "$(cd "$(dirname "$0")/.." && pwd)/" \
  "${HOST}:${REMOTE_DIR}/"

echo "Synced to ${HOST}:${REMOTE_DIR}"
