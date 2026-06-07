#!/usr/bin/env bash
# Sync the Aegis project from this Mac to the Spark (hp15). Run from anywhere.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/"
DEST="hp15:~/aegis/"
rsync -az --delete \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude 'data/' \
  --exclude '.git/' \
  "$SRC" "$DEST"
echo "Synced -> $DEST"
