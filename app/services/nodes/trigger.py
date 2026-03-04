"""HTTP webhook trigger node."""
from __future__ import annotations

from typing import Any


class TriggerNode:
    """Processes the initial webhook trigger data."""

    node_type = "trigger"

    async def execute(self, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Pass through trigger data into the workflow context.

        Config keys:
            type: "webhook"
            path: trigger path (e.g. "/triggers/lead_qualification")

        Context keys used:
            trigger.body: the raw request body
            trigger.headers: request headers
        """
        trigger_data = context.get("trigger", {})
        return {
            "body": trigger_data.get("body", {}),
            "headers": trigger_data.get("headers", {}),
            "path": config.get("path", ""),
            "type": config.get("type", "webhook"),
        }
