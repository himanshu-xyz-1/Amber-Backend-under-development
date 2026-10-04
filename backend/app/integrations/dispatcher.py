"""
Amber SRE - Multi-Channel Notification Dispatcher.
Coordinates concurrent broadcast of on-call incident notifications across Slack, Telegram, and WhatsApp.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from .slack import send_slack_incident_alert
from .telegram import send_telegram_incident_alert
from .whatsapp import send_whatsapp_incident_alert

logger = logging.getLogger(__name__)


async def dispatch_incident_notifications(
    incident_data: Dict[str, Any],
    tool_invocation: Optional[Dict[str, Any]] = None
) -> Dict[str, bool]:
    """
    Broadcasts incident alerts across all configured channels concurrently.
    Returns status map of channel deliveries.
    """
    from backend.app.core.config import settings
    from backend.app.core.license import license_manager

    # Air-Gapped Mode: Strictly suppress all external notification channels (zero egress)
    if settings.AIR_GAPPED:
        logger.info(
            "[AIR-GAPPED] Outbound external notifications (Slack, Telegram, WhatsApp) suppressed. "
            "Alert queued strictly for internal on-prem dashboard."
        )
        return {"slack": False, "telegram": False, "whatsapp": False}

    # License Enforcement: Check if enterprise channels are unlocked
    allow_slack = license_manager.is_feature_enabled("slack_approvals")
    allow_telegram = license_manager.is_feature_enabled("telegram_bot")
    allow_whatsapp = license_manager.is_feature_enabled("whatsapp_bridge")

    if not license_manager.is_valid:
        import os
        contact_url = os.getenv("AMBER_CONTACT_URL", "https://ambersre.xyz/#connect")
        logger.warning(
            "⚠️  [AMBER COMMUNITY EDITION] Multi-channel alerts (Slack, Telegram, WhatsApp) are locked.\n"
            f"👉 Visit {contact_url} to get your Enterprise License Key."
        )

    tasks = {}
    if allow_slack:
        tasks["slack"] = send_slack_incident_alert(incident_data, tool_invocation)
    else:
        logger.debug("Slack alerts locked: requires active Amber Enterprise license.")

    if allow_telegram:
        tasks["telegram"] = send_telegram_incident_alert(incident_data, tool_invocation)
    else:
        logger.debug("Telegram alerts locked: requires active Amber Enterprise license.")

    if allow_whatsapp:
        tasks["whatsapp"] = send_whatsapp_incident_alert(incident_data, tool_invocation)
    else:
        logger.debug("WhatsApp alerts locked: requires active Amber Enterprise license.")

    if not tasks:
        return {"slack": False, "telegram": False, "whatsapp": False}

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    status_map = {}
    for (channel, _), result in zip(tasks.items(), results):
        if isinstance(result, Exception):
            logger.error(f"Error dispatching to {channel}: {result}")
            status_map[channel] = False
        else:
            status_map[channel] = bool(result)

    active_sent = [k for k, v in status_map.items() if v]
    if active_sent:
        logger.info(f"Dispatched alerts for incident {incident_data.get('id')} to: {', '.join(active_sent)}")
    else:
        logger.debug(f"No external notification channels responded or configured for incident {incident_data.get('id')}")

    return status_map
