# Spec: ai-workflow-api — Portfolio Polish

**File**: `~/Projects/ai-workflow-api/docs/specs/2026-03-19-feature-ai-workflow-api-portfolio-polish-spec.md`
**Date**: 2026-03-19
**Effort**: ~3-4h | **Risk**: Low (text + CI + LICENSE only)
**Repo**: `~/Projects/ai-workflow-api/` → `ChunkyTortoise/ai-workflow-api`
**Stack**: FastAPI/ARQ/Redis/Claude/SSE | 148 tests passing
**Differentiator**: Declarative YAML workflow engine + real-time SSE streaming

---

## Context

Unique concept: YAML-driven AI workflows with real-time SSE output. `render.yaml` and `Dockerfile` are already present — deploy-ready. Three existing specs cover rate limiting (`2026-03-16-*`). This is a new spec alongside those.

### Key Findings

- NO `LICENSE` file at repo root — critical gap for open-source credibility
- README has ASCII art — replace with mermaid
- CI has `pytest-cov` in requirements but no `--cov` flags on pytest command
- Static `tests-148 passing` badge — replace with dynamic CI-linked badge
- No "Try It Now" section with curl examples
- No inline workflow YAML showcase
- No Certifications Applied section

---

## Requirements

| REQ | Description | Effort |
|-----|-------------|--------|
| F01 | MIT LICENSE file | 5m |
| F02 | Mermaid architecture diagram | 30m |
| F03 | Add coverage to CI | 10m |
| F04 | Coverage badge | 5m |
| F05 | "Try It Now" section | 30m |
| F06 | Workflow showcase (inline YAML + SSE output) | 30m |
| F07 | Certifications Applied | 30m |
| F08 | Verify stale test count | 10m |
| F09 | Dynamic CI badge | 5m |

---

## F01 — MIT LICENSE File

Create `~/Projects/ai-workflow-api/LICENSE` at repo root:

```
MIT License

Copyright (c) 2026 Cayman Roden

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

After creating the file, update the LICENSE badge in README if it currently shows "No License" or is absent. Add/update badge:

```markdown
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
```

---

## F02 — Mermaid Architecture Diagram

Replace the existing ASCII art architecture section with a mermaid diagram.

```markdown
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
```

If the README has no `## Architecture` heading, add the section between "Features" and "Getting Started".

---

## F03 — Add Coverage to CI

**File**: `.github/workflows/ci.yml`

Find the pytest command. Currently runs without `--cov`. Add:

**Before** (find the actual line):
```yaml
run: pytest tests/ -v
```

**After**:
```yaml
run: pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=75
```

The module being tested is `app` — verify this matches the main package directory (`ls ~/Projects/ai-workflow-api/app/`). If the directory name differs, use the correct module name.

---

## F04 — Coverage Badge

Add a static coverage badge to the badge row at the top of README:

```markdown
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A575%25-brightgreen)](https://github.com/ChunkyTortoise/ai-workflow-api/actions)
```

States "≥75%" which CI now enforces via `--cov-fail-under=75`.

---

## F05 — "Try It Now" Section

Insert near the top of README, right after badges and description. Shows the API is immediately usable without auth.

```markdown
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
```

---

## F06 — Workflow Showcase

Insert after "Try It Now" or in a dedicated "How It Works" section. Sells the YAML-driven concept visually — this is the main differentiator.

Find the actual `document_summary.yaml` file (likely in `workflows/` or `examples/`):

```bash
find ~/Projects/ai-workflow-api -name "document_summary.yaml" 2>/dev/null
```

Read its contents and inline it with annotations. Template for the section:

```markdown
## YAML-Driven Workflows

Workflows are plain YAML — no code, no SDK, just declarative nodes.

**`workflows/document_summary.yaml`**

```yaml
name: document_summary
description: Summarize and classify a document using Claude
version: "1.0"

inputs:
  text:
    type: string
    required: true
    description: The document text to process

nodes:
  # Step 1: Summarize with Claude
  - id: summarizer
    type: llm
    model: claude-sonnet-4-6
    prompt: |
      Summarize the following text in 1-2 concise sentences.
      Focus on the main idea and key takeaway.

      Text: {{ inputs.text }}
    output_key: summary

  # Step 2: Classify the topic
  - id: classifier
    type: llm
    model: claude-haiku-4-5-20251001   # cheaper model for classification
    prompt: |
      Classify this summary into a category and confidence score (0-1).
      Return JSON: {"category": "...", "confidence": 0.0}

      Summary: {{ nodes.summarizer.summary }}
    output_key: classification
    parse_json: true

  # Step 3: Notify if confidence is high
  - id: notify
    type: condition
    condition: "{{ nodes.classifier.classification.confidence }} > 0.85"
    on_true:
      - id: webhook_notify
        type: notify
        url: "{{ env.WEBHOOK_URL }}"
        payload:
          summary: "{{ nodes.summarizer.summary }}"
          category: "{{ nodes.classifier.classification.category }}"

outputs:
  summary: "{{ nodes.summarizer.summary }}"
  classification: "{{ nodes.classifier.classification }}"
```

> **Key concepts**: Template variables (`{{ }}`), node chaining, conditional branching, model selection per node, JSON parsing. Add any `.yaml` to `workflows/` and it's instantly available via the API — no code changes.
```

If `document_summary.yaml` does not exist, use whichever workflow YAML file exists in the repo. If no YAML examples exist, create a minimal representative one at `workflows/document_summary.yaml` for the showcase.

---

## F07 — Certifications Applied

Insert before `## License`:

```markdown
## Certifications Applied

Domain pillars from [19 completed AI/ML certifications](https://caymanroden.com) backing this project:

| Domain | Certification | Applied In |
|--------|--------------|-----------|
| LLM Orchestration | Anthropic Building with Claude (Vanderbilt) | Multi-node LLM workflows, model selection per node |
| Async Systems & Queues | IBM DevOps and Software Engineering | ARQ worker queue, Redis job state, async job processing |
| API Design | Meta Back-End Developer (Python) | FastAPI routes, SSE streaming, OpenAPI docs |
| Workflow Engines | IBM Full Stack Developer | YAML DSL design, node executor pattern, condition branching |
| AI Pipelines | DeepLearning.AI MLOps Specialization | YAML-driven pipeline architecture, declarative AI workflows |
```

---

## F08 — Verify Stale Test Count

**Before editing README**, run:

```bash
cd ~/Projects/ai-workflow-api
pytest tests/ -q --tb=no 2>&1 | tail -5
```

Note the actual count (expected: ~148). Then locate the static badge:

```bash
grep -n "148\|passing\|tests" README.md
```

Update any stale numbers to the actual pytest count.

---

## F09 — Dynamic CI Badge

Replace the existing static `tests-148 passing` badge with a dynamic CI-linked badge that always reflects the latest CI run status.

**Find** the existing static badge (looks like):
```markdown
![Tests](https://img.shields.io/badge/tests-148%20passing-brightgreen)
```

**Replace with** the dynamic GitHub Actions badge:
```markdown
[![Tests](https://github.com/ChunkyTortoise/ai-workflow-api/actions/workflows/ci.yml/badge.svg)](https://github.com/ChunkyTortoise/ai-workflow-api/actions/workflows/ci.yml)
```

Note: verify the workflow filename is `ci.yml` by checking `.github/workflows/`. If it's named differently (e.g., `test.yml`), update the URL accordingly.

---

## Verification

```bash
cd ~/Projects/ai-workflow-api

# LICENSE exists
test -f LICENSE && echo "LICENSE: OK" || echo "LICENSE: MISSING"

# Tests pass with coverage floor
pytest tests/ -q --tb=short --cov=app --cov-fail-under=75

# README has key sections
grep -c "mermaid" README.md && echo "Mermaid: present"
grep -n "## Try It Now\|## Certifications Applied\|## Architecture\|YAML-Driven" README.md && echo "README sections: OK"

# Dynamic CI badge present
grep -n "github.com/ChunkyTortoise/ai-workflow-api/actions" README.md && echo "Dynamic CI badge: OK"

# Coverage badge present
grep -n "coverage" README.md | grep "img.shields.io" && echo "Coverage badge: OK"

# MIT License in badge row
grep -n "MIT\|License" README.md | head -5
```

All checks must pass before committing.

---

## Commit Message

```
feat: add LICENSE, mermaid diagram, coverage CI, workflow showcase

- Add MIT LICENSE (Copyright 2026 Cayman Roden)
- Replace ASCII art with mermaid architecture diagram
- Add --cov=app --cov-fail-under=75 to CI pytest command
- Add static coverage badge (≥75%)
- Add "Try It Now" section with curl examples + SSE stream output
- Add YAML workflow showcase (document_summary.yaml annotated)
- Add Certifications Applied section
- Replace static test badge with dynamic CI-linked badge
```

---

## Deferred

| Item | Why Deferred |
|------|-------------|
| Screenshots/GIF | Browser automation session needed |
| Render deploy | Render billing card required |
| Rate limiting feature | Separate spec exists (2026-03-16-feature-per-client-rate-limiting-spec.md) |
| Interactive API explorer | Low priority for demo portfolio |
