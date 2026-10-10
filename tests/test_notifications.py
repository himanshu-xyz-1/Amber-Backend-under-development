from unittest.mock import patch

import pytest

from backend.app.integrations.dispatcher import dispatch_incident_notifications
from backend.app.integrations.slack import send_slack_incident_alert
from backend.app.integrations.telegram import send_telegram_incident_alert


@pytest.mark.asyncio
async def test_slack_notification_graceful_skip_when_unconfigured():
    # When SLACK_WEBHOOK_URL is None, should return False gracefully
    with patch("backend.app.integrations.slack.settings.SLACK_WEBHOOK_URL", None):
        result = await send_slack_incident_alert({"title": "Test Alert", "severity": "P1"})
        assert result is False


@pytest.mark.asyncio
async def test_telegram_notification_graceful_skip_when_unconfigured():
    # When TELEGRAM_BOT_TOKEN is None, should return False gracefully
    with patch("backend.app.integrations.telegram.settings.TELEGRAM_BOT_TOKEN", None):
        result = await send_telegram_incident_alert({"title": "Test Alert", "severity": "P1"})
        assert result is False


@pytest.mark.asyncio


@pytest.mark.asyncio
async def test_multi_channel_dispatcher_execution():
    incident = {
        "id": "inc-test-123",
        "title": "Postgres Pool Exhausted",
        "severity": "P0",
        "service": "billing-db",
        "root_cause_summary": "10 hanging idle in transaction queries",
        "timestamp": 1700000000
    }
    tool = {
        "id": "tool-test-456",
        "tool_name": "kill_db_connections",
        "tool_args": {"pids": [101, 102]},
        "payload_sha256": "abcdef1234567890",
        "risk_level": "HIGH"
    }

    status = await dispatch_incident_notifications(incident, tool)
    assert isinstance(status, dict)
    assert "slack" in status
    assert "telegram" in status
    assert "telegram" in status
