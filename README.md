# AI Workflow API

A YAML-driven workflow automation API with LLM orchestration, async job processing, and SSE progress streaming.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)
![ARQ](https://img.shields.io/badge/ARQ-async%20workers-orange)
![Claude AI](https://img.shields.io/badge/Claude-AI-orange?logo=anthropic)
![Tests](https://img.shields.io/badge/tests-148%20passing-brightgreen)

---

## Features

- **YAML-driven workflows** — define multi-step pipelines in YAML, no code changes needed
- **5 node types**: `trigger`, `llm`, `condition`, `http`, `notify`
- **Async job processing** — ARQ workers with Redis for background execution
- **SSE progress streaming** — real-time job status via Server-Sent Events
- **LLM orchestration** — Claude API integration with structured output

---

## Architecture

```
Client -> FastAPI -> ARQ Worker Queue (Redis)
                         |
               Workflow Engine (YAML)
                         |
            Node executors: LLM | HTTP | Condition | Notify
                         |
               SQLite (job state) + SSE (progress stream)
```

---

## Tech Stack

- **API**: FastAPI + Uvicorn
- **Queue**: ARQ (async Redis queue)
- **Database**: SQLite + SQLAlchemy async (persistent via Render disk)
- **AI**: Anthropic Claude (`anthropic` SDK)
- **Config**: YAML workflow definitions
- **Tests**: Pytest + fakeredis + respx (148 passing)

---

## Setup

```bash
git clone https://github.com/ChunkyTortoise/ai-workflow-api
cd ai-workflow-api
pip install -r requirements.txt
```

Set environment variables:
```env
ANTHROPIC_API_KEY=your_key_here
REDIS_URL=redis://localhost:6379
DATABASE_URL=sqlite+aiosqlite:///./workflow.db
```

```bash
uvicorn app.main:app --reload   # Start API
arq app.worker.WorkerSettings   # Start ARQ worker
pytest tests/ -v                # Run tests
```

---

## Workflow YAML Format

```yaml
name: document_processor
nodes:
  - id: trigger
    type: trigger
    config:
      event: document_uploaded
  - id: extract
    type: llm
    config:
      prompt: "Extract key fields from: {document_content}"
      model: claude-haiku-4-5-20251001
  - id: notify
    type: notify
    config:
      channel: webhook
      url: "{NOTIFY_URL}"
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/workflows` | List available workflows |
| `POST` | `/workflows/{name}/run` | Trigger a workflow |
| `GET` | `/jobs/{job_id}` | Get job status |
| `GET` | `/jobs/{job_id}/stream` | SSE progress stream |

---

## Deployment

Deployed on Render with persistent disk for SQLite storage.

> **Note**: SQLite data is stored on a Render persistent disk (`/data/workflow.db`). Data persists across deploys but not across disk replacements.

```bash
# render.yaml includes disk configuration
# Set ANTHROPIC_API_KEY + REDIS_URL in Render dashboard
```

---

## Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...                        # Claude API key for LLM nodes
REDIS_URL=redis://localhost:6379/0                   # ARQ worker queue + SSE pub/sub
DATABASE_URL=sqlite+aiosqlite:///./workflow.db       # Async SQLAlchemy (SQLite default)

# Optional
CORS_ORIGINS=["http://localhost:3000"]               # JSON array of allowed origins
LOG_LEVEL=INFO                                       # Python log level
WORKER_MAX_JOBS=10                                   # Max concurrent ARQ jobs
JOB_TIMEOUT_SECONDS=300                              # Per-job timeout
```

---

## Project Structure

```
ai-workflow-api/
├── app/
│   ├── main.py                    # FastAPI app factory + lifespan
│   ├── config.py                  # pydantic-settings (env-based)
│   ├── models.py                  # SQLAlchemy async models (Workflow, WorkflowRun, WorkflowStep)
│   ├── events.py                  # Redis pub/sub for SSE streaming
│   ├── routes/
│   │   ├── workflows.py           # CRUD: POST/GET/DELETE /api/v1/workflows
│   │   ├── runs.py                # POST execute, GET list/detail, POST trigger
│   │   └── stream.py              # GET /api/v1/runs/{id}/stream (SSE)
│   └── services/
│       ├── workflow_engine.py     # YAML parser + step executor + condition branching
│       ├── node_registry.py       # Singleton registry for node types
│       ├── claude_client.py       # Anthropic SDK wrapper
│       ├── template.py            # Variable interpolation for YAML configs
│       └── nodes/
│           ├── trigger.py         # Entry point, passes input through
│           ├── llm.py             # Claude API call with prompt template
│           ├── condition.py       # Branch based on expression evaluation
│           ├── http.py            # External HTTP request
│           └── notify.py          # Email/Slack/webhook notification
├── worker/                        # ARQ background worker settings
├── workflows/                     # Built-in YAML workflow definitions
│   ├── document_summary.yaml
│   ├── lead_qualification.yaml
│   └── support_triage.yaml
├── tests/                         # 148 passing tests
├── docker-compose.yml             # API + Redis + ARQ worker
├── Dockerfile
├── render.yaml                    # Render Blueprint deployment
└── requirements.txt
```

---

## API Examples

All routes are prefixed with `/api/v1`.

### Create a Workflow

```bash
curl -X POST http://localhost:8000/api/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{"yaml_content": "name: my_workflow\ndescription: Test\ntrigger:\n  type: webhook\n  path: /triggers/my_workflow\nsteps:\n  - id: step1\n    type: trigger\n"}'
```
```json
{
  "id": "a1b2c3d4-...",
  "name": "my_workflow",
  "description": "Test",
  "trigger_path": "/triggers/my_workflow",
  "created_at": "2026-03-08T...",
  "updated_at": "2026-03-08T..."
}
```

### List Workflows

```bash
curl http://localhost:8000/api/v1/workflows
```
```json
[
  {
    "id": "a1b2c3d4-...",
    "name": "document_summary",
    "description": "Fetch a document by URL, summarize with AI, and email the report",
    "trigger_path": "/triggers/document_summary"
  }
]
```

### Execute a Workflow

```bash
curl -X POST http://localhost:8000/api/v1/runs/{workflow_id}/execute \
  -H "Content-Type: application/json" \
  -d '{"data": {"document_url": "https://example.com/doc.pdf", "email": "user@example.com"}}'
```
```json
{
  "id": "run_abc123",
  "workflow_id": "a1b2c3d4-...",
  "status": "completed",
  "steps_completed": 3,
  "total_steps": 3,
  "error_message": null,
  "started_at": "2026-03-08T...",
  "completed_at": "2026-03-08T..."
}
```

### Trigger via Webhook Path

```bash
curl -X POST http://localhost:8000/api/v1/runs/trigger/document_summary \
  -H "Content-Type: application/json" \
  -d '{"document_url": "https://example.com/report.pdf", "email": "user@co.com"}'
```

### Stream Progress (SSE)

```bash
curl -N http://localhost:8000/api/v1/runs/{run_id}/stream
```
```
data: {"event": "step_started", "step_id": "fetch_doc", "node_type": "http"}
data: {"event": "step_completed", "step_id": "fetch_doc", "status": "completed", "output": {...}}
data: {"event": "step_started", "step_id": "summarize", "node_type": "llm"}
data: {"event": "step_completed", "step_id": "summarize", "status": "completed", "output": {...}}
data: {"event": "run_completed", "status": "completed", "steps_completed": 3, "total_steps": 3}
```

### List Runs (with filters)

```bash
curl "http://localhost:8000/api/v1/runs?workflow_id=abc&status=completed&page=1&page_size=20"
```

---

## Built-in Workflows

| Workflow | Steps | Description |
|----------|-------|-------------|
| `document_summary` | http -> llm -> notify | Fetches a document URL, summarizes with Claude, emails the report |
| `lead_qualification` | llm -> condition -> notify | Qualifies leads with AI scoring, routes high-score to Slack, low-score to nurture email |
| `support_triage` | llm -> condition -> notify | Analyzes ticket sentiment/priority, escalates urgent to Slack, routes normal to email queue |

---

## Node Types

| Type | Description | Key Config Fields |
|------|-------------|-------------------|
| `trigger` | Entry point, passes webhook data through | `type`, `path` |
| `llm` | Claude API call with prompt template | `model`, `prompt`, `max_tokens` |
| `condition` | Branch based on expression evaluation | `condition`, `on_true`, `on_false` |
| `http` | External HTTP request | `url`, `method`, `timeout` |
| `notify` | Send notification (email/Slack/webhook) | `channel`, `recipient`, `message` |

Step outputs are stored in context and available to downstream steps via `{step_id.field}` template syntax.

---

## Docker

```bash
# Start API + Redis + ARQ worker
docker-compose up

# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
# ReDoc at http://localhost:8000/redoc
```

```yaml
# docker-compose.yml services
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      REDIS_URL: redis://redis:6379/0
      DATABASE_URL: sqlite+aiosqlite:///./workflow.db
  worker:
    build: .
    command: python -m arq worker.worker.WorkerSettings
    environment:
      REDIS_URL: redis://redis:6379/0
```

---

## Tests

```bash
pytest tests/ -v    # 148 passing tests
```

Tests use `fakeredis` for Redis and `respx` for HTTP mocking -- no external services required.
