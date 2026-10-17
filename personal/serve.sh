#!/usr/bin/env bash
set -euo pipefail
python -c 'from personal.app import create_app; create_app()'
python -m personal.worker &
worker_pid=$!
gunicorn --workers 1 --bind "0.0.0.0:${PORT:-8000}" --timeout 60 'personal.app:create_app()' &
web_pid=$!
cleanup() {
  trap - EXIT TERM INT
  kill -TERM "$web_pid" "$worker_pid" 2>/dev/null || true
  wait "$web_pid" "$worker_pid" 2>/dev/null || true
}
trap cleanup EXIT TERM INT
# If either component exits, restart the entire service through the hosting provider.
wait -n "$web_pid" "$worker_pid"
