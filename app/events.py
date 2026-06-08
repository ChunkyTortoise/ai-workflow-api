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


def _log_key(run_id: str) -> str:
    return f"run:{run_id}:log"


# Replayed event logs expire an hour after the run so reconnecting clients can
# still fetch recent history without growing Redis unbounded.
LOG_TTL_SECONDS = 3600


async def publish_event(
    redis: aioredis.Redis,
    run_id: str,
    event: dict[str, Any],
) -> None:
    """Publish a run event: live pub/sub plus an append to a replay log.

    The replay log lets a subscriber that connects after a step (or after a
    fast run has already completed) still receive the full event history.
    """
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    event.setdefault("run_id", run_id)
    payload = json.dumps(event)
    await redis.publish(_channel_name(run_id), payload)
    log_key = _log_key(run_id)
    await redis.rpush(log_key, payload)  # type: ignore[misc]
    await redis.expire(log_key, LOG_TTL_SECONDS)


async def subscribe_events(
    redis: aioredis.Redis,
    run_id: str,
) -> AsyncIterator[dict[str, Any]]:
    """Subscribe to workflow run events via Redis pub/sub (live only)."""
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
