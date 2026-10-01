from conftest import make_case, process, upload

from app.db import SessionLocal
from app.models import Document
from app.storage import file_path


def test_changed_original_cannot_clear(client):
    c = make_case(client)
    d = upload(client, c, "payment_terms: 30 days")
    with SessionLocal() as db:
        document = db.get(Document, d["id"])
        file_path(document.path).write_text("payment_terms: 45 days")
    out = process(client, c)
    assert out["state"] != "READY"
    assert any(doc["parse_error"] for doc in out["documents"])


def test_unreadable_source_requires_explicit_human_exclusion(client):
    c = make_case(client)
    upload(client, c, "payment_terms: 30 days", "valid.txt")
    bad = upload(client, c, "not a pdf", "bad.pdf")
    assert process(client, c)["state"] == "BLOCKED"
    assert (
        client.post(
            "/api/documents/" + bad["id"] + "/exclude",
            json={"reason": "Not business evidence; uploaded accidentally"},
        ).status_code
        == 200
    )
    out = process(client, c)
    assert out["state"] == "READY"
    assert any(e["kind"] == "source_excluded" for e in out["events"])


def test_model_failure_with_other_complete_evidence_does_not_fail_open(client):
    from app.agents import run_case
    from app.providers import ModelFailure

    class Broken:
        def structured(self, *args):
            raise ModelFailure("Model unavailable")

    c = make_case(client)
    upload(client, c, "payment_terms: 30 days")
    upload(
        client, c, "This is another relevant customer note that needs interpretation.", "note.txt"
    )
    user = client.get("/api/auth/me").json()
    run_case(c["id"], user["tenant_id"], user["id"], Broken())
    out = client.get("/api/cases/" + c["id"]).json()
    assert out["state"] == "BLOCKED"
    assert out["error"]


def test_search_is_scoped_and_returns_current_source(client):
    c = make_case(client)
    d = upload(client, c, "payment_terms: 30 days")
    response = client.get("/api/cases/" + c["id"] + "/search?q=payment_terms")
    assert response.status_code == 200, response.text
    assert response.json()[0]["id"] == d["id"]
    assert "path" not in response.json()[0]


def test_parser_subprocess_reads_text_on_this_platform(client):
    # macOS rejects RLIMIT_AS; the sandboxed parser must still extract text there.
    c = make_case(client)
    d = upload(client, c, "payment_terms: 30 days")
    assert d["parse_error"] is None
    assert d["text"] == "payment_terms: 30 days"


def test_unchanged_narrative_is_not_re_extracted_after_human_review(client):
    """A reworded re-extraction must not reopen evidence a reviewer already accepted."""
    from app.agents import run_case
    from app.schemas import Extracted

    calls = []

    class Rewording:
        def structured(self, task, data, schema):
            if schema is not Extracted:
                return schema(message="Please review")
            calls.append(data["document"])
            value = ["within 30 days of invoice", "30 days"][min(len(calls) - 1, 1)]
            quote = "The buyer will pay within 30 days of invoice."
            return Extracted(
                candidates=[
                    {
                        "requirement_id": "terms",
                        "field": "payment_terms",
                        "value": value,
                        "quote": quote,
                    }
                ]
            )

    c = make_case(client)
    upload(client, c, "The buyer will pay within 30 days of invoice.", "email.txt")
    me = client.get("/api/auth/me").json()
    run_case(c["id"], me["tenant_id"], me["id"], Rewording())
    [fact] = client.get("/api/cases/" + c["id"]).json()["facts"]
    r = client.post(
        "/api/facts/" + fact["id"] + "/review", json={"accepted": True, "comment": "Checked"}
    )
    assert r.status_code == 200
    assert client.post("/api/cases/" + c["id"] + "/run", json={}).status_code == 202
    run_case(c["id"], me["tenant_id"], me["id"], Rewording())
    out = client.get("/api/cases/" + c["id"]).json()
    assert out["state"] == "READY" and len(out["facts"]) == 1 and len(calls) == 1

    # A new document version is genuinely new evidence and is reviewed by the model again.
    doc = out["documents"][0]
    upload(client, c, "The buyer will pay within 45 days of invoice.", "email.txt", doc["id"])
    run_case(c["id"], me["tenant_id"], me["id"], Rewording())
    assert len(calls) == 2
