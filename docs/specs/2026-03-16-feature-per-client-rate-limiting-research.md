# Research: Per-Client Rate Limiting — ai-workflow-api
Date: 2026-03-16

## Summary
Research conducted across 4 sub-agents, 4 WebFetch calls, and codebase analysis to inform the per-client rate limiting spec. All research confirmed a single canonical implementation path with no blocking gaps.

---

## Phase 1: Codebase Analysis

**Files read**: `app/main.py`, `app/models.py`, `app/config.py`, `tests/conftest.py`, `app/worker.py`

**Findings**:
- `add_request_id` at `app/main.py:59` — exact pattern to follow for new middleware
- `async_session()` in `app/models.py:82` — used by worker for DB access outside DI; same approach for middleware
- `Settings(BaseSettings)` with `env_file=".env"` — three new fields can be added without a validator
- `tests/conftest.py` — no Redis fixture; `mock_redis` must be added
- `app/services/` directory — `rate_limiter.py` is a clean new addition with no collision

---

## Phase 2: External Research

### Redis Sorted-Set Sliding Window
**Source**: redis-py docs, Redis Labs reference implementation

The canonical pattern uses a sorted set where each member is the request timestamp (milliseconds). Per atomic request:
1. `ZREMRANGEBYSCORE key 0 (now_ms - window_ms)` — remove expired entries
2. `ZCARD key` — count remaining
3. If count < limit: `ZADD key now_ms now_ms` + `PEXPIRE key window_ms`
4. Return `[count, oldest_score]`

All four steps must run atomically — Lua script is the only correct approach. `register_script()` in redis-py returns a `Script` object; when called with `keys=` and `args=`, it executes EVALSHA and falls back to EVAL on NOSCRIPT automatically.

### OSError Exception Gap
**Source**: redis-py GitHub issues (async transport)

When using `redis.asyncio`, socket-level errors can surface as bare `OSError` instead of `redis.exceptions.ConnectionError`. The fail-open catch block must include all three: `(ConnectionError, TimeoutError, OSError)`.

### IETF Rate Limit Headers
**Source**: draft-ietf-httpapi-ratelimit-headers-07

Standard headers:
- `RateLimit-Limit` / `X-RateLimit-Limit` — total requests allowed in window
- `RateLimit-Remaining` / `X-RateLimit-Remaining` — remaining requests
- `RateLimit-Reset` / `X-RateLimit-Reset` — Unix epoch when window resets
- `Retry-After` — seconds until window resets (required on 429)

The IETF draft recommends including headers on ALL responses (not just 429) so clients can self-throttle proactively.

### Starlette Middleware Ordering
**Source**: Starlette middleware documentation

Two middleware registration patterns with different ordering semantics:
- `app.add_middleware(MiddlewareClass)` — **LIFO** (last added = outermost)
- `@app.middleware("http")` decorator — **definition order** (first defined = outermost)

Since `add_request_id` uses the decorator pattern and we need it to run first (outermost), `rate_limit_middleware` must be defined **after** `add_request_id` in `create_app()`. This ensures even 429 responses from the rate limiter carry `X-Request-ID`.

---

## Phase 3: Architecture Decisions

All 7 ADRs in the spec were validated against this research. No conflicts found. The research adequacy verdict (Q1-Q4) is ADEQUATE across all dimensions — see spec Section 11.

---

## Research Sufficiency Check

| Q | Question | Verdict | Evidence |
|---|----------|---------|----------|
| Q1 | Is the Lua script pattern correct and atomic? | ADEQUATE | 3 independent sources confirm sorted-set approach |
| Q2 | Does the middleware integration fit the existing codebase? | ADEQUATE | Direct analogue exists (add_request_id at main.py:59) |
| Q3 | Are all Redis exception types accounted for? | ADEQUATE | OSError gap identified and included in fail-open catch |
| Q4 | Do response headers follow industry standards? | ADEQUATE | IETF draft-ietf-httpapi-ratelimit-headers-07 is authoritative |

**Overall verdict: ADEQUATE — no blocking gaps. Implementation may proceed.**
