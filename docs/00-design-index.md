# Amber — System Design Documentation Index

> **Amber**: Autonomous Incident Remediation & SRE Engine  
> **Status**: Phase 3 — Governed HITL Remediation & In-VPC Production Engine (Active)  
> **Live Web Platform**: [https://ambersre.xyz](https://ambersre.xyz)  
> **Interactive Telegram Bot**: [@ambersre_alert_bot](https://t.me/ambersre_alert_bot)  
> **Last Updated**: 2026-10-03

---

## Reading Order

Start with the PRD, then follow the numbered sequence. Each document is self-contained but cross-references related docs.

---

## Documents

| # | Document | What It Covers |
|---|----------|----------------|
| — | [PRD.md](./PRD.md) | Product Requirements — problem statement, use cases, functional requirements, NFRs, safety specification, rollout phases |
| 02 | [Database Design](./02-database-design.md) | PostgreSQL + pgvector + Redis selection rationale, full schema design with ER diagram, indexing strategy, connection pooling, migrations, Redis key patterns, backup & DR, data retention |
| 03 | [Security & Token Architecture](./03-security-and-token-architecture.md) | Zero-trust token model, inbound webhook HMAC-SHA256 verification, single-use HITL tokens (SHA-256 bound, 10m TTL), RBAC & service IAM, threat model |
| 05 | [Rate Limiter](./05-rate-limiter.md) | Algorithm selection (sliding window + token bucket), 3-layer rate limiting, Redis implementation design, rate limit tiers, webhook ingestion control, LLM API rate management, DDoS protection |
| 06 | [Scalability](./06-scalability.md) | Horizontal scaling strategy, auto-scaling triggers, bottleneck analysis, LLM API scaling & fallback chains, capacity planning (10/100/1000 incidents/day), caching, cost optimization |
| 07 | [Version Control](./07-version-control.md) | Monorepo strategy, trunk-based development, commit conventions, PR process, protected branches, CODEOWNERS, release management, environment mapping |
| 08 | [CI/CD Pipeline](./08-cicd-pipeline.md) | GitHub Actions pipeline, CI stages (lint/test/scan/build), CD stages (Docker/Cloudflare Workers/staging/production), Docker strategy, secret management, database migrations in deploy, rollback strategy |
| 09 | [API Management](./09-api-management.md) | API versioning (/api/v1), full endpoint map, request/response standards, cursor-based pagination, webhook security, OpenAPI spec, API gateway considerations, SDK roadmap |
| 10 | [Future Growth](./10-future-growth.md) | Product roadmap phases, multi-tenancy migration path, Kubernetes migration, observability stack, billing/monetization, plugin architecture, SOC 2 compliance, team scaling |
| 11 | [Privacy Policy & Data](./11-privacy-policy.md) | Data collection boundaries, zero-training guarantee, in-memory PII/secret scrubbing, LLM isolation, data residency, retention & GDPR purge |
| 12 | [Terms of Service & Security](./12-terms-of-service.md) | Subscription tiers (Community Free, Autonomous, Response) & usage limits, deterministic safe execution guarantee, emergency kill-switch, SLA & liability |

---

## Quick Reference — Tech Stack Decisions

| Component | Technology | Justification Doc |
|-----------|-----------|-------------------|
| Backend API | FastAPI + Async SQLAlchemy | [01 Architecture](./01-system-architecture.md) |
| Agent Orchestration | LangGraph StateGraph | [01 Architecture](./01-system-architecture.md) |
| Telegram SRE Bot | Python python-telegram-bot (dedicated polling container) | [01 Architecture](./01-system-architecture.md) |
| Primary Database | PostgreSQL 16 | [02 Database](./02-database-design.md) |
| Vector Store | pgvector extension | [02 Database](./02-database-design.md) |
| Event Queue / Cache | Redis 7 Streams | [02 Database](./02-database-design.md) |
| Security & HITL | Unified ApprovalService + SHA-256 Binding (10m TTL) | [03 Security](./03-security-and-token-architecture.md) |
| Rate Limiting | Redis sliding window + token bucket | [05 Rate Limiter](./05-rate-limiter.md) |
| CI/CD | GitHub Actions | [08 CI/CD](./08-cicd-pipeline.md) |
| Containers | Docker Compose (5 isolated services) | [08 CI/CD](./08-cicd-pipeline.md) |
| Frontend | React 19 + TypeScript + Vite + Tailwind on Cloudflare Workers | [01 Architecture](./01-system-architecture.md) |
| Production Domain | https://ambersre.xyz (Google Trust Services SSL) | [01 Architecture](./01-system-architecture.md) |
| Observability | Langfuse (LLM traces) + Prometheus + Grafana (future) | [10 Future](./10-future-growth.md) |
| Billing | Stripe Commercial Subscriptions | [10 Future](./10-future-growth.md) |

---

## Phase Roadmap Status

```text
Phase 0: Architecture & Safety Core                 [DONE]
   │
Phase 1: Read-Only Diagnostics & Ingestion Buffer   [DONE]
   │
Phase 2: Shadow Mode & Correlation Engine           [DONE]
   │
Phase 3: Governed HITL Remediation (Omni-channel)   [DONE ← CURRENT ACTIVE PHASE]
   │
Phase 4: Autonomous Safe Mitigations (Closed-loop)  [ROADMAP]
   │
Phase 5: Multi-Tenant SaaS & K8s Operator           [ROADMAP]
```
