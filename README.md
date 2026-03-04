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
