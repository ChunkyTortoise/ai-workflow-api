# AI Workflow API

## Stack
FastAPI | SQLAlchemy | ARQ (async Redis queue) | Redis | SSE | Anthropic | Streamlit | Python

## Architecture
YAML-driven workflow engine with 5 node types: trigger / llm / condition / http / notify. ARQ worker processes jobs asynchronously; progress streamed via SSE. LLM node mocks without `ANTHROPIC_API_KEY`.
- `app/main.py` — FastAPI entry point; `/demo` endpoint (no auth required)
- `app/worker.py` — ARQ worker
- `ui/app.py` — Streamlit UI
- `workflows/` — YAML workflow definitions
- `X-API-Key` header required on mutation endpoints

## Deploy
Not yet deployed. Blueprint: `render.yaml`. Target: Render (2 services: API + worker).

## Test
```pytest tests/  # 148 tests```

## Key Env
ANTHROPIC_API_KEY, REDIS_URL, API_KEY, DATABASE_URL
