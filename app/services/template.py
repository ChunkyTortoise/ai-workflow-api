"""Shared template resolution for workflow nodes."""
from __future__ import annotations

import re
from typing import Any


def resolve_template(template: str, context: dict[str, Any]) -> str:
    """Resolve {dotted.path} placeholders in a template string.

    Supports arbitrary nesting depth: {trigger.body.url}, {step1.parsed.score}, etc.
    """

    def _resolve(match: re.Match) -> str:
        path = match.group(1)
        parts = path.split(".")
        current: Any = context
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return match.group(0)  # Can't resolve, leave placeholder
        if current is None:
            return match.group(0)
        return str(current)

    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}", _resolve, template)
