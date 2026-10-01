#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ "${1:-}" == "--disposable-target" ]] || { echo 'Usage: restore.sh --disposable-target BACKUP_DIRECTORY'; exit 1; }
backup_dir="${2:?Provide a backup directory}"
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
command -v uv >/dev/null || { echo 'Install uv first.'; exit 1; }
if command -v podman >/dev/null; then engine=(podman compose); else engine=(docker compose); fi
# Never restore over the configured application DB. Create a NEW isolated DB.
restore_db="handoff_restore_test_$(date -u +%Y%m%d%H%M%S)"
restore_dir="backups/$restore_db"
[[ -f "$backup_dir/database.dump" && -f "$backup_dir/files.tar.gz" ]] || { echo 'Incomplete backup.'; exit 1; }
mkdir -p backups
mkdir "$restore_dir"
backend/.venv/bin/python - "$backup_dir/files.tar.gz" "$restore_dir" <<'PY'
import sys,tarfile
from pathlib import PurePosixPath
with tarfile.open(sys.argv[1],'r:gz') as archive:
    members=archive.getmembers()
    for item in members:
        path=PurePosixPath(item.name)
        if not path.is_relative_to('data/files') or '..' in path.parts or not (item.isfile() or item.isdir()):
            raise SystemExit('Unsafe backup member; restore refused')
    archive.extractall(sys.argv[2],members=members,filter='data')
PY
"${engine[@]}" exec -T db sh -c 'createdb -U "$POSTGRES_USER" "$1"' sh "$restore_db"
"${engine[@]}" exec -T db sh -c 'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d "$1"' sh "$restore_db" < "$backup_dir/database.dump"
printf 'Isolated restore database: %s\nRestored files: %s/data/files\n' "$restore_db" "$restore_dir"
echo 'The application database was not changed. Validate the isolated database and files before any reviewed promotion.'
