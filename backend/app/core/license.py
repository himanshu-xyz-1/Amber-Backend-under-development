"""
Amber SRE Engine - Enterprise License Verification Module.
Cryptographically validates Ed25519-signed commercial license tokens offline.
"""

import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# Embedded Amber Technologies Master Public Key (Ed25519)
# Public verification key - Safe to include in open/source-available code.
AMBER_MASTER_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA1X0r2z+OlvE+422UsysC7IzRTTZCzdzQoiDYeijZChc=
-----END PUBLIC KEY-----"""


class LicenseManager:
    """
    Manages offline cryptographic verification of Amber Enterprise commercial licenses.
    """

    def __init__(self, token: str | None = None):
        import os
        self._raw_token = token
        self._public_key = serialization.load_pem_public_key(AMBER_MASTER_PUBLIC_KEY_PEM)
        self.is_valid: bool = False
        
        self.is_enterprise_mode = os.environ.get("AMBER_EDITION", "community").lower() == "enterprise"
        
        if self.is_enterprise_mode:
            self.status: str = "invalid"
            self.org: str = "Unlicensed Enterprise"
            self.tier: str = "none"
            self.max_nodes: int = 0
            self.max_services: int = 0
        else:
            self.status: str = "community"
            self.org: str = "Community Edition"
            self.tier: str = "community"
            self.max_nodes: int = 15
            self.max_services: int = 20
        self.features: list[str] = [
            "triage", 
            "read_only", 
            "alert_deduplication", 
            "root_cause_analysis", 
            "memory_leak_tracing", 
            "deadlock_detection", 
            "post_mortem_generator", 
            "standard_runbooks"
        ]
        self.expires_at: datetime | None = None
        self.days_remaining: int = 0
        self.error_message: str | None = None

        self._validate()

    def reload(self, token: str | None = None):
        self._raw_token = token
        self._validate()

    def _validate(self):
        self._public_key = serialization.load_pem_public_key(AMBER_MASTER_PUBLIC_KEY_PEM)
        token = self._raw_token if self._raw_token is not None else getattr(settings, "AMBER_LICENSE_KEY", None)

        if not token:
            self.is_valid = False
            self.status = "community"
            self.tier = "community"
            self.error_message = "No license key provided. Running in Community Edition."
            return

        if not token.startswith("amb_live_"):
            self.is_valid = False
            self.status = "invalid"
            self.error_message = "Malformed license key format (must start with 'amb_live_')."
            return

        body = token[len("amb_live_"):]
        parts = body.split(".")
        if len(parts) != 2:
            self.is_valid = False
            self.status = "invalid"
            self.error_message = "Malformed license key signature payload."
            return

        payload_b64, signature_b64 = parts

        try:
            # Reconstruct padding if needed
            pad_payload = payload_b64 + "=" * (-len(payload_b64) % 4)
            pad_sig = signature_b64 + "=" * (-len(signature_b64) % 4)

            payload_bytes = base64.urlsafe_b64decode(pad_payload)
            signature_bytes = base64.urlsafe_b64decode(pad_sig)

            # Cryptographic Verification
            self._public_key.verify(signature_bytes, payload_bytes)

            # Parse payload JSON
            payload = json.loads(payload_bytes.decode("utf-8"))

            expires_str = payload.get("expires_at")
            if not expires_str:
                self.is_valid = False
                self.status = "invalid"
                self.error_message = "License key missing expiration date."
                return

            expires_at = datetime.fromisoformat(expires_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            self.expires_at = expires_at
            now = datetime.now(timezone.utc)

            if now > expires_at:
                self.is_valid = False
                self.status = "expired"
                self.days_remaining = 0
                self.error_message = f"License key expired on {expires_at.strftime('%Y-%m-%d')}."
                return

            # License is valid and active!
            self.is_valid = True
            self.status = "active"
            self.org = payload.get("org", "Valued Enterprise Customer")
            self.tier = payload.get("tier", "autonomous").lower()
            self.max_nodes = payload.get("max_nodes", 200)
            self.max_services = payload.get("max_services", 35)
            self.features = payload.get("features", [])
            self.days_remaining = max(0, (expires_at - now).days)
            self.error_message = None

        except InvalidSignature:
            self.is_valid = False
            self.status = "invalid"
            self.error_message = "Cryptographic signature mismatch. License key has been tampered with."
        except Exception as e:
            self.is_valid = False
            self.status = "invalid"
            self.error_message = f"Failed to parse license key: {e}"

    def is_feature_enabled(self, feature: str) -> bool:
        """
        Check if a specific capability (e.g. 'telegram_bot', 'slack_approvals') is unlocked.
        """
        if not self.is_valid:
            return False
        return feature in self.features or "*" in self.features

    def check_infrastructure_limits(
        self,
        node_count: int | None = None,
        service_count: int | None = None
    ) -> tuple[bool, str | None]:
        """
        Enforces licensed node and service limits.
        """
        if node_count is not None and node_count > self.max_nodes:
            return False, f"Infrastructure node limit exceeded: {node_count} nodes detected (licensed max: {self.max_nodes})."
        if service_count is not None and service_count > self.max_services:
            return False, f"Service limit exceeded: {service_count} monitored services detected (licensed max: {self.max_services})."
        return True, None

    def get_license_details(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "status": self.status,
            "org": self.org,
            "tier": self.tier.upper(),
            "max_nodes": self.max_nodes,
            "max_services": self.max_services,
            "days_remaining": self.days_remaining,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "features": self.features,
            "error_message": self.error_message
        }

    def print_startup_banner(self):
        """Displays informative ASCII status banner at system boot."""
        contact_url = os.getenv("AMBER_CONTACT_URL", "https://ambersre.xyz")
        if self.is_valid:
            print("\n" + "=" * 70)
            print(f"💎 AMBER ENTERPRISE ACTIVE: Licensed to '{self.org}'")
            print(f"📦 Tier: {self.tier.upper()} | Limit: {self.max_nodes} Nodes, {self.max_services} Services")
            print(f"⏳ Validity: {self.days_remaining} Days Remaining (Expires {self.expires_at.strftime('%Y-%m-%d')})")
            print("⚡ Multi-Channel Engine: Slack, Telegram & HITL Approvals UNLOCKED")
            print("=" * 70 + "\n")
        else:
            print("\n" + "=" * 70)
            print("🌱 AMBER COMMUNITY EDITION (FREE FOREVER)")
            print(f"📦 Quota: Up to {self.max_nodes} Nodes | {self.max_services} Services")
            print(f"👉 Need > {self.max_nodes} nodes or automated 1-click rollbacks? Upgrade at {contact_url}")
            print("=" * 70 + "\n")


# Global singleton instance
license_manager = LicenseManager()
