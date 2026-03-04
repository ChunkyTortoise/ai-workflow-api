"""Registry of available workflow node types."""
from __future__ import annotations

from typing import Any, Protocol


class NodeExecutor(Protocol):
    """Protocol for workflow nodes."""

    node_type: str

    async def execute(self, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...


# Lazy imports to avoid circular dependencies
_registry: dict[str, NodeExecutor] | None = None


def _build_registry() -> dict[str, NodeExecutor]:
    from app.services.nodes.condition import ConditionNode
    from app.services.nodes.http import HTTPNode
    from app.services.nodes.llm import LLMNode
    from app.services.nodes.notify import NotifyNode
    from app.services.nodes.trigger import TriggerNode

    return {
        "trigger": TriggerNode(),
        "llm": LLMNode(),
        "condition": ConditionNode(),
        "http": HTTPNode(),
        "notify": NotifyNode(),
    }


def get_registry() -> dict[str, NodeExecutor]:
    """Get the singleton node registry."""
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return _registry


def get_node(node_type: str) -> NodeExecutor:
    """Get a node executor by type. Raises KeyError if not found."""
    registry = get_registry()
    if node_type not in registry:
        raise KeyError(f"Unknown node type: {node_type}. Available: {list(registry.keys())}")
    return registry[node_type]


def register_node(node: NodeExecutor) -> None:
    """Register a custom node type."""
    registry = get_registry()
    registry[node.node_type] = node


def available_node_types() -> list[str]:
    """Return list of available node type names."""
    return list(get_registry().keys())
