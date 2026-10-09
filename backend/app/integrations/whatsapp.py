"""
Amber SRE - WhatsApp Integration (via Twilio API).
Dispatches urgent SMS/WhatsApp on-call notifications for P0/P1 incidents requiring immediate attention.
"""

import logging
from typing import Any

import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


async def send_whatsapp_incident_alert(
    incident_data: dict[str, Any],
    tool_invocation: dict[str, Any] | None = None
) -> bool:
    """
    Sends an urgent WhatsApp message via Twilio API.
    Returns True if sent successfully, False otherwise.
    """
    severity = incident_data.get("severity", "P1")
    title = incident_data.get("title", "Infrastructure Incident")
    service = incident_data.get("service") or incident_data.get("source_service", "Unknown")
    root_cause = incident_data.get("root_cause_summary") or "Investigation active"
    incident_id = incident_data.get("id", "N/A")
    dashboard_url = settings.DASHBOARD_URL

    body_lines = [
        f"🚨 *Amber SRE Alert [{severity}]*",
        f"*Service:* {service}",
        f"*Title:* {title}",
        f"*Root Cause:* {root_cause}",
    ]

    if tool_invocation:
        tool_name = tool_invocation.get("tool_name", "action")
        approval_id = tool_invocation.get("id", "")
        body_lines.extend([
            f"*Proposed Action:* {tool_name}",
            f"*1-Click Approve:* {dashboard_url}?incident={incident_id}&action=approve&token={approval_id}"
        ])
    else:
        body_lines.append(f"*Dashboard:* {dashboard_url}?incident={incident_id}")

    message_body = "\n".join(body_lines)

    # 1. Prefer Self-Hosted QR Bridge if configured (Zero Cost, Zero Third-Party)
    if settings.WHATSAPP_BRIDGE_URL and settings.WHATSAPP_ALERT_TO:
        bridge_url = f"{settings.WHATSAPP_BRIDGE_URL.rstrip('/')}/send"
        clean_recipient = settings.WHATSAPP_ALERT_TO.replace("whatsapp:", "")
        payload = {
            "to": clean_recipient,
            "message": message_body
        }
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.post(bridge_url, json=payload)
                if resp.status_code == 200 and resp.json().get("success"):
                    logger.info(f"Dispatched WhatsApp alert via self-hosted QR bridge to {clean_recipient}")
                    return True
                else:
                    logger.warning(f"Self-hosted WhatsApp bridge failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.warning(f"Error communicating with self-hosted WhatsApp bridge: {e}")

    # 2. Fallback to Twilio WhatsApp if credentials exist
    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN
    from_number = settings.TWILIO_WHATSAPP_FROM
    to_number = settings.WHATSAPP_ALERT_TO

    if not all([account_sid, auth_token, from_number, to_number]):
        logger.debug("No WhatsApp provider configured (neither self-hosted bridge nor Twilio). Skipping.")
        return False

    api_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = {
        "From": from_number,
        "To": to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}",
        "Body": message_body
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                api_url,
                data=data,
                auth=(account_sid, auth_token)
            )
            if resp.status_code in [200, 201]:
                logger.info(f"Successfully dispatched WhatsApp alert via Twilio for Incident {incident_id}")
                return True
            else:
                logger.warning(f"Twilio returned non-200: {resp.status_code} - {resp.text}")
                return False
    except Exception as e:
        logger.warning(f"Failed to deliver WhatsApp alert via Twilio: {e}")
        return False
