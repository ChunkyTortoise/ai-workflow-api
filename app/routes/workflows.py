"""CRUD routes for workflows."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Workflow, get_db
from app.services.workflow_engine import WorkflowDefinition

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowCreate(BaseModel):
    yaml_content: str


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    trigger_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowDetail(WorkflowResponse):
    yaml_content: str
    steps: list[dict[str, Any]]


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    body: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
) -> Workflow:
    """Create a workflow from YAML definition."""
    try:
        definition = WorkflowDefinition(body.yaml_content)
    except yaml.YAMLError as e:
        raise HTTPException(400, f"Invalid YAML: {e}")

    errors = definition.validate()
    if errors:
        raise HTTPException(400, f"Validation errors: {'; '.join(errors)}")

    # Check for duplicate trigger path
    existing = await db.execute(
        select(Workflow).where(Workflow.trigger_path == definition.trigger_path)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Workflow with trigger path '{definition.trigger_path}' already exists")

    workflow = Workflow(
        name=definition.name,
        description=definition.description,
        yaml_content=body.yaml_content,
        trigger_path=definition.trigger_path,
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    db: AsyncSession = Depends(get_db),
) -> list[Workflow]:
    """List all workflows."""
    result = await db.execute(select(Workflow).order_by(Workflow.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a workflow by ID with full details."""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")

    definition = WorkflowDefinition(workflow.yaml_content)
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "trigger_path": workflow.trigger_path,
        "yaml_content": workflow.yaml_content,
        "steps": definition.steps,
        "created_at": workflow.created_at.isoformat(),
        "updated_at": workflow.updated_at.isoformat(),
    }


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a workflow."""
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")

    await db.delete(workflow)
    await db.commit()
