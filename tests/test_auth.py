import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.config import settings


def test_approvals_require_auth():
    client = TestClient(app)

    # In production with AMBER_API_KEY set
    orig_key = settings.AMBER_API_KEY
    try:
        settings.AMBER_API_KEY = "amber_prod_secret_token_123"

        # 1. Missing auth header -> 401 Unauthorized
        res_no_auth = client.get("/api/v1/approvals/pending")
        assert res_no_auth.status_code == 401
        assert "Authentication required" in res_no_auth.json()["detail"]

        # 2. Invalid auth header -> 401 Unauthorized
        res_bad_auth = client.get(
            "/api/v1/approvals/pending",
            headers={"X-API-Key": "wrong_key"}
        )
        assert res_bad_auth.status_code == 401
        assert "Invalid API Key" in res_bad_auth.json()["detail"]

        # 3. Valid X-API-Key header -> 200 OK
        res_good_key = client.get(
            "/api/v1/approvals/pending",
            headers={"X-API-Key": "amber_prod_secret_token_123"}
        )
        assert res_good_key.status_code == 200

        # 4. Valid Authorization Bearer header -> 200 OK
        res_good_bearer = client.get(
            "/api/v1/approvals/pending",
            headers={"Authorization": "Bearer amber_prod_secret_token_123"}
        )
        assert res_good_bearer.status_code == 200

        # 5. /license/activate is also guarded
        res_act_no_auth = client.post("/api/v1/license/activate", json={"license_key": "some_key"})
        assert res_act_no_auth.status_code == 401
    finally:
        settings.AMBER_API_KEY = orig_key


def test_webhook_secret_verification():
    from unittest.mock import patch, AsyncMock
    client = TestClient(app)

    orig_secret = settings.WEBHOOK_SECRET
    try:
        settings.WEBHOOK_SECRET = "webhook_guard_secret_999"

        # 1. Missing webhook secret -> 401
        res_unauth = client.post("/api/v1/webhooks/prometheus", json={"alertname": "HighCPU"})
        assert res_unauth.status_code == 401

        # 2. Invalid webhook secret -> 401
        res_bad = client.post(
            "/api/v1/webhooks/prometheus",
            json={"alertname": "HighCPU"},
            headers={"X-Webhook-Secret": "wrong_secret"}
        )
        assert res_bad.status_code == 401

        # 3. Valid webhook secret -> 202 Accepted
        with patch("backend.app.api.v1.webhooks.process_alert_into_incident", new_callable=AsyncMock):
            res_ok = client.post(
                "/api/v1/webhooks/prometheus",
                json={"alertname": "HighCPU"},
                headers={"X-Webhook-Secret": "webhook_guard_secret_999"}
            )
            assert res_ok.status_code == 202
    finally:
        settings.WEBHOOK_SECRET = orig_secret


@pytest.mark.asyncio
async def test_incident_soft_delete_preserves_audit_trail():
    """Verify that deleting an incident soft-deletes it (status CANCELLED) to preserve SOC2 audit trail."""
    import uuid
    from backend.app.core.database import AsyncSessionLocal, Base, engine
    from backend.app.models.incident import Incident, IncidentStatus, IncidentSeverity
    from sqlalchemy import select

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        inc = Incident(
            title="Temporary Test Incident for Soft Delete",
            severity=IncidentSeverity.P3,
            status=IncidentStatus.TRIGGERED,
            source_service="billing-api"
        )
        session.add(inc)
        await session.commit()
        await session.refresh(inc)
        inc_id = inc.id

    client = TestClient(app)
    headers = {"X-API-Key": "test_amber_api_key_2026"}

    # Execute DELETE request
    res = client.delete(f"/api/v1/incidents/{inc_id}", headers=headers)
    assert res.status_code == 204

    # Verify incident still exists in database with status CANCELLED
    async with AsyncSessionLocal() as session:
        check_res = await session.execute(select(Incident).filter(Incident.id == inc_id))
        deleted_inc = check_res.scalar_one_or_none()
        assert deleted_inc is not None, "Incident was hard-deleted! SOC2 audit trail violated."
        assert deleted_inc.status == IncidentStatus.CANCELLED
        assert "ARCHIVED" in deleted_inc.description


@pytest.mark.asyncio
async def test_unregistered_approver_email_rejected_in_production(monkeypatch):
    """Verify that arbitrary spoofed X-Approver-Email is rejected in production if not in users table."""
    client = TestClient(app)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "AMBER_API_KEY", "prod_secret_key_123")

    headers = {
        "X-API-Key": "prod_secret_key_123",
        "X-Approver-Email": "fake_spoofed_ceo@targetcorp.com"
    }

    res = client.get("/api/v1/approvals/pending", headers=headers)
    assert res.status_code == 403
    assert "Unregistered approver identity" in res.json()["detail"]


@pytest.mark.asyncio
async def test_per_user_api_key_authentication():
    """Verify that scoped personal user API keys authenticate against users table without master key."""
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models.user import User, UserRole
    from backend.app.auth.security import hash_api_key

    import secrets
    import uuid

    # Dynamically generated mock tokens for test execution (prevents static scanner false positives)
    mock_dynamic_token = secrets.token_hex(16)
    key_hash = hash_api_key(mock_dynamic_token)
    unique_email = f"sre_user_{uuid.uuid4().hex[:8]}@example.internal"

    async with AsyncSessionLocal() as session:
        user = User(
            email=unique_email,
            full_name="Ephemeral Test SRE",
            role=UserRole.SRE,
            api_key_hash=key_hash,
            is_active=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    client = TestClient(app)

    # 1. Successful authentication using ephemeral mock API key
    res = client.get("/api/v1/approvals/pending", headers={"X-API-Key": mock_dynamic_token})
    assert res.status_code == 200

    # 2. Rejection of invalid ephemeral key
    invalid_token = secrets.token_hex(16)
    res_bad = client.get("/api/v1/approvals/pending", headers={"X-API-Key": invalid_token})
    assert res_bad.status_code == 401


