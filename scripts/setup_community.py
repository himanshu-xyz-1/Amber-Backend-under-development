import os
import sys
from pathlib import Path
import random
import string
import secrets
from dotenv import set_key

BOLD = "\033[1m"
GREEN = "\033[0;32m"
CYAN = "\033[0;36m"
YELLOW = "\033[1;33m"
NC = "\033[0m"
DIM = "\033[2m"

def main():
    print(f"\n{BOLD}{CYAN}=== Amber SRE Engine (Community Edition) Setup ==={NC}")
    print(f"{DIM}100% Self-Hosted • 15 Nodes • 5 Services • Local Ollama Compute • Zero License Key{NC}\n")

    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text("")

    set_key(str(env_path), "AMBER_EDITION", "community")
    set_key(str(env_path), "AMBER_LICENSE_KEY", "community_bypass")
    
    jwt_secret = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
    set_key(str(env_path), "JWT_SECRET", jwt_secret)

    print(f"{BOLD}1. Notification Setup{NC}")
    slack_webhook = input("   Slack Webhook URL (leave empty to skip): ").strip()
    if slack_webhook:
        set_key(str(env_path), "SLACK_WEBHOOK_URL", slack_webhook)
    
    tg_token = input("   Telegram Bot Token (leave empty to skip): ").strip()
    if tg_token:
        set_key(str(env_path), "TELEGRAM_BOT_TOKEN", tg_token)
        tg_chat = input("   Telegram Chat ID: ").strip()
        if tg_chat:
            set_key(str(env_path), "TELEGRAM_CHAT_ID", tg_chat)

    # Webhook intake secret
    from dotenv import get_key
    webhook_secret = get_key(str(env_path), "WEBHOOK_SECRET")
    if not webhook_secret:
        webhook_secret = secrets.token_hex(16)
        set_key(str(env_path), "WEBHOOK_SECRET", webhook_secret)

    print(f"\n{GREEN}✔ Community Edition configuration saved to .env{NC}")
    print(f"  {BOLD}Max Nodes:{NC} 15")
    print(f"  {BOLD}Max Services:{NC} 5")

    print(f"\n{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")
    print(f"{CYAN}{BOLD}📡 AMBER WEBHOOK INTAKE ENDPOINTS (Add to your Monitoring Tools):{NC}")
    print(f"{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")
    print(f"  • {BOLD}Prometheus Alertmanager:{NC} http://localhost:8000/api/v1/webhooks/prometheus")
    print(f"  • {BOLD}Datadog Webhook:{NC}         http://localhost:8000/api/v1/webhooks/datadog")
    print(f"  • {BOLD}Grafana Contact Point:{NC}   http://localhost:8000/api/v1/webhooks/grafana")
    print(f"  • {BOLD}PagerDuty / Sentry:{NC}      http://localhost:8000/api/v1/webhooks/pagerduty")
    print(f"  • {BOLD}Generic Webhook:{NC}         http://localhost:8000/api/v1/webhooks/generic")
    print(f"\n  {YELLOW}Header (Optional for local, required in prod):{NC}")
    print(f"  X-Webhook-Secret: {webhook_secret}")
    print(f"{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}\n")

    print(f"Next step: Run {BOLD}./amber start{NC} to boot the cluster.\n")

if __name__ == "__main__":
    main()
