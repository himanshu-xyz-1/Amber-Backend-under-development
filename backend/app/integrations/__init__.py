"""
Amber Integrations Module.
Exposes multi-channel alert dispatchers for Slack and Telegram.
"""

from .dispatcher import dispatch_incident_notifications
from .slack import send_slack_incident_alert
from .telegram import send_telegram_incident_alert

__all__ = [
    "dispatch_incident_notifications",
    "send_slack_incident_alert",
    "send_telegram_incident_alert",
]
