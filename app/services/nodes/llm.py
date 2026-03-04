"""Claude LLM call node."""
from __future__ import annotations

import json
from typing import Any

from app.services.claude_client import ClaudeClient
from app.services.template import resolve_template as _resolve_template


class LLMNode:
    """Executes a Claude LLM call with template-resolved prompts."""

    node_type = "llm"

    def __init__(self, claude_client: ClaudeClient | None = None) -> None:
        self._client = claude_client or ClaudeClient()

    async def execute(self, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Execute an LLM call.

        Config keys:
            model: Claude model ID (default: claude-sonnet-4-6)
            prompt: prompt template with {step_id.key} placeholders
            system: optional system prompt
            max_tokens: optional max tokens (default: 1024)

        Returns dict with 'content', 'usage', 'model'.
        """
        prompt = _resolve_template(config.get("prompt", ""), context)
        system = config.get("system")
        if system:
            system = _resolve_template(system, context)

        model = config.get("model", "claude-sonnet-4-6")
        max_tokens = config.get("max_tokens", 1024)

        result = await self._client.complete(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            system=system,
        )

        # Try to parse JSON from response for structured data
        content = result.get("content", "")
        try:
            parsed = json.loads(content)
            result["parsed"] = parsed
        except (json.JSONDecodeError, TypeError):
            result["parsed"] = None

        return result
