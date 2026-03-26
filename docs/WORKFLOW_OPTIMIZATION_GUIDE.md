# Workflow Optimization Guide

This guide covers how to replace manual, multi-step business processes with automated YAML-defined pipelines using the ai-workflow-api engine. It includes concrete before/after metrics, format reference, and deployment steps.

---

## What Workflow Optimization Means

Manual business processes typically involve:
- A human reading incoming data and deciding what to do next
- Copying information between tools (CRM, email, Slack, ticketing systems)
- Waiting for the next available person to act

Workflow automation replaces that loop with a declarative pipeline. You define the steps once in YAML. The engine executes them in order, branching on conditions, calling external APIs, and notifying the right people — without a human in the loop for each occurrence.

The result is not just speed. It is consistency: every lead scored against the same criteria, every document summarized with the same structure, every support ticket routed through the same logic.

---

## YAML Workflow Format

Each workflow is a single YAML file with the following top-level structure:

```yaml
name: lead_qualification
description: Score and route inbound leads from CRM webhook
trigger:
  type: webhook
  path: /webhooks/lead

steps:
  - id: score_lead
    type: llm
    model: claude-3-5-haiku-20241022
    prompt: |
      Score this lead on a scale 1-10 based on company size, role, and stated need.
      Return JSON: {"score": <int>, "tier": "hot|warm|cold", "reason": "<string>"}
    input_key: lead_data
    output_key: scoring_result

  - id: route_check
    type: condition
    condition: "{{ score_lead.score }} >= 7"
    if_true: notify_sales
    if_false: add_to_nurture

  - id: notify_sales
    type: notify
    channel: slack
    message: "Hot lead: {{ lead_data.company }} — Score {{ score_lead.score }}. Reason: {{ score_lead.reason }}"

  - id: add_to_nurture
    type: http
    method: POST
    url: "{{ env.CRM_BASE_URL }}/contacts/{{ lead_data.id }}/tags"
    body:
      tag: nurture_sequence
```

### Node Types

| Type | Purpose |
|------|---------|
| `trigger` | Entry point: webhook endpoint or cron schedule |
| `llm` | Calls Claude (or any configured model); returns structured or freeform text |
| `condition` | Evaluates an expression; routes to `if_true` or `if_false` step |
| `http` | Makes an outbound API call; response stored in `output_key` |
| `notify` | Sends a message to Slack channel or email address |

### Step Interpolation

Later steps reference earlier outputs via `{{ step_id.field }}` syntax. The engine resolves these at runtime using the accumulated execution context. Steps can also reference environment variables via `{{ env.VAR_NAME }}` and trigger payload fields via `{{ trigger.field }}`.

---

## Use Case 1: Lead Qualification

**Before:** Sales rep receives a CRM notification, opens the lead record, reads the company description and notes, decides on tier, manually assigns the contact to a sequence, and posts a Slack note to the account executive. Average: 8 minutes per lead.

**After:** Webhook fires on new lead creation. The workflow scores the lead in one LLM call, routes to notify step (score >= 7) or HTTP step (score < 7), and completes. Wall clock time: under 10 seconds.

**Workflow file:** `examples/lead_qualification.yaml`

Key steps in this workflow:
1. `score_lead` (llm) — structured JSON scoring with tier assignment
2. `route_check` (condition) — branches on numeric score
3. `notify_sales` (notify) — Slack message with score and reason
4. `add_to_nurture` (http) — tags contact in CRM for drip sequence
5. `log_outcome` (http) — writes result to analytics endpoint

At 200 inbound leads per week, the time savings reach approximately 26 person-hours per week.

---

## Use Case 2: Document Summarization

**Before:** Analyst receives a 30-page contract, policy document, or research report. Reads it, highlights key sections, writes a summary memo. Average: 45 minutes per document.

**After:** Document uploaded via webhook or scheduled batch trigger. The workflow extracts text, runs a structured summarization prompt requesting a 5-point summary plus key dates and obligations, and writes the output to the document management system. Wall clock time: under 2 minutes.

**Workflow file:** `examples/document_summary.yaml`

Key steps:
1. `extract_text` (http) — calls document parser endpoint, retrieves raw text
2. `summarize` (llm) — prompt requests JSON with `summary`, `key_dates`, `obligations`, `risk_flags`
3. `store_summary` (http) — writes structured output to document system via API
4. `notify_requester` (notify) — emails summary to the analyst who uploaded the file

The summary format is consistent across all documents. Analysts review a 2-minute output rather than reading for 45 minutes, and the structured JSON fields are indexed for search.

---

## Use Case 3: Support Ticket Triage

**Before:** Support agent opens the queue, reads each incoming ticket, assigns a category, determines priority, routes to the right team, and posts an acknowledgment. Average handling time for triage: 20 minutes across the queue per agent shift.

**After:** Webhook fires on ticket creation from the ticketing system. Workflow classifies the ticket (billing/technical/account/feature request), assigns priority (P1-P3), routes to the correct team queue, and sends an automated acknowledgment to the customer. Wall clock time: 30 seconds.

**Workflow file:** `examples/support_triage.yaml`

Key steps:
1. `classify_ticket` (llm) — returns `{ category, priority, escalate: bool, summary }`
2. `escalation_check` (condition) — routes P1 tickets to `page_oncall` step
3. `route_to_team` (http) — assigns ticket to team queue via ticketing API
4. `acknowledge_customer` (notify) — sends email acknowledgment with ticket ID and expected response time
5. `page_oncall` (http) — calls PagerDuty API for P1 escalations

---

## SSE Streaming

For long-running workflows (multi-step with several LLM calls), the engine sends real-time progress events to the client via Server-Sent Events.

Each step emits:
- `step_started` — step ID and type
- `step_completed` — step ID, output summary, elapsed milliseconds
- `workflow_completed` — total elapsed time, final outputs

Client-side example:

```javascript
const source = new EventSource(`/workflows/${workflowId}/stream`);
source.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`[${data.step_id}] ${data.status} — ${data.elapsed_ms}ms`);
};
```

This allows dashboards and UIs to show progress bars, step-by-step logs, or live output without polling.

---

## Conditional Branching

Condition nodes evaluate Python-compatible expressions over the execution context:

```yaml
- id: confidence_gate
  type: condition
  condition: "{{ score_lead.confidence }} >= 0.8 and {{ score_lead.tier }} == 'hot'"
  if_true: fast_track
  if_false: manual_review
```

Supported operators: comparison (`>`, `>=`, `==`, `!=`), logical (`and`, `or`, `not`), membership (`in`).

Branches can reference any prior step's output fields. The condition engine resolves all `{{ }}` interpolations before evaluating the expression.

---

## Integration Points

**Webhook triggers** accept POST payloads from any system that can send HTTP requests:
- CRM systems (HubSpot, Salesforce, GHL) on lead creation, deal stage change
- Ticketing systems (Zendesk, Jira, Linear) on ticket creation or status change
- Form tools (Typeform, Tally) on submission

**HTTP steps** make outbound calls to any REST API:
- Write back to CRM (tag contacts, update deal fields)
- Call internal microservices
- Post to analytics endpoints
- Trigger downstream workflows via webhook

**Notify steps** currently support:
- Slack (channel or DM via webhook URL)
- Email (SMTP or SendGrid)

To add a new notification channel, implement the `NotificationHandler` interface and register it in `app/handlers/notify.py`.

---

## Workflow Composition

Each step's `output_key` stores its result in the execution context. Later steps reference earlier outputs via interpolation:

```yaml
steps:
  - id: extract_entities
    type: llm
    output_key: entities

  - id: enrich_company
    type: http
    url: "https://api.clearbit.com/v2/companies/find?domain={{ entities.company_domain }}"
    output_key: enrichment

  - id: final_score
    type: llm
    prompt: |
      Given entity data: {{ entities }}
      And enrichment: {{ enrichment }}
      Produce final qualification score.
```

This chaining pattern avoids building monolithic prompts. Each step has a single responsibility and its output is independently testable.

---

## Async Processing via ARQ

Workflows submitted via POST `/workflows/run` are queued in Redis and executed by ARQ workers. The HTTP response returns immediately with a `workflow_id`. The client can:
- Poll `GET /workflows/{id}/status`
- Subscribe to SSE stream at `GET /workflows/{id}/stream`

This means a workflow with 6 LLM calls and multiple HTTP steps does not hold an HTTP connection open for 30+ seconds. The worker pool scales independently of the API tier.

Worker configuration (`.env`):

```
REDIS_URL=redis://localhost:6379
ARQ_WORKER_COUNT=4
ARQ_MAX_JOBS=100
```

---

## Existing Workflow Examples

Three complete workflow files ship with the repo:

| File | Trigger | Steps | Description |
|------|---------|-------|-------------|
| `examples/lead_qualification.yaml` | Webhook | 5 | Score, route, notify, tag |
| `examples/document_summary.yaml` | Webhook | 4 | Extract, summarize, store, notify |
| `examples/support_triage.yaml` | Webhook | 5 | Classify, escalate, route, acknowledge |

Each file is self-contained and usable as a template. Copy and modify for your use case.

---

## Adding a New Workflow

1. Create `examples/your_workflow.yaml` following the format above
2. Register any new environment variables in `.env.example`
3. Test locally: `POST /workflows/run` with a sample payload
4. Add an integration test in `tests/test_workflows/`
5. Run `pytest tests/` — all 148 tests must pass before deploying

---

## Deployment

### Docker Compose (local/staging)

```bash
docker compose up --build
```

Services started: `api` (FastAPI), `worker` (ARQ), `redis`.

### Render Blueprint (production)

The `render.yaml` blueprint defines:
- `api` service: web, auto-deploy on push to `main`
- `worker` service: background worker, same Docker image
- `redis` service: managed Redis instance

Deploy steps:
1. Push to `main`
2. Render detects blueprint, builds image, deploys both services
3. Set environment variables in Render dashboard (never commit secrets)

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `REDIS_URL` | Yes | Redis connection string |
| `SLACK_WEBHOOK_URL` | No | For notify steps targeting Slack |
| `SMTP_HOST` / `SMTP_PORT` | No | For email notify steps |

---

## Test Coverage

```
pytest tests/        # 148 passing
pytest tests/ -v     # verbose output with step-level detail
```

Test structure:
- `tests/test_engine/` — unit tests for each node type
- `tests/test_workflows/` — integration tests for the 3 example workflows
- `tests/test_api/` — HTTP endpoint tests

---

## Summary: When to Use This

Use ai-workflow-api when:
- A process runs more than 10 times per day and involves the same steps each time
- The process requires an LLM decision plus at least one system action (write to CRM, notify someone, call an API)
- You want a clear audit trail of what happened at each step
- The process involves conditional routing that today relies on a human reading and deciding

Do not use it for:
- One-off tasks that change structure frequently
- Processes where human judgment is genuinely required at each occurrence (use it to assist, not replace)
- Real-time use cases requiring sub-100ms response (SSE streaming is the right pattern there, but LLM calls add latency)
