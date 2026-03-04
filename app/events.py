"""Redis pub/sub event system for SSE streaming."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


def _channel_name(run_id: str) -> str:
    return f"run:{run_id}:events"


async def publish_event(
    redis: aioredis.Redis,
    run_id: str,
    event: dict[str, Any],
) -> None:
    """Publish a workflow run event to Redis pub/sub."""
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    event.setdefault("run_id", run_id)
    channel = _channel_name(run_id)
    await redis.publish(channel, json.dumps(event))


async def subscribe_events(
    redis: aioredis.Redis,
    run_id: str,
) -> AsyncIterator[dict[str, Any]]:
    """Subscribe to workflow run events via Redis pub/sub."""
    channel = _channel_name(run_id)
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                yield data
                # Stop if terminal status
                status = data.get("status", "")
                if status in ("completed", "failed"):
                    break
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
