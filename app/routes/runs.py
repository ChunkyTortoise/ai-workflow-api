"""Workflow execution routes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth import require_api_key
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Workflow, WorkflowRun, WorkflowStep, get_db
from app.services.workflow_engine import WorkflowDefinition, WorkflowEngine

router = APIRouter(prefix="/runs", tags=["runs"])


class RunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    steps_completed: int
    total_steps: int
    error_message: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


class RunDetail(RunResponse):
    trigger_data: dict[str, Any]
    steps: list[dict[str, Any]]


class TriggerBody(BaseModel):
    data: dict[str, Any] = {}


@router.post("/{workflow_id}/execute", response_model=RunResponse, status_code=201)
async def execute_workflow(
    workflow_id: str,
    body: TriggerBody,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_api_key),
) -> dict[str, Any]:
    """Execute a workflow and return the run result."""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")

    definition = WorkflowDefinition(workflow.yaml_content)

    # Create run record
    run = WorkflowRun(
        workflow_id=workflow_id,
        status="running",
        trigger_data=body.data,
        total_steps=len(definition.steps),
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Execute workflow synchronously (for simplicity; worker handles async)
    engine = WorkflowEngine()

    async def on_step_complete(step_id: str, completed: int, total: int, step_result: Any) -> None:
        step_record = WorkflowStep(
            run_id=run.id,
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

    trigger_data = {"body": body.data, "headers": {}}
    results = await engine.execute_workflow(definition, trigger_data, on_step_complete)

    # Update run status
    failed = any(r.status == "failed" for r in results)
    run.status = "failed" if failed else "completed"
    run.completed_at = datetime.now(timezone.utc)
    if failed:
        failed_steps = [r for r in results if r.status == "failed"]
        run.error_message = f"Step '{failed_steps[0].step_id}' failed: {failed_steps[0].error}"
    await db.commit()
    await db.refresh(run)

    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "status": run.status,
        "steps_completed": run.steps_completed,
        "total_steps": run.total_steps,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat(),
    }


@router.get("", response_model=list[RunResponse])
async def list_runs(
    workflow_id: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List workflow runs with optional filters."""
    query = select(WorkflowRun).order_by(desc(WorkflowRun.created_at))
    if workflow_id:
        query = query.where(WorkflowRun.workflow_id == workflow_id)
    if status:
        query = query.where(WorkflowRun.status == status)
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    runs = result.scalars().all()

    return [
        {
            "id": r.id,
            "workflow_id": r.workflow_id,
            "status": r.status,
            "steps_completed": r.steps_completed,
            "total_steps": r.total_steps,
            "error_message": r.error_message,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a workflow run with step details."""
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Run not found")

    steps_result = await db.execute(
        select(WorkflowStep).where(WorkflowStep.run_id == run_id)
    )
    steps = steps_result.scalars().all()

    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "status": run.status,
        "steps_completed": run.steps_completed,
        "total_steps": run.total_steps,
        "error_message": run.error_message,
        "trigger_data": run.trigger_data,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat(),
        "steps": [
            {
                "id": s.id,
                "step_id": s.step_id,
                "node_type": s.node_type,
                "status": s.status,
                "output_data": s.output_data,
                "error_message": s.error_message,
            }
            for s in steps
        ],
    }


# Webhook trigger endpoint -- matches workflow trigger paths
@router.post("/trigger/{path:path}")
async def trigger_webhook(
    path: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_api_key),
) -> dict[str, Any]:
    """Trigger a workflow by its webhook path."""
    trigger_path = f"/triggers/{path}"
    result = await db.execute(
        select(Workflow).where(Workflow.trigger_path == trigger_path)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, f"No workflow registered for path: {trigger_path}")

    try:
        body = await request.json()
    except Exception:
        body = {}

    definition = WorkflowDefinition(workflow.yaml_content)

    run = WorkflowRun(
        workflow_id=workflow.id,
        status="running",
        trigger_data=body,
        total_steps=len(definition.steps),
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    engine = WorkflowEngine()

    async def on_step_complete(step_id: str, completed: int, total: int, step_result: Any) -> None:
        step_record = WorkflowStep(
            run_id=run.id,
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

    trigger_data = {"body": body, "headers": dict(request.headers)}
    results = await engine.execute_workflow(definition, trigger_data, on_step_complete)

    failed = any(r.status == "failed" for r in results)
    run.status = "failed" if failed else "completed"
    run.completed_at = datetime.now(timezone.utc)
    if failed:
        failed_steps = [r for r in results if r.status == "failed"]
        run.error_message = f"Step '{failed_steps[0].step_id}' failed: {failed_steps[0].error}"
    await db.commit()

    return {
        "run_id": run.id,
        "workflow_id": workflow.id,
        "workflow_name": workflow.name,
        "status": run.status,
        "steps_completed": run.steps_completed,
        "total_steps": run.total_steps,
    }
