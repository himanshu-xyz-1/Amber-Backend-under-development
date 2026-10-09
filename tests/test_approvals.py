import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.core.database import AsyncSessionLocal, Base, engine
from backend.app.models.incident import Incident, IncidentSeverity, IncidentStatus
from backend.app.models.tool_invocation import (
    InvocationStatus,
    RiskLevel,
    ToolInvocation,
)
from backend.app.services.approval_service import (
    ApprovalExecutionError,
    execute_tool_approval,
)


@pytest.mark.asyncio
async def test_execute_tool_approval_not_found():
    async with AsyncSessionLocal() as session:
        random_id = str(uuid.uuid4())
        with pytest.raises(ApprovalExecutionError) as exc_info:
            await execute_tool_approval(random_id, "approve", session)
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_execute_tool_approval_invalid_uuid():
    async with AsyncSessionLocal() as session:
        with pytest.raises(ApprovalExecutionError) as exc_info:
            await execute_tool_approval("invalid-uuid-format", "approve", session)
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_execute_tool_approval_lifecycle():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Create an incident
        incident = Incident(
            title="Database Connection Exhaustion",
            severity=IncidentSeverity.P1,
            status=IncidentStatus.PROPOSED,
            fingerprint="test-fp-1234",
            source_service="auth-db"
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)

        # Create a tool invocation
        tool_inv = ToolInvocation(
            incident_id=incident.id,
            tool_name="kill_db_connections",
            tool_args={"pids": [101], "mock": True},
            risk_level=RiskLevel.HIGH,
            status=InvocationStatus.PENDING_APPROVAL,
            payload_sha256="abc123sha",
            approval_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        session.add(tool_inv)
        await session.commit()
        await session.refresh(tool_inv)

        inv_id = str(tool_inv.id)

        # 1. Execute rejection test
        rejected = await execute_tool_approval(inv_id, "reject", session)
        assert rejected.status == InvocationStatus.REJECTED

        # 2. Re-open and execute approval test
        rejected.status = InvocationStatus.PENDING_APPROVAL
        await session.commit()

        # Approval without payload_sha256 must be rejected with 403
        with pytest.raises(ApprovalExecutionError) as exc_info:
            await execute_tool_approval(inv_id, "approve", session)
        assert exc_info.value.status_code == 403

        # Approval with matching payload_sha256 succeeds
        approved = await execute_tool_approval(inv_id, "approve", session, payload_sha256="abc123sha")
        assert approved.status == InvocationStatus.EXECUTED
        assert approved.health_check_passed is True
        assert approved.execution_result is not None


def test_audit_api_json_and_text_export():
    from fastapi.testclient import TestClient

    from backend.app.core.config import settings
    from backend.app.main import app

    client = TestClient(app)
    headers = {"X-API-Key": settings.AMBER_API_KEY}

    # 1. JSON audit fetch
    res_json = client.get("/api/v1/approvals/audit?limit=5&format=json", headers=headers)
    assert res_json.status_code == 200
    data = res_json.json()
    assert "audit_trail" in data
    assert "total" in data
    assert data["limit"] == 5
    assert isinstance(data["audit_trail"], list)

    # 2. Text audit fetch
    res_text = client.get("/api/v1/approvals/audit?limit=5&format=text", headers=headers)
    assert res_text.status_code == 200
    assert "AMBER SRE AUDIT LOG TRAIL" in res_text.text

    # 3. File download test
    res_dl = client.get("/api/v1/approvals/audit?limit=5&format=json&download=true", headers=headers)
    assert res_dl.status_code == 200
    assert "attachment; filename=" in res_dl.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_telegram_audit_command_and_document_download(monkeypatch):
    from backend.app.integrations.telegram_bot import (
        handle_audit_command,
        handle_telegram_callback,
    )

    sent_messages = []
    sent_documents = []

    async def mock_send_reply(token, chat_id, text, reply_markup=None):
        sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return {"ok": True}

    async def mock_send_doc(token, chat_id, filename, content, caption=None):
        sent_documents.append({"chat_id": chat_id, "filename": filename, "content": content, "caption": caption})
        return {"ok": True}

    async def mock_answer_cb(token, cb_id, text=None):
        return {"ok": True}

    monkeypatch.setattr("backend.app.integrations.telegram_bot._is_authorized_admin", lambda cid: True)
    monkeypatch.setattr("backend.app.integrations.telegram_bot.send_telegram_reply", mock_send_reply)
    monkeypatch.setattr("backend.app.integrations.telegram_bot.send_telegram_document", mock_send_doc)
    monkeypatch.setattr("backend.app.integrations.telegram_bot.answer_callback_query", mock_answer_cb)

    # Test /audit 15 command
    await handle_audit_command("mock_token", 12345678, "/audit 15")
    assert len(sent_messages) == 1
    assert "AMBER AUDIT TRAIL" in sent_messages[0]["text"]
    assert sent_messages[0]["reply_markup"] is not None

    # Test callback for JSON download
    cb_json = {
        "id": "cb_001",
        "data": "audit_dl:json:15",
        "message": {"chat": {"id": 12345678}},
        "from": {"id": 12345678, "username": "admin_sre"}
    }
    await handle_telegram_callback(cb_json, "mock_token")
    assert len(sent_documents) == 1
    assert sent_documents[0]["filename"].endswith(".json")

    # Test callback for Text log download
    cb_text = {
        "id": "cb_002",
        "data": "audit_dl:text:15",
        "message": {"chat": {"id": 12345678}},
        "from": {"id": 12345678, "username": "admin_sre"}
    }
    await handle_telegram_callback(cb_text, "mock_token")
    assert len(sent_documents) == 2
    assert sent_documents[1]["filename"].endswith(".log")


