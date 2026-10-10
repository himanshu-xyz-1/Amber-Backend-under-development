# Amber System Architecture

## 1. System Overview

Amber is an Autonomous Incident Remediation & Site Reliability Engineering (SRE) Engine designed to eliminate alert fatigue and reduce Mean Time To Resolution (MTTR) by orchestrating autonomous investigation, triage, and targeted remediation. The core thesis of Amber is **"LLM proposes, deterministic policy decides."** While Large Language Models (LLMs) drive non-deterministic reasoning (analyzing logs, hypothesizing root causes, formulating remediation steps), all mutations are gated by strict, deterministic, policy-based guardrails (via static code registries, cryptographic SHA-256 payload binding, and Human-in-the-Loop approvals).

Amber acts as an intelligent overlay on top of existing observability tools, executing read-only diagnostics autonomously, and securely orchestrating remediation steps across the target infrastructure inside a private VPC.

---

## 2. High-Level Architecture Diagram

```text
                                 +------------------------------------------------+
                                 |                                                |
                                 |           AMBER EDGE FRONTEND                  |
                                 |      (React 19 + Vite + Cloudflare Workers)    |
                                 |             https://ambersre.xyz               |
                                 |                                                |
                                 +--------+------------------+--------------------+
                                          |                  | WebSocket / SSE
                                          | REST API         |
+-------------------+           +---------v------------------v---------+       +-------------------------+
| OBSERVABILITY     | Webhooks  |                                      |       |  OMNI-CHANNEL HITL      |
| PagerDuty, Sentry,+----------->        amber-backend (FastAPI :8000)  <------->  ├── Slack Block Kit    |
+-------------------+           +------------------+-------------------+       |  └── Telegram Bot       |
                                                   |                           +-------------------------+
                                +------------------v-------------------+
                                |            amber-redis               |
                                |     (Redis 7 Alpine Event Queue)     |
                                |      Streams, Dedup & Revocation     |
                                +------------------+-------------------+
                                                   | Async Stream Poll
                                +------------------v-------------------+
                                |       ALERT CORRELATION ENGINE       |
                                |    (Sliding Window Fingerprinting)   |
                                +------------------+-------------------+
                                                   | Correlated Incident
                                +------------------v-------------------+       +-------------------------+
                                |      AGENT ORCHESTRATION SERVICE     |       |   amber-postgres        |
                                |       (LangGraph State Machine)      <------->   (PostgreSQL 16 +      |
                                |                                      |       |    pgvector & BM25)     |
                                |   [Triage] -> [Hybrid RAG]           |       +-------------------------+
                                |       -> [Investigation]             |
                                |       -> [Guardrail Validator]       |
                                +------------------+-------------------+
                                                   |
                                +------------------v-------------------+
                                |      UNIFIED APPROVAL SERVICE        |
                                |   (SHA-256 Hashed Payload Binding)   |
                                |    10-Minute TTL Single-Use Gate     |
                                +------------------+-------------------+
                                                   |
                        ┌──────────────────────────┴──────────────────────────┐
                        │                                                     │
                        ▼                                                     ▼
        +-------------------------------+                     +-------------------------------+
        |  (Dedicated Polling Worker)   |                     |    (Node.js Baileys :3001)    |
        |      @ambersre_alert_bot      |                     |    Live Web QR Auth Session   |
        +---------------+---------------+                     +---------------+---------------+
                        │                                                     │
                        └──────────────────────────┬──────────────────────────┘
                                                   │
                                +------------------v-------------------+
                                |      TOOL EXECUTION RUNTIME          |
                                |  LOW: Autonomous Read-only Metrics   |
                                |  HIGH: Cryptographically Approved    |
                                +------------------+-------------------+
                                                   |
                                +------------------v-------------------+
                                |        TARGET INFRASTRUCTURE         |
                                |    (AWS / GCP, K8s, RDS, VPC)        |
                                +--------------------------------------+
```

---

## 3. Service Decomposition

### 1. API Gateway Layer (`amber-backend` :8000)
The central entry point for all synchronous HTTP traffic. It handles:
- Inbound alert webhook ingestion (`/api/v1/webhooks/{source}`).
- Incident CRUD, timeline, and query APIs (`/api/v1/incidents`).
- Cryptographic approval verification (`/api/v1/approvals`).
- Liveness (`/health/liveness`) and database/redis readiness probes (`/health/readiness`).
- Commercial license verification (`/api/v1/license/activate`).

### 2. Event Queue & Token Revocation (`amber-redis` :6379)
Buffers incoming alerts rapidly to meet the `<50ms` p99 latency requirement. Writes raw webhook payloads directly to Redis Streams, acting as a shock absorber during alert storms up to 500 alerts/sec. Also maintains the JWT revocation blacklist and sliding window rate limiting counters.

### 3. Alert Correlation Engine
Processes events from Redis Streams. Uses sliding window fingerprinting (based on service tags, error codes, and time locality) to group related alerts into a single incident entity. Reduces noise and prevents the orchestration engine from being overwhelmed.

### 4. Agent Orchestration Service (LangGraph State Machine)
The core intelligence layer. Uses LangGraph to manage stateful, multi-agent workflows:
- **Triage Node:** Classifies severity (P0–P4) within `<3s`.
- **Hybrid RAG Node:** Interacts with the knowledge service to retrieve relevant runbooks and past post-mortems using pgvector dense embeddings + BM25 keyword matching.
- **Investigation Node:** Executes bounded read-only diagnostic tools (`query_db_metrics`, `fetch_pod_logs`, `check_service_health`) within `<25s`.
- **Guardrail Validator:** Statically analyzes proposed remediation actions against pre-defined safety policies. Mutating actions are halted and sent to the HITL approval queue.

### 5. Unified Approval Service (`backend/app/services/approval_service.py`)
Centralized business logic for approving or rejecting high-risk actions.
- Computes SHA-256 HMAC hash over sorted JSON tool arguments.
- Validates the 10-minute expiration TTL.
- Enforces single-use execution tokens.
- Atomically resolves the associated incident state (`PENDING_APPROVAL` → `APPROVED` → `EXECUTING` → `RESOLVED`).

### 6. Interactive Telegram Bot Worker (`amber-telegram-bot`)
A standalone Python container running an isolated `Application.builder()` polling loop connected to `@ambersre_alert_bot`.
- **Decoupled Architecture:** Runs as a dedicated process separate from Uvicorn web workers, eliminating Telegram 409 Conflict errors.
- **Commands:** `/status`, `/incidents`, `/pending`, `/approve <id>`, `/reject <id>`, `/simulate`.
- **1-Click Approvals:** Dispatches inline button callbacks (`callback_data="approve:<id>"`) directly to on-call mobile devices.

- Provides a web QR authentication endpoint (`GET /`).
- Health status check (`GET /status`).
- HTTP alert dispatch endpoint (`POST /send-alert`).

### 8. Target Infrastructure Tool Runtime
A sandboxed execution environment. Validates parameters against static schemas before calling cluster APIs:
- `query_db_metrics` (LOW risk, autonomous)
- `fetch_pod_logs` (LOW risk, autonomous, secret redaction)
- `check_service_health` (LOW risk, autonomous)
- `kill_db_connections` (HIGH risk, requires HITL approval)
- `rollback_deployment` (HIGH risk, requires HITL approval)
- `restart_service_pod` (HIGH risk, requires HITL approval)

### 9. Edge Frontend (`https://ambersre.xyz`)
React 19 + TypeScript Single Page Application deployed on Cloudflare Workers edge.
- Interactive Alert Storm Simulator (Slack desktop view + Telegram smartphone view).
- Deep Proof Inspection Drawer (live diagnostic evidence, runbook match scores, mutation diffs).
- Full SEO metadata, Schema.org `SoftwareApplication` JSON-LD, and zero-latency CDN delivery.

---

## 4. Data Flow

1. **Ingestion:** Datadog or PagerDuty fires a webhook. `amber-backend` receives it, computes an alert fingerprint, and responds with HTTP 202 Accepted in `<50ms`.
2. **Buffering & Correlation:** The payload is pushed to Redis Streams. The Correlation Engine groups incoming alerts within a 5-minute sliding window into a unified incident.
3. **Triage:** LangGraph routes the incident to the Triage Node, assigning severity (e.g. `P0 - Connection Pool Saturation`).
4. **Investigation:** The Investigation Node queries `amber-postgres` (pgvector) for matched runbooks, executes read-only diagnostics (`query_db_metrics`), and identifies 5 hanging query PIDs.
5. **Remediation Proposal:** The agent proposes `kill_db_connections(pids=[1021, 1024])`.
6. **Guardrail Check:** The Guardrail Validator intercepts the proposal, flags it as `HIGH` risk, and freezes execution.
7. **Omni-Channel Dispatch:** The dispatcher broadcasts the proposal simultaneously to:
   - Slack (Block Kit card with Deep Proof).
   - Telegram (`@ambersre_alert_bot` with inline `[Approve]` and `[Reject]` buttons).
   - Web Dashboard (`https://ambersre.xyz`).
8. **Human Approval:** The SRE Lead clicks `[Approve]` on Telegram.
9. **Execution & State Resolution:** `ApprovalService` verifies the SHA-256 payload hash and TTL, executes the tool, verifies connection pool recovery, and transitions the incident to `RESOLVED`.
10. **Audit & Post-Mortem:** Execution results and timing metrics are logged into PostgreSQL for post-mortem analysis.

---

## 5. Technology Decisions Summary Table

| Component | Technology | Why Chosen | Alternatives Considered |
| :--- | :--- | :--- | :--- |
| **API Framework** | Python FastAPI | Native async, high throughput, deep integration with LangGraph. | Node.js/Express (Lacks mature Python AI libraries). |
| **Orchestrator** | LangGraph | State machine suited for cyclic, multi-node agent workflows with interrupt support. | AutoGen (Too opaque), standard LangChain chains. |
| **Primary Database** | PostgreSQL 16 + pgvector | ACID compliance, JSONB support, and embedded vector search in a single database. | Pinecone/Weaviate (Split-brain sync issues, external data egress). |
| **Event Queue** | Redis 7 Streams | Ultra-fast memory-based append-only log, handles 500 alerts/sec with zero packet loss. | Kafka (Too heavyweight for single-tenant VPC). |
| **Telegram Bot** | python-telegram-bot | Decoupled standalone polling worker, eliminates multi-worker 409 conflict. | Webhook-based (Requires public domain mapping for local bots). |
| **Frontend Edge** | React 19 + Cloudflare Workers | Instant global edge CDN, zero-cost static hosting, universal SSL. | Vercel (Higher cold starts, custom domain setup). |
| **Production Domain** | ambersre.xyz | Dedicated official domain with Google Trust Services SSL. | Mock staging domains. |
