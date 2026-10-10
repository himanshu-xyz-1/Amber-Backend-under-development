#!/usr/bin/env python3
"""
Amber SRE Engine - Enterprise License Activation CLI Tool.
Enables instant interactive activation of Amber Enterprise commercial licenses.
"""

import os
import sys
import re
import argparse
import webbrowser

# Add project root to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.core.license import LicenseManager, license_manager

DEFAULT_CONTACT_URL = os.getenv("AMBER_CONTACT_URL", "https://ambersre.xyz/#connect")


def persist_license_to_env(key: str, env_path: str = ".env"):
    """Safely writes or updates AMBER_LICENSE_KEY in the specified .env file."""
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write(f"AMBER_LICENSE_KEY={key}\n")
        return

    with open(env_path, "r") as f:
        content = f.read()

    if re.search(r"^AMBER_LICENSE_KEY=.*", content, re.MULTILINE):
        new_content = re.sub(r"^AMBER_LICENSE_KEY=.*", f"AMBER_LICENSE_KEY={key}", content, flags=re.MULTILINE)
    else:
        new_content = content.rstrip() + f"\n\n# Amber Commercial License Key\nAMBER_LICENSE_KEY={key}\n"

    with open(env_path, "w") as f:
        f.write(new_content)


def show_status():
    """Prints current license state."""
    details = license_manager.get_license_details()
    if details["is_valid"]:
        print("\n" + "=" * 68)
        print(f"💎 AMBER ENTERPRISE ACTIVE: Licensed to '{details['org']}'")
        print(f"📦 Tier: {details['tier']} | Limit: {details['max_nodes']} Nodes, {details['max_services']} Services")
        print(f"⏳ Days Remaining: {details['days_remaining']} (Expires: {details['expires_at'][:10]})")
        print("⚡ Multi-Channel Engine: Slack, Telegram & HITL Approvals UNLOCKED")
        print("=" * 68 + "\n")
    else:
        print("\n" + "=" * 68)
        print("⚠️  AMBER COMMUNITY EDITION")
        print(f"ℹ️  Status: {details['error_message']}")
        print("🔒 Multi-Channel Notifications (Slack, Telegram) are LOCKED.")
        print(f"👉 GET YOUR KEY: {DEFAULT_CONTACT_URL}")
        print("=" * 68 + "\n")


def activate_key(token: str) -> bool:
    token = token.strip()
    validator = LicenseManager(token=token)

    if not validator.is_valid:
        print(f"\n❌ ACTIVATION FAILED: {validator.error_message}")
        print(f"👉 Need a valid key? Visit {DEFAULT_CONTACT_URL}\n")
        return False

    persist_license_to_env(token)
    license_manager.reload(token)

    print("\n" + "=" * 68)
    print("🎉 SUCCESS! AMBER ENTERPRISE ACTIVATED")
    print(f"🏢 Organization : {validator.org}")
    print(f"📦 Plan Tier    : {validator.tier.upper()}")
    print(f"💻 Node Quota   : {validator.max_nodes} Nodes")
    print(f"⏳ Valid For    : {validator.days_remaining} Days (Expires {validator.expires_at.strftime('%Y-%m-%d')})")
    print("🚀 All Multi-Channel SRE Bridges (Slack, Telegram) are now active!")
    print("=" * 68 + "\n")
    return True


def interactive_prompt():
    print("""
======================================================================
      ⚡ AMBER SRE ENGINE - ENTERPRISE LICENSE ACTIVATION ⚡
======================================================================
""")
    show_status()

    print("Please choose an option:")
    print("  [1] Enter / Paste your License Key")
    print("  [2] Get your License Key (Visit Website Contact Page)")
    print("  [3] Exit")
    print()

    choice = input("Enter choice [1/2/3]: ").strip()

    if choice == "1":
        key = input("\nPaste your AMBER_LICENSE_KEY (amb_live_...): ").strip()
        if not key:
            print("No key entered. Exiting.")
            sys.exit(1)
        activate_key(key)
    elif choice == "2":
        print(f"\n👉 Direct Contact URL: {DEFAULT_CONTACT_URL}")
        print("Opening in your browser...")
        try:
            webbrowser.open(DEFAULT_CONTACT_URL)
        except Exception:
            pass
        print("Once you receive your key, run this tool again to activate.\n")
    else:
        print("Exiting.")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Amber Enterprise License Activation Tool")
    parser.add_argument("--key", type=str, help="License key token (amb_live_...) to activate non-interactively")
    parser.add_argument("--status", action="store_true", help="Print current active license status")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.key:
        success = activate_key(args.key)
        sys.exit(0 if success else 1)

    interactive_prompt()


if __name__ == "__main__":
    main()
