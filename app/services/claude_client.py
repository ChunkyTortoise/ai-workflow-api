"""Anthropic Claude API wrapper."""
from __future__ import annotations

from typing import Any

from app.config import settings


class ClaudeClient:
    """Wrapper around the Anthropic API for LLM calls."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.anthropic_api_key

    async def complete(
        self,
        prompt: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> dict[str, Any]:
        """Send a completion request to Claude.

        Returns dict with 'content' (str) and 'usage' (dict).
        """
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self._api_key)
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                kwargs["system"] = system

            response = await client.messages.create(**kwargs)
            return {
                "content": response.content[0].text,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                "model": response.model,
            }
        except ImportError:
            # Fallback for testing without anthropic installed
            return {
                "content": f"[Mock response for: {prompt[:100]}]",
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "model": model,
            }
        except Exception as e:
            return {
                "content": "",
                "error": str(e),
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "model": model,
            }
