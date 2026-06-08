#!/usr/bin/env python3
"""Run a workflow asynchronously and render its live SSE progress.

Registers the no-LLM `service_health_pipeline`, triggers it via
POST /api/v1/runs/{id}/execute-async, then subscribes to
GET /api/v1/runs/{run_id}/stream and prints each progress event as the
ARQ worker publishes it.

Usage:
    python scripts/stream_demo.py            # uses http://127.0.0.1:8000
    API_URL=http://host:8000 python scripts/stream_demo.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")
WORKFLOW = Path(__file__).resolve().parent.parent / "workflows" / "service_health_pipeline.yaml"


def bar(pct: int, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "[" + "#" * filled + "." * (width - filled) + f"] {pct:3d}%"


def main() -> int:
    yaml_content = WORKFLOW.read_text()

    with httpx.Client(base_url=API_URL, timeout=30.0) as c:
        reg = c.post("/api/v1/workflows", json={"yaml_content": yaml_content})
        if reg.status_code == 201:
            wf_id = reg.json()["id"]
        elif reg.status_code == 409:
            wf_id = next(
                w["id"] for w in c.get("/api/v1/workflows").json()
                if w["name"] == "service_health_pipeline"
            )
        else:
            print(f"register failed: {reg.status_code} {reg.text}")
            return 1
        print(f"> registered service_health_pipeline ({wf_id[:8]})")

        run = c.post(f"/api/v1/runs/{wf_id}/execute-async", json={"data": {}})
        run.raise_for_status()
        run_id = run.json()["id"]
        print(f"> POST execute-async -> queued (run {run_id[:8]})")
        print(f"< streaming /api/v1/runs/{run_id[:8]}/stream\n")

        start = time.monotonic()
        with c.stream("GET", f"/api/v1/runs/{run_id}/stream", timeout=20.0) as resp:
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                evt = json.loads(line[len("data:"):].strip())
                kind = evt.get("type")
                if kind == "run_started":
                    print(f"  run_started     total_steps={evt.get('total_steps')}")
                elif kind == "step_completed":
                    print(
                        f"  {bar(evt.get('progress', 0))}  "
                        f"{evt.get('step_id',''):<16} {evt.get('status','')}"
                    )
                elif kind in ("run_completed", "run_failed"):
                    print(
                        f"  {kind}   status={evt.get('status')} "
                        f"steps {evt.get('steps_completed')}/{evt.get('total_steps')}"
                    )
                    break

        print(f"\ndone in {time.monotonic() - start:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
