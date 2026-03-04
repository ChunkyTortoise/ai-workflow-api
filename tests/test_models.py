"""Tests for database models."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Workflow, WorkflowRun, WorkflowStep


class TestWorkflowModel:
    @pytest.mark.asyncio
    async def test_create_workflow(self, db_session: AsyncSession):
        wf = Workflow(
            name="test",
            description="A test workflow",
            yaml_content="name: test\nsteps: []",
            trigger_path="/triggers/test",
        )
        db_session.add(wf)
        await db_session.commit()
        await db_session.refresh(wf)

        assert wf.id is not None
        assert wf.name == "test"
        assert wf.created_at is not None

    @pytest.mark.asyncio
    async def test_workflow_fields(self, db_session: AsyncSession):
        wf = Workflow(
            name="fields_test",
            description="desc",
            yaml_content="yaml here",
            trigger_path="/triggers/fields_test",
        )
        db_session.add(wf)
        await db_session.commit()
        await db_session.refresh(wf)

        assert wf.description == "desc"
        assert wf.yaml_content == "yaml here"
        assert wf.trigger_path == "/triggers/fields_test"

    @pytest.mark.asyncio
    async def test_query_workflow(self, db_session: AsyncSession):
        wf = Workflow(
            name="query_test",
            yaml_content="test",
            trigger_path="/triggers/query_test",
        )
        db_session.add(wf)
        await db_session.commit()

        result = await db_session.execute(select(Workflow).where(Workflow.name == "query_test"))
        found = result.scalar_one()
        assert found.name == "query_test"


class TestWorkflowRunModel:
    @pytest.mark.asyncio
    async def test_create_run(self, db_session: AsyncSession):
        wf = Workflow(name="r_test", yaml_content="y", trigger_path="/triggers/r_test")
        db_session.add(wf)
        await db_session.commit()
        await db_session.refresh(wf)

        run = WorkflowRun(
            workflow_id=wf.id,
            status="pending",
            trigger_data={"key": "value"},
            total_steps=3,
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        assert run.id is not None
        assert run.status == "pending"
        assert run.trigger_data == {"key": "value"}
        assert run.total_steps == 3
        assert run.steps_completed == 0

    @pytest.mark.asyncio
    async def test_run_defaults(self, db_session: AsyncSession):
        wf = Workflow(name="d_test", yaml_content="y", trigger_path="/triggers/d_test")
        db_session.add(wf)
        await db_session.commit()
        await db_session.refresh(wf)

        run = WorkflowRun(workflow_id=wf.id)
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        assert run.status == "pending"
        assert run.steps_completed == 0
        assert run.total_steps == 0
        assert run.error_message is None
        assert run.started_at is None
        assert run.completed_at is None


class TestWorkflowStepModel:
    @pytest.mark.asyncio
    async def test_create_step(self, db_session: AsyncSession):
        wf = Workflow(name="s_test", yaml_content="y", trigger_path="/triggers/s_test")
        db_session.add(wf)
        await db_session.commit()
        await db_session.refresh(wf)

        run = WorkflowRun(workflow_id=wf.id)
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        step = WorkflowStep(
            run_id=run.id,
            step_id="qualify",
            node_type="llm",
            status="completed",
            output_data={"content": "result"},
        )
        db_session.add(step)
        await db_session.commit()
        await db_session.refresh(step)

        assert step.id is not None
        assert step.step_id == "qualify"
        assert step.node_type == "llm"
        assert step.output_data == {"content": "result"}

    @pytest.mark.asyncio
    async def test_step_defaults(self, db_session: AsyncSession):
        wf = Workflow(name="sd_test", yaml_content="y", trigger_path="/triggers/sd_test")
        db_session.add(wf)
        await db_session.commit()
        await db_session.refresh(wf)

        run = WorkflowRun(workflow_id=wf.id)
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        step = WorkflowStep(
            run_id=run.id,
            step_id="s1",
            node_type="trigger",
        )
        db_session.add(step)
        await db_session.commit()
        await db_session.refresh(step)

        assert step.status == "pending"
        assert step.input_data == {}
        assert step.output_data == {}
        assert step.error_message is None

    @pytest.mark.asyncio
    async def test_step_with_error(self, db_session: AsyncSession):
        wf = Workflow(name="se_test", yaml_content="y", trigger_path="/triggers/se_test")
        db_session.add(wf)
        await db_session.commit()
        await db_session.refresh(wf)

        run = WorkflowRun(workflow_id=wf.id)
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        step = WorkflowStep(
            run_id=run.id,
            step_id="bad",
            node_type="llm",
            status="failed",
            error_message="API call failed",
        )
        db_session.add(step)
        await db_session.commit()
        await db_session.refresh(step)

        assert step.status == "failed"
        assert step.error_message == "API call failed"
