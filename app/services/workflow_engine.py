"""Core workflow execution engine."""
from __future__ import annotations

import logging
from typing import Any

import yaml

from app.services.node_registry import get_node

logger = logging.getLogger(__name__)


class WorkflowDefinition:
    """Parsed YAML workflow definition."""

    def __init__(self, raw_yaml: str) -> None:
        self._data = yaml.safe_load(raw_yaml)
        self.name: str = self._data.get("name", "")
        self.description: str = self._data.get("description", "")
        self.trigger: dict[str, Any] = self._data.get("trigger", {})
        self.steps: list[dict[str, Any]] = self._data.get("steps", [])

    @property
    def trigger_path(self) -> str:
        return self.trigger.get("path", f"/triggers/{self.name}")

    @property
    def step_ids(self) -> list[str]:
        return [s["id"] for s in self.steps]

    def get_step(self, step_id: str) -> dict[str, Any] | None:
        for step in self.steps:
            if step["id"] == step_id:
                return step
        return None

    def validate(self) -> list[str]:
        """Validate the workflow definition. Returns list of errors."""
        errors: list[str] = []
        if not self.name:
            errors.append("Workflow must have a 'name'")
        if not self.trigger:
            errors.append("Workflow must have a 'trigger'")
        if not self.steps:
            errors.append("Workflow must have at least one step")

        step_ids = set()
        for i, step in enumerate(self.steps):
            if "id" not in step:
                errors.append(f"Step {i} missing 'id'")
            elif step["id"] in step_ids:
                errors.append(f"Duplicate step id: {step['id']}")
            else:
                step_ids.add(step["id"])

            if "type" not in step:
                errors.append(f"Step {i} missing 'type'")

        # Validate condition references
        for step in self.steps:
            if step.get("type") == "condition":
                for ref_key in ("on_true", "on_false"):
                    ref = step.get(ref_key)
                    if ref and ref not in step_ids:
                        errors.append(
                            f"Step '{step.get('id')}' references unknown step '{ref}' in {ref_key}"
                        )

        return errors


class StepResult:
    """Result of a single step execution."""

    def __init__(
        self,
        step_id: str,
        node_type: str,
        output: dict[str, Any],
        status: str = "completed",
        error: str | None = None,
    ) -> None:
        self.step_id = step_id
        self.node_type = node_type
        self.output = output
        self.status = status
        self.error = error


class WorkflowEngine:
    """Executes workflow steps and manages context."""

    def __init__(self) -> None:
        self._context: dict[str, Any] = {}
        self._results: list[StepResult] = []

    @property
    def context(self) -> dict[str, Any]:
        return self._context

    @property
    def results(self) -> list[StepResult]:
        return self._results

    def set_trigger_data(self, data: dict[str, Any]) -> None:
        """Set the initial trigger data in the context."""
        self._context["trigger"] = data

    async def execute_step(self, step_config: dict[str, Any]) -> StepResult:
        """Execute a single workflow step.

        Args:
            step_config: Step configuration from YAML definition.

        Returns:
            StepResult with output data.
        """
        step_id = step_config["id"]
        node_type = step_config["type"]

        try:
            node = get_node(node_type)
            output = await node.execute(step_config, self._context)

            # Store step output in context for downstream steps
            self._context[step_id] = output

            result = StepResult(
                step_id=step_id,
                node_type=node_type,
                output=output,
                status="completed",
            )
        except Exception as e:
            logger.error("Step '%s' failed: %s", step_id, e, exc_info=True)
            result = StepResult(
                step_id=step_id,
                node_type=node_type,
                output={},
                status="failed",
                error=str(e),
            )

        self._results.append(result)
        return result

    async def execute_workflow(
        self,
        definition: WorkflowDefinition,
        trigger_data: dict[str, Any],
        on_step_complete: Any | None = None,
    ) -> list[StepResult]:
        """Execute all steps in a workflow.

        Args:
            definition: Parsed workflow definition.
            trigger_data: Initial trigger/webhook data.
            on_step_complete: Optional async callback(step_id, step_index, total, result).

        Returns:
            List of StepResults.
        """
        self.set_trigger_data(trigger_data)
        total_steps = len(definition.steps)
        executed_steps: set[str] = set()

        # Execute steps in order, handling condition branches
        i = 0
        while i < len(definition.steps):
            step = definition.steps[i]
            step_id = step["id"]

            # Skip if already executed (from a branch)
            if step_id in executed_steps:
                i += 1
                continue

            executed_steps.add(step_id)
            result = await self.execute_step(step)

            if on_step_complete:
                await on_step_complete(step_id, len(executed_steps), total_steps, result)

            if result.status == "failed":
                # Mark remaining steps as skipped
                for remaining in definition.steps[i + 1 :]:
                    if remaining["id"] not in executed_steps:
                        skipped = StepResult(
                            step_id=remaining["id"],
                            node_type=remaining["type"],
                            output={},
                            status="skipped",
                        )
                        self._results.append(skipped)
                break

            # Handle condition branching
            if step.get("type") == "condition" and result.output.get("next_step"):
                next_step_id = result.output["next_step"]
                # Find and execute the target step
                target_step = definition.get_step(next_step_id)
                if target_step and next_step_id not in executed_steps:
                    executed_steps.add(next_step_id)
                    branch_result = await self.execute_step(target_step)
                    if on_step_complete:
                        await on_step_complete(
                            next_step_id, len(executed_steps), total_steps, branch_result
                        )

                # Mark the other branch as skipped
                other_key = "on_false" if result.output.get("result") else "on_true"
                other_step_id = step.get(other_key)
                if other_step_id and other_step_id not in executed_steps:
                    executed_steps.add(other_step_id)
                    skipped = StepResult(
                        step_id=other_step_id,
                        node_type="unknown",
                        output={},
                        status="skipped",
                    )
                    target = definition.get_step(other_step_id)
                    if target:
                        skipped.node_type = target["type"]
                    self._results.append(skipped)

            i += 1

        return self._results
