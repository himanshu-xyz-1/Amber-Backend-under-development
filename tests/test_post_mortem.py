import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.core.database import AsyncSessionLocal, Base, engine
from backend.app.main import app
from backend.app.models.alert import Alert, AlertSource
from backend.app.models.incident import Incident, IncidentSeverity, IncidentStatus
from backend.app.models.tool_invocation import (
    InvocationStatus,
    RiskLevel,
    ToolInvocation,
)
from backend.app.services.post_mortem import generate_incident_post_mortem


@pytest.mark.asyncio
async def test_generate_incident_post_mortem_markdown():
    inc = Incident(
        id=uuid.uuid4(),
        title="Payment Service Database Connection Pool Saturation",
        description="High connection pool saturation causing 504 gateway timeouts on /checkout endpoint.",
        severity=IncidentSeverity.P1,
        status=IncidentStatus.RESOLVED,
        source_service="payment-svc",
        fingerprint="fp-payment-db-saturation-123",
        root_cause_summary="Stuck idle-in-transaction PostgreSQL connections held locks on 'payment_ledger'.",
        time_to_resolve=42.5,
        created_at=datetime.now(timezone.utc),
        resolved_at=datetime.now(timezone.utc),
    )

    alert = Alert(
        id=uuid.uuid4(),
        incident_id=inc.id,
        source=AlertSource.PAGERDUTY,
        title="CRITICAL: payment-svc DB connections > 90%",
        fingerprint="fp-alert-1",
        raw_payload={"details": "pool full"}
    )

    inv = ToolInvocation(
        id=uuid.uuid4(),
        incident_id=inc.id,
        tool_name="kill_db_connections",
        tool_args={"pids": [412, 415]},
        risk_level=RiskLevel.HIGH,
        status=InvocationStatus.EXECUTED,
        health_check_passed=True,
        execution_result={"terminated_pids": [412, 415]}
    )

    report_md = generate_incident_post_mortem(inc, alerts=[alert], invocations=[inv])

    assert "# 📋 Incident Post-Mortem: Payment Service Database Connection Pool Saturation" in report_md
    assert "Root Cause Analysis (RCA)" in report_md
    assert "kill_db_connections" in report_md
    assert "PASSED" in report_md
    assert "42.5 seconds" in report_md


@pytest.mark.asyncio
async def test_get_post_mortem_endpoint():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        inc = Incident(
            title="K8s Ingress Gateway Degraded",
            severity=IncidentSeverity.P2,
            status=IncidentStatus.RESOLVED,
            source_service="ingress-nginx"
        )
        session.add(inc)
        await session.commit()
        await session.refresh(inc)
        inc_id = str(inc.id)

    client = TestClient(app)
    headers = {"X-API-Key": "test_amber_api_key_2026"}
    # Test Markdown format
    res = client.get(f"/api/v1/incidents/{inc_id}/post-mortem", headers=headers)
    assert res.status_code == 200
    assert "text/markdown" in res.headers["content-type"]
    assert "Incident Post-Mortem: K8s Ingress Gateway Degraded" in res.text

    # Test JSON format
    res_json = client.get(f"/api/v1/incidents/{inc_id}/post-mortem?format=json", headers=headers)
    assert res_json.status_code == 200
    data = res_json.json()
    assert data["incident_id"] == inc_id
    assert "post_mortem_markdown" in data
