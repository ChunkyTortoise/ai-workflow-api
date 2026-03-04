"""ARQ worker for async workflow execution."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from arq import cron
from arq.connections import RedisSettings

from app.config import settings
from app.events import publish_event
from app.models import WorkflowRun, WorkflowStep, async_session
from app.services.workflow_engine import WorkflowDefinition, WorkflowEngine

logger = logging.getLogger(__name__)


async def execute_workflow_job(
    ctx: dict[str, Any],
    run_id: str,
    workflow_yaml: str,
    trigger_data: dict[str, Any],
) -> dict[str, Any]:
    """ARQ job: execute a workflow asynchronously.

    Args:
        ctx: ARQ context with Redis connection.
        run_id: WorkflowRun ID.
        workflow_yaml: Raw YAML content.
        trigger_data: Trigger/webhook data.

    Returns:
        Dict with run status and step count.
    """
    redis: aioredis.Redis = ctx["redis"]
    definition = WorkflowDefinition(workflow_yaml)
    engine = WorkflowEngine()

    async with async_session() as db:
        # Update run to running
        from sqlalchemy import select

        result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
        run = result.scalar_one_or_none()
        if not run:
            logger.error("Run %s not found", run_id)
            return {"error": "Run not found"}

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()

        await publish_event(redis, run_id, {
            "type": "run_started",
            "status": "running",
            "total_steps": len(definition.steps),
        })

        async def on_step_complete(
            step_id: str, completed: int, total: int, step_result: Any
        ) -> None:
            step_record = WorkflowStep(
                run_id=run_id,
                step_id=step_id,
                node_type=step_result.node_type,
                status=step_result.status,
                output_data=step_result.output,
                error_message=step_result.error,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            db.add(step_record)
            run.steps_completed = completed
            await db.commit()

            await publish_event(redis, run_id, {
                "type": "step_completed",
                "step_id": step_id,
                "node_type": step_result.node_type,
                "status": step_result.status,
                "steps_completed": completed,
                "total_steps": total,
                "progress": int((completed / total) * 100) if total > 0 else 0,
            })

        results = await engine.execute_workflow(
            definition, trigger_data, on_step_complete
        )

        failed = any(r.status == "failed" for r in results)
        run.status = "failed" if failed else "completed"
        run.completed_at = datetime.now(timezone.utc)
        if failed:
            failed_steps = [r for r in results if r.status == "failed"]
            run.error_message = (
                f"Step '{failed_steps[0].step_id}' failed: {failed_steps[0].error}"
            )
        await db.commit()

        await publish_event(redis, run_id, {
            "type": "run_completed" if not failed else "run_failed",
            "status": run.status,
            "steps_completed": run.steps_completed,
            "total_steps": run.total_steps,
            "error": run.error_message,
        })

        return {
            "run_id": run_id,
            "status": run.status,
            "steps_completed": run.steps_completed,
        }


async def startup(ctx: dict[str, Any]) -> None:
    """ARQ worker startup."""
    ctx["redis"] = aioredis.from_url(settings.redis_url)
    logger.info("Worker started")


async def shutdown(ctx: dict[str, Any]) -> None:
    """ARQ worker shutdown."""
    redis = ctx.get("redis")
    if redis:
        await redis.close()
    logger.info("Worker shut down")


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [execute_workflow_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.worker_max_jobs
    job_timeout = settings.job_timeout_seconds
