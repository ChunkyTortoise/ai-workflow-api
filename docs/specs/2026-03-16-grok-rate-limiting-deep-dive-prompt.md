# Rate Limiting Spec Research — 4-Agent Deep Dive (Grok 4.20 Prompt)

Copy-paste the block below into Grok 4.20.

---

```
# Rate Limiting Spec Research — 4-Agent Deep Dive

You are reviewing a completed per-client rate limiting specification for a FastAPI + Redis + SQLAlchemy API. The spec covers the core architecture (Lua sorted-set sliding window, fail-open middleware, per-client config via DB + Redis cache). Initial research validated the fundamentals. Your job is to go DEEPER — find refinements, edge cases, and production-hardening improvements the initial research missed.

## Current Architecture Summary

- **Stack**: FastAPI, redis.asyncio, SQLAlchemy async, PostgreSQL, ARQ worker, Render (2 services)
- **Algorithm**: Lua script on Redis sorted set — ZREMRANGEBYSCORE + ZCARD + ZADD + PEXPIRE (atomic via register_script/EVALSHA)
- **Middleware**: @app.middleware("http") decorator, declared after add_request_id for correct LIFO ordering
- **Fail-open**: catch (ConnectionError, TimeoutError, OSError), allow request on any Redis failure
- **Client config**: ClientConfig table (api_key_prefix VARCHAR(16), rpm INT), cached in Redis 300s (client_cfg:{sha256[:16]})
- **Headers**: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset on ALL responses; Retry-After on 429 only
- **Settings**: rate_limit_default_rpm=60, rate_limit_window_seconds=60, rate_limit_enabled=True (env-configurable)
- **Exempt paths**: /health, /docs, /redoc, /openapi.json, /demo*
- **Dev bypass**: No API_KEY env → no auth → no rate limiting

## What's Already Researched (DO NOT DUPLICATE)

1. Lua sorted-set is the canonical sliding-window pattern (3 sources)
2. register_script() handles NOSCRIPT automatically (redis-py docs)
3. Fail-open is correct for infrastructure-layer rate limiting (IETF, Stripe)
4. OSError must be caught due to redis-py async bug
5. IETF draft-ietf-httpapi-ratelimit-headers-07 defines the header standard
6. Starlette decorator middleware runs in definition order (not LIFO like add_middleware)
7. 300s cache TTL for ClientConfig is acceptable (manually flushable)

## Agent Assignments

### Agent 1: Production Hardening & Memory Management

Research these specific questions:
- **Sorted set memory growth**: What happens when thousands of members accumulate in a single rate-limit key under high concurrency? Does ZREMRANGEBYSCORE fully clean up, or can zombie members survive? What's the memory cost per sorted-set member in Redis 7.x?
- **PEXPIRE vs EXPIRE race**: If the Lua script sets PEXPIRE on every request, does this effectively extend the key's lifetime indefinitely? Should we use PEXPIRE only on ZADD (new member) to avoid resetting the TTL on reads?
- **Connection pool sizing**: For a Render deployment with 2 service instances (API + worker) sharing a single Redis, is max_connections=20 appropriate? What's the formula for pool size given (concurrent_requests * avg_redis_ops_per_request)?
- **Redis memory limits on Render free/starter tier**: What's the max memory? Should we add a maxmemory-policy configuration recommendation (e.g., volatile-lru)?

Deliverable: A table of findings with columns: Issue | Risk Level (H/M/L) | Recommended Change | Evidence Source

### Agent 2: Security & Abuse Resistance

Research these specific questions:
- **SHA-256[:16] collision risk**: Using only the first 16 hex chars (64 bits) of SHA-256 for the api_key_prefix. What's the birthday-problem probability of collision at 10K, 100K, 1M API keys? Is this acceptable for rate limiting (not auth)?
- **Key rotation impact**: If a client's API key is rotated, their rate limit window resets (new hash, new sorted set). Is this a concern? Could an attacker exploit key rotation to bypass rate limits?
- **Timing side-channel**: Does the Lua script execution time leak information about current request count? Is this exploitable for a rate-limiting context?
- **429 response information leakage**: Do the X-RateLimit headers reveal operational details useful to attackers (e.g., exact limit = tier identification, remaining = usage profiling)?
- **Cache poisoning**: Could a malicious request pollute the client_cfg:{prefix} Redis cache entry with a crafted payload? What validation is needed on cache read?

Deliverable: A risk matrix with columns: Attack Vector | Likelihood | Impact | Current Mitigation | Recommended Enhancement

### Agent 3: Observability, Metrics & Alerting

Research these specific questions:
- **Structured logging best practices for rate limiters**: What fields beyond request_id/api_key_prefix/limit/remaining/decision should we log? Should we log at WARN level when a client hits >80% of their limit (approaching threshold)?
- **Prometheus/StatsD metrics**: What metrics should a rate limiter export? (e.g., rate_limit_checks_total, rate_limit_rejections_total, rate_limit_redis_errors_total, rate_limit_lua_script_duration_seconds). What labels? What histogram buckets?
- **Alerting thresholds**: What conditions should trigger alerts? (e.g., sustained 429 rate >5% of traffic, Redis fail-open triggered >3 times in 5 minutes, Lua script p99 >10ms)
- **Dashboard patterns**: What's the standard Grafana/dashboard layout for rate limiting observability? (traffic heatmap by client, 429 rate over time, Redis latency overlay)
- **How do Stripe, GitHub, and Cloudflare expose rate-limit observability internally?**

Deliverable: (1) Recommended metrics list with type (counter/gauge/histogram) and labels. (2) Recommended alerting rules. (3) Any changes to the spec's REQ-NF04 logging requirement.

### Agent 4: Operational Excellence & Day-2 Operations

Research these specific questions:
- **Zero-downtime deployment**: When the rate_limit_middleware is deployed for the first time, existing in-flight requests have no app.state.redis. How does Render handle rolling deploys? Should the middleware check `hasattr(request.app.state, 'redis')` defensively?
- **Hot config reload**: The 300s cache TTL means config changes take up to 5 minutes to propagate. Should we add a `/admin/flush-rate-limit-cache` endpoint (behind admin auth) or a Redis pub/sub cache invalidation channel?
- **Feature flag granularity**: rate_limit_enabled is boolean. Should we support per-path or per-client feature flags for gradual rollout? (e.g., enable rate limiting only for /api/v1/workflows first, then expand)
- **Graceful degradation UX**: When a client hits 429, what's the best practice for the error response body? Should we include more than just {"error": "rate limit exceeded"}? (e.g., limit, reset_at, docs_url, upgrade_url)
- **Runbook**: What should a production runbook for rate limiting incidents include? (Redis down → fail-open, client complaints → check client_configs, sudden 429 spike → check for config drift)
- **Load testing**: What tool/approach for validating REQ-NF01 (2ms p99 under 500 concurrent)? Is locust, k6, or wrk most appropriate for async Python APIs?

Deliverable: (1) A prioritized list of Day-2 improvements ranked by effort vs impact. (2) Any new requirements or ACs to add to the spec. (3) Recommended load testing approach.

## Synthesis Instructions

After all 4 agents complete, synthesize their findings into a single document with:

1. **Refinement Table** — columns: ID (R6, R7, R8...), Refinement, Agent Source, Priority (P0/P1/P2), Effort (S/M/L), Spec Section Affected
2. **New Requirements** — any new REQ-F or REQ-NF items to add (EARS notation)
3. **New Acceptance Criteria** — any new ACs to add (Given/When/Then format)
4. **ADR Updates** — amendments to existing ADRs or new ADRs
5. **Conflicts Between Agents** — where agent findings disagree, note the conflict and your resolution
6. **Final Recommendation** — top 5 highest-impact refinements to incorporate, ordered by risk-reduction value

Format the output as markdown. Be specific — include code snippets, exact Redis commands, specific numbers (memory sizes, collision probabilities, metric names). Vague recommendations like "add monitoring" are not acceptable; say exactly WHAT to monitor, HOW, and at WHAT threshold.
```
