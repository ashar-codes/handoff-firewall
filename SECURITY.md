# Security

## Implemented controls

- Argon2id passwords, random opaque sessions stored as hashes, eight-hour expiry, HttpOnly/SameSite cookies and hashed CSRF tokens. Unsafe requests require the configured Origin. Production requires secure cookies and HTTPS origin.
- Persistent sign-in throttling per hashed email and IP, with bounded request/password lengths. No universal production password; administrator bootstrap refuses a populated identity store.
- Backend RBAC for every operation and tenant-scoped resolution of cases, sources, actions, approvals and exports. User changes revoke sessions; worker steps recheck operational authority; approval execution rechecks approver authority.
- Locked case mutations, deduplicated active jobs and action effects, typed state transitions, bounded loops/timeouts/retries and durable waits.
- Approval fingerprint binds exact payload/recipient/connector, source versions, rule version, actor decision and expiry. Changed sources/payloads cannot reuse an old approval.
- Strict model-output schemas. Untrusted source text cannot alter policy or tool authority. Candidate extraction requires an exact source quote and literal value; semantic candidate facts require human acceptance. A hallucinated draft is only text; it cannot expand the finite action capabilities.
- PDF/TXT/CSV/JSON allowlist, 10 MiB upload limit, original-file preservation, random storage keys, confined path resolution, 0600 file mode, subprocess parser timeout/CPU/memory bounds, PDF signature and active-content checks, no pickle/untrusted object deserialization. Scanned/encrypted PDFs are rejected for extraction; failures are visible.
- Source hashes checked at verification; replacement preserves versions, invalidates dependent checks and reopens READY cases.
- Immutable ORM audit events and PostgreSQL audit/policy triggers. Model failures produce safe user-facing errors; logs exclude model prompts/source text/session secrets by default.
- Static Nginx CSP, frame denial, nosniff, no public DB/API port in full-container mode. Development DB port binds localhost.

## Reviewed attack paths

Cross-workspace ID guessing; viewer/operator permission escalation; stale approvals; duplicate run/action calls; unsafe filenames; unsupported/binary uploads; forged model quotes; document instructions requesting shell/SQL authority; invalid transitions; disappearing/changing original files; model outage; worker retries; and concurrent source/action mutation are addressed through backend boundaries and targeted tests. Filesystem/parser operations belong to trusted application code and are never model tools.

## Honest boundaries before customer production

1. Workspace read scope is shared among its authorized members. Department/record-level ACLs and PostgreSQL RLS are not implemented. Use a separate workspace/database boundary when customers require narrower sharing.
2. Authentication is local. SSO/MFA and enterprise identity provisioning are deferred. Reviewers may approve their own work under the current role model; enforce organizational separation through accounts/process until a maker/checker policy is added.
3. Structured key/value evidence is accepted under the approved import policy unless a requirement requires human review. Upload access does not prove the authenticity of the originating business document; configure human review for consequential assertions. The agent verifies configured documentary readiness, not legal entitlement or physical workmanship.
4. PDF parsing is constrained, but the subprocess is not a hardened OS/container sandbox. Deploy parsers in a dedicated container with network disabled and strict resources for hostile public upload environments. Antivirus, OCR and comprehensive PDF active-content sanitization are deferred; files are download-only, never embedded active content.
5. Application checks enforce tenant association. The database is not a zero-trust boundary against an administrator with write privileges. A privileged DB owner can disable triggers or alter records. Audit anchoring to a separately controlled service/WORM storage is deferred.
6. TLS, disk/backup encryption, least-privilege DB roles, outbound-network controls, reverse-proxy configuration and backup/restore operations are deployment responsibilities. The Compose example is localhost development, not an Internet-ready production configuration. Do not expose Ollama unauthenticated.
7. Retention/deletion automation, tenant-wide exports, OAuth connectors and email delivery are deferred. A case export is available now. Align retention and access policies with the first customer before collecting real records.
8. Real PostgreSQL multi-worker contention, kill/recovery tests under load, container builds, backups/restores on target infrastructure and live-model evaluation must pass before a production pilot. Do not equate the included fixture tests with an independent penetration test or a completed customer validation.

## Secrets and reporting

`.env`, installed dependencies, uploaded documents, model weights and database contents are excluded from the deliverable. Fixture credentials occur only in explicit disposable tests; development seed passwords are user-chosen. Rotate credentials if a local configuration is exposed. Report security defects with the affected route, role, expected boundary and a sanitized reproduction, never real source documents or secrets.

## Independent audit repairs (2026-10-01)

The audit reproduced false-READY paths involving stale cached alias mappings, injected structured cell boundaries and unreviewed contradictory candidates. Shared field mapping, accumulated invalidation, full final rule evaluation, escaped structured cells and candidate review blocks close those paths. Intake conditions now require the same reviewer authority as condition edits. Rejected evidence remains rejected across automatic batch review.

Worker commits/finalization are fenced by the current claim generation and unexpired lease; failed steps roll back partial writes. The request-body limit counts actual received bytes rather than trusting Content-Length. Generic exception logging omits exception text/SQL parameters. SSE rechecks current identity/role/tenant and releases its initial connection before streaming. Backup output has restrictive permissions; restore creates a new isolated database and rejects unsafe archive members.

Static review and negative tests covered the routes and boundaries described in ASTRA_AUDIT.md. The actual worker kill/recovery drill passed on SQLite; native PostgreSQL contention remains unverified. Dependency scanners reported no known advisories at verification time after the justified Vitest update; this is not proof that dependencies or this application are vulnerability-free. The model URL is administrator-controlled configuration, not an uploaded-document/API-selected URL; no arbitrary browsing tool is exposed.
