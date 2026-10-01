#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
command -v uv >/dev/null || { echo 'Install uv first (macOS: brew install uv).'; exit 1; }
command -v npm >/dev/null || { echo 'Install Node.js 24 LTS first.'; exit 1; }
cd backend
uv sync --locked
cd "$project_root"
if [[ ! -f .env ]]; then
  backend/.venv/bin/python - <<'PY'
from pathlib import Path
import secrets,os
password=secrets.token_hex(24)
content=Path('.env.example').read_text().replace('REPLACE_WITH_RANDOM_PASSWORD',password)
Path('.env').write_text(content)
os.chmod('.env',0o600)
PY
fi
if [[ ! -f backend/.env ]]; then cp .env backend/.env; chmod 600 backend/.env; fi
if command -v podman >/dev/null; then engine=(podman compose)
elif command -v docker >/dev/null; then engine=(docker compose)
else echo 'Install Podman and a Compose provider, or configure an existing PostgreSQL server in backend/.env.'; exit 1; fi
"${engine[@]}" up -d db
cd backend
uv run python - <<'PY'
from app.db import engine
from sqlalchemy import text
import time
for attempt in range(60):
    try:
        with engine.connect() as connection: connection.execute(text('SELECT 1'))
        break
    except Exception: time.sleep(1)
else: raise SystemExit('PostgreSQL did not become ready; inspect container logs and backend/.env')
PY
uv run alembic upgrade head
uv run python -m app.seed
cd "$project_root/frontend"
npm ci
echo 'Setup complete. Run: bash scripts/dev.sh (from the project root).'

