#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
api_pid= worker_pid= ui_pid=
cleanup() { for process_id in "$api_pid" "$worker_pid" "$ui_pid"; do if [[ -n "$process_id" ]]; then kill "$process_id" 2>/dev/null || true; fi; done; }
trap cleanup EXIT INT TERM
cd "$project_root/backend"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 & api_pid=$!
uv run python -m app.worker & worker_pid=$!
cd "$project_root/frontend"
npm run dev & ui_pid=$!
echo 'Open http://localhost:5173. Press Ctrl+C to stop all three processes.'
wait

