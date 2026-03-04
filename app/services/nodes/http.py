"""HTTP request node for calling external APIs."""
from __future__ import annotations

from typing import Any

import httpx

from app.services.template import resolve_template as _resolve_template


class HTTPNode:
    """Makes HTTP requests to external APIs."""

    node_type = "http"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def execute(self, config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Execute an HTTP request.

        Config keys:
            url: target URL (supports template placeholders)
            method: HTTP method (default: GET)
            headers: optional headers dict
            body: optional request body (supports template placeholders)
            timeout: request timeout in seconds (default: 30)

        Returns dict with 'status_code', 'body', 'headers'.
        """
        url = _resolve_template(config.get("url", ""), context)
        method = config.get("method", "GET").upper()
        headers = config.get("headers", {})
        body = config.get("body")
        timeout = config.get("timeout", 30)

        if isinstance(body, str):
            body = _resolve_template(body, context)

        # Resolve template placeholders in headers
        resolved_headers = {k: _resolve_template(str(v), context) for k, v in headers.items()}

        client = self._client or httpx.AsyncClient()
        should_close = self._client is None

        try:
            response = await client.request(
                method=method,
                url=url,
                headers=resolved_headers,
                content=body if isinstance(body, str) else None,
                json=body if isinstance(body, dict) else None,
                timeout=timeout,
            )
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text

            return {
                "status_code": response.status_code,
                "body": response_body,
                "headers": dict(response.headers),
            }
        except httpx.HTTPError as e:
            return {
                "status_code": 0,
                "body": "",
                "error": str(e),
                "headers": {},
            }
        finally:
            if should_close:
                await client.aclose()
