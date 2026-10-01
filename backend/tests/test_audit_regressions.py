"""Independent audit regressions: assert authority and outcomes, not prompt wording."""

import json

import pytest
from conftest import login_as, make_case, process, upload

from app.agents import run_case
from app.schemas import Extracted


def test_spaced_alias_cannot_leave_cached_ready(client):
    case = make_case(
        client,
        [
            {"id": "terms", "label": "Terms", "fields": ["payment_terms"]},
            {"id": "tax", "label": "Tax", "fields": ["tax_id"], "mandatory": False},
        ],
    )
    upload(client, case, "payment_terms: 30 days")
    assert process(client, case)["state"] == "READY"
    upload(client, case, "tax_id: T1\npayment terms: 45 days", "new.txt")
    out = process(client, case)
    assert out["state"] != "READY"
    assert out["statuses"]["terms"]["state"] == "CONFLICTING"


def test_operator_cannot_exempt_conditional_rule_at_intake(client):
    case = make_case(
        client,
        [
            {
                "id": "approval",
                "label": "Approval",
                "fields": ["approval"],
                "condition": {"field": "discount", "equals": "yes"},
            }
        ],
    )
    login_as(client, "Operator")
    body = {
        "title": "Bypass",
        "business_key": "BYPASS",
        "template_id": case["template_id"],
        "goal": "Finance",
        "context": {"discount": "no"},
    }
    assert client.post("/api/cases", json=body).status_code == 403
    body["context"] = {}
    assert client.post("/api/cases", json=body).status_code == 201


@pytest.mark.parametrize(
    "name,content",
    [
        ("note.json", json.dumps({"notes": "customer note\npayment_terms: 30 days"})),
        ("note.csv", 'notes\n"customer note\npayment_terms: 30 days"\n'),
    ],
)
def test_structured_cell_cannot_inject_authoritative_field(client, name, content):
    case = make_case(client)
    upload(client, case, content, name)
    out = process(client, case)
    assert not any(f["accepted"] for f in out["facts"])
    assert out["state"] != "READY"


def test_candidate_contradiction_blocks_existing_accepted_value(client):
    class CandidateModel:
        def structured(self, task, data, schema):
            if schema is Extracted:
                return schema(
                    candidates=[
                        {
                            "requirement_id": "terms",
                            "field": "payment_terms",
                            "value": "45 days",
                            "quote": "The contract requires payment within 45 days.",
                        }
                    ]
                )
            return schema(message="Review the conflicting candidate")

    case = make_case(client)
    upload(client, case, "payment_terms: 30 days")
    upload(client, case, "The contract requires payment within 45 days.", "contract.txt")
    me = client.get("/api/auth/me").json()
    run_case(case["id"], me["tenant_id"], me["id"], CandidateModel())
    out = client.get("/api/cases/" + case["id"]).json()
    assert out["state"] != "READY"
    assert out["statuses"]["terms"]["state"] == "AWAITING_REVIEW"


def test_mixed_document_searches_narrative_even_with_exact_match(client):
    calls = []

    class MixedModel:
        def structured(self, task, data, schema):
            if schema is Extracted:
                calls.append(data)
                return schema(
                    candidates=[
                        {
                            "requirement_id": "terms",
                            "field": "payment_terms",
                            "value": "45 days",
                            "quote": "The contract requires payment within 45 days.",
                        }
                    ]
                )
            return schema(message="Review terms")

    case = make_case(
        client,
        [
            {"id": "terms", "label": "Terms", "fields": ["payment_terms"]},
            {"id": "tax", "label": "Tax", "fields": ["tax_id"]},
        ],
    )
    upload(client, case, "tax_id: T1\nThe contract requires payment within 45 days.")
    me = client.get("/api/auth/me").json()
    run_case(case["id"], me["tenant_id"], me["id"], MixedModel())
    assert calls
    out = client.get("/api/cases/" + case["id"]).json()
    assert any(f["method"] == "model_candidate" for f in out["facts"])


def test_failed_specialist_rolls_back_partial_effects(client, monkeypatch):
    from app import agents
    from app.models import Fact

    def broken(db, case, model):
        db.add(
            Fact(
                tenant_id=case.tenant_id,
                case_id=case.id,
                requirement_id="terms",
                field="payment_terms",
                value="fabricated partial",
                source_hash="x",
                source_version=1,
                location="test",
                quote="test",
                method="test",
                accepted=True,
            )
        )
        db.flush()
        raise RuntimeError("Fault after database flush")

    case = make_case(client)
    monkeypatch.setattr(agents, "evidence_agent", broken)
    out = process(client, case)
    assert out["state"] == "BLOCKED"
    assert not out["facts"]
    assert any(e["kind"] == "agent_failed" for e in out["events"])


def test_repeated_invalidation_preserves_all_dirty_requirements(client):
    case = make_case(
        client,
        [
            {"id": "terms", "label": "Terms", "fields": ["payment_terms"]},
            {"id": "tax", "label": "Tax", "fields": ["tax_id"]},
        ],
    )
    old = upload(client, case, "payment_terms: 30 days\ntax_id: T1")
    assert process(client, case)["state"] == "READY"
    upload(client, case, "tax_id: T1", "replacement.txt", old["id"])
    upload(client, case, "tax_id: T1\n", "unrelated.txt")
    out = process(client, case)
    assert out["state"] != "READY"
    assert out["statuses"]["terms"]["state"] == "MISSING"


def test_partial_reply_reuses_unanswered_request(client):
    case = make_case(client, [{"id": k, "label": k, "fields": [k]} for k in ["po", "tax"]])
    action = process(client, case)["actions"][0]
    assert (
        client.post(
            f"/api/actions/{action['id']}/reply",
            json={"values": {"po": "P1"}, "comment": "Partial answer"},
        ).status_code
        == 200
    )
    from app.worker import tick

    assert tick()
    out = client.get("/api/cases/" + case["id"]).json()
    waiting = [a for a in out["actions"] if a["status"] == "WAITING"]
    assert len(waiting) == 1 and waiting[0]["id"] == action["id"]
    assert waiting[0]["result"]["answered_requirements"] == ["po"]
    assert (
        client.post(
            f"/api/actions/{action['id']}/reply",
            json={"values": {"po": "again"}, "comment": "Retry"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/actions/{action['id']}/reply",
            json={"values": {"tax": "T1"}, "comment": "Remaining answer"},
        ).status_code
        == 200
    )


def test_rejected_fact_is_not_reintroduced_by_batch_review(client):
    case = make_case(
        client, [{"id": "terms", "label": "Terms", "fields": ["payment_terms"], "review": True}]
    )
    upload(client, case, "payment_terms: 30 days")
    out = process(client, case)
    fact = out["facts"][0]
    assert (
        client.post(
            f"/api/facts/{fact['id']}/review", json={"accepted": False, "comment": "Wrong source"}
        ).status_code
        == 200
    )
    out = process(client, case)
    assert out["statuses"]["terms"]["state"] == "MISSING"
    assert not any(
        fact["id"] in a["payload"]["candidate_facts"]
        for a in out["actions"]
        if a["status"] in {"PROPOSED", "WAITING"}
    )
    event = next(e for e in out["events"] if e["kind"] == "fact_reviewed")
    assert event["data"]["fact_id"] == fact["id"]
    assert event["data"]["after"]["review_decision"] == "REJECTED"


def test_conflict_resolution_retains_actor_and_history(client):
    case = make_case(client)
    upload(client, case, "payment_terms: 30 days", "a.txt")
    upload(client, case, "payment_terms: 45 days", "b.txt")
    out = process(client, case)
    first, second = out["facts"]
    assert (
        client.post(
            f"/api/facts/{first['id']}/review",
            json={
                "accepted": True,
                "comment": "Signed contract governs",
                "supersedes": [second["id"]],
            },
        ).status_code
        == 200
    )
    out = process(client, case)
    assert out["state"] == "READY"
    history = out["conflict_history"][0]
    assert history["resolution_state"] == "RESOLVED"
    assert history["resolution"]["actor_id"] == client.get("/api/auth/me").json()["id"]
    assert "Signed contract" in history["resolution"]["reason"]


def test_old_or_expired_worker_claim_cannot_write(client):
    from app.db import SessionLocal
    from app.models import Job, now

    case = make_case(client)
    job = client.post("/api/cases/" + case["id"] + "/run", json={}).json()
    me = client.get("/api/auth/me").json()
    with SessionLocal() as db:
        j = db.get(Job, job["id"])
        j.status = "RUNNING"
        j.attempts = 2
        j.lease_until = now() + 60
        db.commit()
    for claim in [(job["id"], 1), ("missing", 2)]:
        assert run_case(case["id"], me["tenant_id"], me["id"], claim=claim) == "LEASE_LOST"
    with SessionLocal() as db:
        j = db.get(Job, job["id"])
        j.lease_until = now() - 1
        db.commit()
    assert run_case(case["id"], me["tenant_id"], me["id"], claim=(job["id"], 2)) == "LEASE_LOST"
    assert client.get("/api/cases/" + case["id"]).json()["state"] == "NEW"
    from app.worker import tick

    assert tick()
    out = client.get("/api/cases/" + case["id"]).json()
    assert out["state"] == "WAITING"
    assert out["jobs"][0]["attempts"] == 3
    assert len(out["actions"]) == 1


def test_stale_worker_finalizer_cannot_overwrite_reclaimed_job(client, monkeypatch):
    from app import worker
    from app.db import SessionLocal
    from app.models import Job, now

    case = make_case(client)
    job = client.post("/api/cases/" + case["id"] + "/run", json={}).json()

    def reclaimed(*args, **kwargs):
        with SessionLocal() as db:
            j = db.get(Job, job["id"])
            j.attempts += 1
            j.lease_until = now() + 300
            db.commit()

    monkeypatch.setattr(worker, "run_case", reclaimed)
    assert worker.tick()
    with SessionLocal() as db:
        j = db.get(Job, job["id"])
        assert j.status == "RUNNING" and j.active_key == case["id"] and j.attempts == 2


def test_worker_database_failure_retries_without_exiting(monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app import worker

    calls = []

    def tick():
        calls.append(1)
        if len(calls) == 1:
            raise OperationalError("operation", {}, Exception("private connection string"))
        raise KeyboardInterrupt

    sleeps = []
    monkeypatch.setattr(worker, "tick", tick)
    monkeypatch.setattr(worker.time, "sleep", sleeps.append)
    with pytest.raises(KeyboardInterrupt):
        worker.main()
    assert len(calls) == 2 and sleeps == [0.5]


def test_cross_tenant_action_user_sse_and_policy_ids(client):
    case = make_case(client)
    doc = upload(client, case, "payment_terms: 30 days")
    users = client.get("/api/users").json()
    process(client, case)
    # Make an unresolved action in another case before switching workspaces.
    waiting = make_case(client, business_key="SECOND")
    action = process(client, waiting)["actions"][0]
    login_as(client, "Other")
    for url in ["/api/cases/" + case["id"] + "/events", "/api/cases/" + case["id"] + "/export"]:
        assert client.get(url).status_code == 404
    assert (
        client.post(
            "/api/documents/" + doc["id"] + "/exclude", json={"reason": "Cross tenant"}
        ).status_code
        == 404
    )
    assert client.post("/api/actions/" + action["id"] + "/execute", json={}).status_code == 404
    assert (
        client.post(
            "/api/actions/" + action["id"] + "/reply",
            json={"values": {"terms": "X"}, "comment": "Cross tenant"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/actions/" + action["id"] + "/decision",
            json={
                "fingerprint": action["fingerprint"],
                "decision": "APPROVED",
                "comment": "Cross tenant",
            },
        ).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/users/" + users[0]["id"], json={"role": "Administrator", "active": True}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/cases",
            json={
                "title": "X",
                "business_key": "X",
                "template_id": case["template_id"],
                "goal": "X",
            },
        ).status_code
        == 404
    )


def test_rejection_escalates_and_explicit_retry_replans(client):
    case = make_case(
        client, [{"id": "terms", "label": "Terms", "fields": ["payment_terms"], "review": True}]
    )
    upload(client, case, "payment_terms: 30 days")
    action = process(client, case)["actions"][0]
    assert (
        client.post(
            "/api/actions/" + action["id"] + "/decision",
            json={
                "fingerprint": action["fingerprint"],
                "decision": "REJECTED",
                "comment": "Check contract again",
            },
        ).status_code
        == 200
    )
    assert client.get("/api/cases/" + case["id"]).json()["state"] == "ESCALATED"
    out = process(client, case)
    assert out["state"] == "WAITING"
    assert len([a for a in out["actions"] if a["status"] == "PROPOSED"]) == 1


def test_ready_source_integrity_can_be_rechecked(client):
    from app.db import SessionLocal
    from app.models import Document
    from app.storage import file_path

    case = make_case(client)
    doc = upload(client, case, "payment_terms: 30 days")
    assert process(client, case)["state"] == "READY"
    with SessionLocal() as db:
        file_path(db.get(Document, doc["id"]).path).write_text("changed original")
    assert process(client, case)["state"] != "READY"


def test_received_body_limit_does_not_trust_content_length(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings(), "upload_limit", 1)
    # A streaming request has no trustworthy Content-Length.
    response = client.post(
        "/api/auth/login",
        content=iter([b"x" * 600000, b"x" * 600000]),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert client.get("/api/health").status_code == 200


def test_unexpected_error_does_not_log_sensitive_exception(client, monkeypatch, caplog):
    from app import main

    secret = "sensitive-source-and-password-fixture"

    def broken(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(main, "case_summary", broken)
    client.post(
        "/api/templates",
        json={
            "name": "T",
            "source": "A",
            "destination": "B",
            "rules": [{"id": "a", "label": "A", "fields": ["a"]}],
        },
    )
    template = client.get("/api/templates").json()[0]
    response = client.post(
        "/api/cases",
        json={"title": "X", "business_key": "X", "template_id": template["id"], "goal": "X"},
    )
    assert response.status_code == 500
    assert secret not in response.text and secret not in caplog.text


@pytest.mark.parametrize(
    "name,content",
    [
        ("duplicate.json", '{"payment_terms":"30 days","payment_terms":"45 days"}'),
        ("duplicate.csv", "payment_terms,payment_terms\n30 days,45 days\n"),
    ],
)
def test_duplicate_structured_fields_do_not_silently_discard_conflicts(client, name, content):
    case = make_case(client)
    doc = upload(client, case, content, name)
    assert doc["parse_error"]
    assert process(client, case)["state"] == "BLOCKED"


def test_oversized_narrative_is_not_silently_truncated(client):
    case = make_case(client)
    upload(client, case, "payment_terms: 30 days")
    upload(client, case, "Uninterpreted source note. " * 1000, "large.txt")
    out = process(client, case)
    assert out["state"] == "BLOCKED" and "review window" in out["error"]


def test_exact_fact_budget_blocks_instead_of_accepting_partial_source(client):
    case = make_case(client)
    upload(client, case, "\n".join("payment_terms: " + str(i) for i in range(250)))
    out = process(client, case)
    assert out["state"] == "BLOCKED" and "fact budget" in out["error"]
    assert not out["facts"]
