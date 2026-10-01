"""Model outage must not strand approvals, block wording, or duplicate outreach."""

from conftest import make_case, upload

from app.agents import run_case
from app.db import SessionLocal
from app.models import Action, Approval, Case, now
from app.providers import ModelFailure
from app.schemas import Draft

REVIEWED = [{"id": "terms", "label": "Terms", "fields": ["payment_terms"], "review": True}]
TWO_GAPS = [
    {"id": "terms", "label": "Payment terms", "fields": ["payment_terms"]},
    {"id": "tax", "label": "Tax registration", "fields": ["tax_id"]},
]
INTERNAL = ("fingerprint", "requirement_id", "AWAITING_REVIEW", "MISSING", "payment_terms")


class Broken:
    def structured(self, *args):
        raise ModelFailure("Local model unavailable")


class Polisher:
    """A working model that returns a fixed rewrite of the request."""

    def __init__(self, message):
        self.message = message

    def structured(self, task, data, schema):
        return schema(message=self.message.format(**data)) if schema is Draft else schema()


def run(client, case, model):
    me = client.get("/api/auth/me").json()
    run_case(case["id"], me["tenant_id"], me["id"], model)
    return client.get("/api/cases/" + case["id"]).json()


def rerun(client, case, model):
    assert client.post("/api/cases/" + case["id"] + "/run", json={}).status_code == 202
    return run(client, case, model)


def fail_case(case):
    with SessionLocal() as db:  # simulate an earlier failed step so /run performs a retry
        db.get(Case, case["id"]).error = "Model provider unavailable"
        db.commit()


def executed(out, action_id):
    return [
        e
        for e in out["events"]
        if e["kind"] == "action_executed" and e["data"]["action_id"] == action_id
    ]


def approve(client, action):
    r = client.post(
        "/api/actions/" + action["id"] + "/decision",
        json={"fingerprint": action["fingerprint"], "decision": "APPROVED", "comment": "Checked"},
    )
    assert r.status_code == 200, r.text


def proposed_review(client, key="ORDER-1"):
    case = make_case(client, REVIEWED, business_key=key)
    upload(client, case, "payment_terms: 30 days")
    out = run(client, case, Broken())
    # Wording failure is visible but never blocks the workflow or the professional request.
    assert out["state"] == "WAITING" and out["error"] is None
    assert any(e["kind"] == "model_failure" for e in out["events"])
    [action] = out["actions"]
    assert action["status"] == "PROPOSED"
    assert action["payload"]["message"] == (
        f"Please review the terms (“30 days” in evidence.txt) for {key} "
        "and accept it if it is valid."
    )
    return case, action


def test_approved_action_executes_once_while_model_stays_down(client):
    case, action = proposed_review(client)
    approve(client, action)
    out = run(client, case, Broken())  # the resume queued by the approval
    assert out["state"] == "READY"
    assert [a["status"] for a in out["actions"]] == ["COMPLETED"]
    assert len(executed(out, action["id"])) == 1
    out = rerun(client, case, Broken())
    assert len(executed(out, action["id"])) == 1 and len(out["actions"]) == 1


def test_explicit_rerun_keeps_approval_valid_during_outage(client):
    case, action = proposed_review(client)
    approve(client, action)
    out = rerun(client, case, Broken())
    assert out["state"] == "READY"
    assert [(a["id"], a["status"]) for a in out["actions"]] == [(action["id"], "COMPLETED")]
    assert len(executed(out, action["id"])) == 1


def test_expired_approval_cannot_execute_during_outage(client):
    case, action = proposed_review(client)
    approve(client, action)
    with SessionLocal() as db:
        db.query(Approval).filter_by(action_id=action["id"]).one().expires_at = now() - 1
        db.commit()
    out = run(client, case, Broken())
    assert out["state"] != "READY"
    assert out["actions"][0]["status"] == "PROPOSED" and not executed(out, action["id"])
    assert not any(f["accepted"] for f in out["facts"])


def test_wording_is_cosmetic_but_business_payload_and_sources_are_bound(client):
    case, action = proposed_review(client)
    approve(client, action)
    with SessionLocal() as db:  # rewording alone keeps the approved business action valid
        stored = db.get(Action, action["id"])
        stored.payload = {**stored.payload, "message": "Please review the terms for ORDER-1."}
        db.commit()
    assert run(client, case, Broken())["state"] == "READY"

    case, action = proposed_review(client, "ORDER-2")
    approve(client, action)
    with SessionLocal() as db:  # changing what is asked is a different action
        stored = db.get(Action, action["id"])
        stored.payload = {**stored.payload, "candidate_facts": []}
        db.commit()
    out = run(client, case, Broken())
    assert out["state"] != "READY" and not executed(out, action["id"])
    assert out["actions"][0]["status"] == "INVALIDATED"

    case, action = proposed_review(client, "ORDER-3")
    approve(client, action)
    upload(client, case, "payment_terms: 45 days", "newer.txt")
    out = run(client, case, Broken())
    assert out["state"] != "READY" and not executed(out, action["id"])
    assert next(a for a in out["actions"] if a["id"] == action["id"])["status"] == "INVALIDATED"


def test_request_is_sent_with_standard_wording_and_never_duplicated(client):
    case = make_case(client, TWO_GAPS)
    out = run(client, case, Broken())
    [action] = out["actions"]
    assert action["status"] == "WAITING" and out["state"] == "WAITING"
    message = action["payload"]["message"]
    assert message == (
        "Could you please provide the following for ORDER-1: "
        "the payment terms and the tax registration?"
    )
    assert not any(token in message for token in INTERNAL)
    for _ in range(3):
        out = rerun(client, case, Broken())
        assert [(a["id"], a["status"]) for a in out["actions"]] == [(action["id"], "WAITING")]
        assert len(executed(out, action["id"])) == 1


def test_retry_after_failure_keeps_the_sent_request(client):
    case = make_case(client, TWO_GAPS)
    [action] = run(client, case, Broken())["actions"]
    for _ in range(2):
        fail_case(case)
        out = rerun(client, case, Broken())
        assert [(a["id"], a["status"]) for a in out["actions"]] == [(action["id"], "WAITING")]
        assert len(executed(out, action["id"])) == 1
    retry = next(e for e in out["events"] if e["kind"] == "retry")
    assert retry["data"]["retained_actions"] == [action["id"]]
    assert any("reused outstanding" in e["summary"] for e in out["events"])


def test_real_source_change_can_justify_a_new_narrower_request(client):
    case = make_case(client, TWO_GAPS)
    [action] = run(client, case, Broken())["actions"]
    upload(client, case, "payment_terms: 30 days")  # authoritative data changed
    out = run(client, case, Broken())
    old = next(a for a in out["actions"] if a["id"] == action["id"])
    new = [a for a in out["actions"] if a["id"] != action["id"]]
    assert old["status"] == "INVALIDATED"
    assert [(a["kind"], a["payload"]["requirements"]) for a in new] == [
        ("internal_clarification", ["tax"])
    ]


def test_model_wording_is_validated_and_refreshed_in_place(client):
    case, action = proposed_review(client)
    # Leaking an internal ID or adding another question is rejected; standard wording stays.
    for bad in [
        "Please review fact 1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed terms for {reference}.",
        "Please review the terms for {reference} and also send the tax registration.",
        "Please review the terms for {reference}; it has already been approved.",
    ]:
        fail_case(case)
        out = rerun(client, case, Polisher(bad))
        assert out["actions"][0]["payload"]["message"] == action["payload"]["message"]
    assert sum(e["kind"] == "wording_rejected" for e in out["events"]) == 3
    # A valid rewrite of the unsent proposal changes wording only: same row, same fingerprint.
    fail_case(case)
    good = Polisher("Could you review the terms for {reference} and accept them if correct?")
    out = rerun(client, case, good)
    [refreshed] = out["actions"]
    assert refreshed["id"] == action["id"] and refreshed["fingerprint"] == action["fingerprint"]
    assert refreshed["payload"]["message"].startswith("Could you review the terms for ORDER-1")
    approve(client, refreshed)  # the approval binds the business action, not the words
