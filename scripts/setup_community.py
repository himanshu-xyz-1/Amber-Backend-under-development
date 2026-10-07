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

    print(f"\n{GREEN}✔ Community Edition configuration saved to .env{NC}")
    print(f"  {BOLD}Max Nodes:{NC} 15")
    print(f"  {BOLD}Max Services:{NC} 5")
    print(f"\nNext step: Run {BOLD}./amber start{NC} to boot the cluster.\n")

if __name__ == "__main__":
    main()
