from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://handoff:handoff@127.0.0.1:5432/handoff"
    frontend_origin: str = "http://localhost:5173"
    cookie_secure: bool = False
    storage_path: str = "./data/files"
    upload_limit: int = Field(default=10 * 1024 * 1024, ge=1, le=25 * 1024 * 1024)
    model_provider: Literal["ollama", "openai-compatible", "test"] = "ollama"
    model_base_url: str = "http://127.0.0.1:11434"
    model_name: str = "qwen2.5:7b"
    model_timeout: float = Field(default=30, ge=1, le=60)
    max_steps: int = Field(default=24, ge=1, le=100)
    max_run_seconds: int = Field(default=180, ge=15, le=1800)
    session_hours: int = Field(default=8, ge=1, le=24)


@lru_cache
def settings():
    s = Settings()
    if s.app_env == "production":
        if not s.cookie_secure or not s.frontend_origin.startswith("https://"):
            raise ValueError("Production requires secure cookies and an HTTPS origin")
        if s.model_provider == "test":
            raise ValueError("The test model is forbidden in production")
        if not s.database_url.startswith("postgresql"):
            raise ValueError("Production requires PostgreSQL")
    return s
