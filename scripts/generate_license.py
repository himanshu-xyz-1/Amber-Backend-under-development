#!/usr/bin/env python3
"""
Amber SRE Engine - Enterprise License Key Generator (Founder Tool)
Used by the founding team to cryptographically issue signed Ed25519 commercial license keys.
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

DEFAULT_KEY_PATH = Path(
    os.environ.get(
        "AMBER_MASTER_PRIVATE_KEY_PATH",
        Path.home() / ".amber_secrets" / "amber_master_private.pem"
    )
)

TIER_CONFIG = {
    "community": {
        "max_nodes": 15,
        "max_services": 20,
        "features": ["triage", "root_cause_analysis", "post_mortem", "read_only"]
    },
    "observe": {
        "max_nodes": 15,
        "max_services": 5,
        "features": ["triage", "root_cause_analysis", "post_mortem", "read_only"]
    },
    "autonomous": {
        "max_nodes": 100,
        "max_services": 35,
        "features": [
            "triage",
            "root_cause_analysis",
            "post_mortem",
            "slack_approvals",
            "telegram_bot",
            "auto_remediation",
            "hitl_sha256"
        ]
    },
    "response": {
        "max_nodes": 500,
        "max_services": 9999,
        "features": [
            "triage",
            "root_cause_analysis",
            "post_mortem",
            "slack_approvals",
            "telegram_bot",
            "auto_remediation",
            "hitl_sha256",
            "air_gapped_runtime",
            "priority_sla"
        ]
    },
    "agency": {
        "max_nodes": 500,
        "max_services": 150,
        "max_workspaces": 10,
        "features": [
            "triage",
            "root_cause_analysis",
            "post_mortem",
            "slack_approvals",
            "telegram_bot",
            "auto_remediation",
            "hitl_sha256",
            "white_label",
            "multi_tenant",
            "custom_domain",
            "sub_licensing"
        ]
    }
}


def load_master_private_key(key_path: Path) -> ed25519.Ed25519PrivateKey:
    if not key_path.exists():
        print(f"❌ Error: Master private key not found at {key_path}")
        print("Please generate it first before issuing licenses.")
        sys.exit(1)
    with open(key_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def generate_license(
    org: str,
    tier: str,
    days: int,
    custom_nodes: int = None,
    custom_services: int = None,
    key_path: Path = DEFAULT_KEY_PATH
) -> str:
    priv_key = load_master_private_key(key_path)

    tier_lower = tier.lower()
    if tier_lower not in TIER_CONFIG:
        print(f"❌ Invalid tier: {tier}. Must be one of: {list(TIER_CONFIG.keys())}")
        sys.exit(1)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=days)

    tier_defaults = TIER_CONFIG[tier_lower]
    max_nodes = custom_nodes or tier_defaults["max_nodes"]
    max_services = custom_services or tier_defaults["max_services"]

    payload = {
        "org": org,
        "tier": tier_lower,
        "max_nodes": max_nodes,
        "max_services": max_services,
        "features": tier_defaults["features"],
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "issuer": "Amber Technologies Inc."
    }

    payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")

    # Ed25519 Digital Signature
    signature = priv_key.sign(payload_json)
    signature_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")

    token = f"amb_live_{payload_b64}.{signature_b64}"
    return token, payload


def main():
    parser = argparse.ArgumentParser(description="Issue cryptographically signed Amber SRE Enterprise License Keys")
    parser.add_argument("--org", required=True, help="Organization / Client Name (e.g., 'Swiggy', 'Acme Corp')")
    parser.add_argument("--tier", default="autonomous", choices=["community", "observe", "autonomous", "response", "agency"], help="Subscription Tier")
    parser.add_argument("--days", type=int, default=30, help="License validity duration in days (e.g. 14, 30, 365)")
    parser.add_argument("--nodes", type=int, default=None, help="Custom node count override (optional)")

    args = parser.parse_args()

    token, payload = generate_license(
        org=args.org,
        tier=args.tier,
        days=args.days,
        custom_nodes=args.nodes
    )

    print("\n" + "=" * 68)
    print("🔑 AMBER ENTERPRISE LICENSE KEY GENERATED")
    print("=" * 68)
    print(f"Organization : {payload['org']}")
    print(f"Tier         : {payload['tier'].upper()}")
    print(f"Max Nodes    : {payload['max_nodes']}")
    print(f"Issued At    : {payload['issued_at']}")
    print(f"Expires At   : {payload['expires_at']} ({args.days} days)")
    print(f"Features     : {', '.join(payload['features'])}")
    print("-" * 68)
    print("Add this to the client's .env file:")
    print(f"\nAMBER_LICENSE_KEY={token}\n")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    main()
