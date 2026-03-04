"""SSE streaming endpoint for workflow run progress."""
from __future__ import annotations

import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.events import subscribe_events

router = APIRouter(tags=["streaming"])


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

    Events include:
    - step_started: {step_id, node_type, step_index, total_steps}
    - step_completed: {step_id, node_type, status, output}
    - run_completed: {status, steps_completed, total_steps}
    - run_failed: {error, step_id}
    """

    async def event_generator():
        async for event in subscribe_events(redis, run_id):
            yield {
                "data": json.dumps(event),
                "retry": 3000,
            }

    return EventSourceResponse(event_generator())
