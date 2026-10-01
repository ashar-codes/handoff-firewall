import os
import tempfile
from pathlib import Path

import pytest

os.environ["APP_ENV"] = "test"
os.environ["MODEL_PROVIDER"] = "test"
_test_workspace = tempfile.TemporaryDirectory(prefix="handoff-tests-")
_test_database = str(Path(_test_workspace.name) / "test.db")
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "sqlite:///" + _test_database)
os.environ["STORAGE_PATH"] = str(Path(_test_workspace.name) / "files")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Tenant, User  # noqa: E402
from app.security import hasher  # noqa: E402

PASSWORD = "Testing-password-42"


@pytest.fixture(autouse=True)
def database():
    assert engine.url.database in {_test_database, "handoff_test"}, (
        "Tests require a disposable database"
    )
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        t = Tenant(name="Test workspace")
        second = Tenant(name="Other workspace")
        db.add_all([t, second])
        db.flush()
        for role in ["Administrator", "Operator", "Reviewer", "Viewer", "Policy Manager"]:
            db.add(
                User(
                    tenant_id=t.id,
                    name=role,
                    email=role.lower().replace(" ", "") + "@test.invalid",
                    role=role,
                    password_hash=hasher.hash(PASSWORD),
                )
            )
        db.add(
            User(
                tenant_id=second.id,
                name="Other admin",
                email="other@test.invalid",
                role="Administrator",
                password_hash=hasher.hash(PASSWORD),
            )
        )
        db.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        c.headers["origin"] = "http://localhost:5173"
        response = c.post(
            "/api/auth/login", json={"email": "administrator@test.invalid", "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        c.headers["X-CSRF-Token"] = c.cookies["hf_csrf"]
        yield c


def login_as(client, role):
    email = role.lower().replace(" ", "") + "@test.invalid"
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies["hf_csrf"]
    return response.json()


def make_case(client, rules=None, context=None, business_key="ORDER-1"):
    t = client.post(
        "/api/templates",
        json={
            "name": "Order ready",
            "source": "Sales",
            "destination": "Finance",
            "rules": rules
            or [{"id": "terms", "label": "Payment terms", "fields": ["payment_terms"]}],
        },
    )
    assert t.status_code == 201, t.text
    c = client.post(
        "/api/cases",
        json={
            "title": "Customer order",
            "business_key": business_key,
            "template_id": t.json()["id"],
            "goal": "Ready for Finance",
            "context": context or {},
        },
    )
    assert c.status_code == 201, c.text
    return c.json()


def upload(client, case, text, name="evidence.txt", replaces=None):
    result = client.post(
        "/api/cases/" + case["id"] + "/documents",
        files={"file": (name, text.encode(), "text/plain")},
        data={"replaces_id": replaces} if replaces else {},
    )
    assert result.status_code == 201, result.text
    return result.json()


def process(client, case):
    from app.worker import tick

    response = client.post("/api/cases/" + case["id"] + "/run", json={})
    assert response.status_code == 202, response.text
    assert tick()
    return client.get("/api/cases/" + case["id"]).json()
