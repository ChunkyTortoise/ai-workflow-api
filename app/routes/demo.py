"""Demo endpoint — runs a mock workflow without auth or API keys."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/demo", tags=["demo"])

MOCK_WORKFLOW_STEPS = ["trigger", "llm", "notify"]

DEMO_RESPONSES = {
    "summarize": "Mock summary: The input text has been processed and condensed into key points.",
    "classify": "Mock classification: Category=technical, Confidence=0.92, Subcategory=ai-workflow",
    "extract": 'Mock extraction: {"entities": ["workflow", "automation", "AI"], "sentiment": "positive"}',
}


@router.post("")
async def run_demo(body: dict[str, Any]) -> dict[str, Any]:
    """Run a mock workflow synchronously. No auth or API keys required.

    Pass any text in the body and get a demo response showing the
    workflow execution pipeline.
    """
    text = body.get("text", body.get("input", "Hello, workflow!"))
    workflow_id = body.get("workflow_id", "summarize")

    mock_result = DEMO_RESPONSES.get(
        workflow_id,
        f"Mock result: Processed '{str(text)[:50]}...' through {workflow_id} workflow",
    )

    steps_log = []
    for step in MOCK_WORKFLOW_STEPS:
        steps_log.append({
            "step": step,
            "status": "complete",
            "output": {"result": mock_result} if step == "llm" else {},
        })

    return {
        "result": mock_result,
        "steps_executed": MOCK_WORKFLOW_STEPS,
        "steps_log": steps_log,
        "tokens_used": 0,
        "demo_mode": True,
        "workflow_id": workflow_id,
    }
