"""Tests for API routes."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import CONDITION_WORKFLOW_YAML, MINIMAL_WORKFLOW_YAML, SAMPLE_WORKFLOW_YAML


# === Workflow CRUD Routes ===


class TestWorkflowRoutes:
    @pytest.mark.asyncio
    async def test_create_workflow(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "minimal"
        assert data["trigger_path"] == "/triggers/minimal"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_workflow_invalid_yaml(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": "{{{{invalid yaml"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_workflow_validation_error(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": "name: test\nsteps: []"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_duplicate_trigger_path(self, client: AsyncClient):
        await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        response = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_list_workflows_empty(self, client: AsyncClient):
        response = await client.get("/api/v1/workflows")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_workflows(self, client: AsyncClient):
        await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        response = await client.get("/api/v1/workflows")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "minimal"

    @pytest.mark.asyncio
    async def test_get_workflow(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        wf_id = create_resp.json()["id"]
        response = await client.get(f"/api/v1/workflows/{wf_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "minimal"
        assert "steps" in data
        assert "yaml_content" in data

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self, client: AsyncClient):
        response = await client.get("/api/v1/workflows/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_workflow(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        wf_id = create_resp.json()["id"]
        response = await client.delete(f"/api/v1/workflows/{wf_id}")
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/api/v1/workflows/{wf_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_workflow_not_found(self, client: AsyncClient):
        response = await client.delete("/api/v1/workflows/nonexistent-id")
        assert response.status_code == 404


# === Run Routes ===


class TestRunRoutes:
    @pytest.mark.asyncio
    async def test_execute_workflow(self, client: AsyncClient):
        # Create workflow first
        create_resp = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        wf_id = create_resp.json()["id"]

        # Execute
        response = await client.post(
            f"/api/v1/runs/{wf_id}/execute",
            json={"data": {"message": "hello"}},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "completed"
        assert data["workflow_id"] == wf_id
        assert data["steps_completed"] >= 1

    @pytest.mark.asyncio
    async def test_execute_workflow_not_found(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/runs/nonexistent/execute",
            json={"data": {}},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_runs_empty(self, client: AsyncClient):
        response = await client.get("/api/v1/runs")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_runs(self, client: AsyncClient):
        # Create and execute workflow
        create_resp = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        wf_id = create_resp.json()["id"]
        await client.post(f"/api/v1/runs/{wf_id}/execute", json={"data": {}})

        response = await client.get("/api/v1/runs")
        assert response.status_code == 200
        assert len(response.json()) == 1

    @pytest.mark.asyncio
    async def test_list_runs_filter_by_workflow(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        wf_id = create_resp.json()["id"]
        await client.post(f"/api/v1/runs/{wf_id}/execute", json={"data": {}})

        response = await client.get(f"/api/v1/runs?workflow_id={wf_id}")
        assert response.status_code == 200
        assert len(response.json()) == 1

        response = await client.get("/api/v1/runs?workflow_id=other")
        assert response.status_code == 200
        assert len(response.json()) == 0

    @pytest.mark.asyncio
    async def test_list_runs_filter_by_status(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        wf_id = create_resp.json()["id"]
        await client.post(f"/api/v1/runs/{wf_id}/execute", json={"data": {}})

        response = await client.get("/api/v1/runs?status=completed")
        assert response.status_code == 200
        assert len(response.json()) == 1

        response = await client.get("/api/v1/runs?status=failed")
        assert response.status_code == 200
        assert len(response.json()) == 0

    @pytest.mark.asyncio
    async def test_get_run_detail(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        wf_id = create_resp.json()["id"]
        exec_resp = await client.post(f"/api/v1/runs/{wf_id}/execute", json={"data": {"key": "val"}})
        run_id = exec_resp.json()["id"]

        response = await client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "steps" in data
        assert "trigger_data" in data

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, client: AsyncClient):
        response = await client.get("/api/v1/runs/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_sample_workflow(self, client: AsyncClient):
        """Test the multi-step sample workflow with mocked LLM."""
        create_resp = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": SAMPLE_WORKFLOW_YAML},
        )
        wf_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/runs/{wf_id}/execute",
            json={"data": {"name": "Test User"}},
        )
        assert response.status_code == 201
        data = response.json()
        # LLM node will use mock client (no API key configured)
        assert data["status"] in ("completed", "failed")

    @pytest.mark.asyncio
    async def test_webhook_trigger(self, client: AsyncClient):
        await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        response = await client.post(
            "/api/v1/runs/trigger/minimal",
            json={"message": "webhook payload"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["workflow_name"] == "minimal"

    @pytest.mark.asyncio
    async def test_webhook_trigger_not_found(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/runs/trigger/nonexistent_path",
            json={},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_empty_data(self, client: AsyncClient):
        create_resp = await client.post(
            "/api/v1/workflows",
            json={"yaml_content": MINIMAL_WORKFLOW_YAML},
        )
        wf_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/runs/{wf_id}/execute",
            json={"data": {}},
        )
        assert response.status_code == 201
        assert response.json()["status"] == "completed"


# === Health Check ===


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
