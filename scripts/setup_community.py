#!/usr/bin/env python3
"""
Amber SRE Engine — Free Community Edition Setup Wizard
100% Self-Hosted • 15 Nodes • 20 Services • Slack-Only • Zero License Key Required
"""

import os
import sys
import shutil
import secrets
import string
import subprocess
import webbrowser
from pathlib import Path
from dotenv import set_key, get_key

# ANSI Colors
BOLD = "\033[1m"
GREEN = "\033[0;32m"
CYAN = "\033[0;36m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"
DIM = "\033[2m"

def print_banner():
    print(f"\n{BOLD}{CYAN}======================================================================{NC}")
    print(f"{BOLD}{CYAN}  ⚡ AMBER SRE ENGINE — COMMUNITY EDITION SETUP{NC}")
    print(f"  {DIM}100% Free Forever • 15 Nodes • 20 Services • Slack Alerts • Zero License Key{NC}")
    print(f"{BOLD}{CYAN}======================================================================{NC}\n")

def check_dependencies():
    print(f"{BOLD}1. Checking System Dependencies...{NC}")
    deps = {
        "Python (3.10+)": sys.version_info >= (3, 10),
        "Docker": shutil.which("docker") is not None,
        "Docker Compose": shutil.which("docker") is not None and subprocess.run(["docker", "compose", "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0,
        "Curl": shutil.which("curl") is not None,
        "Git": shutil.which("git") is not None,
    }
    
    all_ok = True
    for name, ok in deps.items():
        if ok:
            print(f"  {GREEN}[✔ INSTALLED]{NC} {name}")
        else:
            print(f"  {RED}[✖ MISSING]{NC}   {name}")
            all_ok = False
            
    if not all_ok:
        print(f"\n{YELLOW}⚠️  Some recommended tools are missing. Please ensure Docker is running for cluster services.{NC}")
    else:
        print(f"  {GREEN}✔ All core dependencies verified.{NC}")
    print("")

def configure_env():
    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text("")

    set_key(str(env_path), "AMBER_EDITION", "community")
    set_key(str(env_path), "AMBER_MAX_NODES", "15")
    set_key(str(env_path), "AMBER_MAX_SERVICES", "20")
    set_key(str(env_path), "AMBER_LICENSE_KEY", "community_bypass")

    jwt_secret = get_key(str(env_path), "JWT_SECRET")
    if not jwt_secret:
        jwt_secret = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
        set_key(str(env_path), "JWT_SECRET", jwt_secret)

    webhook_secret = get_key(str(env_path), "WEBHOOK_SECRET")
    if not webhook_secret:
        webhook_secret = secrets.token_hex(16)
        set_key(str(env_path), "WEBHOOK_SECRET", webhook_secret)

    return env_path, webhook_secret

def setup_slack(env_path):
    print(f"{BOLD}2. Slack Alert Notification Setup (Community Tier: Slack-Only){NC}")
    print(f"  {DIM}Amber sends Root-Cause Analysis (RCA) and alert summaries directly to your Slack channel.{NC}")
    print(f"  Steps:")
    print(f"    1. Go to {CYAN}https://api.slack.com/apps{NC} -> Click 'Create New App' -> 'From scratch'.")
    print(f"    2. Click 'Incoming Webhooks' -> Activate it -> Click 'Add New Webhook to Workspace'.")
    print(f"    3. Copy the Webhook URL and paste it below.\n")

    slack_url = input(f"  Enter Slack Webhook URL (press Enter to skip): ").strip()
    if slack_url:
        set_key(str(env_path), "SLACK_WEBHOOK_URL", slack_url)
        print(f"  {GREEN}✔ Slack Webhook configured with official Amber branding.{NC}\n")
    else:
        print(f"  {YELLOW}ℹ Slack skipped. You can configure it later in .env{NC}\n")

def setup_ollama():
    print(f"{BOLD}3. Local AI Engine Setup (Ollama){NC}")
    ollama_path = shutil.which("ollama")
    if ollama_path:
        print(f"  {GREEN}[✔ INSTALLED]{NC} Local Ollama engine detected.")
    else:
        print(f"  {YELLOW}ℹ Ollama not found on host. Amber will run Ollama automatically inside Docker.{NC}")
    print("")

def select_monitoring_stack(webhook_secret):
    print(f"{BOLD}4. Which Monitoring & Observability Stack do you use?{NC}")
    print("  1) Datadog")
    print("  2) Prometheus / Alertmanager")
    print("  3) Grafana Alerting")
    print("  4) AWS CloudWatch")
    print("  5) Generic / Other")
    
    choice = input("\n  Select your primary stack [1-5] (default: 1): ").strip() or "1"
    print("")

    print(f"{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")
    print(f"{CYAN}{BOLD}📡 YOUR DEDICATED WEBHOOK CONFIGURATION GUIDE:{NC}")
    print(f"{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")

    if choice == "1":
        print(f"{BOLD}▶ DATADOG WEBHOOK SETUP:{NC}")
        print(f"  1. In Datadog, go to {CYAN}Integrations{NC} -> Search {CYAN}Webhooks{NC}.")
        print(f"  2. Click 'New Webhook' and set:")
        print(f"     • Name: {BOLD}amber-sre{NC}")
        print(f"     • URL:  {BOLD}http://<your-host>:8000/api/v1/webhooks/datadog{NC}")
        print(f"     • Custom Headers (JSON):")
        print(f'       {{"X-Webhook-Secret": "{webhook_secret}"}}')
        print(f"  3. Add {BOLD}@webhook-amber-sre{NC} to your Datadog Monitors alert message.")

    elif choice == "2":
        print(f"{BOLD}▶ PROMETHEUS / ALERTMANAGER SETUP:{NC}")
        print(f"  Add the following receiver to your {BOLD}alertmanager.yml{NC}:")
        print(f"""
  receivers:
    - name: 'amber-sre'
      webhook_configs:
        - url: 'http://<your-host>:8000/api/v1/webhooks/prometheus'
          send_resolved: true
          http_config:
            bearer_token: '{webhook_secret}'
""")

    elif choice == "3":
        print(f"{BOLD}▶ GRAFANA ALERTING SETUP:{NC}")
        print(f"  1. Go to {CYAN}Alerting{NC} -> {CYAN}Contact Points{NC} -> Click 'Add contact point'.")
        print(f"  2. Integration: Select {BOLD}Webhook{NC}.")
        print(f"  3. URL: {BOLD}http://<your-host>:8000/api/v1/webhooks/grafana{NC}")
        print(f"  4. Optional Header:")
        print(f"     Header: X-Webhook-Secret | Value: {webhook_secret}")

    elif choice == "4":
        print(f"{BOLD}▶ AWS CLOUDWATCH SETUP:{NC}")
        print(f"  1. Create an Amazon SNS Topic (e.g. 'amber-cloudwatch-alerts').")
        print(f"  2. Add an HTTPS Subscription:")
        print(f"     • Endpoint: {BOLD}http://<your-host>:8000/api/v1/webhooks/generic{NC}")
        print(f"  3. Route CloudWatch Alarms to this SNS topic.")

    else:
        print(f"{BOLD}▶ GENERIC WEBHOOK SETUP:{NC}")
        print(f"  Endpoint: {BOLD}http://<your-host>:8000/api/v1/webhooks/generic{NC}")
        print(f"  Method:   {BOLD}POST{NC}")
        print(f"  Header:   X-Webhook-Secret: {webhook_secret}")

    print(f"{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}\n")

def main():
    print_banner()
    check_dependencies()
    env_path, webhook_secret = configure_env()
    setup_slack(env_path)
    setup_ollama()
    select_monitoring_stack(webhook_secret)

    print(f"{GREEN}{BOLD}======================================================================{NC}")
    print(f"{GREEN}{BOLD}  ✔ AMBER COMMUNITY EDITION CONFIGURATION COMPLETE!{NC}")
    print(f"  Capacity: Up to {BOLD}15 Nodes • 20 Services{NC} (Free Forever)")
    print(f"  To start all services now, run: {BOLD}./amber start{NC}")
    print(f"{GREEN}{BOLD}======================================================================{NC}\n")

    # The Community Growth Hook (Star on GitHub)
    print(f"{YELLOW}{BOLD}⭐ Enjoying Amber Community Edition?{NC}")
    print(f"Please consider giving us a star on GitHub: {CYAN}https://github.com/himanshu-xyz-1/Amber-Backend-under-development{NC}")
    print(f"Opening GitHub in your browser...\n")

    try:
        webbrowser.open("https://github.com/himanshu-xyz-1/Amber-Backend-under-development")
    except Exception:
        pass

if __name__ == "__main__":
    main()
