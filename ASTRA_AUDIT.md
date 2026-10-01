# Handoff Firewall — independent implementation audit

Review date: 2026-10-01. This report records code inspection, reproductions, repairs and execution in the development environment. It is not a penetration-test certificate or a claim of customer production validation.

Input: supplied `handoff-firewall(2).zip`, production PRD, one-page brief and independent audit prompt. Source archive SHA-256: `2d0197c72e3a5449ba059f915880bce5185fd41cc460f54c4f67edd231fb2219`. The supplied repository was inspected before editing, including application modules, migrations, tests, UI, infrastructure and documentation. The PRD and brief were read as text. The existing application was repaired rather than replaced. Original build claims are preserved separately in `docs/ORIGINAL_BUILD_REPORT.md`.

## Executive summary

The architecture was suitable for a bounded, governed handoff product, but the original test suite missed several business-integrity failures. Reproduced defects allowed stale cached satisfaction, structured-cell injection, contradictory unreviewed evidence and operator-supplied conditional exemptions to defeat the intended readiness boundary. Worker exception handling could commit partial writes, and old claims were not fenced at checkpoints. These required repairs before relying on the product.

The reviewed release keeps the existing FastAPI/React/PostgreSQL design, six functional responsibilities, local model adapters and database worker. It adds a small shared lexical parser, claim fencing, request-body enforcement, additive migration 0003 and targeted regressions. All 61 backend tests pass on SQLite and a PostgreSQL-compatible PGlite harness; four frontend unit tests and four actual browser scenarios pass. An actual process-kill recovery drill passes on SQLite. Native PostgreSQL contention, deployment operations and live-model/customer evaluation remain gates.

## What was already strong

- Deterministic rule evaluation, explicit state transitions and finite tool authority; model output was not an unrestricted execution plan.
- Immutable template versions, explicit case migration, original document preservation and source hashes.
- Snapshot-bound action fingerprints, approval expiry/current approver checks, active-job uniqueness and idempotent action effects.
- Local Argon2 authentication, hashed session/CSRF secrets, server-side roles, tenant-scoped object lookup and conservative production configuration checks.
- Persisted checkpoints, audit events and internal requests; genuine SSE and an operational UI rather than a simulated chat demonstration.
- Locked dependencies, migrations, sample data and useful negative tests. A complete case already bypassed unnecessary repair/action work.

## Critical findings

Severity here describes impact on the product's readiness invariant, not a calculated CVSS score.

| Finding and reproduction | Repair and verification |
|---|---|
| Alias/cache mismatch: extraction recognized spaced fields that invalidation did not. A new document could introduce conflicting payment terms while cached terms remained SATISFIED and the case cleared. Multiple mutations could also discard prior dirty requirements. | Extraction and invalidation share `evidence_text.py`; invalidation accumulates dependency closure. `ready()` force-evaluates every rule before clearance. Regression asserts the conflicting case cannot become READY. |
| CSV/JSON multiline cell content became new authoritative key/value lines after conversion. An unrelated cell could manufacture a required field. | Escape cell/header boundaries, reject duplicate JSON keys and CSV headers, malformed row widths and non-finite JSON numbers. Tests cover both formats and reject ambiguous duplicate structures. |
| A contradictory model candidate could coexist with accepted evidence without preventing clearance. | Differing unaccepted candidates require review and block satisfaction. Exact evidence no longer suppresses narrative extraction from the rest of the source. Tests prove both boundaries. |

These failures mattered even though the original 38 tests passed. Eight initial audit regression cases failed on the supplied code before the fixes, establishing concrete gaps rather than speculative refactoring reasons.

## High-priority findings

1. **Conditional intake privilege bypass.** Operators could supply initial context even though editing it required reviewer authority. They could make conditional requirements inapplicable. Nonempty intake context now requires the same review permission; creation and edits record context in audit data. API denial and restricted browser intake are tested.
2. **Partial failed-step commits.** A specialist could add facts/actions, raise, and have the exception path commit those writes with its error record. Failed steps now roll back, reload the case and validate the current claim before persisting only failure state. A regression injects a write followed by failure and verifies its absence.
3. **Unfenced recovery claims.** A stale worker could checkpoint or finalize after its claim was reclaimed. `leases.py` validates generation, lease, status, active key, tenant and case at boundaries under lock. Claiming holds only the job lock; execution locks case then job. Stale checkpoint/finalization tests and process recovery pass. Native PostgreSQL race behavior still needs verification.
4. **Restore target safety.** The old disposable-target flag still restored over the configured application database. The script now creates a new database, extracts to a separate destination, rejects links/traversal and never promotes data automatically. Static and shell-syntax review passed; no container restore rehearsal was available.

## Medium/low findings

- A partial clarification completed the whole bundle and could create repeated questions. Answered keys are now tracked while the remaining original request stays WAITING.
- Rejected facts were indistinguishable from pending review and could reappear in automatic acceptance proposals. Explicit review decisions prevent that behavior.
- Conflict closure lost useful explanation. Migration 0003 adds structured kind/severity/expected value, lifecycle and resolution metadata; detail/export retain history and approvals. Legacy missing attribution is marked honestly.
- Rejected governed actions could leave an unproductive wait. They now escalate; authorized retry invalidates and replans the relevant proposals.
- SSE initially retained its dependency connection, and the UI depended too heavily on event delivery. Connections are released before streaming; current session/role/tenant is rechecked. Debounced canonical refresh and five-second polling recover a broken stream.
- Failed forms, route changes, mobile logout and graph status presentation had usability gaps. Failed forms retain values; old case data is cleared on route change; logout remains available at narrow widths; graph states reflect recorded completion/failure/wait. Approval dialogs expose source/value/quote/version/hash. Case goal text is explicitly labeled to avoid looking like current clearance.
- Actual received request bytes now enforce the size bound even with misleading headers; generic server errors no longer log potentially sensitive exception/SQL text.
- Oversized narrative and excessive exact facts previously risked incomplete interpretation. They now fail visibly for manual handling instead of accepting a partial source. Local model generation is capped.
- Vitest was updated to 4.1.11 for the development mocker advisory [GHSA-82fw-gwwq-j7x9](https://github.com/advisories/GHSA-82fw-gwwq-j7x9). No production exploit was demonstrated. Final npm and Python runtime scans reported zero known advisories.

## Agent-system assessment

The system is bounded agentic investigation and repair implemented as a state graph. It is not six autonomous conversational services. The Orchestrator observes durable state and selects an allowed next responsibility. Requirement Agent validates the pinned policy; Evidence Agent investigates authorized sources; Conflict Agent compares supported assertions; Repair Planner proposes unresolved work; Action Agent enforces human and execution authority. These are useful conceptual boundaries in one application, without needing six separate processes or LLM calls.

Routing is adaptive: complete cases skip conflict/repair/action; remaining sources are searched before outreach; contradiction, missing evidence, approval and human input drive different paths. Models assist candidate extraction and wording only. Ordinary code owns identity, roles, applicability, hashes, versions, status, budgets, retries, approval validity, idempotency and readiness. Strict schemas and literal source support limit extraction claims; a model statement cannot approve or clear a case. Event data consists of typed routing reasons and outcomes, not private chain-of-thought.

The graph shows observed dispatch counts from Orchestrator to specialists and explicit verify/wait decisions. Its chronological event list supplies ordering. Edges are not invented specialist-to-specialist conversations, and unused nodes remain uncalled.

## Minimum-repair assessment

The core differentiator exists as a practical heuristic: inspect current evidence first; compute mandatory prerequisite closure; avoid requesting a fact blocked solely by prerequisites; reuse outstanding requests; bundle by owner/action type; rank transparent effort values. Partial-reply repair now preserves unanswered work, reducing repeated interaction.

This is not a global optimization algorithm or a measured economic benefit. Effort scores are fixed heuristics, not calibrated costs or probabilities. Unknown conditional context still requires reviewer judgment. There is no semantic/vector index, broad autonomous connector discovery or learned outreach strategy. Real historical cases must measure unnecessary questions, missing-gap recall, false-ready rate, human touches and elapsed time against a checklist/fixed workflow baseline.

## Security assessment

Review covered session creation/revocation, cookie attributes, CSRF/Origin, roles, tenant-scoped case/document/fact/action/policy/user/export/SSE lookups, approval fingerprints, source paths, parsing, model authority and logging. Added cross-tenant tests exercise action/user/SSE/policy IDs in addition to existing case/document/export tests. The cookie assertion now checks actual response attributes.

Final source searches examined secrets, private keys, shell/SQL execution, deserialization, URLs, cookies, CSRF and object lookups. Fixed SQL and parser subprocesses remain trusted application code; no arbitrary shell/SQL tools are model-accessible. The inference URL comes from administrator configuration; document content cannot select a network destination. Fixture passwords are confined to explicit tests; setup generates database credentials and prompts for sample-account credentials. Packaging excludes local configuration and data.

Limits remain material: workspace-wide sharing, no database RLS, no SSO/MFA or mandatory maker/checker separation, no hardened parser sandbox, and no external immutable audit anchor. Exact structured evidence follows the configured import policy; upload permission does not authenticate an originating business claim. Consequential requirements should demand human review. No automated scan or test count establishes comprehensive security.

## Reliability assessment

Successful specialist transactions checkpoint durable state. Failed ones roll back. Fenced claims prevent stale commits; active-job uniqueness and action effect records prevent ordinary duplicate scheduling/effects. Database failures trigger bounded retry backoff. Approval execution validates the exact action/source/policy snapshot and current human authority; source mutation conservatively invalidates approval authority.

The restart drill kills an actual worker during planning after earlier checkpoints, explicitly expires its isolated lease to avoid a long wait, and starts a new worker. It verifies one clarification request, WAITING across API restart, approval/resume and READY across another restart. This proves process persistence for the tested SQLite scenario, not distributed exactly-once delivery. No external delivery connector exists.

PGlite exercised PostgreSQL-compatible SQL, migration behavior, triggers and test scenarios. It does not reproduce native PostgreSQL concurrent lock scheduling. Native two-worker contention, database disconnects during commits, target-host storage failure and backup restoration remain unverified. HTTP per-operation timeouts plus generation/run budgets do not provide a separate hard whole-response deadline against a malicious local inference server.

## Testing assessment

The supplied 38 backend tests and four frontend tests were independently rerun successfully before repair. They meaningfully covered many policy/auth/source/approval scenarios but missed cache/parser composition, intake context, candidate contradictions, transaction rollback and partial replies. New regressions assert observable business behavior, including denial and absence of effects, rather than mirroring function implementations. Fixture providers make routing repeatable but cannot validate real model comprehension.

Current verification includes 61 backend tests on each database harness, four frontend tests, four browser scenarios with actual API/worker/UI, real SSE plus forced stream failure, and an actual process kill/restart drill. Desktop and 390px screenshots cover primary pages and case tabs; visual review checked readable hierarchy, graph direction and state labels. Automated overflow assertions and browser page-error checks passed. This is not exhaustive accessibility certification or large-volume performance testing.

## Changes made

| Area | Main files and rationale |
|---|---|
| Readiness/evidence | `backend/app/domain.py`, `agents.py`, `evidence_text.py`, `parse_file.py`, `providers.py`: false-READY prevention, consistent lexical mapping and explicit budgets. |
| Auth/API | `main.py`, `action_routes.py`, `request_limits.py`: intake authority, reviewed source/fact transitions, partial replies, bounded bodies, SSE and exports. |
| Persistence/worker | `models.py`, `leases.py`, `worker.py`, migration `0003_audit_integrity.py`: review/conflict history, atomic failures and claim fencing. |
| UI | Case workspace, queue, action cards, agent graph, hooks and app navigation: exact review context, accurate state, recovery and narrow-screen operation. |
| Verification | `test_audit_regressions.py`, existing test fixes, browser scenarios and `scripts/verify-restart.py`: reproduced failures and actual recovery. |
| Operations/dependencies | Backup/restore scripts, container dependency flags/startup gate, Vitest and lockfile: safer restore destination and reproducible installation. |
| Documentation | README, architecture, agent/security/decision/testing/API docs, notices, this audit and current build report. Original report retained. |

## Verification performed

See `BUILD_REPORT.md` for exact commands and results. All executed final checks passed: locked backend install; Ruff lint/format; SQLite pytest (61); PGlite pytest (61); migration up/down/up and schema checks; frontend installation, typecheck, ESLint, unit tests (4) and build; browser E2E (4); process restart drill; shell syntax; npm/Python advisory scans; clean ZIP inspection. The final goal-label-only edit received typecheck/lint/build verification after the browser run.

The normal Playwright download failed earlier in this environment. Browser execution used an external Chromium 153 package harness, not a bundled browser. PGlite and Chromium verification dependencies are outside the release. Starlette's TestClient deprecation and host npm proxy warnings were non-failing.

## Remaining limitations

- No native PostgreSQL concurrent-worker/load verification, container build/startup, macOS execution, deployment restore, TLS/proxy or storage-permission drill.
- No live Ollama extraction/repair evaluation, real customer dataset, recall/false-ready measurement or resource benchmark.
- Queue is capped at 1,000 cases and global audit at 500 events; case history/detail are not paginated. Dashboard aggregates are over the loaded window. Large installations need pagination and measured load work.
- No live email/ERP/CRM delivery, OAuth connectors, OCR, numerical tolerances, arbitrary rule expressions, semantic retrieval, retention automation or enterprise identity/record ACLs.
- Source authenticity, policy suitability and human decision quality remain organizational responsibilities. Historical missing conflict attribution cannot be reconstructed by migration.

## Production readiness

The repaired core is runnable and substantially better defended against the reproduced integrity failures. It is appropriate for local evaluation and controlled integration work with reviewed sample/historical data. It is not cleared for an unattended business-critical rollout. Complete native PostgreSQL concurrency, deployment recovery and real-model/customer evaluation before a production pilot. These are outstanding verification gates, not hidden implemented features.
