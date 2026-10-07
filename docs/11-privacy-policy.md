# Amber — Privacy Policy & Data Collection Specification

> **Product**: Amber — Autonomous Incident Remediation & SRE Engine  
> **Classification**: Enterprise Legal, Compliance & Privacy Specification  
> **Version**: 1.0.0  
> **Effective Date**: 2026-10-01  
> **Applicability**: Self-Hosted VPC Deployments, Single-Tenant Instances & Cloud Gateways  

---

## 1. Core Privacy Thesis: Customer Sovereignty

Amber operates on the fundamental principle of **Zero-Knowledge Infrastructure Defense**. 

Traditional APM and SRE tools hoard customer logs and telemetry in third-party multi-tenant silos. Amber is architected to operate within your isolated security perimeter:
- **No Model Training on Customer Data**: Customer telemetry, diagnostic outputs, runbooks, and error logs are **never** utilized to train, retrain, fine-tune, or calibrate public or proprietary LLMs (e.g., OpenAI, Anthropic, Google Gemini, or internal models).
- **Single-Tenant Isolation**: Each enterprise customer operates within a dedicated VPC or self-hosted deployment. Amber does not mingle execution graphs, state checkpoints, or alert streams across organizations.
- **Client-Side Secret Redaction**: All payload scrubbing occurs in-memory at the ingestion edge **before** LLM serialization or database persistence.

---

## 2. Information and Data We Collect

Amber collects and processes only the minimum data required to triage, investigate, and remediate technical infrastructure incidents.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION BOUNDARY                         │
├──────────────────────────┬─────────────────────────────────────────────┤
│ COLLECTED & STORED       │ REDACTED / DROPPED IN MEMORY (NEVER STORED) │
├──────────────────────────┼─────────────────────────────────────────────┤
│ • Alert Metadata & Titles│ • Raw Database Row Values / Customer Records│
│ • Service Names & Nodes  │ • Passwords, Bearer Tokens, API Keys        │
│ • Sanitized Stack Traces │ • Credit Card Numbers, SSNs, PII            │
│ • Container Metrics      │ • Private TLS Certificates & Private Keys   │
│ • Runbook Markdown Docs  │ • Unsanitized Customer Environment Envs     │
│ • Audit Log & Approvals  │ • Raw Session Payloads Containing End-Users │
└──────────────────────────┴─────────────────────────────────────────────┘
```

### 2.1. Alert & Webhook Ingestion Telemetry
- **Source Identifiers**: Ingestion origin (PagerDuty, Sentry, Datadog, Prometheus, CloudWatch).
- **Incident Envelope**: Alert timestamps, incident fingerprint (SHA-256 hash of service + error classification), severity tier (P0–P4), firing rule names.
- **Error Signatures**: Exception classes (e.g., `DeadlockDetected`, `OOMKilled`, `ConnectionPoolExhausted`), file paths, line numbers, and truncated function names.

### 2.2. Diagnostic & Health Metrics
- **System Metrics**: Connection pool utilization, thread counts, CPU/Memory percentage, disk I/O wait times, queue depth.
- **Redacted Pod / Container Logs**: Standard error/out logs captured during the 5-minute pre-incident window, truncated to a maximum of 500 lines per diagnostic pass, filtered through our mandatory regex sanitization engine.

### 2.3. Operational Context & Runbooks
- **Runbooks & SOPs**: Customer-uploaded markdown runbooks, operational playbooks, and historical post-mortems ingested into the local pgvector database.
- **Agent Execution State**: LangGraph state machine steps, tool call parameters, verification health check statuses, and human-in-the-loop (HITL) approval records.

### 2.4. Account & Authentication Metadata
- **Service & User Identities**: SRE business email address, scoped API key hashes, verified communication handles (`slack_user_id`, `whatsapp_phone`, `@telegram_handle`), and assigned RBAC roles (`SRE`, `LEAD`, `DEVELOPER`, `ADMIN`).
- **Cryptographic Audit Trails**: Webhook source HMAC secrets, single-use HITL approval tokens, IP addresses of approvers, and SHA-256 payload binding signatures.

---

## 3. In-Flight Secret & PII Redaction Pipeline

Before any log line, webhook payload, or query output is passed to an AI reasoning node or written to PostgreSQL, it passes through the synchronous in-memory **Amber Sanitize Filter**:

1. **High-Entropy Token Detection**: Shannon entropy scans (>4.5 bits/char) targeting AWS Access Keys (`AKIA...`), GitHub Personal Access Tokens (`ghp_...`), JWTs, and private keys (`BEGIN RSA PRIVATE KEY`).
2. **Regex Secret Scrubbing**:
   - `(?i)(bearer\s+[a-zA-Z0-9_\-\.]{20,})` → `[REDACTED_BEARER_TOKEN]`
   - `(?i)(password|secret|token|apikey|authorization)\s*[:=]\s*["']?([^"',\s]+)` → `$1: [REDACTED_SECRET]`
   - `(?i)(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b)` → `[REDACTED_EMAIL]`
   - `(\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b)` → Masked to subnet level (e.g., `10.0.x.x`)
3. **Payload Truncation**: Maximum log payload limit of 64 KB per diagnostic tool execution to prevent memory overflow or token stuffing attacks.

---

## 4. Third-Party AI Model Interaction & Data Isolation

Amber leverages Large Language Model APIs (e.g., Anthropic Claude 3.5 Sonnet, Google Gemini 2.0 Flash) strictly for **stateless reasoning and tool selection**.

- **Zero Data Retention Agreements (ZDR)**: Commercial enterprise API agreements ensure that prompts sent to foundation model providers are processed statelessly in-memory and are **never cached or used for training**.
- **Payload Minimization**: Only the sanitized root-cause diagnostic summary and tool schemas are transmitted in prompt context. Raw database queries, end-user personal data, and infrastructure IP topologies are stripped prior to egress.
- **Air-Gapped / Local LLM Compatibility**: For defense and high-security compliance tiers (Tier 3), Amber supports local inference runtimes (e.g., vLLM or Ollama deploying Llama 3 / DeepSeek) where zero data ever exits the customer's private subnet.

---

## 5. Data Storage, Retention & Deletion

### 5.1. Retention Windows
- **Active Incidents & Audit Logs**: Retained for 90 days in primary PostgreSQL storage for SLA auditing and compliance review.
- **Diagnostic Execution Cache**: Ephemeral Redis diagnostic keys expire automatically after 24 hours.
- **Historical Post-Mortems**: Preserved permanently unless an explicit purge request is initiated by an organization administrator.

### 5.2. Data Residency
- For self-hosted VPC deployments, all data resides entirely within the customer's designated cloud account (AWS, GCP, Azure, or bare metal). Amber Technologies Inc. has zero external access to underlying volumes or databases.

### 5.3. Right to Erasure (GDPR / CCPA)
Upon customer written request or organization de-provisioning:
- All database records (`users`, `incidents`, `alerts`, `tool_invocations`) are hard-deleted within 7 business days.
- Local vector embeddings stored in pgvector tables are permanently dropped.
- Cryptographic confirmation certificate of purge is issued to the customer's Chief Information Security Officer (CISO).

---

## 6. Security Certifications & Compliance Posture

- **SOC 2 Type II Alignment**: Comprehensive controls around access control, change management, encryption-in-transit (TLS 1.3), and encryption-at-rest (AES-256 via customer-managed KMS).
- **Single-Sign-On (SSO) & SCIM**: SAML 2.0 / OIDC enterprise identity integration ensuring instant de-provisioning upon employee offboarding.
- **Vulnerability Disclosures**: Periodic independent third-party penetration testing and continuous automated vulnerability dependency scanning via Bandit and Trivy.

---

## 7. Contact Information & Privacy Office

For privacy inquiries, data subject access requests (DSAR), or Data Processing Addendum (DPA) execution:
- **Privacy & Security Intake**: `team@ambersre.xyz`
- **Official Website**: `https://ambersre.xyz/#connect`
- **Physical Address**: Amber SRE Technologies Inc., 548 Market St, Suite 48210, San Francisco, CA 94104, USA.
