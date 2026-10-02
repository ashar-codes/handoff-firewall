from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _psycopg(url):
    """Accept the plain postgresql:// strings Supabase/Render show; SQLAlchemy needs a driver."""
    if url and url.startswith(("postgresql://", "postgres://")):
        return "postgresql+psycopg://" + url.split("://", 1)[1]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://handoff:handoff@127.0.0.1:5432/handoff"
    # Optional separate connection for schema migrations (e.g. a direct/owner connection).
    migration_database_url: str | None = None
    # Small per-process pools: API and worker share one Supabase session-pooler budget.
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=50)
    frontend_origin: str = "http://localhost:5173"
    # Built React app served by FastAPI in single-origin deployments; unset in development.
    frontend_dist: str | None = None
    cookie_secure: bool = False
    storage_provider: Literal["local", "supabase"] = "local"
    storage_path: str = "./data/files"
    supabase_url: str | None = None
    # Backend-only; never logged, returned in errors or sent to the browser.
    supabase_service_role_key: SecretStr | None = None
    supabase_storage_bucket: str = Field(
        default="handoff-evidence", pattern=r"^[a-z0-9][a-z0-9_-]{2,62}$"
    )
    storage_timeout: float = Field(default=20, ge=1, le=60)
    upload_limit: int = Field(default=10 * 1024 * 1024, ge=1, le=25 * 1024 * 1024)
    model_provider: Literal["ollama", "openai-compatible", "groq", "test"] = "ollama"
    model_base_url: str = "http://127.0.0.1:11434"
    model_name: str = "qwen2.5:7b"
    model_timeout: float = Field(default=30, ge=1, le=60)
    # Hosted providers only; never logged or returned in errors.
    groq_api_key: SecretStr | None = None
    model_reasoning_effort: Literal["low", "medium", "high"] = "medium"
    max_steps: int = Field(default=24, ge=1, le=100)
    max_run_seconds: int = Field(default=180, ge=15, le=1800)
    session_hours: int = Field(default=8, ge=1, le=24)

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _driver(cls, value):
        return _psycopg(value)

    @field_validator("frontend_origin", "supabase_url")
    @classmethod
    def _no_trailing_slash(cls, value):
        return value.rstrip("/") if value else value


def validate(s):
    """Refuse unsafe or incomplete configurations before anything starts."""
    if s.app_env == "production":
        if not s.cookie_secure or not s.frontend_origin.startswith("https://"):
            raise ValueError("Production requires secure cookies and an HTTPS origin")
        if s.model_provider == "test":
            raise ValueError("The test model is forbidden in production")
        if not s.database_url.startswith("postgresql"):
            raise ValueError("Production requires PostgreSQL")
    if s.model_provider == "groq" and s.app_env != "test" and not s.groq_api_key:
        raise ValueError("MODEL_PROVIDER=groq requires GROQ_API_KEY")
    if s.storage_provider == "supabase" and not (
        s.supabase_url and s.supabase_url.startswith("https://") and s.supabase_service_role_key
    ):
        raise ValueError(
            "STORAGE_PROVIDER=supabase requires an https SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
        )
    return s


@lru_cache
def settings():
    return validate(Settings())
