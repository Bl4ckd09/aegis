"""Central configuration for Aegis. All values overridable via environment."""
from __future__ import annotations

import os
from pathlib import Path

# --- Perception VLM (the detector) ---
# Backend: "ollama" (native /api/chat) or "openai" (llama.cpp / any OpenAI-compatible server).
# We prefer serving on llama.cpp (OpenAI backend); Ollama qwen3.6 stays as the proven fallback.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
VL_BACKEND = os.environ.get("AEGIS_VL_BACKEND", "ollama")          # "ollama" | "openai"
VL_MODEL = os.environ.get("AEGIS_VL_MODEL", "qwen3.6")             # model tag/name
VL_OPENAI_URL = os.environ.get("AEGIS_VL_OPENAI_URL", "http://localhost:8090/v1")  # llama.cpp VLM server

# --- Operator-briefing text model (prefer NVIDIA Nemotron on llama.cpp) ---
# Nemotron-3-Nano-30B is served by llama.cpp at :30000 (OpenAI-compatible). It is a reasoning
# model, so give it enough tokens for the think trace + answer; we read message.content.
BRIEFING_BACKEND = os.environ.get("AEGIS_BRIEFING_BACKEND", "openai")  # "openai" | "ollama"
BRIEFING_URL = os.environ.get("AEGIS_BRIEFING_URL", "http://localhost:30000/v1")
BRIEFING_MODEL = os.environ.get("AEGIS_BRIEFING_MODEL", "nemotron-3-nano-30b")
BRIEFING_MAX_TOKENS = int(os.environ.get("AEGIS_BRIEFING_MAX_TOKENS", "900"))

# --- TfL open data endpoints (Open Government Licence) ---
TFL_APP_KEY = os.environ.get("TFL_APP_KEY", "")  # optional; raises rate limits
JAMCAM_LIST_URL = "https://api.tfl.gov.uk/Place/Type/JamCam"
DISRUPTION_URL = "https://api.tfl.gov.uk/Road/all/Disruption"

# --- Detection loop ---
# CAMERA_LIMIT caps the camera *universe* shown on the map (None = all ~795 available).
# The detector classifies a ROLLING WINDOW over that universe: SWEEP_BATCH cameras every
# BATCH_INTERVAL seconds, cycling through all of them — so the whole London network is on
# the map while GPU cost stays flat (bounded per-batch) instead of scaling to N per sweep.
CAMERA_LIMIT = int(os.environ["AEGIS_CAMERA_LIMIT"]) if os.environ.get("AEGIS_CAMERA_LIMIT") else None
DETECT_CONCURRENCY = int(os.environ.get("AEGIS_CONCURRENCY", "8"))   # parallel VL calls in flight
SWEEP_BATCH = int(os.environ.get("AEGIS_SWEEP_BATCH", "40"))         # cameras classified per rolling batch
BATCH_INTERVAL_SECONDS = float(os.environ.get("AEGIS_BATCH_INTERVAL", "12"))  # gap between batches
POLL_INTERVAL_SECONDS = int(os.environ.get("AEGIS_POLL_INTERVAL", "180"))  # disruptions feed refresh
VL_TIMEOUT_SECONDS = float(os.environ.get("AEGIS_VL_TIMEOUT", "120"))

# --- Disruption cross-reference (lead-time insight) ---
MATCH_RADIUS_M = float(os.environ.get("AEGIS_MATCH_RADIUS_M", "300"))
# Only credit a "lead time" if our detection is within this many seconds before the
# official update (avoids matching stale, unrelated disruptions).
MATCH_TIME_WINDOW_S = float(os.environ.get("AEGIS_MATCH_WINDOW_S", str(6 * 3600)))

# --- Briefing ---
BRIEFING_INTERVAL_SECONDS = int(os.environ.get("AEGIS_BRIEFING_INTERVAL", "120"))

# --- Categories (fixed enum the VL model must choose from) ---
CATEGORIES = ["clear", "congestion", "accident", "stalled_vehicle", "hazard", "obscured"]
# Anything not "clear" / "obscured" is an actionable incident.
INCIDENT_CATEGORIES = {"congestion", "accident", "stalled_vehicle", "hazard"}

# --- Storage ---
DATA_DIR = Path(os.environ.get("AEGIS_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))
INCIDENTS_JSONL = DATA_DIR / "incidents.jsonl"
SNAPSHOT_DIR = DATA_DIR / "snapshots"        # offline-demo fallback frames
THUMB_DIR = DATA_DIR / "thumbs"              # saved source frames for the log

# --- Replay / offline mode (demo fallback if venue network dies) ---
REPLAY_MODE = os.environ.get("AEGIS_REPLAY", "0") == "1"

DATA_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
