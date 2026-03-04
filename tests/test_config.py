"""Tests for application configuration."""
from __future__ import annotations

import pytest

from app.config import Settings


class TestConfig:
    def test_default_database_url(self):
        s = Settings(anthropic_api_key="test")
        assert "sqlite" in s.database_url

    def test_default_redis_url(self):
        s = Settings(anthropic_api_key="test")
        assert s.redis_url == "redis://localhost:6379/0"

    def test_default_log_level(self):
        s = Settings(anthropic_api_key="test")
        assert s.log_level == "INFO"

    def test_default_worker_max_jobs(self):
        s = Settings(anthropic_api_key="test")
        assert s.worker_max_jobs == 10

    def test_default_job_timeout(self):
        s = Settings(anthropic_api_key="test")
        assert s.job_timeout_seconds == 300

    def test_parse_cors_origins_string(self):
        s = Settings(anthropic_api_key="test", cors_origins='["http://localhost:3000"]')
        assert s.cors_origins == ["http://localhost:3000"]

    def test_parse_cors_origins_list(self):
        s = Settings(anthropic_api_key="test", cors_origins=["http://a.com", "http://b.com"])
        assert len(s.cors_origins) == 2

    def test_default_cors_origins(self):
        s = Settings(anthropic_api_key="test")
        assert "http://localhost:3000" in s.cors_origins

    def test_anthropic_api_key_default_empty(self):
        s = Settings()
        assert s.anthropic_api_key == ""
