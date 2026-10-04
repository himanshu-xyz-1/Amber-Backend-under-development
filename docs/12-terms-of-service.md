# Amber — Master Terms of Service & Enterprise Security Agreement

> **Product**: Amber — Autonomous Incident Remediation & SRE Engine  
> **Classification**: Commercial Master Services Agreement (MSA) & SLA Specification  
> **Version**: 1.0.0  
> **Effective Date**: 2026-10-01  
> **Governing Entity**: Amber SRE Technologies Inc.  

---

## 1. Agreement Overview & Scope of Service

This Master Terms of Service ("Agreement") governs the licensing, deployment, and operational execution of **Amber** ("Service", "Software", or "Engine"), developed and operated by **Amber SRE Technologies Inc.** ("Amber", "Company", "We"). 

By provisioning an Amber instance, deploying the Amber VPC agent, executing a Software Order Form, or submitting webhook alerts to Amber API gateways, the customer organization ("Customer", "Subscriber", "You") agrees to these terms in full.

Amber is an autonomous site reliability engineering (SRE) diagnostic and guided remediation engine that ingests observability alerts, performs correlation, analyzes infrastructure telemetry, and executes deterministic or human-approved remediation runbooks.

---

## 2. Subscription Tiers & Strict Usage Boundaries

To guarantee deterministic system latency (<100ms webhook ingestion, <3s triage) and protect infrastructure from runaway cloud compute costs, Amber enforces explicit tier boundaries:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               AMBER SUBSCRIPTION TIERS                                 │
├─────────────────────┬──────────────────────────┬───────────────────────────────────────┤
│ TIER / COMMITMENT   │ PRICING (USD)            │ INFRASTRUCTURE & EXECUTION LIMITS     │
├─────────────────────┼──────────────────────────┼───────────────────────────────────────┤
│ COMMUNITY TIER      │ • $0 / Month             │ • Up to 15 Production Microservices   │
│ (Self-Hosted,       │ • Free Forever           │ • Up to 50 Kubernetes / Cloud Nodes   │
│  Air-Gapped SRE)    │   Zero License Key Req   │ • 1,000 alerts / month                │
│                     │                          │ • Alert Storm Deduplication (< 80ms)  │
│                     │                          │ • Deterministic RCA Proof Blocks      │
│                     │                          │ • Read-Only IAM Diagnostics           │
│                     │                          │ • 50+ Built-in Runbooks & Local Ollama│
├─────────────────────┼──────────────────────────┼───────────────────────────────────────┤
│ LEVEL 1: AUTONOMOUS │ • Monthly: $2,499/mo     │ • Up to 35 Production Microservices   │
│ (Automated Fixes)   │ • Annual: $2,099/mo      │ • Up to 200 Kubernetes / Cloud Nodes  │
│                     │   (Billed $25,188/yr)    │ • Unlimited Alert Ingestion           │
│                     │                          │ • 100 Included Mutating Actions / mo  │
│                     │                          │ • Multi-Channel HITL (Slack/TG/WA)    │
│                     │                          │ • Offline Ed25519 License Validation  │
├─────────────────────┼──────────────────────────┼───────────────────────────────────────┤
│ LEVEL 2: RESPONSE   │ • Monthly: $4,499/mo     │ • Custom / Unlimited Microservices    │
│ (Enterprise Response│ • Annual: $3,699/mo      │ • Dedicated Single-Tenant VPC Cluster │
│  & SRE Escalation)  │   (Billed $44,388/yr)    │ • 500 High-Volume Remediations / mo   │
│                     │                          │ • < 15-min Incident Bridge Escalation │
│                     │                          │ • Full White-Glove Runbook Eng        │
│                     │                          │ • Strictly Limited to 5 Design Orgs   │
└─────────────────────┴──────────────────────────┴───────────────────────────────────────┘
```

### 2.1. Overage & Fair-Use Remediation Policy
- **Alert Storm Bursting**: Amber buffers up to 500+ alerts/sec without packet loss during incidents using Redis Streams.
- **Remediation Quota Extensions**: Organizations on Level 1 (Autonomous) that exhaust their 100 remediation quota within a billing cycle may purchase supplementary packs at **$15 per verified remediation**, or transition actions to Human-In-The-Loop (HITL) review at zero additional surcharge. Organizations on Level 2 (Response) retain an allowance of 500 verified remediations per month, with custom overage allowances provisioned per enterprise order form.

---

## 3. Deterministic Dual-Plane Safe Execution Guarantee

### 3.1. Deterministic Guardrail Thesis (Core Safety Protocol)
Amber explicitly does **not** allow probabilistic Large Language Models (LLMs) to execute arbitrary bash commands or mutating cluster calls. The platform operates under a strict dual-plane architecture:

$$\text{Action Execution} = (\text{LLM Reasoning Proposal}) \cap (\text{Deterministic Tool Policy Allowlist})$$

1. **Static Risk Classification**: Tool risk levels (`LOW` vs. `HIGH`) are immutably declared in source code (`backend/app/tools/`). An LLM prompt cannot override, downgrade, or bypass a tool's safety classification.
2. **Mandatory Human-in-the-Loop (HITL) for HIGH Risk Actions**:
   - Any state-mutating tool (e.g., terminating database connections, triggering deployment rollbacks, pod evictions) is intercepted by the Guardrail Validator.
   - The engine generates a single-use, 10-minute cryptographic approval token bound to the SHA-256 hash of the exact tool arguments:
   $$\text{Token Payload} = \text{HMAC-SHA256}(\text{Tool Name} \parallel \text{JSON Arguments} \parallel \text{Expires At})$$
   - Execution is blocked until an authenticated SRE or Lead approves the action via Slack Connect or the Amber Web Console.
3. **Automated Health Verification & Safe Rollback**:
   - Every autonomous remediation action executes a mandatory post-action verification probe (`CheckServiceHealth` or custom HTTP/Prometheus query).
   - If health probes do not return `200 OK` within 45 seconds, the engine automatically rolls back the mutation to its previous verified state, records an incident checkpoint, and immediately escalates to the customer on-call team.

### 3.2. Scope of Guarantee vs. Third-Party Outcome Disclaimer
- **What We Guarantee**: Amber warrants that no mutating infrastructure command will ever be executed without either (a) deterministic static allowlist authorization for low-risk actions, or (b) an unexpired, cryptographically valid SHA-256 HITL approval signature. Amber further warrants that its fail-safe escalation triggers upon any ambiguity or confidence score below 85%.
- **What Is Disclaimed**: Amber does not warrant that Customer's proprietary application code, third-party database engines, cloud provider hardware, or upstream network transit will function error-free. Amber is an incident mitigation platform, not an insurer against underlying third-party software bugs.

---

## 4. Emergency Kill-Switch & Customer Sovereignty

Customer engineering leadership retains sovereign, unassailable control over their infrastructure at all times:

1. **Global Master Kill-Switch**: The Amber API exposes a high-priority endpoint:
   ```http
   POST /api/v1/settings/kill-switch
   Authorization: Bearer <ADMIN_JWT>
   Content-Type: application/json

   { "state": "ENGAGED", "reason": "Incident freeze by CTO" }
   ```
2. **Latency Guarantee**: Upon kill-switch engagement, all Amber worker nodes immediately downgrade to **Read-Only Observation Mode** across all worker threads in $\le \mathbf{250\text{ ms}}$. Any queued mutating actions are instantaneously canceled and marked `REJECTED_BY_KILL_SWITCH`.
3. **Hard IAM Revocation**: Because Amber connects via standard cloud IAM roles or Kubernetes ServiceAccounts, Customer SREs may revoke Amber's cloud credentials in the AWS/GCP/Azure console at any second, permanently severing cluster access without Amber's intervention.

---

## 5. Service Level Agreement (SLA) & Support Terms

### 5.1. Engine Availability SLA
Amber commits to an API Gateway & Ingestion availability of **99.9% uptime** per calendar month for Cloud and Hosted endpoints, excluding scheduled maintenance announced 48 hours in advance.

### 5.2. Level 3 Response & Incident Bridge Escalation SLA
For subscribers enrolled in **Level 3 (Response)**:
- **Dedicated Communication Channel**: Private Slack Connect or direct incident bridge bridging Customer's Lead SREs with Amber's Founding Engineering & Principal SRE team.
- **Incident Escalation Response**: Amber guarantees a **< 15-minute first-response SLA** by a Principal SRE for P0/P1 infrastructure incidents occurring during contracted operational windows. If automated remediation requires escalation, an Amber Principal SRE directly joins the customer incident war-room.
- **Cap on Response Partner Slots**: To maintain this SLA without dilution, Level 3 enrollment is hard-capped at **5 active enterprise organizations**.

---

## 6. Limitation of Liability & Indemnification

1. **Cap on Aggregate Liability**: To the maximum extent permitted by applicable law, in no event shall either party's aggregate cumulative liability arising out of or related to this Agreement exceed the total fees paid by Customer to Amber under the applicable Software Order Form in the **twelve (12) months** immediately preceding the incident giving rise to liability.
2. **Consequential Damages Waiver**: Neither party shall be liable to the other for any indirect, incidental, punitive, special, or consequential damages, including loss of profits, data corruption, or operational downtime, even if advised of the possibility of such damages.
3. **Intellectual Property Indemnity**: Amber shall defend, indemnify, and hold harmless Customer against any third-party claims asserting that the Amber software infringes any patent, copyright, or trademark.

---

## 7. Term, Renewal & Billing Cycles

- **Billing Cycles**: Monthly subscriptions are billed on the first day of each calendar billing period via Stripe or ACH. Annual subscriptions are prepaid in full at the discounted annual rate ($7,788, $17,988, or $27,588).
- **Auto-Renewal & Notice**: Annual contracts renew automatically for subsequent 12-month periods unless written non-renewal notice is delivered at least 30 days prior to expiration.
- **Termination for Cause**: Either party may terminate immediately upon material breach if such breach remains uncured 30 days after receipt of formal written notice.

---

## 8. Governing Law & Dispute Resolution

This Agreement shall be governed by and construed under the laws of the **State of Delaware**, USA, without regard to its conflict of law principles. Any dispute arising under this Agreement shall be resolved through confidential, binding commercial arbitration administered by JAMS in San Francisco, California.

---

## 9. Signatures & Acceptance

For Enterprise Order Forms and custom VPC licensing, this Agreement is executed via digital or electronic signature:

```
For: Amber SRE Technologies Inc.           For: [Customer Organization]

Name: Himanshu                             Name: __________________________
Title: Founder & CEO                       Title: _________________________
Date: 2026-10-01                           Date: __________________________
```
