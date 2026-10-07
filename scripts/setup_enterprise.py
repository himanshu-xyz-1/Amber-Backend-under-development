import os
import sys
from pathlib import Path
import random
import string
import secrets
from dotenv import set_key

# Import license verification
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.core.license import LicenseManager

BOLD = "\033[1m"
GREEN = "\033[0;32m"
CYAN = "\033[0;36m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"
DIM = "\033[2m"

def main():
    print(f"\n{BOLD}{CYAN}=== Amber SRE Engine (Commercial Edition) Setup ==={NC}")
    print(f"{DIM}Deterministic Incident Investigation, Root-Cause Proof & On-Call Automation{NC}\n")

    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text("")

    print(f"{BOLD}1. License Activation{NC}")
    license_key = input("   Enter your Commercial License Key (ey...): ").strip()
    
    if not license_key:
        print(f"\n{RED}❌ License key is required for the Commercial Edition.{NC}")
        print(f"To run the free version, use: {BOLD}./amber community{NC}\n")
        sys.exit(1)

    # Verify the key strictly
    manager = LicenseManager(key_string=license_key)
    if not manager.is_valid or manager.tier == "community":
        print(f"\n{RED}❌ Invalid, expired, or non-commercial license key.{NC}")
        print(f"Please contact sales@ambersre.xyz for support.\n")
        sys.exit(1)

    set_key(str(env_path), "AMBER_EDITION", "enterprise")
    set_key(str(env_path), "AMBER_LICENSE_KEY", license_key)
    
    jwt_secret = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
    set_key(str(env_path), "JWT_SECRET", jwt_secret)

    print(f"\n{GREEN}✔ Enterprise License Verified{NC}")
    print(f"  {BOLD}Org:{NC} {manager.org}")
    print(f"  {BOLD}Tier:{NC} {manager.tier.capitalize()}")
    print(f"  {BOLD}Node Quota:{NC} {manager.max_nodes}")

    print(f"\n{BOLD}2. Notification Setup{NC}")
    slack_webhook = input("   Slack Webhook URL (leave empty to skip): ").strip()
    if slack_webhook:
        set_key(str(env_path), "SLACK_WEBHOOK_URL", slack_webhook)
    
    # Webhook intake secret
    from dotenv import get_key
    webhook_secret = get_key(str(env_path), "WEBHOOK_SECRET")
    if not webhook_secret:
        webhook_secret = secrets.token_hex(16)
        set_key(str(env_path), "WEBHOOK_SECRET", webhook_secret)

    print(f"\n{GREEN}✔ Enterprise configuration saved to .env{NC}")

    print(f"\n{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")
    print(f"{CYAN}{BOLD}📡 AMBER WEBHOOK INTAKE ENDPOINTS (Add to your Monitoring Tools):{NC}")
    print(f"{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")
    print(f"  • {BOLD}Prometheus Alertmanager:{NC} http://localhost:8000/api/v1/webhooks/prometheus")
    print(f"  • {BOLD}Datadog Webhook:{NC}         http://localhost:8000/api/v1/webhooks/datadog")
    print(f"  • {BOLD}Grafana Contact Point:{NC}   http://localhost:8000/api/v1/webhooks/grafana")
    print(f"  • {BOLD}PagerDuty / Sentry:{NC}      http://localhost:8000/api/v1/webhooks/pagerduty")
    print(f"  • {BOLD}Generic Webhook:{NC}         http://localhost:8000/api/v1/webhooks/generic")
    print(f"\n  {YELLOW}Header (Required for webhook authentication in production):{NC}")
    print(f"  X-Webhook-Secret: {webhook_secret}")
    print(f"{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}\n")

    print(f"Next step: Run {BOLD}./amber start{NC} to boot the cluster.\n")

if __name__ == "__main__":
    main()
