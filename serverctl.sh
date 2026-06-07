#!/usr/bin/env bash
# Start/stop/restart the Aegis server on the host it runs on (intended for hp15).
# Detaches with setsid so it survives the SSH session. Usage:
#   ./serverctl.sh start|stop|restart|status|log
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PIDFILE="data/aegis.pid"
LOG="data/aegis.log"
HOST="${AEGIS_HOST:-0.0.0.0}"
PORT="${AEGIS_PORT:-8000}"
mkdir -p data

is_running() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

start() {
  if is_running; then echo "already running (pid $(cat "$PIDFILE"))"; return; fi
  if [ ! -d .venv ]; then
    # --system-site-packages so the app can use system RAPIDS (cuDF/cuPy)
    python3 -m venv .venv --system-site-packages
    .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements.txt
  fi
  setsid .venv/bin/uvicorn backend.main:app --host "$HOST" --port "$PORT" \
    > "$LOG" 2>&1 < /dev/null &
  echo $! > "$PIDFILE"
  sleep 1
  is_running && echo "started pid $(cat "$PIDFILE") -> http://$HOST:$PORT (log: $LOG)" \
             || { echo "FAILED to start; tail of log:"; tail -n 20 "$LOG"; exit 1; }
}

stop() {
  if is_running; then kill "$(cat "$PIDFILE")" && echo "stopped"; else echo "not running"; fi
  rm -f "$PIDFILE"
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  status) is_running && echo "running (pid $(cat "$PIDFILE"))" || echo "stopped" ;;
  log) tail -n "${2:-40}" "$LOG" ;;
  *) echo "usage: $0 {start|stop|restart|status|log}"; exit 1 ;;
esac
