"""Conditional branch node."""
from __future__ import annotations

from typing import Any


def _resolve_value(ref: str, context: dict[str, Any]) -> Any:
    """Resolve a {step_id.key} reference to its value from context."""
    # Strip braces
    cleaned = ref.strip("{}")
    parts = cleaned.split(".")

    current: Any = context
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    """Evaluate a simple condition expression.

    Supports: >=, <=, >, <, ==, !=
    Example: "{qualify.score} >= 7"
    """
    operators = [">=", "<=", "!=", "==", ">", "<"]
    for op in operators:
        if op in condition:
            parts = condition.split(op, 1)
            if len(parts) == 2:
                left_raw = parts[0].strip()
                right_raw = parts[1].strip()

                # Resolve references
                left = _resolve_value(left_raw, context) if "{" in left_raw else left_raw
                right = _resolve_value(right_raw, context) if "{" in right_raw else right_raw

                # Convert to numbers if possible
                try:
                    left = float(left) if left is not None else 0
                except (ValueError, TypeError):
                    left = str(left) if left is not None else ""
                try:
                    right = float(right) if right is not None else 0
                except (ValueError, TypeError):
                    right = str(right) if right is not None else ""

                if op == ">=":
                    return left >= right
                elif op == "<=":
                    return left <= right
                elif op == ">":
                    return left > right
                elif op == "<":
                    return left < right
                elif op == "==":
                    return left == right
                elif op == "!=":
                    return left != right

    # Default: truthy check on resolved value
    val = _resolve_value(condition, context)
    return bool(val)


class ConditionNode:
    """Evaluates a condition and returns the branch to take."""

    node_type = "condition"

    async def execute(self, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Evaluate the condition.

        Config keys:
            condition: expression like "{qualify.score} >= 7"
            on_true: step ID to jump to if true
            on_false: step ID to jump to if false

        Returns dict with 'result' (bool), 'next_step' (str), 'condition' (str).
        """
        condition_expr = config.get("condition", "true")
        result = _evaluate_condition(condition_expr, context)

        next_step = config.get("on_true") if result else config.get("on_false")

        return {
            "result": result,
            "next_step": next_step,
            "condition": condition_expr,
            "evaluated_to": result,
        }
