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
