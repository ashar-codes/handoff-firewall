"""Deployment configuration, first-admin bootstrap and single-origin frontend serving."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, validate

PRODUCTION = {
    "app_env": "production",
    "cookie_secure": True,
    "frontend_origin": "https://handoff.onrender.com/",
    "database_url": "postgresql://postgres.ref:pw@aws-0-x.pooler.supabase.com:5432/postgres",
    "model_provider": "groq",
    "groq_api_key": "gsk_fixture",
    "storage_provider": "supabase",
    "supabase_url": "https://ref.supabase.co/",
    "supabase_service_role_key": "sb_secret_fixture",
}


def test_valid_production_configuration_is_normalised():
    s = validate(Settings(_env_file=None, **PRODUCTION))
    assert s.database_url.startswith("postgresql+psycopg://postgres.ref:")
    assert s.frontend_origin == "https://handoff.onrender.com"
    assert s.supabase_url == "https://ref.supabase.co"


@pytest.mark.parametrize(
    "override",
    [
        {"cookie_secure": False},
        {"frontend_origin": "http://handoff.onrender.com"},
        {"frontend_origin": ""},
        {"database_url": "sqlite:///handoff.db"},
        {"model_provider": "test"},
        {"groq_api_key": None},
        {"supabase_service_role_key": None},
        {"supabase_url": "http://ref.supabase.co"},
    ],
)
def test_unsafe_production_configuration_is_refused(override):
    with pytest.raises(ValueError):
        validate(Settings(_env_file=None, **{**PRODUCTION, **override}))


def test_bucket_name_is_constrained():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, supabase_storage_bucket="../public")


def test_environment_bootstrap_is_once_only_and_rejects_samples(client, monkeypatch):
    from app import bootstrap
    from app.db import Base, SessionLocal, engine
    from app.models import User

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(sys, "argv", ["bootstrap", "--from-env"])
    bootstrap.main()  # nothing configured: skipped, no user
    with SessionLocal() as db:
        assert not db.query(User).count()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@example.test")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "Long-enough-password-1")
    with pytest.raises(SystemExit):
        bootstrap.main()  # sample domain refused
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "Owner@Company.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "short")
    with pytest.raises(SystemExit):
        bootstrap.main()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "Long-enough-password-1")
    bootstrap.main()
    bootstrap.main()  # idempotent on every restart
    with SessionLocal() as db:
        [admin] = db.query(User).all()
        assert admin.email == "owner@company.com" and admin.role == "Administrator"
        assert "Long-enough" not in admin.password_hash


SERVE = """
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
c = TestClient(app)
assert settings().app_env == "production"
r = c.get("/cases/123/history")  # client-side route refresh
assert r.status_code == 200 and "app-root" in r.text and r.headers["cache-control"] == "no-store"
assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
a = c.get("/assets/app.js")
assert a.status_code == 200 and "immutable" in a.headers["cache-control"]
assert c.get("/api/does-not-exist").status_code == 404
assert c.get("/api/does-not-exist").headers["content-type"].startswith("application/json")
assert c.get("/docs").text.count("app-root") == 1  # docs disabled; SPA shell instead
assert c.get("/openapi.json").headers["content-type"].startswith("text/html")
assert c.get("/../../etc/passwd").status_code in {200, 404}
cors = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"][0]
assert cors.kwargs["allow_origins"] == ["https://handoff.onrender.com"]
print("served")
"""


def test_production_app_serves_built_frontend_on_one_origin(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<div id="app-root"></div>')
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    env = {
        **os.environ,
        "APP_ENV": "production",
        "COOKIE_SECURE": "true",
        "FRONTEND_ORIGIN": "https://handoff.onrender.com",
        "FRONTEND_DIST": str(tmp_path),
        "DATABASE_URL": "postgresql://user:pw@127.0.0.1:9/handoff",  # never connected here
        "MODEL_PROVIDER": "groq",
        "GROQ_API_KEY": "gsk_fixture",
        "STORAGE_PROVIDER": "local",
    }
    result = subprocess.run(
        [sys.executable, "-c", SERVE],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0 and "served" in result.stdout, result.stderr[-2000:]


def test_missing_frontend_build_fails_clearly(tmp_path):
    env = {**os.environ, "APP_ENV": "test", "FRONTEND_DIST": str(tmp_path / "missing")}
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0 and "does not contain a built index.html" in result.stderr
