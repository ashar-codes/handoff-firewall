from conftest import PASSWORD, login_as, make_case, process, upload
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuthSession, Job, User
from app.providers import LocalProvider, ModelFailure, provider
from app.schemas import Draft
from app.security import verify_password


def test_auth_cookies_csrf_origin_and_logout(client):
    assert client.get("/api/auth/me").status_code == 200
    cookie_response = client.post(
        "/api/auth/login", json={"email": "administrator@test.invalid", "password": PASSWORD}
    )
    cookies = cookie_response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("hf_session="))
    assert (
        "HttpOnly" in session_cookie
        and "SameSite=strict" in session_cookie
        and "Path=/" in session_cookie
    )
    client.headers["X-CSRF-Token"] = client.cookies["hf_csrf"]
    assert client.post("/api/cases", headers={"X-CSRF-Token": "bad"}, json={}).status_code == 403
    assert (
        client.post(
            "/api/auth/logout", headers={"origin": "https://evil.test"}, json={}
        ).status_code
        == 403
    )
    assert client.post("/api/auth/logout", json={}).status_code == 200
    assert client.get("/api/cases").status_code == 401


def test_passwords_hashed_and_session_tokens_not_stored(client):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "administrator@test.invalid"))
        assert user.password_hash.startswith("$argon2id$")
        assert verify_password(user.password_hash, PASSWORD)
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
        assert session.token_hash != client.cookies["hf_session"]


def test_login_throttle_persisted(client):
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/login", json={"email": "absent@test.invalid", "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"email": "absent@test.invalid", "password": "wrong"}
        ).status_code
        == 429
    )


def test_viewer_and_operator_cannot_approve_or_edit_policy(client):
    c = make_case(client)
    process(client, c)
    login_as(client, "Viewer")
    assert client.get("/api/cases").status_code == 200
    assert client.post("/api/cases/" + c["id"] + "/run", json={}).status_code == 403
    assert (
        client.post(
            "/api/templates",
            json={
                "name": "x",
                "source": "a",
                "destination": "b",
                "rules": [{"id": "a", "label": "a", "fields": ["a"]}],
            },
        ).status_code
        == 403
    )
    login_as(client, "Operator")
    assert (
        client.post("/api/facts/bad/review", json={"accepted": True, "comment": "fake"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/users",
            json={
                "email": "x@test.invalid",
                "name": "x",
                "role": "Administrator",
                "password": PASSWORD,
            },
        ).status_code
        == 403
    )


def test_cross_workspace_isolation_all_object_boundaries(client):
    c = make_case(client)
    d = upload(client, c, "payment_terms: 30 days")
    out = process(client, c)
    fact = out["facts"][0]
    login_as(client, "Other")
    for url in [
        "/api/cases/" + c["id"],
        "/api/cases/" + c["id"] + "/export",
        "/api/documents/" + d["id"] + "/download",
        "/api/cases/" + c["id"] + "/search?q=terms",
    ]:
        assert client.get(url).status_code == 404, url
    assert client.post("/api/cases/" + c["id"] + "/run", json={}).status_code == 404
    assert (
        client.post(
            "/api/facts/" + fact["id"] + "/review",
            json={"accepted": True, "comment": "cross-tenant"},
        ).status_code
        == 404
    )
    assert not client.get("/api/cases").json()
    assert not client.get("/api/actions").json()
    assert not client.get("/api/templates").json()


def test_upload_type_size_duplicate_and_path_controls(client, monkeypatch):
    c = make_case(client)
    assert (
        client.post(
            "/api/cases/" + c["id"] + "/documents",
            files={"file": ("payload.pkl", b"pickled", "application/octet-stream")},
        ).status_code
        == 422
    )
    d = upload(client, c, "payment_terms: 30 days", "../../safe.txt")
    assert "/" not in d["name"]
    assert "path" not in d
    assert (
        client.post(
            "/api/cases/" + c["id"] + "/documents",
            files={"file": ("copy.txt", b"payment_terms: 30 days")},
        ).status_code
        == 409
    )
    bad = upload(client, c, "not a PDF", "bad.pdf")
    assert bad["parse_error"]
    binary = client.post(
        "/api/cases/" + c["id"] + "/documents", files={"file": ("binary.txt", b"\x00\x01")}
    )
    assert binary.status_code == 201 and binary.json()["parse_error"]
    from app.config import settings

    monkeypatch.setattr(settings(), "upload_limit", 20)
    assert (
        client.post(
            "/api/cases/" + c["id"] + "/documents", files={"file": ("big.txt", b"x" * 21)}
        ).status_code
        == 413
    )


def test_json_and_csv_documents(client):
    c = make_case(client)
    upload(client, c, '{"payment_terms":"30 days"}', "facts.json")
    assert process(client, c)["state"] == "READY"
    c2 = make_case(client, business_key="ORDER-2")
    upload(client, c2, "payment_terms\n45 days\n", "facts.csv")
    assert process(client, c2)["state"] == "READY"


def test_queued_run_is_deduplicated(client):
    c = make_case(client)
    a = client.post("/api/cases/" + c["id"] + "/run", json={}).json()
    b = client.post("/api/cases/" + c["id"] + "/run", json={}).json()
    assert a["id"] == b["id"]
    with SessionLocal() as db:
        assert len(list(db.scalars(select(Job)))) == 1


def test_local_provider_contract_and_failures(monkeypatch):
    import httpx

    from app.config import settings

    monkeypatch.setattr(settings(), "model_provider", "ollama")
    captured = []

    def post(self, url, **kwargs):
        captured.append((url, kwargs["json"]))
        return httpx.Response(
            200,
            json={"message": {"content": '{"message":"Please supply tax evidence"}'}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    result = LocalProvider().structured("Draft only", {"labels": ["Tax"]}, Draft)
    assert result.message == "Please supply tax evidence"
    assert captured[0][0].endswith("/api/chat")
    assert captured[0][1]["format"]["additionalProperties"] is False

    def broken(self, url, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx.Client, "post", broken)
    import pytest

    with pytest.raises(ModelFailure):
        LocalProvider().structured("Draft", {}, Draft)


def test_test_provider_not_allowed_in_development(monkeypatch):
    import pytest

    from app.config import settings

    monkeypatch.setattr(settings(), "app_env", "development")
    with pytest.raises(ModelFailure):
        provider()
