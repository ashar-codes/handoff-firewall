# Agent implementation and contributor rules

Repository code, migrations and tests are authoritative. Preserve security, correct readiness, persisted waits and explainability ahead of feature count. Run relevant checks after changes. Never use a test provider silently as a runtime fallback. Do not expose arbitrary shell, SQL, files or browsing to a model. Never commit secrets, business documents, databases or model weights.

## Responsibilities and tools

| Agent | Input and responsibility | Permitted capabilities and output |
|---|---|---|
| Orchestrator | Persisted case, graph observations, rule/evidence state, budgets | Select an allowlisted specialist or VERIFY/WAIT/MANUAL/STOP; record typed routing event |
| Requirement Agent | Tenant-scoped immutable template version | Validate `Rule`, verify canonical hash, establish requirement state; cannot invent requirements |
| Evidence Agent | Authorized current case documents and rules | Narrow case search/read/match; create source-linked `Fact` objects; model `Extracted` output is strict and candidate-only |
| Conflict Agent | Current accepted facts and applicability | Normalize/compare values, respect explicit authority, create `Conflict` records; cannot invent precedence |
| Repair Planner | Unresolved mandatory dependency closure, existing requests, owners | Bundle review/clarification actions with owner, prerequisites, affected rules, exact payload and snapshot; strict `Draft` output only affects message wording |
| Action Agent | Persisted proposed/approved actions | Create internal request, accept explicitly human-approved candidate facts, record approved external draft, enforce idempotency and authority; no external delivery |

`app/agents.py` implements these six responsibilities over shared durable state. Specialist outputs are ordinary domain records and summaries. Models return Pydantic `Extracted` or `Draft` schemas. Unknown JSON fields are rejected. Document instructions have no authority. A model cannot select arbitrary tools or directly change statuses.

## Routing

Missing approved initialization invokes Requirement Agent. Remaining sources invoke Evidence Agent. Actual conflicts invoke Conflict Agent. If mandatory evidence is current and sufficient, verification bypasses repair. Otherwise Repair Planner proposes permitted grouped actions; Action Agent runs those whose policies permit execution. Pending approval/input persists and stops. New input invalidates affected conclusions and resumes through verification. Escalated cases need authorized retry.

Precedence in `route()`: terminal state stops; Requirement Agent until initialized; Evidence Agent until searched; a human-APPROVED action goes to Action Agent before the source/extraction-failure MANUAL fallback (execution still revalidates approval fingerprint, expiry, approver authority and snapshot); source/extraction failure → MANUAL; actual contradiction → Conflict Agent; every mandatory requirement SATISFIED with affirmative support → VERIFY (full recomputation); Repair Planner if unplanned; permitted actions → Action Agent; otherwise WAIT. While an extraction failure is recorded, Action Agent executes only human-approved actions. Wording failure never holds a case: the planner always has deterministic professional wording and records a visible `model_failure` or `wording_rejected` event. Human replies, evidence decisions and uploads are applied at the API through `invalidate()` before the next run.

A run after a failure is a retry, not new evidence: it keeps the revision, existing proposals, approvals and sent requests, and repeats investigation/drafting. Repair Planner never creates a second action for the same case, owner, kind, requirement set and source/rule snapshot; it reuses outstanding WAITING requests and may refresh only an unsent, unapproved proposal's wording. A genuine source/evidence change invalidates related requests and may justify a new, narrower one.

## Budgets

Default: 24 specialist/routing steps, 180 elapsed seconds, 30 seconds per model request, one model retry, one document per evidence checkpoint, and at most two model drafting calls per planning step. Remaining groups after the drafting budget get explicit manual proposals and a visible failure/budget event. A worker claim gets a lease long enough for the elapsed budget plus bounded in-flight calls; at most three recovery claims. These limits prevent unrestricted loops, not malicious database-administrator activity.

## Human authority

Operators create cases, upload files and reply to their assigned requests. Reviewers accept evidence, explicitly resolve conflicts, edit conditions, and approve governed actions. Policy managers create versions/migrate cases. Administrators manage access. AI never approves for anyone. Runtime agents are not permission-granting roles.

## Testing requirements

Use test-only providers for repeatable scenario assertions. Confirm complete cases skip unnecessary nodes, conflicting cases do not clear, requests are bundled, replies require review, stale approvals fail, and state survives restarts. Include malformed/adversarial model outputs and cross-workspace requests. Use the production local provider separately for model-quality evaluation; fixture success is not a quality claim.

## Audit additions

Final verification recomputes the bounded rule set; cache satisfaction is never clearance authority. Narrative search still runs when exact fields were found. A contradictory unreviewed candidate prevents clearance. Every worker checkpoint must retain a valid generation-fenced lease; specialist exceptions roll back partial facts/actions. Partial replies must not complete unanswered questions or trigger duplicate outreach. Rejection is a distinct human decision and is never silently converted to acceptance.

Model generation is capped at 2,048 tokens; extraction refuses oversized narrative/over-budget exact matches with a visible manual path. HTTP operation timeouts and run budgets do not constitute an independently enforced whole-response deadline against a malicious inference server; deploy the configured local inference endpoint as trusted infrastructure.

## Readiness, normalization and communication (alpha hardening)

READY requires every mandatory requirement to be SATISFIED with a recorded support trace (accepted current facts with document, version, hash, method, reviewer and normalized value); absence of a conflict is never support. Values are compared after deterministic typed normalization (`app/normalization.py`, version `biz-v1`): payment terms to net days, explicit-currency amounts with `Decimal`, identifier case/separators only. Vague or multi-valued text stays raw and can only cause review. Payment terms and amounts stated in prose are also detected deterministically and stored as candidates, so a contradiction the model misses still blocks READY, while an equivalent statement does not.

Repair actions carry structured `questions` and a business `reference`. `app/communication.py` renders deterministic professional wording; a model may only polish it, and its output is rejected unless it keeps the reference and every topic, uses only the deterministic wording's vocabulary plus courtesy words, and contains no internal identifiers, state labels, field names, links, addresses or authority claims. Wording is excluded from internal action fingerprints, so rewording never creates a new action or invalidates an approval; an external draft's approved text remains bound.
