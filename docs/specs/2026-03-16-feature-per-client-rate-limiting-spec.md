---
title: "Spec: Per-Client Rate Limiting"
type: feature
status: draft
version: 1
date: 2026-03-16
complexity: deep
target_repo: ai-workflow-api
origin: docs/brainstorms/2026-03-16-per-client-rate-limiting-brainstorm.md
---

# Spec: Per-Client Rate Limiting

## 1. Problem Statement & Context

The AI Workflow API has no rate limiting, allowing a single API key to exhaust server and Claude quota. Adding per-client sliding-window rate limiting via Redis sorted sets protects shared resources and enables differentiated tiers without breaking existing workflows.

### Codebase Context
- **Repository**: `~/Projects/ai-workflow-api/`
- **Key files** (absolute paths):
  - `~/Projects/ai-workflow-api/app/main.py` — FastAPI entry point; `create_app()` builds middleware stack; `lifespan()` manages startup/shutdown
  - `~/Projects/ai-workflow-api/app/models.py` — SQLAlchemy async models; `Base`, `_uuid`, `_utcnow` conventions; `async_session` factory
  - `~/Projects/ai-workflow-api/app/config.py` — `Settings(BaseSettings)` with env-var-backed fields
  - `~/Projects/ai-workflow-api/app/services/` — existing service layer (node handlers, Claude client, workflow engine)
  - `~/Projects/ai-workflow-api/tests/conftest.py` — `db_engine`, `db_session`, `client` fixtures; no Redis fixture yet
- **Existing patterns**: `add_request_id` middleware at `app/main.py:59`; `async_session()` used for DB access in `app/worker.py`
- **CLAUDE.md guidance**: `X-API-Key` header required on mutation endpoints; deploy target is Render (2 services)
- **Related specs/brainstorms**: none

---

## 2. Requirements (EARS Notation)

### Functional Requirements
- **REQ-F01**: When the system receives an HTTP request with an `X-API-Key` header, the system shall check the request count against the client's configured or default rate limit using a Redis sliding-window algorithm before passing the request to the route handler.
- **REQ-F02**: When the rate limit is exceeded, the system shall return HTTP 429 with a JSON body `{"error": "rate limit exceeded"}` and a `Retry-After` header indicating seconds until the window resets.
- **REQ-F03**: When the rate limit is not exceeded, the system shall add `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers to every response, including 2xx responses.
- **REQ-F04**: Where a `ClientConfig` row exists for the API key's SHA-256 prefix, the system shall use that row's `rpm` field as the rate limit; otherwise the system shall use `settings.rate_limit_default_rpm`.
- **REQ-F05**: When Redis is unavailable (ConnectionError, TimeoutError, or OSError), the system shall fail open and allow the request to proceed without rate limiting.
- **REQ-F06**: Where the request path matches an exempt prefix (`/health`, `/docs`, `/redoc`, `/openapi.json`, `/demo`), the system shall bypass rate limiting entirely.
- **REQ-F07**: If the `API_KEY` environment variable is not set (dev/demo mode), then when any request arrives, the system shall skip rate limiting entirely.
- **REQ-F08**: The system shall cache `ClientConfig` lookups in Redis for 300 seconds using key pattern `client_cfg:{sha256[:16]}` to avoid per-request database queries.

### Non-Functional Requirements
- **REQ-NF01**: The rate-limit check shall add no more than 2ms p99 overhead per request under 500 concurrent clients, as measured by the Lua script round-trip to a local Redis instance.
- **REQ-NF02**: All `ClientConfig` database reads outside dependency injection (e.g., in middleware) shall use `async_session()` from `app/models.py`, consistent with the existing worker pattern.
- **REQ-NF03**: When Redis is unavailable, the service shall degrade gracefully (fail-open) so no production traffic is blocked by a Redis outage.
- **REQ-NF04**: All rate-limit decisions shall be logged at DEBUG level with `request_id`, `api_key_prefix`, `limit`, `remaining`, and `decision` fields.

### Out of Scope
- IP-based rate limiting (API key only)
- Admin API for managing `ClientConfig` rows (direct DB seeding is sufficient)
- Distributed Redis cluster support (single-node Redis assumed)
- Per-endpoint granularity (global RPM per API key only)

---

## 3. Acceptance Criteria (Given/When/Then)

### AC-01: Request below limit is allowed
- **Given** a client with API key `test-key` has no `ClientConfig` row and `settings.rate_limit_default_rpm = 60`
- **When** the client sends 1 request to `POST /api/v1/workflows`
- **Then** the response status is not 429; headers include `X-RateLimit-Limit: 60`, `X-RateLimit-Remaining: 59`, and `X-RateLimit-Reset` (Unix timestamp)
- **Verification**: `pytest tests/test_rate_limiter.py::test_ac01_allow_below_limit -v`

### AC-02: Request exceeding limit returns 429
- **Given** a client has exhausted 60 requests within the 60-second window
- **When** the 61st request arrives with the same `X-API-Key`
- **Then** the response status is 429 with body `{"error": "rate limit exceeded"}` and `Retry-After` header is present and positive
- **Verification**: `pytest tests/test_rate_limiter.py::test_ac02_reject_over_limit -v`

### AC-03: Per-client config overrides default limit
- **Given** a `ClientConfig` row exists for key `premium-key` with `rpm=300`
- **When** the client sends request 61 within the window
- **Then** the response is not 429 (premium limit not yet hit)
- **Verification**: `pytest tests/test_rate_limiter.py::test_ac03_per_client_config -v`

### AC-04: Redis fail-open — request allowed when Redis down
- **Given** `app.state.redis` raises `ConnectionError` on every call
- **When** any authenticated request arrives
- **Then** the response is not 429 and no unhandled exception propagates
- **Verification**: `pytest tests/test_rate_limiter.py::test_ac04_fail_open -v`

### AC-05: Exempt paths bypass rate limiting
- **Given** rate limiting is active and the Redis window is full
- **When** a request arrives for `/health`, `/docs`, `/redoc`, `/openapi.json`, or `/demo/run`
- **Then** the response is not 429 and no rate-limit headers are added
- **Verification**: `pytest tests/test_rate_limiter.py::test_ac05_exempt_paths -v`

### AC-06: Dev mode (no API_KEY env) skips rate limiting
- **Given** `settings.api_key` is empty (dev/demo mode)
- **When** any request arrives
- **Then** the middleware returns immediately without touching Redis; response is not 429
- **Verification**: `pytest tests/test_rate_limiter.py::test_ac06_dev_mode_bypass -v`

### AC-07: Rate-limit headers present on all non-exempt responses
- **Given** a client is below their rate limit
- **When** the client sends a request that succeeds with HTTP 200
- **Then** `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers are all present in the response
- **Verification**: `pytest tests/test_rate_limiter.py::test_ac07_headers_on_200 -v`

### AC-08: Middleware ordering — 429 responses include X-Request-ID
- **Given** rate limiting is active
- **When** a client exceeds the limit and receives a 429 response
- **Then** the `X-Request-ID` header is still present (rate limit middleware runs after add_request_id)
- **Verification**: `pytest tests/test_rate_limiter.py::test_ac08_request_id_on_429 -v`

---

## 4. Architecture Decisions

### ADR-01: Redis sorted-set sliding window via Lua script
- **Status**: Accepted
- **Context**: Rate limiting requires atomic read-modify-write; non-atomic approaches (GET + INCR) have race conditions under concurrent load.
- **Decision**: Use a Lua script executing ZREMRANGEBYSCORE + ZCARD + ZADD + PEXPIRE atomically via `redis.eval()` / `register_script()`. This is the canonical sliding-window pattern confirmed across redis-py docs, IETF draft-ietf-httpapi-ratelimit-headers, and multiple Redis rate limiting reference implementations.
- **Alternatives considered**:
  - Token bucket via INCR+EXPIRE: simpler but allows burst spikes at window boundaries — rejected for fairness
  - Fixed window (INCR+EXPIRE per minute): race condition at window reset allows 2x burst — rejected
  - Server-side counter without Redis: doesn't work across multiple API worker processes — rejected
- **Consequences**: Lua script must be registered with `register_script()` at service init; redis-py handles NOSCRIPT errors automatically via EVALSHA to EVAL fallback.
- **Confidence**: HIGH

### ADR-02: Fail-open on Redis unavailability
- **Status**: Accepted
- **Context**: Redis outages should not take down the API. Rate limiting is a traffic-shaping concern, not a hard security gate.
- **Decision**: Catch `(redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, OSError)` in the middleware and return `allow=True`. OSError is required due to a known redis-py async bug where socket errors surface as OSError rather than ConnectionError.
- **Alternatives considered**:
  - Fail-closed (return 503 on Redis down): safer against abuse but causes full API outage during Redis restarts — rejected
- **Consequences**: During Redis outages, rate limits are not enforced. This is acceptable as Redis restarts are typically short-lived.
- **Confidence**: HIGH

### ADR-03: @app.middleware("http") decorator (not add_middleware)
- **Status**: Accepted
- **Context**: Existing `add_request_id` uses `@app.middleware("http")` pattern. Starlette's `add_middleware` is LIFO for class-based middleware; decorator middleware runs in declaration order.
- **Decision**: Implement `rate_limit_middleware` as a decorator middleware. Define it AFTER `add_request_id` in `create_app()` so that `add_request_id` runs first (outer), ensuring `X-Request-ID` is set before the rate limiter can return a 429.
- **Alternatives considered**:
  - Class-based middleware via `add_middleware`: would require inverting the declaration order logic — rejected for consistency
- **Consequences**: Ordering of middleware decorators in `create_app()` is significant and must be documented.
- **Confidence**: HIGH

### ADR-04: Redis connection pool on app.state
- **Status**: Accepted
- **Context**: Existing `from_url()` call in events doesn't configure pool parameters. Rate limiting middleware needs controlled connection management.
- **Decision**: Create `ConnectionPool.from_url(settings.redis_url, max_connections=20, socket_timeout=1.0, health_check_interval=30)` in `lifespan()`, store a `Redis` client as `app.state.redis`.
- **Alternatives considered**:
  - New connection per request: too expensive — rejected
  - Reuse existing ARQ pool: ARQ manages its own pool lifecycle, coupling would be fragile — rejected
- **Consequences**: Pool must be closed in lifespan shutdown.
- **Confidence**: HIGH

### ADR-05: ClientConfig in app/models.py
- **Status**: Accepted
- **Context**: Need per-client configuration (custom RPM). Existing model conventions use `Base`, `_uuid()`, `_utcnow()`.
- **Decision**: Add `ClientConfig` table to `app/models.py` after existing models. `create_all` picks it up automatically. No Alembic migration needed for greenfield.
- **Alternatives considered**:
  - YAML config file for client limits: no DB required but no runtime updates — rejected for extensibility
- **Consequences**: No expand-contract needed — additive table only, no existing data affected.
- **Confidence**: HIGH

### ADR-06: Settings fields for rate limiting
- **Status**: Accepted
- **Context**: Limits must be configurable via env without code changes.
- **Decision**: Add `rate_limit_default_rpm: int = 60`, `rate_limit_window_seconds: int = 60`, `rate_limit_enabled: bool = True` to `Settings`. `rate_limit_enabled=False` disables the feature globally.
- **Alternatives considered**:
  - Hardcoded defaults: no env override path — rejected
- **Consequences**: Three new env vars; existing deployments get sensible defaults.
- **Confidence**: HIGH

### ADR-07: Redis cache for ClientConfig lookups
- **Status**: Accepted
- **Context**: Rate limit middleware runs on every request; a DB round-trip per request is too expensive.
- **Decision**: Cache `ClientConfig` rows in Redis for 300 seconds with key `client_cfg:{sha256[:16]}` (first 16 hex chars of SHA-256 of API key). Serialize as JSON.
- **Alternatives considered**:
  - In-memory LRU cache: doesn't survive process restarts or work across multiple workers — rejected
  - No cache (DB every request): violates REQ-NF01 at scale — rejected
- **Consequences**: Config changes take up to 300 seconds to propagate. Acceptable for this use case.
- **Confidence**: HIGH

---

## 5. Interface Contracts

### API Contracts

No new HTTP endpoints. Rate limiting is transparent middleware. Response header contract:

```
# Headers added to all non-exempt responses (200, 429, etc.)
X-RateLimit-Limit: {int}        # requests allowed per window
X-RateLimit-Remaining: {int}    # requests remaining in current window (0 on 429)
X-RateLimit-Reset: {int}        # Unix timestamp when window resets

# Added only on 429
Retry-After: {int}              # seconds until window resets

# 429 response body
{"error": "rate limit exceeded"}
```

### Data Models (Schema Changes)

```python
# app/models.py — add after WorkflowStep, before "# Database setup"
class ClientConfig(Base):
    __tablename__ = "client_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    api_key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    rpm: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
```

### Service Interface

```python
# app/services/rate_limiter.py

LUA_SCRIPT: str  # Sorted-set sliding window Lua script

class RateLimiterService:
    def __init__(self, redis_client: Redis) -> None: ...

    async def check(
        self,
        api_key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """
        Returns (allowed, remaining, reset_ts).
        remaining = limit - current_count (clamped to 0).
        reset_ts = Unix timestamp when oldest request in window expires.
        Raises nothing — caller handles exceptions.
        """
        ...

    async def get_client_config(
        self,
        api_key: str,
        db_session: AsyncSession,
    ) -> int:
        """
        Returns rpm for the given api_key.
        Checks Redis cache first (key: client_cfg:{sha256[:16]}).
        Falls back to DB query on cache miss.
        Returns settings.rate_limit_default_rpm if no ClientConfig row exists.
        """
        ...
```

### External Service Contracts

| Service | Operation | Input | Output | Error Cases |
|---------|-----------|-------|--------|-------------|
| Redis | Lua sorted-set eval | key, now_ms, window_ms, limit | [current_count, oldest_ts_ms] | ConnectionError, TimeoutError, OSError — fail-open |
| Redis | GET/SETEX (cache) | client_cfg:{prefix} | JSON string or None | ConnectionError — fall back to DB |
| PostgreSQL | SELECT ClientConfig | api_key_prefix | ClientConfig row or None | Propagate; middleware catches all exceptions |

---

## 6. Task Waves

> Each task description is **fully self-contained** — an agent can execute it without reading any other part of this spec.

### Wave 1 — Foundation (parallel)

**Quality gate to enter Wave 1**: None

---

#### Task 1
```json
{
  "subject": "Add ClientConfig model to app/models.py",
  "description": "Context: The rate limiting feature needs a database table to store per-client RPM overrides. This task adds the ClientConfig SQLAlchemy model to the existing models file using the same conventions as Workflow/WorkflowRun/WorkflowStep. File to modify: /Users/cave/Projects/ai-workflow-api/app/models.py, line ~79 (after WorkflowStep class, before the '# Database setup' comment). Interface contract: class ClientConfig(Base) with __tablename__='client_configs'; fields: id String(36) primary_key default=_uuid, api_key_prefix String(16) nullable=False unique=True index=True, rpm Integer nullable=False default=60, notes Text nullable=True, created_at DateTime(timezone=True) default=_utcnow, updated_at DateTime(timezone=True) default=_utcnow onupdate=_utcnow. Implementation: (1) Open app/models.py. (2) Insert ClientConfig class after WorkflowStep and before the '# Database setup' comment. (3) Use existing _uuid and _utcnow helpers. (4) Integer import is already present. Edge cases: Do not add relationship back-refs. Do not add Alembic migration — create_all handles greenfield. Success criteria: Running python -c 'from app.models import ClientConfig; print(ClientConfig.__tablename__)' prints client_configs. Test command: pytest tests/ -x --tb=short -q. Scope: /Users/cave/Projects/ai-workflow-api/app/models.py only. Forbidden: Do not modify any existing model class. Do not create an Alembic migration. Do not add foreign keys from other models to ClientConfig. Dependencies: none.",
  "activeForm": "Adding database model mapping",
  "blockedBy": []
}
```

#### Task 2
```json
{
  "subject": "Add rate limit settings to app/config.py",
  "description": "Context: Rate limiting needs three configurable parameters that operators can set via environment variables. This task adds them to the existing Settings class. File to modify: /Users/cave/Projects/ai-workflow-api/app/config.py. Interface contract: Add to Settings class — rate_limit_default_rpm: int = 60 (requests per window for clients with no ClientConfig row), rate_limit_window_seconds: int = 60 (sliding window duration), rate_limit_enabled: bool = True (global kill-switch; False disables all rate limiting). Implementation: (1) Open app/config.py. (2) After the '# Worker' section (job_timeout_seconds field), add a '# Rate limiting' comment and the three new fields. (3) No validator needed — pydantic-settings handles int/bool parsing from env vars automatically. Edge cases: rate_limit_enabled=False must disable the middleware entirely. Success criteria: Running python -c 'from app.config import settings; print(settings.rate_limit_default_rpm, settings.rate_limit_window_seconds, settings.rate_limit_enabled)' prints 60 60 True. Test command: pytest tests/ -x --tb=short -q. Scope: /Users/cave/Projects/ai-workflow-api/app/config.py only. Forbidden: Do not modify existing fields. Do not add validators unless required. Dependencies: none.",
  "activeForm": "Configuring rate limiting",
  "blockedBy": []
}
```

#### Task 3
```json
{
  "subject": "Create RateLimiterService in app/services/rate_limiter.py",
  "description": "Context: This is the core rate limiting logic: a Lua sliding-window script and the service class that wraps it. File to create: /Users/cave/Projects/ai-workflow-api/app/services/rate_limiter.py. Interface contract: (A) Module-level constant LUA_SCRIPT: str containing a Lua script that takes KEYS[1] as the sorted-set key and ARGV[1] as now_ms, ARGV[2] as window_ms, ARGV[3] as limit — executes ZREMRANGEBYSCORE to remove expired entries, ZCARD to get current count, if count < limit then ZADD with score=now_ms and PEXPIRE key window_ms, returns table {count, oldest_score_ms}. (B) class RateLimiterService with __init__(self, redis_client) storing self._redis and registering: self._script = redis_client.register_script(LUA_SCRIPT). (C) async check(self, api_key, limit, window_seconds) -> tuple[bool, int, int]: builds key='rate:{sha256(api_key)[:16]}', calls self._script(keys=[key], args=[now_ms_str, window_ms_str, str(limit)]), returns (count <= limit, max(0, limit - count), reset_ts_unix). (D) async get_client_config(self, api_key, db_session) -> int: computes prefix = hashlib.sha256(api_key.encode()).hexdigest()[:16], checks redis GET 'client_cfg:{prefix}', on hit returns json.loads(cached)['rpm'], on miss queries DB for ClientConfig where api_key_prefix=prefix, caches result as JSON for 300s with SETEX, returns rpm or settings.rate_limit_default_rpm. Implementation steps: (1) Create the file. (2) Imports: hashlib, json, time, redis.asyncio as aioredis, sqlalchemy.ext.asyncio.AsyncSession, sqlalchemy.future.select, app.config.settings, app.models.ClientConfig. (3) Write LUA_SCRIPT constant. (4) Implement RateLimiterService. Edge cases: get_client_config must handle ConnectionError and TimeoutError when reading cache and fall back to DB. check() raises no exceptions. Success criteria: Running python -c 'from app.services.rate_limiter import RateLimiterService, LUA_SCRIPT; print(len(LUA_SCRIPT) > 50)' prints True. Test command: pytest tests/test_rate_limiter.py -x --tb=short -q. Scope: /Users/cave/Projects/ai-workflow-api/app/services/rate_limiter.py only. Forbidden: Do not import from app.main (circular). Do not use synchronous redis-py. Do not add HTTP routes. Dependencies: none.",
  "activeForm": "Building rate limiter scaffolding",
  "blockedBy": []
}
```

**Quality gate to exit Wave 1**:
- [ ] `python -c "from app.models import ClientConfig; from app.config import settings; from app.services.rate_limiter import RateLimiterService"` exits 0
- [ ] `python -c "from app.config import settings; assert settings.rate_limit_default_rpm == 60"` exits 0
- [ ] `pytest tests/ -x --tb=short -q` passes (existing tests unaffected)

---

### Wave 2 — Core Integration (depends on Wave 1)

**Quality gate to enter Wave 2**: Wave 1 quality gate passes

---

#### Task 4
```json
{
  "subject": "Extend lifespan() with Redis pool in app/main.py",
  "description": "Context: The rate limit middleware needs a shared Redis connection pool stored on app.state. The existing lifespan() function only initialises the database. Depends on: Task 2 output (settings.redis_url from app/config.py), Task 3 output (app/services/rate_limiter.py exists). File to modify: /Users/cave/Projects/ai-workflow-api/app/main.py, lifespan() function (lines 28-37). Interface contract: On startup — create pool = ConnectionPool.from_url(settings.redis_url, max_connections=20, socket_timeout=1.0, health_check_interval=30); create app.state.redis = Redis(connection_pool=pool); log 'Redis pool initialised'. On shutdown — await app.state.redis.aclose(). Implementation: (1) Add imports at top: from redis.asyncio import Redis, ConnectionPool. (2) In lifespan(), after await init_db(), add pool creation and app.state.redis assignment before yield. (3) After yield in shutdown, add await app.state.redis.aclose(). Edge cases: If Redis is unavailable at startup, log a warning but do NOT raise — rate limiting will fail-open. Success criteria: Running python -c 'import asyncio; from app.main import app; print(hasattr(app, \"state\"))' prints True. The app starts without error when Redis is down. Test command: pytest tests/ -x --tb=short -q. Scope: /Users/cave/Projects/ai-workflow-api/app/main.py lifespan() function only. Forbidden: Do not modify create_app(). Do not modify existing middleware. Do not raise on Redis connection failure at startup. Dependencies: Task 2, Task 3.",
  "activeForm": "Extending lifespan Redis pooling",
  "blockedBy": ["1", "2", "3"]
}
```

#### Task 5
```json
{
  "subject": "Add rate_limit_middleware to create_app() in app/main.py",
  "description": "Context: The rate limiting middleware is the main integration point. It must be declared AFTER add_request_id so that add_request_id runs as the outer wrapper, giving 429 responses an X-Request-ID header. Covers AC-01, AC-02, AC-03, AC-04, AC-05, AC-06, AC-07, AC-08. Depends on: Task 3 output (RateLimiterService), Task 4 output (app.state.redis). File to modify: /Users/cave/Projects/ai-workflow-api/app/main.py, create_app() function. Interface contract: Define @app.middleware('http') async def rate_limit_middleware(request, call_next) AFTER the add_request_id middleware. Logic: (1) If not settings.rate_limit_enabled: return await call_next(request). (2) Check exempt paths: if request.url.path in set containing /health, /docs, /redoc, /openapi.json, or path starts with /demo, return await call_next(request). (3) api_key = request.headers.get('X-API-Key', ''). If not api_key: return await call_next(request). (4) Try: create RateLimiterService(request.app.state.redis); use async_session() context to get rpm = await limiter.get_client_config(api_key, db); (allowed, remaining, reset_ts) = await limiter.check(api_key, rpm, settings.rate_limit_window_seconds). Except (ConnectionError, TimeoutError, OSError): set allowed=True, remaining=rpm, reset_ts = int(time.time()) + settings.rate_limit_window_seconds. (5) If not allowed: return JSONResponse({'error': 'rate limit exceeded'}, status_code=429, headers with Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining=0, X-RateLimit-Reset). (6) response = await call_next(request); set X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset on response.headers; return response. Implementation: Add imports (time, RateLimiterService, async_session, redis exceptions). Edge cases: OSError in except clause. JSONResponse for 429 not call_next. Headers on both 200 and 429. Success criteria: pytest tests/test_rate_limiter.py -x --tb=short -q passes. Test command: pytest tests/test_rate_limiter.py -x --tb=short -q. Scope: /Users/cave/Projects/ai-workflow-api/app/main.py, rate_limit_middleware function only. Forbidden: Do not modify add_request_id middleware. Do not modify existing route handlers. Do not add new routes. Dependencies: Task 3, Task 4.",
  "activeForm": "Implementing middleware filtering",
  "blockedBy": ["3", "4"]
}
```

#### Task 6
```json
{
  "subject": "Harden get_client_config cache fallback in rate_limiter.py",
  "description": "Context: The Redis cache for ClientConfig lookups (300s TTL, key client_cfg:{prefix}) was scaffolded in Task 3. This task reviews and hardens the implementation — verifying error handling on cache miss, DB fallback, and negative caching when no row found. Depends on: Task 3 output at /Users/cave/Projects/ai-workflow-api/app/services/rate_limiter.py. File to modify: /Users/cave/Projects/ai-workflow-api/app/services/rate_limiter.py, get_client_config() method. Interface contract: (1) prefix = hashlib.sha256(api_key.encode()).hexdigest()[:16]. (2) Try redis GET client_cfg:{prefix}; if hit: return json.loads(val)['rpm']. (3) On cache GET exception: fall through to DB. (4) DB query: SELECT * FROM client_configs WHERE api_key_prefix = prefix LIMIT 1 using sqlalchemy.future.select with await db.execute(). (5) rpm = row.rpm if row else settings.rate_limit_default_rpm. (6) Cache result as JSON {'rpm': rpm} with SETEX 300. (7) On cache SET exception: log warning, do not raise. (8) Return rpm. Edge cases: API key not in DB returns default 60 rpm. Redis cache SET failure must not prevent the response. Success criteria: pytest tests/test_rate_limiter.py::test_ac03_per_client_config tests/test_rate_limiter.py::test_cache_miss_falls_back_to_db -v passes. Test command: pytest tests/test_rate_limiter.py -x --tb=short -q. Scope: /Users/cave/Projects/ai-workflow-api/app/services/rate_limiter.py, get_client_config() method only. Forbidden: Do not change the method signature. Do not add synchronous database calls. Dependencies: Task 3.",
  "activeForm": "Hardening cache layer caching",
  "blockedBy": ["3"]
}
```

**Quality gate to exit Wave 2**:
- [ ] `python -c "from app.main import app"` exits 0
- [ ] `pytest tests/ -x --tb=short -q` — all existing tests pass (no regressions)
- [ ] `python -c "from app.services.rate_limiter import RateLimiterService; from app.models import ClientConfig; print('ok')"` exits 0

---

### Wave 3 — Tests (depends on Wave 2)

**Quality gate to enter Wave 3**: Wave 2 quality gate passes

---

#### Task 7
```json
{
  "subject": "Write unit tests for RateLimiterService",
  "description": "Context: RateLimiterService needs unit tests covering the Lua script mock, fail-open, NOSCRIPT fallback, and cache behaviour. Tests run in isolation with no real Redis. Depends on: Task 3 output at /Users/cave/Projects/ai-workflow-api/app/services/rate_limiter.py; Task 9 output for mock_redis fixture in conftest.py. File to create: /Users/cave/Projects/ai-workflow-api/tests/test_rate_limiter.py (unit test section). Interface contract: Use AsyncMock for redis client. Test functions: test_check_returns_allow_when_under_limit (mock script returns [1, now_ms]); test_check_returns_deny_when_over_limit (mock script returns [61, now_ms]); test_check_fail_open_on_connection_error (mock script raises ConnectionError); test_check_remaining_clamped_to_zero (count > limit, remaining must be 0 not negative); test_get_client_config_returns_cached_rpm (mock redis.get returns JSON); test_get_client_config_db_fallback_on_cache_miss (mock redis.get returns None, mock db returns ClientConfig with rpm=120); test_cache_miss_falls_back_to_db (same pattern for AC-03 coverage). Implementation: (1) Import pytest, pytest_asyncio, AsyncMock, MagicMock from unittest.mock. (2) Import RateLimiterService from app.services.rate_limiter. (3) Write each test as async def with inline AsyncMock setup. (4) Assert return values: allowed bool, remaining int >= 0, reset_ts positive Unix timestamp. Edge cases: remaining must never be negative. reset_ts must be a positive int. Success criteria: All 7 unit tests pass and coverage for rate_limiter.py exceeds 80 percent. Test command: pytest tests/test_rate_limiter.py -k 'unit or cache or check' -v. Scope: /Users/cave/Projects/ai-workflow-api/tests/test_rate_limiter.py (unit test section). Forbidden: Do not start a real Redis process. Do not use time.sleep in tests. Do not import app.main in this test module. Dependencies: Task 3, Task 9.",
  "activeForm": "Writing unit test covering",
  "blockedBy": ["3", "6", "9"]
}
```

#### Task 8
```json
{
  "subject": "Write integration tests for rate limit middleware",
  "description": "Context: Middleware integration tests use the httpx AsyncClient fixture and mock app.state.redis to verify AC-01 through AC-08. Depends on: Task 5 output (middleware in app/main.py), Task 9 output (mock_redis fixture in conftest.py). File to modify: /Users/cave/Projects/ai-workflow-api/tests/test_rate_limiter.py (add integration test section). Interface contract: Tests use the existing client fixture from conftest.py and override app.state.redis with mock_redis. Required tests: test_ac01_allow_below_limit (AC-01 verification: response not 429, X-RateLimit-Limit header present); test_ac02_reject_over_limit (AC-02 verification: status 429, Retry-After present); test_ac03_per_client_config (AC-03 verification: premium client not blocked at request 61); test_ac04_fail_open (AC-04 verification: no 429 when ConnectionError); test_ac05_exempt_paths parametrize over /health /docs /redoc /openapi.json /demo/run (AC-05 verification: no rate-limit headers); test_ac06_dev_mode_bypass (AC-06 verification: no headers when api_key setting empty); test_ac07_headers_on_200 (AC-07 verification: all three X-RateLimit headers on 200); test_ac08_request_id_on_429 (AC-08 verification: X-Request-ID present on 429). Implementation: (1) For each test, monkeypatch or set app.state.redis to a mock simulating under/over limit or error. (2) Set X-API-Key header on requests that need it. (3) Assert response.status_code and response.headers. (4) For AC-05 confirm rate-limit headers absent. (5) For AC-06 use monkeypatch to set settings.api_key='' temporarily. Edge cases: AC-05 must test at least 3 exempt paths. AC-08 confirms both X-Request-ID header presence and 429 status. Success criteria: All 8 AC integration tests pass. Test command: pytest tests/test_rate_limiter.py -k 'ac0' -v. Scope: /Users/cave/Projects/ai-workflow-api/tests/test_rate_limiter.py (integration test section). Forbidden: Do not make real HTTP calls to external services. Do not modify conftest.py in this task. Dependencies: Task 5, Task 9.",
  "activeForm": "Writing integration testing",
  "blockedBy": ["5", "9"]
}
```

#### Task 9
```json
{
  "subject": "Add mock_redis fixture to tests/conftest.py",
  "description": "Context: No Redis fixture exists in conftest.py. All rate limiter tests need an AsyncMock redis client configurable per-test. This task adds mock_redis and rate_limiter_client fixtures to conftest.py. Depends on: Task 5 output (app.state.redis used by middleware in app/main.py). File to modify: /Users/cave/Projects/ai-workflow-api/tests/conftest.py. Interface contract: (A) @pytest_asyncio.fixture async def mock_redis() — creates AsyncMock() with attributes: .get = AsyncMock(return_value=None), .setex = AsyncMock(return_value=True), .register_script returning a callable AsyncMock that returns [0, int(time.time()*1000)] by default. (B) @pytest_asyncio.fixture async def rate_limiter_client(db_session, mock_redis) — same as existing client fixture but also sets app.state.redis = mock_redis before yielding and restores after. Import app from app.main at fixture body level not module level to avoid circular import issues. Implementation: (1) Add imports: from unittest.mock import AsyncMock, MagicMock; import time. (2) Add mock_redis fixture. (3) Add rate_limiter_client fixture wrapping existing client fixture pattern and injecting mock_redis into app.state.redis. Edge cases: mock_redis.register_script must return a callable that behaves as a coroutine (AsyncMock callable). The fixture must restore app.state.redis after the test to avoid state leakage. Success criteria: pytest tests/conftest.py --collect-only shows mock_redis and rate_limiter_client fixtures without error. Test command: pytest tests/ -x --tb=short -q. Scope: /Users/cave/Projects/ai-workflow-api/tests/conftest.py only. Forbidden: Do not start a real Redis server. Do not modify existing db_engine, db_session, or client fixtures. Do not add non-fixture code. Dependencies: none.",
  "activeForm": "Adding Redis fixture scaffolding",
  "blockedBy": []
}
```

**Quality gate to exit Wave 3**:
- [ ] `pytest tests/test_rate_limiter.py -v` — all tests pass
- [ ] `pytest tests/ -x --tb=short -q` — full suite passes (no regressions)
- [ ] AC-01 through AC-08 each have at least one PASSED test

---

### Wave 4 — Verification (final)

**Quality gate to enter Wave 4**: All prior waves complete and gates pass

---

#### Task 10
```json
{
  "subject": "Verify all acceptance criteria pass end-to-end",
  "description": "Context: Final verification wave. Run each AC verification command and confirm output. AC-01 verification: run pytest tests/test_rate_limiter.py::test_ac01_allow_below_limit -v and confirm PASSED, response not 429, X-RateLimit-Limit header present. AC-02 verification: run pytest tests/test_rate_limiter.py::test_ac02_reject_over_limit -v and confirm PASSED, status 429, Retry-After header positive. AC-03 verification: run pytest tests/test_rate_limiter.py::test_ac03_per_client_config -v and confirm PASSED, premium client not rate-limited at request 61. AC-04 verification: run pytest tests/test_rate_limiter.py::test_ac04_fail_open -v and confirm PASSED, no 429 when Redis raises ConnectionError. AC-05 verification: run pytest tests/test_rate_limiter.py::test_ac05_exempt_paths -v and confirm PASSED, all exempt paths return non-429. AC-06 verification: run pytest tests/test_rate_limiter.py::test_ac06_dev_mode_bypass -v and confirm PASSED, no rate-limit headers when api_key setting empty. AC-07 verification: run pytest tests/test_rate_limiter.py::test_ac07_headers_on_200 -v and confirm PASSED, all three X-RateLimit headers present on 200. AC-08 verification: run pytest tests/test_rate_limiter.py::test_ac08_request_id_on_429 -v and confirm PASSED, X-Request-ID present on 429. Full suite: run pytest tests/ -x --tb=short -q and confirm all 148 or more tests pass. Self-audit: After running all AC commands, review each acceptance criterion against the actual implementation — (1) confirm rate_limit_middleware in app/main.py addresses REQ-F01 through REQ-F08; (2) confirm interface contracts in Section 5 match actual function signatures in app/services/rate_limiter.py; (3) confirm no regression in existing test count (was 148, must be >= 148); (4) confirm Section 7 Layer column is present in this spec; (5) confirm Section 9 references expand-contract as not applicable. List any discrepancies found. Rollback if any AC fails: run git revert HEAD~N where N equals number of commits made during this feature; run pytest tests/ to confirm regression-free rollback. Report: list each AC as PASS or FAIL with evidence from test output. Scope: Read-only verification — do not modify implementation files during this task unless a critical blocking bug is found. Forbidden: Do not skip failing tests. Do not patch tests to force pass. Do not modify Section 7 or Section 9 of the spec. Dependencies: Task 7, Task 8, Task 9.",
  "activeForm": "Verifying acceptance criteria",
  "blockedBy": ["7", "8", "9"]
}
```

---

## 7. Verification Plan

| AC | Layer | Verification Method | Command | Pass Criteria |
|----|-------|---------------------|---------|---------------|
| AC-01 | 2 (Conformance) | Integration test | `pytest tests/test_rate_limiter.py::test_ac01_allow_below_limit -v` | Exit 0; status not 429; X-RateLimit-Limit present |
| AC-02 | 2 (Conformance) | Integration test | `pytest tests/test_rate_limiter.py::test_ac02_reject_over_limit -v` | Exit 0; status = 429; Retry-After > 0 |
| AC-03 | 1 (Semantic) | Integration test | `pytest tests/test_rate_limiter.py::test_ac03_per_client_config -v` | Exit 0; premium client not blocked at 61 req |
| AC-04 | 1 (Semantic) | Unit test | `pytest tests/test_rate_limiter.py::test_ac04_fail_open -v` | Exit 0; no 429 on ConnectionError |
| AC-05 | 0 (Structural) | Integration test | `pytest tests/test_rate_limiter.py::test_ac05_exempt_paths -v` | Exit 0; no X-RateLimit headers on exempt paths |
| AC-06 | 1 (Semantic) | Integration test | `pytest tests/test_rate_limiter.py::test_ac06_dev_mode_bypass -v` | Exit 0; no rate-limit headers when dev mode |
| AC-07 | 2 (Conformance) | Integration test | `pytest tests/test_rate_limiter.py::test_ac07_headers_on_200 -v` | Exit 0; all three X-RateLimit headers on 200 |
| AC-08 | 2 (Conformance) | Integration test | `pytest tests/test_rate_limiter.py::test_ac08_request_id_on_429 -v` | Exit 0; X-Request-ID present on 429 |

> Layer 0 = Structural (files exist, imports, types); Layer 1 = Semantic (unit tests, coverage); Layer 2 = Conformance (integration, AC end-to-end). See `references/quality-gates.md`.

Full test suite: `pytest tests/ -x --tb=short`

---

## 8. Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Redis unavailable at deploy time | M | M | Fail-open logic (ADR-02); startup does not raise on Redis down |
| Lua script NOSCRIPT error on Redis restart | L | M | register_script() handles EVALSHA to EVAL fallback automatically |
| Middleware ordering breaks X-Request-ID on 429 | M | L | ADR-03 specifies declaration order; AC-08 tests this explicitly |
| Per-request DB hit if cache bypassed | L | H | 300s Redis cache (ADR-07); cache miss path has DB query with index on api_key_prefix |
| OSError not caught in fail-open | M | H | Catch (ConnectionError, TimeoutError, OSError) explicitly per redis-py async known issue |
| Rate limit config change latency (300s cache TTL) | L | L | Acceptable per ADR-07; operators can flush Redis key manually |

---

## 9. Rollback & Recovery Plan

### Expand-Contract Assessment
**Not applicable for this spec — additive table only.** The `client_configs` table is new and has no foreign keys from existing tables. `create_all` handles creation automatically. No existing rows, columns, or enums are modified. The expand-contract migration strategy (add nullable column first, backfill, then add constraint) would apply if we were adding a nullable column to `workflows` or `workflow_runs`, but is not required for a wholly new table.

### Per-Wave Rollback

**Wave 1 rollback**:
```bash
git checkout HEAD -- app/services/rate_limiter.py
git checkout HEAD -- app/models.py app/config.py
```

**Wave 2 rollback**:
```bash
git revert <wave2-commit-hash>
# Or per-file:
git checkout HEAD -- app/main.py
```

**Wave 3 rollback**:
```bash
git checkout HEAD -- tests/conftest.py tests/test_rate_limiter.py
```

**Full rollback**:
```bash
git revert <first-wave1-commit>..<last-wave3-commit>
pytest tests/ -x --tb=short  # confirm 148 tests pass, no regressions
```

### Recovery Scenarios
- **Redis pool creation fails at startup**: App starts anyway (fail-open); rate limiting logs a warning on first request; no traffic impact
- **ClientConfig table missing after rollback**: Drop via `DROP TABLE IF EXISTS client_configs;` in psql — additive only
- **Middleware causes unexpected 429s**: Set `RATE_LIMIT_ENABLED=false` env var and restart — disables feature globally per REQ-F07

### Rollback Triggers
- Any existing test regresses to FAIL
- p99 API latency increases more than 5ms
- Redis connection pool exhausted in production logs

---

## 10. Agent Team Composition

| Role | Agent Type | Specialization | Assigned Waves |
|------|------------|----------------|----------------|
| Foundation Builder | `general-purpose` | SQLAlchemy models, pydantic settings | Wave 1 (Tasks 1, 2) |
| Service Author | `general-purpose` | Redis, Lua scripting, async Python | Wave 1 (Task 3) |
| Integration Author | `general-purpose` | FastAPI middleware, lifespan, dependency injection | Wave 2 (Tasks 4, 5, 6) |
| Test Author | `general-purpose` | pytest-asyncio, AsyncMock, httpx | Wave 3 (Tasks 7, 8, 9) |
| Verifier | `general-purpose` | End-to-end AC verification, self-audit | Wave 4 (Task 10) |

**Recommended swarm config**:
- Team size: 5 agents
- Parallelism: Wave 1 (3 tasks parallel), Wave 2 (Tasks 4+5 sequential, Task 6 parallel with 5), Wave 3 (3 tasks parallel after Wave 2)
- Coordination: Shared interface contracts in Section 5; no direct agent-to-agent communication needed
- Estimated waves: 4, total tasks: 10

---

## 11. Research Synthesis

### Agreements (HIGH confidence)
1. **Sorted-set sliding window Lua script is the canonical Redis rate limiting approach** — Sources: redis-py docs, IETF draft-ietf-httpapi-ratelimit-headers, Redis Labs reference implementation — Confidence: HIGH
2. **register_script() handles NOSCRIPT automatically** — no manual SHA management needed — Sources: redis-py official docs, redis-py GitHub examples — Confidence: HIGH
3. **Fail-open is the correct default for infrastructure-layer rate limiting** — Sources: Stripe API design, IETF draft, distributed systems best practices — Confidence: HIGH
4. **OSError must be included in the exception catch** — known redis-py async bug where socket errors surface as OSError — Sources: redis-py issue tracker, FastAPI Redis integration guides — Confidence: HIGH
5. **Rate-limit response headers should appear on ALL responses** — IETF best practice for client self-throttling — Sources: IETF draft-ietf-httpapi-ratelimit-headers-07 — Confidence: HIGH
6. **Middleware ordering with Starlette decorators is declaration-order (not LIFO)** — class-based add_middleware is LIFO; @app.middleware("http") decorators execute in definition order — Sources: Starlette source, FastAPI docs — Confidence: HIGH

### Conflicts (resolution required)
1. **Cache TTL for ClientConfig** — Some sources recommend shorter TTLs (60s); project plan specified 300s — Resolution: 300s acceptable; config changes are rare; Redis key can be manually flushed — Confidence: MEDIUM

### Gaps
1. **Exact Lua script error handling on ZADD when key already exists** — Impact: low — Blocking: NO — Fallback assumption: treat count as idempotent, use ZCARD result

### Confidence Matrix

| # | Finding (abbreviated) | Confidence | Sources | Recency |
|---|----------------------|-----------|---------|---------|
| 1 | Sorted-set Lua script is canonical | HIGH | redis-py docs, IETF draft | 2024 |
| 2 | register_script() auto-NOSCRIPT | HIGH | redis-py docs | 2024 |
| 3 | Fail-open correct default | HIGH | IETF draft, Stripe | 2024 |
| 4 | OSError must be caught | HIGH | redis-py issues | 2024 |
| 5 | Headers on all responses | HIGH | IETF draft | 2024 |
| 6 | Decorator middleware order | HIGH | Starlette source | 2024 |
| 7 | 300s cache TTL | MEDIUM | Plan spec only | 2026 |

### Source Inventory

| Source | Succeeded | Recency | Authority | Specificity |
|--------|-----------|---------|-----------|-------------|
| A (Repo: app/main.py, models.py, config.py) | Yes | N/A | High | High |
| B (Repo: tests/conftest.py, worker.py) | Yes | N/A | High | High |
| C (redis-py docs via WebFetch) | Yes | 2024 | High | High |
| D (IETF ratelimit-headers draft via WebFetch) | Yes | 2024 | High | Medium |
| E (Starlette middleware docs via WebFetch) | Yes | 2024 | High | High |
| F (NotebookLM) | Skipped | — | — | — |

### Research Adequacy Verdict

- Findings: 6 HIGH-confidence | Unknowns covered: 5/6 | Blocking gaps: none
- **Q1 (Lua script correctness)**: ADEQUATE — confirmed across 3 independent sources
- **Q2 (Middleware integration pattern)**: ADEQUATE — existing codebase has direct analogue (add_request_id at main.py:59)
- **Q3 (Fail-open exception types)**: ADEQUATE — redis-py async known issue documented
- **Q4 (Header standards compliance)**: ADEQUATE — IETF draft is authoritative
- **Verdict**: ADEQUATE — ready to implement

---

## Sources & Research

### Internal (file paths read during spec creation)
- `/Users/cave/Projects/ai-workflow-api/app/main.py` — middleware pattern (add_request_id), lifespan structure, create_app() flow
- `/Users/cave/Projects/ai-workflow-api/app/models.py` — Base, _uuid, _utcnow conventions; async_session factory
- `/Users/cave/Projects/ai-workflow-api/app/config.py` — Settings(BaseSettings) pattern; existing fields
- `/Users/cave/Projects/ai-workflow-api/tests/conftest.py` — existing fixtures; confirmed no Redis fixture

### External (URLs consulted)
- https://redis-py.readthedocs.io — register_script(), ConnectionPool, exception hierarchy
- https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/ — header naming convention (X-RateLimit-*, Retry-After)
- https://www.starlette.io/middleware/ — middleware decorator ordering vs add_middleware LIFO behaviour
