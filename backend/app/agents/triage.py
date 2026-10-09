"""
Amber SRE Engine — Triage Node.

Classifies incident severity (P0–P4) using the Universal LLM Gateway.
Any configured provider (local Ollama model, cloud Claude, Gemini, GPT-4o)
is used transparently. If LLM is unavailable, falls back to deterministic
heuristics — Amber never crashes, it just keeps working.
"""

import logging
import time

from backend.app.core.llm import llm_gateway

from .state import AmberGraphState

logger = logging.getLogger(__name__)

TRIAGE_SYSTEM_PROMPT = (
    "You are an expert SRE Triage Engine embedded in the Amber Autonomous Incident Remediation system. "
    "Your job is to classify infrastructure alerts with precision. "
    "Always output a single valid JSON object — no markdown, no extra text, no explanation outside JSON."
)


def _classify_heuristic(title: str, message: str, service: str) -> tuple[str, str]:
    """
    Deterministic rule-based SRE heuristic classifier.
    Used when LLM is unavailable, rate-limited, or trust level is too low.
    Sub-millisecond execution. Zero hallucination risk.
    """
    text = f"{title} {message} {service}".lower()

    # Explicit severity tags in title
    for tag in ["p0", "p1", "p2", "p3", "p4"]:
        if f"[{tag}]" in text or f"severity: {tag}" in text:
            return tag.upper(), f"Explicit {tag.upper()} tag detected in alert payload for {service}."

    # P0: Total outage / deadlock / pool starvation / split-brain
    if any(k in text for k in [
        "zero transaction commits", "advisory lock", "deadlock cascade", "deadlock",
        "starvation", "pool starvation", "connection pool starvation",
        "connection pool saturation", "pool saturation", "routing blackhole",
        "nxdomain", "primary db down", "database down", "split brain",
    ]):
        return "P0", "Heuristic: Critical database lock/starvation or outage causing total failure."

    # P1: Core flow degradation / CrashLoop / OOM / node failure
    if any(k in text for k in [
        "oomkilled", "oom eviction", "eviction storm", "crashloop", "crashloopbackoff",
        "sigsegv", "504 gateway timeout", "gateway timeout", "525 ssl", "ssl handshake",
        "diskpressure", "node diskpressure", "eviction alert", "node not ready",
        "inodes exhausted", "redos", "runaway loop", "grpc deadline", "syn backlog",
        "heap limit", "threadpool starvation", "payment failure rate",
        "signature verification failure",
    ]):
        return "P1", "Heuristic: Core customer-facing service failure or node pressure."

    # P2: Performance degradation / replication lag / rate limits
    if any(k in text for k in [
        "rate limit breached", "429 rate limit", "slow sequential scan",
        "unindexed slow", "dns propagation", "replication lag", "desync",
        "consumer group lag", "kafka consumer lag", "buffer overflow",
        "malformed json", "fragmentation ratio", "degraded performance", "elevated error",
    ]):
        return "P2", "Heuristic: Non-blocking performance degradation or queue/cache lag."

    # P3: Non-customer-facing batch / background / backup
    if any(k in text for k in ["cron job", "nightly backup", "backup-worker", "batch job", "s3 upload failed", "etl"]):
        return "P3", "Heuristic: Non-customer-facing background batch/cron failure."

    # P4: Informational / advance warnings
    if any(k in text for k in ["cert renewal", "certificate renewal", "ssl certificate", "days remaining", "informational", "notice:"]):
        return "P4", "Heuristic: Advance lifecycle / maintenance notification."

    return "P2", "Heuristic fallback: Standard operational alert assigned default P2."


async def triage_node(state: AmberGraphState) -> dict:
    """
    Triage node for incident severity classification.
    Uses the Universal LLM Gateway for structured classification,
    with deterministic heuristic fallback when LLM is unavailable.
    """
    start_time = time.time()
    alert_payload = state.get("alert_payload", {})
    source = state.get("alert_source", "UNKNOWN")
    title = alert_payload.get("title", "")
    message = alert_payload.get("message", "")
    service = alert_payload.get("service") or alert_payload.get("source_service", "core-service")

    severity = "P2"
    reasoning = "Standard operational alert triage."
    used_llm = False

    prompt = f"""Classify this infrastructure alert into exactly ONE severity level.

Severity definitions:
- P0: Total customer outage, complete service unavailability, critical DB down.
- P1: Significant customer impact, degraded primary user flow, redundancy loss.
- P2: Moderate performance degradation, non-blocking service issue, elevated error rate.
- P3: Minor issue, internal metric threshold exceeded, non-customer-facing.
- P4: Informational or low-priority notice.

Alert Source: {source}
Service: {service}
Title: {title}
Message: {message}
Payload Context: {alert_payload}

Return ONLY this JSON object (no markdown, no extra text):
{{
  "severity": "P0" | "P1" | "P2" | "P3" | "P4",
  "reasoning": "1 concise sentence explaining the severity assignment.",
  "affected_service": "{service}"
}}"""

    parsed = await llm_gateway.generate_json(
        prompt=prompt,
        system_prompt=TRIAGE_SYSTEM_PROMPT,
        temperature=0.1,
        timeout=20.0,
    )

    if parsed:
        severity = parsed.get("severity", severity)
        reasoning = parsed.get("reasoning", reasoning)
        service = parsed.get("affected_service", service)
        used_llm = True
    else:
        logger.info("[Triage] LLM unavailable or returned no result. Using deterministic heuristics.")
        severity, reasoning = _classify_heuristic(title, message, service)

    elapsed_time = time.time() - start_time
    logger.info(f"Triage completed in {elapsed_time:.3f}s via {'LLM' if used_llm else 'heuristics'}: {severity} — {reasoning}")

    return {
        "severity": severity,
        "triage_reasoning": f"[{elapsed_time:.2f}s | {'LLM' if used_llm else 'heuristic'}] {reasoning}",
        "affected_service": service,
        "current_node": "triage",
    }
