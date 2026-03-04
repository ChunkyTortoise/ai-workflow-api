# AI Workflow Automation API

YAML-driven AI workflow automation with real-time SSE streaming.

Define workflows as YAML: `trigger -> transform -> AI step -> action`. Execute via webhook or API. Watch progress in real-time via SSE.

## Stack

- **API**: FastAPI + SSE (sse-starlette)
- **Worker**: ARQ (async Redis queue)
- **AI**: Anthropic Claude
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **Queue/PubSub**: Redis

## Quick Start

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY in .env

pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Create a Workflow

```bash
curl -X POST http://localhost:8000/api/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{"yaml_content": "name: hello\ndescription: test\ntrigger:\n  type: webhook\n  path: /triggers/hello\nsteps:\n  - id: greet\n    type: notify\n    channel: log\n    message: Hello from workflow"}'
```

## Execute via Webhook

```bash
curl -X POST http://localhost:8000/api/v1/runs/trigger/hello \
  -H "Content-Type: application/json" \
  -d '{"name": "World"}'
```

## Node Types

| Type | Description |
|------|-------------|
| `trigger` | Webhook trigger (entry point) |
| `llm` | Claude AI call with template prompts |
| `condition` | Branch based on expression evaluation |
| `http` | HTTP request to external APIs |
| `notify` | Notification stubs (email/Slack/GHL) |

## Tests

```bash
pytest tests/ -v
```

## Deploy

Docker Compose (local):
```bash
docker-compose up -d
```

Render (cloud):
- Push to GitHub
- Connect repo in Render dashboard
- Use the included `render.yaml` Blueprint
- Set `ANTHROPIC_API_KEY` in dashboard
