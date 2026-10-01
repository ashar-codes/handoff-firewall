#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
test_dir="$(mktemp -d "${TMPDIR:-/tmp}/handoff-e2e.XXXXXX")"
export APP_ENV=test MODEL_PROVIDER=test
export DATABASE_URL="sqlite:///$test_dir/test.db"
export STORAGE_PATH="$test_dir/files"
export FRONTEND_ORIGIN="http://localhost:5173"
export SEED_PASSWORD="${E2E_PASSWORD:-Testing-password-42}"
export E2E_PASSWORD="$SEED_PASSWORD"
export QA_SCREENSHOT_DIR="${QA_SCREENSHOT_DIR:-$test_dir/screenshots}"
mkdir -p "$QA_SCREENSHOT_DIR"
api_pid= worker_pid= ui_pid=
cleanup() {
  for process_id in "$api_pid" "$worker_pid" "$ui_pid"; do
    if [[ -n "$process_id" ]]; then kill "$process_id" 2>/dev/null || true; fi
  done
}
trap cleanup EXIT INT TERM
cd "$project_root/backend"
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 > "$test_dir/api.log" 2>&1 & api_pid=$!
uv run python -m app.worker > "$test_dir/worker.log" 2>&1 & worker_pid=$!
cd "$project_root/frontend"
npm run dev > "$test_dir/ui.log" 2>&1 & ui_pid=$!
node --input-type=module - <<'JS'
for (const url of ['http://127.0.0.1:8000/api/health','http://127.0.0.1:5173']) {
  let ok=false;
  for(let attempt=0;attempt<40;attempt++) {
    try { if((await fetch(url)).ok){ok=true;break;} } catch {}
    await new Promise(resolve=>setTimeout(resolve,250));
  }
  if(!ok) throw new Error('Server did not become healthy: '+url);
}
JS
npm run test:e2e
printf 'Disposable verification logs and screenshots: %s\n' "$test_dir"
