"""Tests for individual node types."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.nodes.condition import ConditionNode, _evaluate_condition, _resolve_value
from app.services.nodes.http import HTTPNode
from app.services.nodes.llm import LLMNode
from app.services.template import resolve_template as _resolve_template
from app.services.nodes.notify import NotifyNode
from app.services.nodes.trigger import TriggerNode


# === TriggerNode Tests ===


class TestTriggerNode:
    @pytest.mark.asyncio
    async def test_basic_trigger(self):
        node = TriggerNode()
        result = await node.execute(
            {"type": "webhook", "path": "/triggers/test"},
            {"trigger": {"body": {"name": "Alice"}, "headers": {"x-test": "1"}}},
        )
        assert result["body"] == {"name": "Alice"}
        assert result["headers"] == {"x-test": "1"}
        assert result["path"] == "/triggers/test"

    @pytest.mark.asyncio
    async def test_trigger_empty_context(self):
        node = TriggerNode()
        result = await node.execute({"type": "webhook"}, {})
        assert result["body"] == {}
        assert result["headers"] == {}

    @pytest.mark.asyncio
    async def test_trigger_preserves_nested_data(self):
        node = TriggerNode()
        body = {"user": {"name": "Bob", "scores": [1, 2, 3]}}
        result = await node.execute(
            {"type": "webhook", "path": "/t"},
            {"trigger": {"body": body, "headers": {}}},
        )
        assert result["body"]["user"]["scores"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_trigger_node_type(self):
        assert TriggerNode.node_type == "trigger"


# === LLMNode Tests ===


class TestLLMNode:
    @pytest.mark.asyncio
    async def test_resolve_template_simple(self):
        result = _resolve_template("Hello {name}", {"name": "World"})
        assert result == "Hello World"

    @pytest.mark.asyncio
    async def test_resolve_template_nested(self):
        result = _resolve_template(
            "Score: {step1.score}",
            {"step1": {"score": 8, "name": "test"}},
        )
        assert result == "Score: 8"

    @pytest.mark.asyncio
    async def test_resolve_template_no_match(self):
        result = _resolve_template("Hello {unknown}", {"name": "World"})
        assert result == "Hello {unknown}"

    @pytest.mark.asyncio
    async def test_resolve_template_multiple(self):
        result = _resolve_template(
            "{a.x} and {b.y}",
            {"a": {"x": "foo"}, "b": {"y": "bar"}},
        )
        assert result == "foo and bar"

    @pytest.mark.asyncio
    async def test_llm_node_calls_client(self):
        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value={
            "content": "Hello!",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "model": "claude-sonnet-4-6",
        })
        node = LLMNode(claude_client=mock_client)
        result = await node.execute(
            {"prompt": "Say hello", "model": "claude-sonnet-4-6"},
            {},
        )
        assert result["content"] == "Hello!"
        mock_client.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_node_resolves_prompt(self):
        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value={
            "content": "response",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "model": "claude-sonnet-4-6",
        })
        node = LLMNode(claude_client=mock_client)
        await node.execute(
            {"prompt": "Analyze: {trigger.body}"},
            {"trigger": {"body": "test data"}},
        )
        call_args = mock_client.complete.call_args
        assert "test data" in call_args.kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_llm_node_parses_json_response(self):
        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value={
            "content": '{"score": 8, "summary": "Good lead"}',
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "model": "claude-sonnet-4-6",
        })
        node = LLMNode(claude_client=mock_client)
        result = await node.execute({"prompt": "test"}, {})
        assert result["parsed"]["score"] == 8

    @pytest.mark.asyncio
    async def test_llm_node_non_json_response(self):
        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value={
            "content": "Just plain text",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "model": "claude-sonnet-4-6",
        })
        node = LLMNode(claude_client=mock_client)
        result = await node.execute({"prompt": "test"}, {})
        assert result["parsed"] is None

    @pytest.mark.asyncio
    async def test_llm_node_with_system_prompt(self):
        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value={
            "content": "ok",
            "usage": {"input_tokens": 5, "output_tokens": 2},
            "model": "claude-sonnet-4-6",
        })
        node = LLMNode(claude_client=mock_client)
        await node.execute(
            {"prompt": "test", "system": "You are helpful"},
            {},
        )
        call_args = mock_client.complete.call_args
        assert call_args.kwargs["system"] == "You are helpful"

    @pytest.mark.asyncio
    async def test_llm_node_type(self):
        assert LLMNode.node_type == "llm"

    @pytest.mark.asyncio
    async def test_llm_node_default_model(self):
        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value={
            "content": "ok",
            "usage": {"input_tokens": 5, "output_tokens": 2},
            "model": "claude-sonnet-4-6",
        })
        node = LLMNode(claude_client=mock_client)
        await node.execute({"prompt": "test"}, {})
        call_args = mock_client.complete.call_args
        assert call_args.kwargs["model"] == "claude-sonnet-4-6"


# === ConditionNode Tests ===


class TestConditionNode:
    def test_resolve_value_simple(self):
        ctx = {"step1": {"score": 8}}
        assert _resolve_value("{step1.score}", ctx) == 8

    def test_resolve_value_missing(self):
        ctx = {"step1": {"score": 8}}
        assert _resolve_value("{step2.score}", ctx) is None

    def test_resolve_value_nested(self):
        ctx = {"a": {"b": {"c": 42}}}
        assert _resolve_value("{a.b}", ctx) == {"c": 42}

    def test_evaluate_gte_true(self):
        ctx = {"qualify": {"score": 8}}
        assert _evaluate_condition("{qualify.score} >= 7", ctx) is True

    def test_evaluate_gte_false(self):
        ctx = {"qualify": {"score": 5}}
        assert _evaluate_condition("{qualify.score} >= 7", ctx) is False

    def test_evaluate_gte_equal(self):
        ctx = {"qualify": {"score": 7}}
        assert _evaluate_condition("{qualify.score} >= 7", ctx) is True

    def test_evaluate_lt(self):
        ctx = {"x": {"val": 3}}
        assert _evaluate_condition("{x.val} < 5", ctx) is True

    def test_evaluate_gt(self):
        ctx = {"x": {"val": 10}}
        assert _evaluate_condition("{x.val} > 5", ctx) is True

    def test_evaluate_eq(self):
        ctx = {"x": {"val": 5}}
        assert _evaluate_condition("{x.val} == 5", ctx) is True

    def test_evaluate_neq(self):
        ctx = {"x": {"val": 3}}
        assert _evaluate_condition("{x.val} != 5", ctx) is True

    def test_evaluate_lte(self):
        ctx = {"x": {"val": 5}}
        assert _evaluate_condition("{x.val} <= 5", ctx) is True

    def test_evaluate_missing_value_defaults_zero(self):
        ctx = {}
        assert _evaluate_condition("{missing.val} >= 7", ctx) is False

    @pytest.mark.asyncio
    async def test_condition_node_true_branch(self):
        node = ConditionNode()
        result = await node.execute(
            {"condition": "{s1.score} >= 7", "on_true": "good", "on_false": "bad"},
            {"s1": {"score": 9}},
        )
        assert result["result"] is True
        assert result["next_step"] == "good"

    @pytest.mark.asyncio
    async def test_condition_node_false_branch(self):
        node = ConditionNode()
        result = await node.execute(
            {"condition": "{s1.score} >= 7", "on_true": "good", "on_false": "bad"},
            {"s1": {"score": 3}},
        )
        assert result["result"] is False
        assert result["next_step"] == "bad"

    @pytest.mark.asyncio
    async def test_condition_node_type(self):
        assert ConditionNode.node_type == "condition"


# === HTTPNode Tests ===


class TestHTTPNode:
    @pytest.mark.asyncio
    async def test_http_node_get(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}
        mock_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        node = HTTPNode(client=mock_client)
        result = await node.execute(
            {"url": "https://example.com/api", "method": "GET"},
            {},
        )
        assert result["status_code"] == 200
        assert result["body"]["result"] == "ok"

    @pytest.mark.asyncio
    async def test_http_node_post(self):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "123"}
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)

        node = HTTPNode(client=mock_client)
        result = await node.execute(
            {"url": "https://example.com/api", "method": "POST", "body": {"name": "test"}},
            {},
        )
        assert result["status_code"] == 201

    @pytest.mark.asyncio
    async def test_http_node_resolves_url(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)

        node = HTTPNode(client=mock_client)
        await node.execute(
            {"url": "{trigger.body.url}", "method": "GET"},
            {"trigger": {"body": {"url": "https://resolved.com"}}},
        )
        call_args = mock_client.request.call_args
        assert call_args.kwargs["url"] == "https://resolved.com"

    @pytest.mark.asyncio
    async def test_http_node_error(self):
        import httpx

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        node = HTTPNode(client=mock_client)
        result = await node.execute(
            {"url": "https://down.com", "method": "GET"},
            {},
        )
        assert result["status_code"] == 0
        assert "error" in result

    @pytest.mark.asyncio
    async def test_http_node_text_response(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "plain text response"
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)

        node = HTTPNode(client=mock_client)
        result = await node.execute({"url": "https://example.com", "method": "GET"}, {})
        assert result["body"] == "plain text response"

    @pytest.mark.asyncio
    async def test_http_node_type(self):
        assert HTTPNode.node_type == "http"

    @pytest.mark.asyncio
    async def test_http_node_default_method(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)

        node = HTTPNode(client=mock_client)
        await node.execute({"url": "https://example.com"}, {})
        call_args = mock_client.request.call_args
        assert call_args.kwargs["method"] == "GET"


# === NotifyNode Tests ===


class TestNotifyNode:
    @pytest.mark.asyncio
    async def test_notify_log(self):
        node = NotifyNode()
        result = await node.execute(
            {"channel": "log", "message": "test message"},
            {},
        )
        assert result["sent"] is True
        assert result["channel"] == "log"
        assert result["message"] == "test message"

    @pytest.mark.asyncio
    async def test_notify_slack_stub(self):
        node = NotifyNode()
        result = await node.execute(
            {"channel": "slack", "message": "alert", "recipient": "#general"},
            {},
        )
        assert result["sent"] is True
        assert "stub" in result["note"].lower()

    @pytest.mark.asyncio
    async def test_notify_email_stub(self):
        node = NotifyNode()
        result = await node.execute(
            {
                "channel": "email",
                "message": "Dear user...",
                "recipient": "user@example.com",
                "subject": "Hello",
            },
            {},
        )
        assert result["sent"] is True
        assert result["recipient"] == "user@example.com"
        assert result["subject"] == "Hello"

    @pytest.mark.asyncio
    async def test_notify_unsupported_channel(self):
        node = NotifyNode()
        result = await node.execute(
            {"channel": "pigeon", "message": "coo"},
            {},
        )
        assert result["sent"] is False
        assert "unsupported" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_notify_resolves_template(self):
        node = NotifyNode()
        result = await node.execute(
            {"channel": "log", "message": "Score: {step1.score}"},
            {"step1": {"score": 9}},
        )
        assert result["message"] == "Score: 9"

    @pytest.mark.asyncio
    async def test_notify_ghl_channel(self):
        node = NotifyNode()
        result = await node.execute(
            {"channel": "ghl", "message": "GHL notification"},
            {},
        )
        assert result["sent"] is True
        assert result["channel"] == "ghl"

    @pytest.mark.asyncio
    async def test_notify_webhook_channel(self):
        node = NotifyNode()
        result = await node.execute(
            {"channel": "webhook", "message": "webhook payload"},
            {},
        )
        assert result["sent"] is True

    @pytest.mark.asyncio
    async def test_notify_node_type(self):
        assert NotifyNode.node_type == "notify"

    @pytest.mark.asyncio
    async def test_notify_default_channel(self):
        node = NotifyNode()
        result = await node.execute({"message": "test"}, {})
        assert result["channel"] == "log"

    @pytest.mark.asyncio
    async def test_notify_resolves_recipient(self):
        node = NotifyNode()
        result = await node.execute(
            {"channel": "email", "message": "hi", "recipient": "{trigger.body.email}"},
            {"trigger": {"body": {"email": "a@b.com"}}},
        )
        assert result["recipient"] == "a@b.com"
