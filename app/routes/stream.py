"""SSE streaming endpoint for workflow run progress."""
from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.events import _log_key

router = APIRouter(tags=["streaming"])

# Stop tailing a run that has produced no new event for this long (a guard
# against a stream left open on a crashed or abandoned run).
IDLE_TIMEOUT_SECONDS = 20.0
_POLL_INTERVAL = 0.1
_TERMINAL_TYPES = ("run_completed", "run_failed")


def get_redis() -> aioredis.Redis:
    """Get Redis client. Override in tests."""
    from app.config import settings

    return aioredis.from_url(settings.redis_url)


@router.get("/runs/{run_id}/stream")
async def stream_run_events(
    run_id: str,
    redis: aioredis.Redis = Depends(get_redis),
):
    """SSE stream of workflow run progress events.

    Replays the run's event log from the start, then tails it for new events,
    so a client that connects late (or after a fast run completes) still sees
    the full sequence: run_started, step_completed (with progress %), and
    run_completed / run_failed.
    """
    log_key = _log_key(run_id)

    async def event_generator():
        seen = 0
        idle = 0.0
        while idle < IDLE_TIMEOUT_SECONDS:
            events = await redis.lrange(log_key, seen, -1)
            if events:
                idle = 0.0
                for raw in events:
                    data = json.loads(raw)
                    yield {"data": json.dumps(data), "retry": 3000}
                    seen += 1
                    if data.get("type") in _TERMINAL_TYPES:
                        return
            else:
                idle += _POLL_INTERVAL
                await asyncio.sleep(_POLL_INTERVAL)

    return EventSourceResponse(event_generator())
