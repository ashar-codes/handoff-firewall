#!/usr/bin/env bash
# Production entrypoint for one deployed instance: one API process and one durable worker.
# Order: validate configuration -> upgrade-only migrations -> optional first-admin bootstrap
# -> worker + API. Either process exiting stops the instance so the platform restarts it.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# Image layout: /app/start-production.sh + /app/backend; repository layout: scripts/ + backend/.
if [[ -d "$here/backend" ]]; then cd "$here/backend"; else cd "$here/../backend"; fi

# Render publishes the service URL; an explicit FRONTEND_ORIGIN always wins.
export FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-${RENDER_EXTERNAL_URL:-}}"

echo "[start] validating configuration"
python -c "from app.config import settings; s = settings(); print('[start] app_env=' + s.app_env + ' storage=' + s.storage_provider + ' model=' + s.model_provider)"

echo "[start] applying database migrations (upgrade only)"
python -m app.migrate

echo "[start] first-administrator bootstrap check"
python -m app.bootstrap --from-env

api_pid="" worker_pid=""
stop() {
  trap - TERM INT
  [[ -n "$api_pid" ]] && kill -TERM "$api_pid" 2>/dev/null || true
  [[ -n "$worker_pid" ]] && kill -TERM "$worker_pid" 2>/dev/null || true
  wait || true
}
trap 'stop; exit 143' TERM INT

echo "[start] starting worker"
python -m app.worker &
worker_pid=$!

echo "[start] starting API on port ${PORT:-8000}"
python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips='*' --no-server-header --workers 1 &
api_pid=$!

# Whichever process exits first decides the instance's fate.
set +e
wait -n "$api_pid" "$worker_pid"
status=$?
set -e
echo "[start] a process exited (status $status); stopping the instance"
stop
exit "$status"
