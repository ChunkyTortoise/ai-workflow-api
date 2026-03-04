"""Application configuration via environment variables."""
from __future__ import annotations

import json
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./workflow.db"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    anthropic_api_key: str = ""

    # API
    cors_origins: List[str] = ["http://localhost:3000"]
    log_level: str = "INFO"

    # Worker
    worker_max_jobs: int = 10
    job_timeout_seconds: int = 300

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return json.loads(v)
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
