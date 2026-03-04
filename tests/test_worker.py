"""Tests for the ARQ worker."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow_engine import WorkflowDefinition, WorkflowEngine


class TestWorkerConcepts:
    """Test the patterns used by the worker without requiring Redis."""

    @pytest.mark.asyncio
    async def test_workflow_execution_returns_results(self):
        yaml_content = """
name: worker_test
trigger:
  type: webhook
  path: /triggers/worker_test
steps:
  - id: t1
    type: trigger
    path: /triggers/worker_test
  - id: n1
    type: notify
    channel: log
    message: "done"
"""
        defn = WorkflowDefinition(yaml_content)
        engine = WorkflowEngine()
        results = await engine.execute_workflow(defn, {"body": {}, "headers": {}})
        assert len(results) == 2
        assert all(r.status == "completed" for r in results)

    @pytest.mark.asyncio
    async def test_callback_receives_step_info(self):
        yaml_content = """
name: cb_test
trigger:
  type: webhook
  path: /triggers/cb
steps:
  - id: s1
    type: trigger
    path: /test
  - id: s2
    type: notify
    channel: log
    message: "done"
"""
        defn = WorkflowDefinition(yaml_content)
        engine = WorkflowEngine()
        callbacks = []

        async def cb(step_id, completed, total, result):
            callbacks.append({
                "step_id": step_id,
                "completed": completed,
                "total": total,
                "status": result.status,
            })

        await engine.execute_workflow(defn, {"body": {}}, cb)
        assert len(callbacks) == 2
        assert callbacks[0]["step_id"] == "s1"
        assert callbacks[1]["step_id"] == "s2"
        assert callbacks[1]["completed"] == 2

    @pytest.mark.asyncio
    async def test_failed_step_triggers_callback(self):
        yaml_content = """
name: fail_test
trigger:
  type: webhook
  path: /triggers/fail
steps:
  - id: bad
    type: nonexistent
"""
        defn = WorkflowDefinition(yaml_content)
        engine = WorkflowEngine()
        callbacks = []

        async def cb(step_id, completed, total, result):
            callbacks.append(result.status)

        await engine.execute_workflow(defn, {"body": {}}, cb)
        assert "failed" in callbacks


class TestEventPublishing:
    """Test event publishing helpers."""

    @pytest.mark.asyncio
    async def test_publish_event_structure(self):
        """Verify event dict structure is correct."""
        from app.events import _channel_name

        channel = _channel_name("run-123")
        assert channel == "run:run-123:events"

    @pytest.mark.asyncio
    async def test_publish_event_with_mock_redis(self):
        """Verify publish_event calls Redis correctly."""
        from app.events import publish_event

        mock_redis = AsyncMock()
        await publish_event(mock_redis, "run-123", {
            "type": "step_completed",
            "step_id": "s1",
            "status": "completed",
        })
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert "run:run-123:events" in call_args[0]

    @pytest.mark.asyncio
    async def test_publish_event_adds_timestamp(self):
        """Verify timestamp is auto-added."""
        import json

        from app.events import publish_event

        mock_redis = AsyncMock()
        await publish_event(mock_redis, "run-1", {"type": "test"})
        call_args = mock_redis.publish.call_args
        data = json.loads(call_args[0][1])
        assert "timestamp" in data
        assert "run_id" in data

    @pytest.mark.asyncio
    async def test_channel_name_format(self):
        from app.events import _channel_name

        assert _channel_name("abc") == "run:abc:events"
        assert _channel_name("123-456") == "run:123-456:events"


class TestWorkerSettings:
    def test_worker_settings_has_functions(self):
        from worker.worker import WorkerSettings

        assert len(WorkerSettings.functions) == 1

    def test_worker_settings_max_jobs(self):
        from worker.worker import WorkerSettings

        assert WorkerSettings.max_jobs > 0

    def test_worker_settings_timeout(self):
        from worker.worker import WorkerSettings

        assert WorkerSettings.job_timeout > 0
