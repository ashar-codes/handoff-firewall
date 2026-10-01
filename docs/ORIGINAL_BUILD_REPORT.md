> Historical report from the supplied source archive. These are original build claims, not the verification record for the reviewed release. See ../BUILD_REPORT.md and ../ASTRA_AUDIT.md.

# Build report — 2026-09-30

## Delivered release

Handoff Firewall 0.1.0 implements the first production-structured core requested by the supplied PRD and build specification. It includes React/TypeScript UI, FastAPI API, durable worker, PostgreSQL migrations, private original-file storage, local-model adapters, six bounded agent responsibilities, versioned requirements, source-linked evidence, structured conflicts, bundled repairs, human review, snapshot-bound approvals, deterministic readiness verification, audit events, case exports, local authentication and backend RBAC. No paid model service is required. The default runtime provider is Ollama; fixture responses require the explicit test environment.

The complete source, locked dependency manifests, container definitions, setup/run/backup scripts and documentation are included. Seven clearly labeled sample cases cover complete, missing, conflicting, stale-source, pending-review and clarification-resume scenarios. Imported sample review history is synthetic and labeled; it is not presented as a live model run.

## Executed verification

| Check | Actual result |
|---|---|
| Locked Python dependency installation | Passed with `uv sync --locked` on Python 3.12 |
| Clean frontend installation | Passed with `npm ci` on Node 24 |
| Backend lint and formatting | Ruff checks passed |
| Backend tests, disposable SQLite | 38 passed |
| Backend tests, PostgreSQL-compatible PGlite | 38 passed; this is not a native PostgreSQL load/concurrency test |
| Migrations and PostgreSQL-specific constraints | Upgrade to head, downgrade to base, upgrade to head passed on PGlite; audit/policy immutability triggers, text search and indexes checked |
| Frontend type checking and lint | TypeScript and ESLint passed |
| Frontend unit tests | 4 passed |
| Production frontend build | Vite build passed; lazy-loaded case workspace and pages |
| Real browser end-to-end tests | 3 passed with actual API, worker, UI and SSE, disposable SQLite and explicit test-model fixtures |
| Browser coverage | Conflict routing; login/intake/investigation/wait/clarification/approval/READY; refresh persistence; primary pages and case tabs at desktop and 390px |
| Visual review | Reviewed primary screens, case requirements and agent graph screenshots; responsive overflow assertions passed |

Backend tests cover tenant/RBAC boundaries, CSRF/origin/session behavior, persistent throttling, source provenance/replacement/exclusion, rule changes, original-file integrity, dependencies, conflicts, stale and expired approvals, deduplicated effects, durable waits, bounded execution, model failure and adversarial model output. Browser tests use real application endpoints rather than a mocked UI backend. Provider contract tests mock model transport; no live-model quality result is claimed.

The standard Playwright browser download was unavailable in this environment. Browser tests instead used a local Chromium 153 binary supplied by an external verification harness; that binary and the PGlite harness are not bundled. Local users can install Playwright Chromium normally using the documented command.

Non-failing dependency warnings: FastAPI/Starlette TestClient emitted an httpx deprecation warning; npm emitted transitive-package deprecation and host proxy-configuration warnings. These did not prevent installation, checks or builds.

## Verification blockers and remaining pilot gates

- No live Ollama server/model was available. Evaluate extraction, repair quality, latency, memory use and false-ready rate against reviewed historical customer cases before pilot use.
- Native PostgreSQL and Docker/Podman were unavailable in this execution environment. PostgreSQL-compatible SQL checks passed on PGlite, but native multi-worker contention, process-kill lease recovery and container builds/startup remain target-machine checks.
- macOS setup, backup/restore, TLS/proxy configuration and storage permissions must be verified on the deployment machine. No production disaster-recovery result is claimed.

## Scope and deferred capabilities

This is a working core release, not a completed enterprise rollout. External communications are approved draft records only: no email, ERP or CRM message is sent. OAuth connectors, SSO/MFA, department-level ACLs, OCR, semantic/vector retrieval, numerical tolerance rules, retention automation and enterprise deployment operations are deferred. See SECURITY.md for the trust boundaries and TESTING.md for pilot gates.

## First local commands

After installing the prerequisites in README.md and extracting the ZIP:

```bash
cd handoff-firewall
bash scripts/setup.sh
bash scripts/dev.sh
```

Setup asks for a development sample-account password. Open http://localhost:5173 and sign in as `admin@example.test` with that chosen password. Install and start the local model using README.md before evaluating model-dependent workflows.
