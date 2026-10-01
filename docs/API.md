# API quick reference

Base path `/api`. Reads require a signed-in session; mutations require the exact configured Origin and `X-CSRF-Token` equal to the `hf_csrf` cookie. Login sets an HttpOnly session cookie. The React client implements this transport. API tool boundaries are internal application capabilities, not arbitrary model-controlled HTTP calls.

| Operation | Route | Authority |
|---|---|---|
| Sign in/out and current identity | POST `/auth/login`, POST `/auth/logout`, GET `/auth/me` | Local account |
| Users | GET/POST `/users`, PATCH `/users/{id}` | Read / Administrator |
| Template versions | GET/POST `/templates`, POST `/templates/{id}/versions` | Read / Policy |
| Case intake/list/detail | POST/GET `/cases`, GET `/cases/{id}` | Operate / Read |
| Run/resume | POST `/cases/{id}/run` | Operate |
| Escalate/reopen | POST `/cases/{id}/transition` | Reviewer; never direct READY |
| Update conditions | PUT `/cases/{id}/context` | Reviewer |
| Migrate rule version | POST `/cases/{id}/rules/{templateId}` | Policy |
| Upload/replace evidence | POST `/cases/{id}/documents` multipart `file`, optional `replaces_id` | Operate |
| Retrieve original/search | GET `/documents/{id}/download`, GET `/cases/{id}/search?q=…` | Read |
| Accept/reject/supersede fact | POST `/facts/{id}/review` | Reviewer |
| List/approve/reject actions | GET `/actions`, POST `/actions/{id}/decision` | Read / Reviewer |
| Execute permitted internal action | POST `/actions/{id}/execute` | Operate + action policy |
| Record assigned clarification | POST `/actions/{id}/reply` | Assigned owner or reviewer |
| Prepare external draft | POST `/cases/{id}/external-drafts` | Operate, after search; no delivery |
| Export/audit/live events | GET `/cases/{id}/export`, GET `/audit`, GET `/cases/{id}/events?after=…` | Read |
| Health/runtime | GET `/health`, GET `/system` | Health public / Administrator |

CSV/JSON evidence files are first-class inputs. For bulk case intake, use the authenticated case-intake API with stable business keys; duplicate keys return 409. A general CSV-to-case mapper or external webhook delivery service is not included. Source-system integrations can read status from the case API without a messaging connector.

Rule fields are accepted aliases of one factual assertion (for example `po_number` or `purchase_order`). Differing accepted values conflict. Conditions have exactly `field` and `equals`; a missing context field is ambiguous, never implicitly false. Dependencies are an acyclic list of requirement IDs. `expected` enforces a normalized exact value. Numerical tolerances and arbitrary rule expressions are not supported in this release.

## Reviewed API details

- `POST /cases` requires reviewer permission when `context` is nonempty; an operator may create a case with unknown conditions.
- `POST /cases/{id}/run` supports re-verification of READY and authorized retry of ESCALATED cases. It never bypasses the readiness checks.
- `POST /documents/{id}/exclude` requires reviewer authority and invalidates dependent conclusions while preserving the original version.
- Partial `POST /actions/{id}/reply` keeps the request WAITING until remaining requirements are answered. `result.answered_requirements` identifies answered keys; duplicate answers to an already answered key are rejected.
- Fact review records an explicit decision and source-linked audit metadata. Rejected facts are not automatically included in later review batches.
- Case detail/export includes approval records and `conflict_history`, including closed conflicts and resolution metadata. Migration 0003 marks previously closed records as `LEGACY_CLOSED` where historical detail was not stored.
- SSE clients should refresh canonical case state after reconnect and poll if streaming fails; event order is not a substitute for current authorized state.
