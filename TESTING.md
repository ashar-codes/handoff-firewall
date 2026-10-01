# Verification

The complete reproducible commands are in README.md. BUILD_REPORT.md records actual results for this package.

Backend tests recreate a disposable database and use an explicit fixture model. They test authorization/tenant boundaries, authentication/CSRF/origin/throttling, source provenance and invalidation, conditional/alternative/dependency rules, adaptive routing, conflicts, bundled repairs, review/approval binding and expiry, idempotency, queued-run deduplication, step limits, model failures, hostile output, uploads, source replacement, policy migration and persisted pause/resume. Database names are guarded to prevent accidental business-data reset.

Frontend tests check disabled action behavior, link semantics, CSRF transport and safe API rejection handling. TypeScript, ESLint and production bundling are separate checks.

Playwright starts a fresh application with a disposable SQLite database and test model. It verifies login, actual SSE routing delivery, waiting-state refresh, clarification, reviewer acceptance, READY verification, ready-state refresh, real agent graph rendering and lack of page errors. It visits all primary pages and case tabs at desktop and 390px width; screenshots are generated outside the deliverable for visual review.

## Local-model evaluation

Switch to the real local provider and run representative historical cases. Evaluate missing-gap recall, false-ready rate, valid evidence links, unnecessary outreach, human touches, total/active elapsed time and compute cost. Compare against a deterministic checklist and fixed workflow. The included test-model messages are not evidence of actual model performance. Invalid/timeout output must remain visible and must not clear the case.

## Before a production pilot

- Run migrations from empty real PostgreSQL and verify immutable audit/policy triggers and search indexes.
- Run two workers with simultaneous intake/replies/approvals; kill one mid-run; confirm no duplicate effects and lease recovery.
- Build/start the containers on the target architecture; verify healthy storage permissions and local-model reachability.
- Run the flow with a real Ollama model and customer-specific reviewed requirements.
- Freeze writes, take database/files backups, restore into an isolated instance, then compare hashes, approvals and waiting-case resume.
- Review account/tenant boundaries, TLS/cookies/proxy configuration and documented security limitations.

No paid test service is required.

## Independent audit verification

The reviewed release passed 61 backend tests on disposable SQLite and the same 61 through a PGlite PostgreSQL-compatible socket harness. The latter also passed migrations up/down/up and `scripts/check_pg_schema.py` (indexes, text search, immutable audit/policy triggers). Native PostgreSQL row locking and concurrent multi-worker execution remain a separate gate.

Four frontend unit tests and four real Chromium Playwright scenarios passed. The fourth browser scenario covers policy version creation, mobile logout, restricted operator intake and canonical polling with SSE forcibly unavailable. Screenshots were reviewed at desktop and 390px; graph dispatch direction and completed/wait states derive from recorded events.

New audit regressions cover alias/cache false readiness, intake privilege bypass, CSV/JSON cell injection, contradictory candidates, mixed-source extraction, failed-step rollback, dirty-set accumulation, partial replies, rejected facts, conflict history, lease fencing, stale finalizers, database retry, cross-tenant IDs, rejected actions, READY integrity recheck, chunked body limits, safe logging, duplicate structured fields and source budgets. Eight initial reproductions failed against the supplied implementation before fixes. These are scenario assertions, not merely line coverage.

Run `cd backend && uv run python ../scripts/verify-restart.py` for a real process kill/recovery drill. It creates its own temporary database/files, kills a worker mid-step, explicitly advances the isolated abandoned lease to expiry, and verifies single-request recovery, WAITING persistence, human approval/resume and READY persistence after API restarts. The fixture provider is explicit. No live Ollama performance or native multi-process locking claim follows from this drill.

See BUILD_REPORT.md for commands/results and ASTRA_AUDIT.md for the findings. `docs/ORIGINAL_BUILD_REPORT.md` preserves supplied historical claims separately.
