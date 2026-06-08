"""Tests for the async execution path: enqueue endpoint + worker event stream."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

MINIMAL_YAML = """
name: async_minimal
description: Single-step workflow for async tests
trigger:
  type: webhook
  path: /triggers/async_minimal
steps:
  - id: receive
    type: trigger
    path: /triggers/async_minimal
"""


@pytest.mark.asyncio
async def test_execute_async_enqueues_worker_job(client: AsyncClient):
    """POST /execute-async returns 202 + queued and enqueues execute_workflow_job."""
    from app.main import app
    from app.routes.runs import get_arq_pool

    fake_pool = AsyncMock()
    app.dependency_overrides[get_arq_pool] = lambda: fake_pool
    try:
        created = await client.post("/api/v1/workflows", json={"yaml_content": MINIMAL_YAML})
        assert created.status_code == 201
        wf_id = created.json()["id"]

        resp = await client.post(f"/api/v1/runs/{wf_id}/execute-async", json={"data": {"x": 1}})
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert data["id"]

        fake_pool.enqueue_job.assert_awaited_once()
        args = fake_pool.enqueue_job.await_args[0]
        assert args[0] == "execute_workflow_job"
        assert args[1] == data["id"]
        assert args[2] == MINIMAL_YAML
        assert args[3] == {"body": {"x": 1}, "headers": {}}
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)


@pytest.mark.asyncio
async def test_execute_async_unknown_workflow(client: AsyncClient):
    """Unknown workflow id returns 404 and never enqueues."""
    from app.main import app
    from app.routes.runs import get_arq_pool

    fake_pool = AsyncMock()
    app.dependency_overrides[get_arq_pool] = lambda: fake_pool
    try:
        resp = await client.post("/api/v1/runs/does-not-exist/execute-async", json={"data": {}})
        assert resp.status_code == 404
        fake_pool.enqueue_job.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_arq_pool, None)


@pytest.mark.asyncio
async def test_worker_publishes_event_sequence(db_engine, monkeypatch):
    """execute_workflow_job publishes run_started, step_completed, run_completed."""
    import worker.worker as w
    from app.models import WorkflowRun

    test_session = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(w, "async_session", test_session)

    async with test_session() as s:
        run = WorkflowRun(workflow_id="wf-async", status="queued", trigger_data={}, total_steps=1)
        s.add(run)
        await s.commit()
        await s.refresh(run)
        run_id = run.id

    fake_redis = AsyncMock()
    await w.execute_workflow_job(
        {"redis": fake_redis}, run_id, MINIMAL_YAML, {"body": {}, "headers": {}}
    )

    published = [json.loads(call.args[1]) for call in fake_redis.publish.await_args_list]
    types = [e["type"] for e in published]
    assert types[0] == "run_started"
    assert "step_completed" in types
    assert types[-1] == "run_completed"


class _FakeRedis:
    """Minimal async stand-in exposing lrange over a fixed event log."""

    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        if end == -1:
            return self._events[start:]
        return self._events[start : end + 1]


@pytest.mark.asyncio
async def test_stream_replays_full_event_log(client: AsyncClient):
    """The stream replays a completed run's whole log and stops at run_completed."""
    from app.main import app
    from app.routes.stream import get_redis

    log = [
        json.dumps({"type": "run_started", "total_steps": 2}),
        json.dumps({"type": "step_completed", "step_id": "receive",
                    "status": "completed", "progress": 50}),
        json.dumps({"type": "run_completed", "status": "completed",
                    "steps_completed": 2, "total_steps": 2}),
    ]
    app.dependency_overrides[get_redis] = lambda: _FakeRedis(log)
    try:
        resp = await client.get("/api/v1/runs/any-run/stream")
        assert resp.status_code == 200
        body = resp.text
        assert "run_started" in body
        assert "step_completed" in body
        assert "run_completed" in body
    finally:
        app.dependency_overrides.pop(get_redis, None)
