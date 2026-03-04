"""Tests for the workflow engine."""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.services.workflow_engine import StepResult, WorkflowDefinition, WorkflowEngine


# === WorkflowDefinition Tests ===


class TestWorkflowDefinition:
    def test_parse_valid_yaml(self):
        yaml_content = """
name: test
description: A test
trigger:
  type: webhook
  path: /triggers/test
steps:
  - id: s1
    type: trigger
"""
        defn = WorkflowDefinition(yaml_content)
        assert defn.name == "test"
        assert defn.description == "A test"
        assert defn.trigger_path == "/triggers/test"
        assert len(defn.steps) == 1

    def test_parse_multiple_steps(self):
        yaml_content = """
name: multi
trigger:
  type: webhook
  path: /triggers/multi
steps:
  - id: s1
    type: trigger
  - id: s2
    type: llm
    prompt: "hello"
  - id: s3
    type: notify
    channel: log
"""
        defn = WorkflowDefinition(yaml_content)
        assert len(defn.steps) == 3
        assert defn.step_ids == ["s1", "s2", "s3"]

    def test_get_step_by_id(self):
        yaml_content = """
name: test
trigger:
  type: webhook
  path: /triggers/test
steps:
  - id: alpha
    type: trigger
  - id: beta
    type: llm
    prompt: "test"
"""
        defn = WorkflowDefinition(yaml_content)
        step = defn.get_step("beta")
        assert step is not None
        assert step["type"] == "llm"

    def test_get_step_not_found(self):
        yaml_content = """
name: test
trigger:
  type: webhook
  path: /triggers/test
steps:
  - id: s1
    type: trigger
"""
        defn = WorkflowDefinition(yaml_content)
        assert defn.get_step("nonexistent") is None

    def test_validate_valid(self):
        yaml_content = """
name: test
trigger:
  type: webhook
  path: /triggers/test
steps:
  - id: s1
    type: trigger
"""
        defn = WorkflowDefinition(yaml_content)
        errors = defn.validate()
        assert errors == []

    def test_validate_missing_name(self):
        yaml_content = """
trigger:
  type: webhook
steps:
  - id: s1
    type: trigger
"""
        defn = WorkflowDefinition(yaml_content)
        errors = defn.validate()
        assert any("name" in e.lower() for e in errors)

    def test_validate_missing_trigger(self):
        yaml_content = """
name: test
steps:
  - id: s1
    type: trigger
"""
        defn = WorkflowDefinition(yaml_content)
        errors = defn.validate()
        assert any("trigger" in e.lower() for e in errors)

    def test_validate_no_steps(self):
        yaml_content = """
name: test
trigger:
  type: webhook
steps: []
"""
        defn = WorkflowDefinition(yaml_content)
        errors = defn.validate()
        assert any("step" in e.lower() for e in errors)

    def test_validate_missing_step_id(self):
        yaml_content = """
name: test
trigger:
  type: webhook
steps:
  - type: trigger
"""
        defn = WorkflowDefinition(yaml_content)
        errors = defn.validate()
        assert any("id" in e.lower() for e in errors)

    def test_validate_missing_step_type(self):
        yaml_content = """
name: test
trigger:
  type: webhook
steps:
  - id: s1
"""
        defn = WorkflowDefinition(yaml_content)
        errors = defn.validate()
        assert any("type" in e.lower() for e in errors)

    def test_validate_duplicate_step_ids(self):
        yaml_content = """
name: test
trigger:
  type: webhook
steps:
  - id: s1
    type: trigger
  - id: s1
    type: llm
"""
        defn = WorkflowDefinition(yaml_content)
        errors = defn.validate()
        assert any("duplicate" in e.lower() for e in errors)

    def test_validate_condition_bad_reference(self):
        yaml_content = """
name: test
trigger:
  type: webhook
steps:
  - id: s1
    type: condition
    condition: "true"
    on_true: nonexistent
    on_false: s1
"""
        defn = WorkflowDefinition(yaml_content)
        errors = defn.validate()
        assert any("nonexistent" in e for e in errors)

    def test_default_trigger_path(self):
        yaml_content = """
name: my_workflow
trigger:
  type: webhook
steps:
  - id: s1
    type: trigger
"""
        defn = WorkflowDefinition(yaml_content)
        assert defn.trigger_path == "/triggers/my_workflow"

    def test_description_default_empty(self):
        yaml_content = """
name: test
trigger:
  type: webhook
steps:
  - id: s1
    type: trigger
"""
        defn = WorkflowDefinition(yaml_content)
        assert defn.description == ""


# === WorkflowEngine Tests ===


class TestWorkflowEngine:
    @pytest.mark.asyncio
    async def test_set_trigger_data(self):
        engine = WorkflowEngine()
        engine.set_trigger_data({"body": {"name": "test"}})
        assert engine.context["trigger"]["body"]["name"] == "test"

    @pytest.mark.asyncio
    async def test_execute_trigger_step(self):
        engine = WorkflowEngine()
        engine.set_trigger_data({"body": {"key": "value"}, "headers": {}})
        result = await engine.execute_step({
            "id": "t1",
            "type": "trigger",
            "path": "/triggers/test",
        })
        assert result.status == "completed"
        assert result.output["body"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_execute_notify_step(self):
        engine = WorkflowEngine()
        engine.set_trigger_data({"body": {}})
        result = await engine.execute_step({
            "id": "n1",
            "type": "notify",
            "channel": "log",
            "message": "hello",
        })
        assert result.status == "completed"
        assert result.output["sent"] is True

    @pytest.mark.asyncio
    async def test_execute_unknown_node_fails(self):
        engine = WorkflowEngine()
        result = await engine.execute_step({
            "id": "x1",
            "type": "nonexistent_type",
        })
        assert result.status == "failed"
        assert "Unknown node type" in result.error

    @pytest.mark.asyncio
    async def test_step_output_stored_in_context(self):
        engine = WorkflowEngine()
        engine.set_trigger_data({"body": {}, "headers": {}})
        await engine.execute_step({
            "id": "t1",
            "type": "trigger",
            "path": "/test",
        })
        assert "t1" in engine.context

    @pytest.mark.asyncio
    async def test_execute_simple_workflow(self):
        yaml_content = """
name: simple
trigger:
  type: webhook
  path: /triggers/simple
steps:
  - id: t1
    type: trigger
    path: /triggers/simple
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
    async def test_workflow_stops_on_failure(self):
        yaml_content = """
name: fail_test
trigger:
  type: webhook
  path: /triggers/fail
steps:
  - id: bad
    type: nonexistent
  - id: after
    type: notify
    channel: log
    message: "should be skipped"
"""
        defn = WorkflowDefinition(yaml_content)
        engine = WorkflowEngine()
        results = await engine.execute_workflow(defn, {"body": {}})
        assert results[0].status == "failed"
        assert results[1].status == "skipped"

    @pytest.mark.asyncio
    async def test_on_step_complete_callback(self):
        yaml_content = """
name: callback_test
trigger:
  type: webhook
  path: /triggers/cb
steps:
  - id: s1
    type: trigger
    path: /test
"""
        defn = WorkflowDefinition(yaml_content)
        engine = WorkflowEngine()
        callbacks = []

        async def on_complete(step_id, completed, total, result):
            callbacks.append((step_id, completed, total, result.status))

        await engine.execute_workflow(defn, {"body": {}}, on_complete)
        assert len(callbacks) == 1
        assert callbacks[0][0] == "s1"

    @pytest.mark.asyncio
    async def test_results_property(self):
        engine = WorkflowEngine()
        assert engine.results == []
        engine.set_trigger_data({"body": {}})
        await engine.execute_step({"id": "t", "type": "trigger", "path": "/t"})
        assert len(engine.results) == 1


# === StepResult Tests ===


class TestStepResult:
    def test_step_result_defaults(self):
        r = StepResult(step_id="s1", node_type="llm", output={"data": 1})
        assert r.status == "completed"
        assert r.error is None

    def test_step_result_with_error(self):
        r = StepResult(step_id="s1", node_type="llm", output={}, status="failed", error="boom")
        assert r.status == "failed"
        assert r.error == "boom"

    def test_step_result_output(self):
        output = {"content": "hello", "usage": {"tokens": 100}}
        r = StepResult(step_id="s1", node_type="llm", output=output)
        assert r.output["content"] == "hello"
