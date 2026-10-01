#!/usr/bin/env bash
set -euo pipefail
umask 077
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
if command -v podman >/dev/null; then engine=(podman compose); else engine=(docker compose); fi
backup_dir="${1:-backups/$(date -u +%Y%m%dT%H%M%SZ)}"
[[ ! -e "$backup_dir" ]] || { echo 'Backup directory already exists; choose a new path.'; exit 1; }
(cd backend && uv run python - <<'CHECK'
from pathlib import Path
from app.config import settings
if Path(settings().storage_path).resolve() != Path('data/files').resolve():
    raise SystemExit('This backup script requires default backend/data/files storage; use a reviewed custom-store backup procedure.')
CHECK
)
mkdir -p "$backup_dir"; chmod 700 "$backup_dir"
"${engine[@]}" exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_dir/database.dump"
tar -czf "$backup_dir/files.tar.gz" -C backend data/files
chmod 600 "$backup_dir"/*
echo 'Backup written. Keep both files together and encrypt backups at rest.'

