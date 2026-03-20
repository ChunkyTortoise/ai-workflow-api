# AI Workflow API

A YAML-driven workflow automation API with LLM orchestration, async job processing, and SSE progress streaming.

[![Tests](https://github.com/ChunkyTortoise/ai-workflow-api/actions/workflows/ci.yml/badge.svg)](https://github.com/ChunkyTortoise/ai-workflow-api/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A575%25-brightgreen)](https://github.com/ChunkyTortoise/ai-workflow-api/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)
![ARQ](https://img.shields.io/badge/ARQ-async%20workers-orange)
![Claude AI](https://img.shields.io/badge/Claude-AI-orange?logo=anthropic)

---

## Try It Now

No auth required for demo endpoints. Run locally with Docker or call the demo API directly.

### Summarize a Document (SSE stream)

```bash
# Submit a summarization workflow
curl -X POST http://localhost:8000/demo \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": "document_summary",
    "input": {
      "text": "Retrieval-Augmented Generation (RAG) combines a retrieval system with a generative model. The retrieval component fetches relevant documents from a corpus, and the generator conditions its output on both the query and retrieved context. This approach grounds LLM responses in factual, up-to-date information without expensive fine-tuning."
    }
  }'

# Example response
{
  "job_id": "wf_a1b2c3d4",
  "status": "queued",
  "stream_url": "/jobs/wf_a1b2c3d4/stream"
}
```

### Stream Real-time Output

```bash
# Stream SSE output as the workflow executes
curl -N http://localhost:8000/jobs/wf_a1b2c3d4/stream

# Example SSE stream
data: {"node": "summarizer", "status": "running", "progress": 0.3}
data: {"node": "summarizer", "status": "complete", "output": "RAG enhances LLM accuracy by combining retrieval with generation, grounding responses in factual context without fine-tuning."}
data: {"node": "classifier", "status": "complete", "output": {"category": "AI/ML", "confidence": 0.94}}
data: {"status": "workflow_complete", "total_nodes": 2, "elapsed_ms": 1847}
```

### Classify Text

```bash
curl -X POST http://localhost:8000/demo \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": "text_classify",
    "input": {"text": "Our Q3 revenue grew 23% driven by enterprise contract expansions."}
  }'
```

---

## Features

- **YAML-driven workflows** — define multi-step pipelines in YAML, no code changes needed
- **5 node types**: `trigger`, `llm`, `condition`, `http`, `notify`
- **Async job processing** — ARQ workers with Redis for background execution
- **SSE progress streaming** — real-time job status via Server-Sent Events
- **LLM orchestration** — Claude API integration with structured output

---

## Architecture

```mermaid
graph TB
    Client["Client<br/>(HTTP / curl)"]

    subgraph API["FastAPI Layer"]
        EP[POST /workflows/run<br/>POST /demo]
        JS[Job Status<br/>GET /jobs/{id}]
    end

    subgraph Queue["ARQ Worker Queue (Redis)"]
        WQ[Job Queue]
        WK[ARQ Worker]
    end

    subgraph Engine["Workflow Engine"]
        YP[YAML Parser]
        NE[Node Executor]
        NE --> LLM[LLM Node<br/>Claude]
        NE --> HTTP[HTTP Node<br/>External APIs]
        NE --> COND[Condition Node<br/>if/else branching]
        NE --> NOTIF[Notify Node<br/>Webhooks]
    end

    subgraph State["Job State"]
        SQ[SQLite<br/>job_results]
    end

    subgraph Stream["Real-time Output"]
        SSE[SSE Stream<br/>GET /jobs/{id}/stream]
    end

    Client --> EP
    EP --> WQ
    WQ --> WK
    WK --> YP
    YP --> Engine
    Engine --> State
    Engine --> SSE
    Client --> SSE
    Client --> JS
    JS --> State

    style Client fill:#4A90D9,color:#fff
    style Engine fill:#7B68EE,color:#fff
    style SSE fill:#50C878,color:#fff
    style LLM fill:#FF8C42,color:#fff
```

---

## YAML-Driven Workflows

Workflows are plain YAML — no code, no SDK, just declarative nodes.

**`workflows/document_summary.yaml`**

```yaml
name: document_summary
description: Fetch a document by URL, summarize with AI, and email the report
trigger:
  type: webhook
  path: /triggers/document_summary
steps:
  - id: fetch_doc
    type: http
    method: GET
    url: "{trigger.body.document_url}"
    timeout: 30
  - id: summarize
    type: llm
    model: claude-sonnet-4-6
    prompt: |
      Summarize the following document content. Provide:
      1. A one-paragraph executive summary
      2. Key findings (bullet points)
      3. Action items (if any)

      Document content:
      {fetch_doc.body}
    max_tokens: 2048
  - id: send_report
    type: notify
    channel: email
    recipient: "{trigger.body.email}"
    subject: "Document Summary Report"
    message: |
      Here is your document summary:

      {summarize.content}

      Original document: {trigger.body.document_url}
```

> **Key concepts**: Template variables (`{}`), node chaining, model selection per step, multi-channel notify. Add any `.yaml` to `workflows/` and it's instantly available via the API — no code changes.

---

## Tech Stack

- **API**: FastAPI + Uvicorn
- **Queue**: ARQ (async Redis queue)
- **Database**: SQLite + SQLAlchemy async (persistent via Render disk)
- **AI**: Anthropic Claude (`anthropic` SDK)
- **Config**: YAML workflow definitions
- **Tests**: Pytest + fakeredis + respx (145 passing)

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
│           └── notify.py         # Email/Slack/webhook notification
├── worker/                        # ARQ background worker settings
├── workflows/                     # Built-in YAML workflow definitions
│   ├── document_summary.yaml
│   ├── lead_qualification.yaml
│   └── support_triage.yaml
├── tests/                         # 145 passing tests
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
pytest tests/ -v    # 145 passing tests
```

Tests use `fakeredis` for Redis and `respx` for HTTP mocking -- no external services required.

---

## Certifications Applied

Domain pillars from [19 completed AI/ML certifications](https://caymanroden.com) backing this project:

| Domain | Certification | Applied In |
|--------|--------------|-----------|
| LLM Orchestration | Anthropic Building with Claude (Vanderbilt) | Multi-node LLM workflows, model selection per node |
| Async Systems & Queues | IBM DevOps and Software Engineering | ARQ worker queue, Redis job state, async job processing |
| API Design | Meta Back-End Developer (Python) | FastAPI routes, SSE streaming, OpenAPI docs |
| Workflow Engines | IBM Full Stack Developer | YAML DSL design, node executor pattern, condition branching |
| AI Pipelines | DeepLearning.AI MLOps Specialization | YAML-driven pipeline architecture, declarative AI workflows |

---

## License

[MIT](LICENSE) — Copyright (c) 2026 Cayman Roden
