"""Tests for the node registry."""
from __future__ import annotations

from typing import Any

import pytest

from app.services.node_registry import (
    available_node_types,
    get_node,
    get_registry,
    register_node,
)


class TestNodeRegistry:
    def test_registry_has_all_types(self):
        registry = get_registry()
        expected = {"trigger", "llm", "condition", "http", "notify"}
        assert expected == set(registry.keys())

    def test_get_trigger_node(self):
        node = get_node("trigger")
        assert node.node_type == "trigger"

    def test_get_llm_node(self):
        node = get_node("llm")
        assert node.node_type == "llm"

    def test_get_condition_node(self):
        node = get_node("condition")
        assert node.node_type == "condition"

    def test_get_http_node(self):
        node = get_node("http")
        assert node.node_type == "http"

    def test_get_notify_node(self):
        node = get_node("notify")
        assert node.node_type == "notify"

    def test_get_unknown_node_raises(self):
        with pytest.raises(KeyError, match="Unknown node type"):
            get_node("nonexistent")

    def test_available_node_types(self):
        types = available_node_types()
        assert "trigger" in types
        assert "llm" in types
        assert "condition" in types
        assert "http" in types
        assert "notify" in types

    def test_register_custom_node(self):
        class CustomNode:
            node_type = "custom_test"

            async def execute(self, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
                return {"custom": True}

        register_node(CustomNode())
        node = get_node("custom_test")
        assert node.node_type == "custom_test"

    def test_register_overwrites_existing(self):
        class OverrideNotify:
            node_type = "notify"

            async def execute(self, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
                return {"overridden": True}

        original = get_node("notify")
        register_node(OverrideNotify())
        new = get_node("notify")
        assert new is not original

        # Restore original
        from app.services.nodes.notify import NotifyNode
        register_node(NotifyNode())

    def test_registry_is_singleton(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
