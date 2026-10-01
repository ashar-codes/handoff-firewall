# Handoff Firewall

Handoff Firewall checks whether a business handoff has the evidence required by its receiving team. It searches the case’s authorized documents, records contradictions, bundles repair requests by owner, pauses for human input, and clears the case only after deterministic verification.

This repository implements the first production-structured core release. It is not a claim of completed customer-pilot validation. Read **ASTRA_AUDIT.md** for the independent code review and repairs, and **BUILD_REPORT.md** for checks actually executed and remaining deployment checks.

## First local run on macOS

Prerequisites: Python 3.12+, **uv**, Node.js **24 LTS**, PostgreSQL 17 or a compatible container runtime, and optionally Ollama. No paid API is required. Podman is a free alternative to Docker Desktop.

For a fresh Mac with Homebrew:

```bash
brew install uv node@24 podman podman-compose ollama
podman machine init
podman machine start
```

Ensure `node` and `npm` resolve to Node 24 (`node --version`); follow Homebrew’s PATH instructions if Node 24 is keg-only. Skip machine initialization if your Podman machine already exists.

Extract the ZIP and run:

```bash
cd handoff-firewall
bash scripts/setup.sh
bash scripts/dev.sh
```

Setup installs locked dependencies, generates a random development database password, starts PostgreSQL, runs migrations, and asks you to choose a **sample-account password**. Use `admin@example.test` and that chosen password at **http://localhost:5173**. Additional sample accounts are `operator@example.test`, `reviewer@example.test`, and `viewer@example.test`; they use the same chosen development password. No production account or universal production password is shipped.

Setup does not download model weights. Without a local model, the UI remains usable; model-dependent work exposes an operational error and preserves a manual repair path.

## Local model

In another terminal:

```bash
ollama serve
ollama pull qwen2.5:7b
```

The default backend configuration uses:

```dotenv
MODEL_PROVIDER=ollama
MODEL_BASE_URL=http://127.0.0.1:11434
MODEL_NAME=qwen2.5:7b
MODEL_TIMEOUT=30
```

Choose a model that fits your machine and whose license permits your intended commercial use. The default 7B model can be demanding on low-memory Macs. The application does not assert model-quality targets until evaluated on your real cases. Ollama structured outputs are validated by Pydantic; invalid output gets one bounded retry.

For another local OpenAI-compatible inference server, set `MODEL_PROVIDER=openai-compatible`, set `MODEL_BASE_URL` to its `/v1` URL, and set `MODEL_NAME`. No consumer ChatGPT/Claude subscription is used at runtime.

## First workflow to exercise

1. Open **Handoff queue**, then the sample complete order. Run investigation; it should go to READY without repair planning.
2. Open the sample order with conflicting terms. Run it, inspect the source facts, structured conflict, bundled clarification and review action.
3. In **Repair plan**, record a missing tax identifier. The reply is candidate evidence, not an automatic proof.
4. Accept source-linked candidate evidence using **Action center** or the fact viewer. To settle conflicting terms, explicitly accept the governing fact and select the conflicting fact it supersedes, with a reason.
5. Run/resume verification. Source changes reopen the case and invalidate affected decisions. Unrelated outstanding internal requests are retained.
6. Export the handoff package as JSON. Original documents remain separately downloadable.

The UI is operational rather than chat-led. **Agent activity** displays real recorded dispatches and outcomes, not simulated progress.

## Native PostgreSQL without containers

Install PostgreSQL, create an empty database and an application user, then:

```bash
cd handoff-firewall
cp .env.example backend/.env
# Edit backend/.env: DATABASE_URL must point to your PostgreSQL database.
cd backend
uv sync --locked
uv run alembic upgrade head
uv run python -m app.seed
cd ../frontend
npm ci
cd ..
bash scripts/dev.sh
```

Keep `FRONTEND_ORIGIN=http://localhost:5173`; open that exact URL. Settings load `backend/.env` for native backend commands. Root `.env` configures Compose. If changing shared settings, keep the two files consistent.

To use an empty workspace instead of samples:

```bash
cd backend
uv run python -m app.bootstrap --email you@example.com --name "Your name" --workspace "Your business"
```

Bootstrap prompts for a password and refuses to run after any user exists. Create further accounts in Administration. Disabling an account, changing its role or resetting its password revokes its sessions. Administrators cannot disable/demote themselves.

## Individual run commands

From `backend/`, in separate terminals:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
uv run python -m app.worker
```

From `frontend/`:

```bash
npm run dev
```

Health: `http://127.0.0.1:8000/api/health`. OpenAPI: `http://127.0.0.1:8000/docs`. Every unsafe API call requires the configured Origin; authenticated mutations additionally require the CSRF token supplied by the UI.

## All-container option

Generate/edit root `.env`, then use `podman compose` or `docker compose`:

```bash
docker compose --profile full up --build -d
docker compose exec api uv run python -m app.bootstrap --email you@example.com
```

Open **http://localhost:8080**. This is a local development configuration. For Podman, set `CONTAINER_MODEL_BASE_URL` to a host address reachable from its VM, for example `http://host.containers.internal:11434`, where supported. Do not expose Ollama publicly. Native API + containerized PostgreSQL is the recommended first Mac setup.

Before remote production deployment, configure TLS, `APP_ENV=production`, `COOKIE_SECURE=true`, the exact HTTPS `FRONTEND_ORIGIN`, restricted DB credentials, persistent storage, backup encryption and restore checks. Production refuses SQLite, insecure cookies and the test model provider. See SECURITY.md.

## Tests and checks

```bash
cd backend
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run pytest -q
cd ../frontend
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium
cd ..
bash scripts/verify-e2e.sh
```

`verify-e2e.sh` creates a new disposable SQLite database/file store, runs actual migrations, starts API/worker/UI, and runs Playwright with an explicit **test-only** model provider. It never targets your configured production database. It requires ports 8000/5173 to be free. For PostgreSQL-specific backend checks, create a disposable database named **handoff_test** and run:

```bash
cd backend
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/handoff_test uv run pytest -q
```

Tests refuse other target database names. They recreate application tables. Never point them at business data.

## Migrations, backup and restore

```bash
cd backend
uv run alembic current
uv run alembic upgrade head
```

Migration `0001` creates the schema; `0002` creates search indexes; additive `0003` records explicit evidence decisions and conflict lifecycle metadata. When upgrading an existing installation, stop API/worker writes, back up data, run `uv run alembic upgrade head`, and restart both processes. Old resolved conflicts are marked `LEGACY_CLOSED`; missing historical attribution is not invented. Downgrades are for an empty/disposable database or a reviewed recovery process and can destroy records. Take backups first. There is no automatic destructive reset command for your working database.

Stop API/worker writes before a consistent native-application backup, then from the root:

```bash
bash scripts/backup.sh
bash scripts/restore.sh --disposable-target backups/YOUR_BACKUP_DIRECTORY
```

These scripts cover **native backend file storage + Compose PostgreSQL**, not the full-container named file volume. For full containers, back up both the database and `files` volume during a write freeze. File keys are relative to the configured store so backups can move to another host. The restore script creates a new `handoff_restore_test_TIMESTAMP` database and restores files beneath `backups/` without overwriting the application database. It rejects archive traversal and links. Compare case counts, original-file hashes, approvals, and waiting-case resume in that isolated target before any separately reviewed promotion. Production disaster recovery remains a deployment check.

## Troubleshooting

- **Database unavailable:** inspect `podman compose logs db` / `docker compose logs db`, and verify `backend/.env`. A conflicting port 5432 requires changing the mapping and database URL together.
- **Origin not allowed:** open `http://localhost:5173`, not `http://127.0.0.1:5173`, unless you changed `FRONTEND_ORIGIN` accordingly.
- **Model error:** check `ollama list`, model name, server URL, machine memory and timeout. Deterministic complete cases can still verify; manual requests/evidence review remain available.
- **A scanned/encrypted PDF is unreadable:** upload a text-layer PDF or a supported text/structured export. OCR is not implemented.
- **Waiting case does not move:** check the worker terminal, Action center, evidence acceptance and unresolved conflicting facts. A reply alone is not approval.
- **Run after crash:** queued jobs recover automatically; running jobs recover after the bounded lease expires. Cases and completed actions persist.
- **Changed policy:** creating a new template version does not alter existing cases. An authorized policy manager can migrate a case using `POST /api/cases/{case_id}/rules/{template_id}`.
- **Sign-in throttled:** wait 15 minutes; controls persist in the database.

## Scope of this release

Manual/API intake, versioned policies, exact alias retrieval, safe file parsing, model-proposed candidate extraction, conflicts, dependency-aware bundled repairs, approvals, internal requests, external drafts, live events and exports are implemented. Email/ERP/CRM delivery, OAuth connectors, SSO, OCR, numerical tolerance rules, semantic/vector retrieval, retention automation and multi-server deployment operations are deferred. No interface claims those integrations are live.

All workspace members with read permission can read that workspace’s cases; department-level ACLs are not yet implemented. Commercial rollout should begin with one reviewed handoff and measured historical cases, not unchecked general-purpose autonomy.

## Reviewed behavior and recovery

Only reviewers/administrators may supply nonempty case conditions at intake or edit them later. Unknown conditions remain ambiguous. Partial clarification replies preserve the unanswered portion of the original request. Rejected facts are not automatically proposed again for batch acceptance. Conflict history and exact approval records are included in case detail/export.

Incremental checks use accumulated dependency invalidation; the final READY gate recomputes all rules and verifies original bytes. **Reverify handoff** checks a READY case again. Mixed structured/narrative documents are fully considered within bounded extraction: narrative sources over 16,000 characters or more than 200 exact matches require manual handling rather than silently accepting a partial source. Correct or split an oversized source, exclude its old version with reviewer authority, and review the replacement evidence.

To run the independent process-recovery drill on disposable SQLite:

```bash
cd backend
uv run python ../scripts/verify-restart.py
```

This kills an actual worker mid-planning, accelerates lease expiry in the isolated fixture, recovers with a new worker, and restarts the API in WAITING and READY. It is not a PostgreSQL concurrency/load test.
