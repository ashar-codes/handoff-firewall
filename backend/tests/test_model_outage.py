"""Model outage must not strand human approvals or duplicate outreach."""

from conftest import make_case, upload

from app.agents import run_case
from app.db import SessionLocal
from app.models import Action, Approval, now
from app.providers import ModelFailure, TestProvider

REVIEWED = [{"id": "terms", "label": "Terms", "fields": ["payment_terms"], "review": True}]
TWO_GAPS = [
    {"id": "terms", "label": "Terms", "fields": ["payment_terms"]},
    {"id": "tax", "label": "Tax", "fields": ["tax_id"]},
]


class Broken:
    def structured(self, *args):
        raise ModelFailure("Local model unavailable")


def run(client, case, model):
    me = client.get("/api/auth/me").json()
    run_case(case["id"], me["tenant_id"], me["id"], model)
    return client.get("/api/cases/" + case["id"]).json()


def rerun(client, case, model):
    assert client.post("/api/cases/" + case["id"] + "/run", json={}).status_code == 202
    return run(client, case, model)


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
    assert out["state"] == "BLOCKED" and out["error"] == "Local model unavailable"
    assert any(e["kind"] == "model_failure" for e in out["events"])
    [action] = out["actions"]
    assert action["status"] == "PROPOSED" and action["payload"]["message"].startswith("Manual")
    return case, action


def test_approved_action_executes_once_while_model_stays_down(client):
    case, action = proposed_review(client)
    approve(client, action)
    out = run(client, case, Broken())  # the resume queued by the approval
    assert out["state"] == "READY"
    assert [a["status"] for a in out["actions"]] == ["COMPLETED"]
    assert len(executed(out, action["id"])) == 1
    routed = [e["data"]["target"] for e in out["events"] if e["kind"] == "routing"]
    assert "Action Agent" in routed
    out = rerun(client, case, Broken())
    assert len(executed(out, action["id"])) == 1 and len(out["actions"]) == 1


def test_explicit_rerun_keeps_approval_valid_during_outage(client):
    case, action = proposed_review(client)
    approve(client, action)
    out = rerun(client, case, Broken())
    assert out["state"] == "READY"
    assert [(a["id"], a["status"]) for a in out["actions"]] == [(action["id"], "COMPLETED")]
    assert len(executed(out, action["id"])) == 1
    retry = next(e for e in out["events"] if e["kind"] == "retry")
    assert retry["data"]["retained_actions"] == [action["id"]]


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


def test_changed_fingerprint_or_source_blocks_approved_action(client):
    case, action = proposed_review(client)
    approve(client, action)
    with SessionLocal() as db:
        stored = db.get(Action, action["id"])
        stored.payload = {**stored.payload, "message": "Tampered after approval"}
        db.commit()
    out = run(client, case, Broken())
    assert out["state"] != "READY" and not executed(out, action["id"])
    assert out["actions"][0]["status"] == "INVALIDATED"

    case, action = proposed_review(client, "ORDER-2")
    approve(client, action)
    upload(client, case, "payment_terms: 45 days", "newer.txt")
    out = run(client, case, Broken())
    assert out["state"] != "READY" and not executed(out, action["id"])
    assert next(a for a in out["actions"] if a["id"] == action["id"])["status"] == "INVALIDATED"


def test_sent_request_is_reused_across_repeated_outage_reruns(client):
    case = make_case(client, TWO_GAPS)
    [action] = run(client, case, Broken())["actions"]
    assert action["kind"] == "internal_clarification" and action["status"] == "PROPOSED"
    r = client.post("/api/actions/" + action["id"] + "/execute", json={})
    assert r.status_code == 200 and r.json()["action"]["status"] == "WAITING"
    for _ in range(3):
        out = rerun(client, case, Broken())
        assert [(a["id"], a["status"]) for a in out["actions"]] == [(action["id"], "WAITING")]
        assert len(executed(out, action["id"])) == 1
        assert out["state"] == "WAITING"
    retries = [e for e in out["events"] if e["kind"] == "retry"]
    assert retries[0]["data"]["retained_actions"] == [action["id"]]
    assert any("reused outstanding" in e["summary"] for e in out["events"])


def test_real_source_change_can_justify_a_new_narrower_request(client):
    case = make_case(client, TWO_GAPS)
    [action] = run(client, case, Broken())["actions"]
    client.post("/api/actions/" + action["id"] + "/execute", json={})
    upload(client, case, "payment_terms: 30 days")  # authoritative data changed
    out = run(client, case, Broken())
    old = next(a for a in out["actions"] if a["id"] == action["id"])
    new = [a for a in out["actions"] if a["id"] != action["id"]]
    assert old["status"] == "INVALIDATED"
    assert [(a["kind"], a["payload"]["requirements"]) for a in new] == [
        ("internal_clarification", ["tax"])
    ]


def test_retry_with_restored_model_redrafts_unsent_proposal_in_place(client):
    case = make_case(client, TWO_GAPS)
    [manual] = run(client, case, Broken())["actions"]
    for _ in range(2):  # retrying while still down keeps the same row and the manual hold
        out = rerun(client, case, Broken())
        assert [(a["id"], a["status"]) for a in out["actions"]] == [(manual["id"], "PROPOSED")]
        assert out["state"] == "BLOCKED"
    out = rerun(client, case, TestProvider())
    [action] = out["actions"]
    assert action["id"] == manual["id"] and action["fingerprint"] != manual["fingerprint"]
    assert action["payload"]["message"].startswith("Please clarify")
    assert action["status"] == "WAITING" and out["state"] == "WAITING"
    assert len(executed(out, action["id"])) == 1
