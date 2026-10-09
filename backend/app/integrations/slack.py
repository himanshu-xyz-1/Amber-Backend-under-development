"""
Amber SRE - Slack Integration.
Dispatches interactive Block Kit cards for incident triage and HITL approvals via Incoming Webhooks.
"""

import logging
from typing import Any

import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


async def send_slack_incident_alert(
    incident_data: dict[str, Any],
    tool_invocation: dict[str, Any] | None = None
) -> bool:
    """
    Sends an urgent incident notification with rich Block Kit formatting to configured Slack webhook.
    Returns True if sent successfully, False otherwise.
    """
    webhook_url = settings.SLACK_WEBHOOK_URL
    if not webhook_url:
        logger.debug("Slack webhook URL not configured, skipping Slack alert.")
        return False

    severity = incident_data.get("severity", "P1")
    title = incident_data.get("title", "Infrastructure Incident Detected")
    service = incident_data.get("service") or incident_data.get("source_service", "Unknown Service")
    root_cause = incident_data.get("root_cause_summary") or "Automated investigation in progress."
    incident_id = incident_data.get("id", "N/A")
    dashboard_url = settings.DASHBOARD_URL

    # Severity emoji mapping
    sev_emoji = {
        "P0": "🚨 *[P0 - CATASTROPHIC OUTAGE]*",
        "P1": "🔥 *[P1 - CRITICAL INCIDENT]*",
        "P2": "⚠️ *[P2 - MAJOR DEGRADATION]*",
        "P3": "⚡ *[P3 - MINOR ANOMALY]*",
        "P4": "ℹ️ *[P4 - INFORMATIONAL]*",
    }.get(severity, f"⚠️ *[{severity}]*")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Amber SRE Alert: {service}",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{sev_emoji}\n*{title}*"
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Service:*\n`{service}`"},
                {"type": "mrkdwn", "text": f"*Status:*\n`{incident_data.get('status', 'TRIGGERED')}`"},
                {"type": "mrkdwn", "text": f"*Incident ID:*\n`{incident_id}`"},
                {"type": "mrkdwn", "text": f"*Triggered At:*\n<!date^{int(incident_data.get('timestamp', 0))}^" + "{time}|Just now>"}
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🔍 AI Root Cause Diagnosis:*\n>{root_cause}"
            }
        }
    ]

    # If action requires approval, add High-Risk Remediations Block
    if tool_invocation:
        tool_name = tool_invocation.get("tool_name", "remediation_tool")
        tool_args = tool_invocation.get("tool_args", {})
        sha256 = tool_invocation.get("payload_sha256", "N/A")
        approval_id = tool_invocation.get("id", "")

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*⚡ Proposed Mutating Action (Human-In-The-Loop Required):*\n"
                    f"• *Tool:* `{tool_name}`\n"
                    f"• *Parameters:* `{tool_args}`\n"
                    f"• *Cryptographic Token Hash:* `{sha256[:16]}...` (10m TTL)"
                )
            }
        })
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ 1-Click Approve (Web)", "emoji": True},
                    "style": "primary",
                    "url": f"{dashboard_url}?incident={incident_id}&action=approve&token={approval_id}"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔍 View Deep Proof", "emoji": True},
                    "url": f"{dashboard_url}?incident={incident_id}"
                }
            ]
        })
    else:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📊 Open Incident Dashboard", "emoji": True},
                    "url": f"{dashboard_url}?incident={incident_id}"
                }
            ]
        })

    payload = {
        "username": "Amber SRE",
        "icon_url": "https://ambersre.xyz/favicon.png",
        "text": f"Amber SRE Alert [{severity}]: {title}",
        "blocks": blocks
    }

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code == 200:
                logger.info(f"Successfully dispatched Slack alert for Incident {incident_id}")
                return True
            else:
                logger.warning(f"Slack webhook returned non-200 status: {resp.status_code} - {resp.text}")
                return False
    except Exception as e:
        logger.warning(f"Failed to deliver Slack webhook: {e}")
        return False


async def send_slack_test_ping(
    webhook_url: str,
    client_name: str,
    company: str,
    tier: str = "Community"
) -> tuple[bool, str | None]:
    """
    Sends an immediate test ping card to verify the Slack Webhook URL during setup.
    Returns (success, error_or_message).
    """
    if not webhook_url or not webhook_url.startswith("https://hooks.slack.com/"):
        return False, "Invalid Slack Webhook URL. It must begin with https://hooks.slack.com/"

    payload = {
        "username": "Amber SRE",
        "icon_url": "https://ambersre.xyz/favicon.png",
        "text": "⚡ Amber SRE Alert Channel Paired Successfully!",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚡ Amber SRE Alert Channel Paired!",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Client:*\n{client_name}"},
                    {"type": "mrkdwn", "text": f"*Company:*\n{company}"},
                    {"type": "mrkdwn", "text": f"*Tier:*\n{tier.upper()}"},
                    {"type": "mrkdwn", "text": "*Status:*\nActive & Monitoring 🟢"}
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "This channel is now connected to receive real-time production incident alerts and root-cause proofs."
                    }
                ]
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(webhook_url.strip(), json=payload)
            if resp.status_code == 200:
                return True, "Test alert delivered to Slack."
            else:
                return False, f"Slack webhook returned HTTP {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, f"Slack connection failed: {e}"

