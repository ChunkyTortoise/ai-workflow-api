"""Shared test fixtures."""
from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, get_db


@pytest_asyncio.fixture
async def db_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a test database session."""
    async_session_factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Yield a test HTTP client with overridden DB dependency."""
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


SAMPLE_WORKFLOW_YAML = """
name: test_workflow
description: A test workflow
trigger:
  type: webhook
  path: /triggers/test_workflow
steps:
  - id: step1
    type: trigger
    path: /triggers/test_workflow
  - id: step2
    type: llm
    model: claude-sonnet-4-6
    prompt: "Say hello to {trigger.body}"
  - id: step3
    type: notify
    channel: log
    message: "Result: {step2.content}"
"""

CONDITION_WORKFLOW_YAML = """
name: condition_test
description: Test conditional branching
trigger:
  type: webhook
  path: /triggers/condition_test
steps:
  - id: analyze
    type: trigger
    path: /triggers/condition_test
  - id: check
    type: condition
    condition: "{analyze.body.score} >= 7"
    on_true: good_path
    on_false: bad_path
  - id: good_path
    type: notify
    channel: log
    message: "Score is good"
  - id: bad_path
    type: notify
    channel: log
    message: "Score is low"
"""

MINIMAL_WORKFLOW_YAML = """
name: minimal
description: Minimal workflow
trigger:
  type: webhook
  path: /triggers/minimal
steps:
  - id: step1
    type: trigger
    path: /triggers/minimal
"""

HTTP_WORKFLOW_YAML = """
name: http_test
description: Test HTTP node
trigger:
  type: webhook
  path: /triggers/http_test
steps:
  - id: fetch
    type: http
    method: GET
    url: "https://httpbin.org/get"
    timeout: 5
"""
