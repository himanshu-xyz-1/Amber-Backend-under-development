import logging
from typing import Any

from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.runbook import Runbook

from .state import AmberGraphState

logger = logging.getLogger(__name__)

# Production System Runbooks (Always available as high-fidelity baseline knowledge)
CANONICAL_RUNBOOKS = [
    {
        "title": "Postgres Connection Pool Saturation & Lock Contention",
        "category": "database",
        "tags": ["postgres", "rds", "connection-pool", "p0", "locks"],
        "content": (
            "Symptoms: Pool utilization > 90%, client 504 gateway timeouts, active queries in 'idle in transaction'.\n"
            "Action: Run query_db_metrics to inspect hanging PIDs. For queries blocked > 60s, dispatch kill_db_connections "
            "with specific target PIDs. Verify pool drops to < 20% within 5s."
        ),
        "confidence": 0.96
    },
    {
        "title": "Kubernetes Pod CrashLoopBackOff & OOMKill Remediation",
        "category": "kubernetes",
        "tags": ["k8s", "crashloop", "oom", "p1", "pods"],
        "content": (
            "Symptoms: Pod status CrashLoopBackOff, exit code 137 (OOMKilled) or unhandled runtime panic.\n"
            "Action: Fetch pod logs with secret redaction. If recent deployment was pushed within 30 minutes, "
            "execute rollback_deployment to previous revision. Otherwise execute restart_service_pod."
        ),
        "confidence": 0.92
    },
    {
        "title": "Microservice HTTP 504 Upstream Gateway Timeout",
        "category": "networking",
        "tags": ["http", "latency", "p99", "gateway", "504"],
        "content": (
            "Symptoms: p99 latency > 2000ms, downstream retry storm.\n"
            "Action: Run check_service_health on internal endpoints. Inspect downstream database/redis dependencies."
        ),
        "confidence": 0.88
    }
]


async def rag_node(state: AmberGraphState) -> dict:
    """
    Production RAG node:
    Searches PostgreSQL runbooks table combined with canonical SRE runbook index
    to extract actionable remediation instructions.
    """
    service = state.get("affected_service", "core-service")
    alert_payload = state.get("alert_payload", {})
    alert_text = f"{alert_payload.get('title', '')} {alert_payload.get('message', '')} {service}".lower()

    matched_runbooks: list[dict[str, Any]] = []

    # 1. Search Canonical Knowledge Base
    for rb in CANONICAL_RUNBOOKS:
        # Check tag matches or content similarity
        if any(tag in alert_text for tag in rb["tags"]) or (service in rb["title"].lower()):
            matched_runbooks.append({
                "title": rb["title"],
                "content_snippet": rb["content"][:200] + "...",
                "confidence": rb["confidence"]
            })

    # 2. Query dynamic runbooks from PostgreSQL database if available
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Runbook).filter(Runbook.is_active == True).limit(5)
            )
            db_runbooks = result.scalars().all()
            for db_rb in db_runbooks:
                matched_runbooks.append({
                    "title": db_rb.title,
                    "content_snippet": (db_rb.content or "")[:200] + "...",
                    "confidence": 0.85
                })
    except Exception as e:
        logger.debug(f"Dynamic DB runbook retrieval note: {e}")

    # Fallback to default if no specific match
    if not matched_runbooks:
        matched_runbooks.append(CANONICAL_RUNBOOKS[0])

    instructions = (
        f"Correlate diagnostics against {matched_runbooks[0]['title']}. "
        "Enforce minimal blast radius: propose read-only health checks first, "
        "and request cryptographic HITL approval for any connection termination or rollback."
    )

    return {
        "matched_runbooks": matched_runbooks,
        "runbook_instructions": instructions,
        "current_node": "rag"
    }
