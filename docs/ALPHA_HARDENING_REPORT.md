# Alpha hardening report

Branch `alpha-quality-hardening`, compared with baseline `0209fe9`. All data is synthetic. Model: Groq `openai/gpt-oss-120b`, strict JSON schema, `reasoning_effort=medium`.

## What changed

1. **READY coverage.**
   - Every SATISFIED requirement now carries a persisted support trace: fact, document, version, hash, method, reviewer, raw and normalised value, and normaliser version.
   - `ready()` refuses any mandatory requirement without affirmative support.
   - Payment terms and amounts stated in prose are detected deterministically and stored as candidates. A contradiction the model misses therefore still blocks READY; an equivalent statement does not.
   - No extra model call was added.
2. **Deterministic normalisation** (`app/normalization.py`, `biz-v1`):
   - Payment terms normalise to net days. Vague, multi-valued, discount-style or business-day terms stay raw.
   - Amounts are `Decimal`s with an explicit currency. A currency is supplied only by an approved rule `currency`, never guessed.
   - Identifiers normalise only case and separators; look-alike characters are never merged.
   - The value type comes from the rule's `value_type`, or is inferred conservatively from field names.
3. **Communication layer** (`app/communication.py`):
   - Actions carry structured `questions` and a business `reference`.
   - Deterministic professional wording is always available.
   - A model may only polish that wording. Its output is rejected unless it keeps the reference and every topic, stays within the deterministic wording's vocabulary plus neutral courtesy words, and contains no IDs, state labels, field names, links, addresses or authority claims.
   - Wording is excluded from internal-action fingerprints. An external draft's text stays bound.
   - A wording failure no longer holds a case; it records `model_failure` or `wording_rejected`.
4. **UI:** action cards show plain-language topics.
5. **Provider:** Groq error `type/code` is now logged, never the message.
6. **Harness:** 18 new cases, message-quality, equivalence and support metrics, timestamped output files.

Existing ground truth was not changed. The new cases (C22–C39) were written before any model run of this phase. Two new cases received unique business keys after a dry run collided with seeded keys; the identifier values under test were kept.

## Before / after

| Metric | Baseline `0209fe9` | Hardening (live) |
|---|---|---|
| Cases | 24 | 42 (the same 24 + 18 new) |
| Fully correct | 20 | 40 (22 of the original 24) |
| Safely escalated | 4 | 1 (C07, stale approval) |
| Incorrect | 0 | 1 (C06, hidden approval missed by the model) |
| Unsafe | 0 | 0 |
| False READY | 0 | 0 |
| READY without affirmative support | not measured | 0 |
| Unsupported facts proposed by the model | 3 | 3 |
| Unsupported facts accepted by the system | 0 | 0 |
| Unsafe actions / duplicate outreach | 0 / 0 | 0 / 0 |
| Human-facing messages with internal IDs | 7 of 27 | 0 of 39 |
| Messages with jargon | most | 0 |
| Unnecessary human requests | 1 | 1 (C06, a consequence of the recall miss) |
| Equivalence cases resolved without a human | 0 of 2 (C04, C16) | 6 of 6 (C04, C16, C24, C28, C30, C32) |
| Strict outputs valid | 44 of 44 | 61 of 61 |
| Model calls per case | 1.83 | 1.45 (1.75 on the original 24) |
| Tokens per call | about 760 | about 840 |
| Median / p95 latency | 1.06 s / 2.36 s | 1.55 s / 2.44 s (one 20.7 s Groq outlier) |

**Semantic equivalence:** `Net 30` vs `within thirty days` now reaches READY directly, with no human (C04, C24, C28).

**Currency formatting:** `PKR 500,000` vs `Rs. 500000` now reaches READY directly (C16, C30). PKR vs USD remains a structured conflict (C31).

**Missed extraction:** it can no longer silently clear a payment-terms or amount contradiction.
- C22 (a prose contradiction against an ERP value) is blocked in the live run, in a model-free run and in the outage run.
- C03 had become READY in a model-free run on the baseline; it is now blocked.
- **Residual gap:** contradictions in prose about free-form identifiers (for example a different tax ID stated only in prose) are still detected only by the model.

**Messages:** every new message uses business references, plain topic names, and values with source document names. 38 of 40 live model rewrites were rejected by the first validator version, almost all because of the word "reference". So every message in that run is the deterministic wording.

## Evaluation runs and their validity

| Run | Use |
|---|---|
| **Hardening run** (01:16–01:27, 42 cases, 61 calls, 0 rate limits) | The live result above. Code identical to the commit except for the validator vocabulary, provider error-code logging and harness file naming. The per-case JSON was overwritten by the next run, a harness flaw now fixed; the console per-case results and summary are recorded here, and the raw model calls are kept in `groq-openai-gpt-oss-120b.hardening-run-calls.jsonl`. |
| Validator vocabulary widened afterwards | Measured offline on the 39 recorded rewrites only: the vocabulary check now passes 34 of 39. Not yet verified live. |
| Second live run (01:39–01:50) | Invalid as a quality measurement: Groq's free-tier **tokens-per-day cap** (200,000 per rolling day) was exhausted, giving 54 HTTP 429s. Kept as `groq-openai-gpt-oss-120b.rate-limited.json`: every affected case degraded safely, with 0 false READY and 0 unsafe actions. |
| Third live run | Stopped after 12 calls, all rate-limited (cap confirmed from Groq's error body). No result file. |
| **Outage mode** (dead local endpoint, 42 cases) | `groq-outage-simulation.hardening.json`: 22 PASS, 20 SAFE_ESCALATION, 0 INCORRECT, 0 UNSAFE, 0 false READY. 17 messages, 0 with IDs or jargon. Equivalence 4/4. The escalations are prose cases that correctly go MANUAL without extraction. |

Hardening-run per-case outcomes: C01–C05 PASS; C06 INCORRECT; C07 SAFE_ESCALATION; C08–C39 PASS.

Baseline artifacts from `0209fe9` (`groq-openai-gpt-oss-120b.json`, `groq-outage-simulation.json`) are kept unchanged for comparison.

## Browser review

Four cases were created through the real UI on the dev app, then viewed at 1280 px and 390 px:
- a bundled clarification;
- a conflict;
- a review request;
- an equivalent-terms READY case.

New actions show no UUIDs or field names, layouts have no horizontal overflow, and there are no page errors. Actions created before this change keep their original wording, including old "Manual review needed" drafts, and their card headings fall back to requirement IDs; audit history is not rewritten. Message quality also depends on policy labels: the seeded label "Consistent payment terms" yields "the consistent payment terms".

## Regression

- Backend SQLite: 128 of 128.
- Backend native PostgreSQL 17.11: 128 of 128.
- Frontend: typecheck, lint, 4 of 4 tests and build pass.
- Playwright: 4 of 4.
- Restart drill: PASS.
- Two-worker native-PG concurrency: PASS.
- Groq provider mocked tests: 11 of 11.
- Prompt injection: C10a–d pass in the live run; C38 (a document asking for internal IDs) passes live and in outage mode.

## Performance

- No coverage check calls the model: detection is regex- and `Decimal`-based.
- The drafting call is unchanged in number, but its output is now often discarded by the validator.
- The database transaction held during model calls is unchanged and still documented. The number and size of in-transaction calls are similar to the baseline.

## Known problems

- **C06:** the model missed a hidden approval in 3 of the last 4 runs. A plausible cause is that the extraction context gives only the case key and title, while the approval names the PO. A candidate fix is to include the case's accepted identifiers in the extraction context; it is untested.
- **Model wording polish** is not yet shown to add value, and the widened validator has not been verified live.
- **Stale approvals (C07)** are still proposed by the model and caught by reviewer review.
- **Free-form identifier contradictions** stated only in prose depend on the model.
- **Free-tier quota:** 200,000 tokens per day blocks repeated full evaluations.
- **Case-detail API:** reads the case and its jobs in separate statements, so pollers can briefly see a mixed view. This is cosmetic; persisted state is correct.
- **Existing approvals:** approvals on internal actions created before this change will be invalidated once, because fingerprints now exclude wording. This is conservative.
