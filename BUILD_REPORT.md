# Reviewed build report — 2026-10-01

This is the verification record for the repaired source release. `ASTRA_AUDIT.md` describes findings and remaining risks. `docs/ORIGINAL_BUILD_REPORT.md` preserves the report supplied with the input archive; its claims were not treated as evidence.

## Baseline and changes

Before repairs, the supplied code independently passed its 38 backend tests, four frontend unit tests, lint/type checks and frontend build. Eight initial new regression cases failed against that baseline. Repairs address false READY, intake condition privileges, CSV/JSON boundary injection, unreviewed contradictions, mixed-source search, atomic worker failure, claim fencing, partial replies, evidence rejection, conflict history, SSE recovery and safe restore destinations. Migration 0003 is additive. The existing architecture and free local runtime are retained.

## Executed verification

Commands below use repository-relative paths unless explicitly marked as an external harness.

| Check | Command | Observed result |
|---|---|---|
| Locked backend install | From `backend`: `uv sync --locked` | Passed; 47 lock entries, 44 environment packages, Python 3.12.14 |
| Ruff | From `backend`: `uv run ruff check .` and `uv run ruff format --check .` | Passed; 33 formatted files |
| Backend SQLite | From `backend`: `uv run pytest -q` | **61 passed**, one TestClient deprecation warning; 28.20 seconds |
| PostgreSQL-compatible migrations | `uv run alembic upgrade head`; `PYTHONPATH=. uv run python ../scripts/check_pg_schema.py`; `uv run alembic downgrade base`; `uv run alembic upgrade head` on an isolated PGlite socket target | Passed through 0003; immutable audit/policy triggers, text search and indexes verified |
| Backend PostgreSQL-compatible | `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:55436/handoff_test uv run pytest -q --tb=short` | **61 passed**, one TestClient warning; 37.22 seconds |
| Frontend locked install | From `frontend`: `npm ci` (earlier in audit) | Passed on Node 24; dependency update retained lockfile |
| Frontend static checks | `npm run typecheck`; `npm run lint` | Passed; repeated after final goal-label edit |
| Frontend unit tests | `npm test` | **4 passed** across two files with Vitest 4.1.11 |
| Production bundle | `npm run build` | Passed; repeated after final goal-label edit |
| Real browser E2E | From root: `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/tmp/astra-chromium LD_LIBRARY_PATH=/tmp/astra-browser-libs/lib:/tmp/astra-browser-libs QA_SCREENSHOT_DIR=/tmp/astra-ui-final bash scripts/verify-e2e.sh` | **4 passed** in 25.1 seconds; real API, worker, UI, disposable SQLite, explicit fixture model |
| Process restart | From `backend`: `uv run python ../scripts/verify-restart.py` | Passed: actual worker killed mid-planning, lease accelerated to expiry, recovery creates one request; WAITING and READY survive API restarts |
| Shell syntax | `bash -n scripts/*.sh` | Passed |
| JS advisories | From `frontend`: `npm audit --json` | 0 reported vulnerabilities |
| Python runtime advisories | `uv export --locked --no-dev --format requirements-txt --no-hashes > /tmp/astra-runtime-requirements.txt`; `uvx pip-audit -r /tmp/astra-runtime-requirements.txt --no-deps --disable-pip --format json` | 36 dependencies scanned; 0 known vulnerabilities reported |
| Release inspection | ZIP CRC, root/exclusion/required-file checks, clean extraction, Python AST parsing and source diff inventory | Passed; see `docs/RELEASE_MANIFEST.json` |

### External database harness

Native PostgreSQL and container runtimes were unavailable. The audit installed `@electric-sql/pglite@0.5.8` and `@electric-sql/pglite-socket@0.2.11` outside the repository. It ran:

```bash
/tmp/astra-tools/node_modules/.bin/pglite-server \
  --port=55436 --host=127.0.0.1 --db=memory:// --max-connections=20 \
  --run 'bash /tmp/astra-check-pg.sh'
```

The child script exported `DATABASE_URL` to the disposable `handoff_test` socket target, `APP_ENV=test`, `PYTHONPATH=.`, ran the migration/schema commands in the table, then exported `TEST_DATABASE_URL="$DATABASE_URL"` and ran the entire pytest suite. Child exit code was zero. PGlite SQL success does **not** establish native PostgreSQL concurrent locking or multi-worker safety under load.

### Browser and visual scope

The normal Playwright Chromium download failed earlier in this environment. An external `@sparticuz/chromium` package supplied Chromium 153 and supporting libraries. That binary, its dependencies and screenshots are not bundled. Local users should run `npx playwright install chromium`, then `bash scripts/verify-e2e.sh` normally.

Verified scenarios: conflict routing cannot clear; login/intake/real SSE/wait/clarification/approval/READY/refresh; six primary screens and five case tabs at desktop and 390px; policy creation/versioning, mobile sign-out, restricted operator intake and polling recovery with SSE deliberately blocked. Page-error and document-overflow assertions passed. Screenshots were reviewed for layout and graph direction/status. A final text-only change labels the case objective as `Goal:`; typecheck, lint and build were rerun afterward.

### Warnings

Starlette's TestClient emitted an httpx deprecation warning. npm emitted host proxy configuration warnings and some transitive dependency deprecations during installation. `pip-audit` warned that the exported pinned scan input omitted hashes; installation itself used the lockfile. These warnings did not fail verification. Advisory scans are time-specific and not security certification.

## Checks not performed / pilot gates

- Native PostgreSQL simultaneous workers, contention and crash/commit races.
- Docker/Podman builds/startup and macOS execution.
- Live Ollama model quality, latency, resource use and historical customer case evaluation.
- Deployment backup/restore, TLS/proxy and storage permissions. Restore safety changes received static review, not a live container rehearsal.
- Large-volume performance, complete accessibility audit or independent penetration test.

This is a runnable repaired core for controlled evaluation, not an approved unattended production rollout. External communication remains persisted drafts only; no email/ERP/CRM delivery is claimed. Other deferred scope is documented in README and SECURITY.

## First local macOS run

With Homebrew installed:

```bash
brew install uv node@24 podman podman-compose ollama
export PATH="$(brew --prefix node@24)/bin:$PATH"
podman machine init
podman machine start
unzip handoff-firewall-astra-reviewed.zip
cd handoff-firewall
bash scripts/setup.sh
bash scripts/dev.sh
```

Skip `podman machine init` if already initialized. Setup prompts for the development sample password. Open `http://localhost:5173`; sign in as `admin@example.test` with that password. Start `ollama serve` in another terminal and run `ollama pull qwen2.5:7b` before exercising model-dependent paths. No model weights or paid runtime service are bundled or required.
