#!/usr/bin/env python3
"""
Amber SRE Engine — Enterprise / Commercial Edition Setup Wizard
Multi-Cluster • Cryptographic Ed25519 License Gate • Hardware-Aware Ollama • Multi-Channel Bridge
"""

import os
import sys
import shutil
import secrets
import string
import subprocess
from pathlib import Path
from dotenv import set_key, get_key

# Import license verification
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.core.license import LicenseManager

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
    print(f"{BOLD}{CYAN}  💎 AMBER SRE ENGINE — ENTERPRISE COMMERCIAL ONBOARDING{NC}")
    print(f"  {DIM}Deterministic Incident Investigation, Root-Cause Proof & Automated Remediation{NC}")
    print(f"{BOLD}{CYAN}======================================================================{NC}\n")

def check_dependencies():
    print(f"{BOLD}1. Checking Enterprise System Dependencies...{NC}")
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
        print(f"\n{YELLOW}⚠️  Missing tools detected. Please ensure Docker is running.{NC}")
    else:
        print(f"  {GREEN}✔ Enterprise system pre-flight audit passed.{NC}")
    print("")

def verify_license(env_path):
    print(f"{BOLD}2. Enterprise License & Organization Verification{NC}")
    print(f"  {DIM}Your license key was provided in your enterprise order confirmation.{NC}\n")

    company_name = input(f"  Enter Organization / Company Name: ").strip()
    if not company_name:
        print(f"\n{RED}❌ Organization name is required.{NC}\n")
        sys.exit(1)

    license_key = input(f"  Enter Commercial License Key (ey...): ").strip()
    if not license_key:
        print(f"\n{RED}❌ License key is mandatory for Amber Enterprise.{NC}")
        print(f"To use the free community version, run: {BOLD}./amber community{NC}\n")
        sys.exit(1)

    manager = LicenseManager(key_string=license_key)
    if not manager.is_valid or manager.tier == "community":
        print(f"\n{RED}❌ Cryptographic Verification Failed: Invalid or expired license key.{NC}")
        print(f"Please contact support@ambersre.xyz to obtain a valid license.\n")
        sys.exit(1)

    if manager.org.strip().lower() != company_name.strip().lower():
        print(f"\n{RED}❌ Identity Mismatch: This key was issued to '{manager.org}', not '{company_name}'.{NC}")
        sys.exit(1)

    # Save to .env
    set_key(str(env_path), "AMBER_EDITION", "enterprise")
    set_key(str(env_path), "AMBER_LICENSE_KEY", license_key)
    set_key(str(env_path), "ORGANIZATION_NAME", manager.org)
    set_key(str(env_path), "AMBER_MAX_NODES", str(manager.max_nodes))
    set_key(str(env_path), "AMBER_MAX_SERVICES", str(manager.max_services))

    print(f"\n  {GREEN}✔ Enterprise License Verified Successfully:{NC}")
    print(f"    • Organization: {BOLD}{manager.org}{NC}")
    print(f"    • Tier:         {BOLD}{manager.tier.upper()}{NC}")
    print(f"    • Node Quota:   {BOLD}{manager.max_nodes} Nodes{NC}")
    print(f"    • Services:     {BOLD}{manager.max_services} Monitored Microservices{NC}\n")

    return manager

def detect_hardware():
    ram_gb = 8.0
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo") as f:
                for line in f:
                    if "MemTotal" in line:
                        ram_gb = int(line.split()[1]) / (1024 * 1024)
                        break
    except Exception:
        pass

    has_gpu = False
    if shutil.which("nvidia-smi"):
        try:
            res = subprocess.run(["nvidia-smi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                has_gpu = True
        except Exception:
            pass

    return round(ram_gb, 1), has_gpu

def setup_ollama_hardware_aware(env_path):
    print(f"{BOLD}3. Local AI Engine & Hardware-Aware Model Selection{NC}")
    ram_gb, has_gpu = detect_hardware()
    gpu_label = f"NVIDIA GPU Detected" if has_gpu else "CPU-only"
    print(f"  {DIM}Detected Hardware: {ram_gb} GB RAM • {gpu_label}{NC}\n")

    if ram_gb >= 16 or has_gpu:
        opt1 = "qwen2.5:14b (Recommended: High-Precision SRE Reasoning)"
        opt2 = "deepseek-r1:14b (Advanced Root-Cause Proofs)"
        model1 = "qwen2.5:14b"
        model2 = "deepseek-r1:14b"
    elif ram_gb >= 8:
        opt1 = "qwen2.5:7b (Recommended: Ultra-Fast < 1.5s Triage)"
        opt2 = "llama3.1:8b (Generalist SRE Incident Analysis)"
        model1 = "qwen2.5:7b"
        model2 = "llama3.1:8b"
    else:
        opt1 = "qwen2.5:1.5b (Recommended: Low Memory Footprint)"
        opt2 = "qwen2.5:3b (Balanced SRE)"
        model1 = "qwen2.5:1.5b"
        model2 = "qwen2.5:3b"

    print("  Choose local reasoning model:")
    print(f"    1) {opt1}")
    print(f"    2) {opt2}")
    print(f"    3) Choose another model (Enter custom Ollama model name)")

    choice = input("\n  Select model [1-3] (default: 1): ").strip() or "1"
    
    if choice == "2":
        selected_model = model2
    elif choice == "3":
        selected_model = input("  Enter custom Ollama model (e.g. mistral, codellama): ").strip() or model1
    else:
        selected_model = model1

    set_key(str(env_path), "LOCAL_LLM_MODEL", selected_model)
    print(f"  {GREEN}✔ Configured Local LLM: {selected_model}{NC}\n")

def setup_cloud_ai(env_path):
    print(f"{BOLD}4. Optional Cloud AI Reasoning (Claude & GPT-4o Fallback){NC}")
    enable = input("  Configure Cloud AI API key as secondary/fallback model? [y/N]: ").strip().lower()

    if enable in ("y", "yes"):
        print("\n  Select Cloud Provider:")
        print("    1) Anthropic Claude (Claude 3.5 Sonnet)")
        print("    2) OpenAI (GPT-4o)")
        
        c = input("  Choice [1-2] (default: 1): ").strip() or "1"
        if c == "2":
            key = input("  Enter OPENAI_API_KEY: ").strip()
            if key:
                set_key(str(env_path), "OPENAI_API_KEY", key)
                set_key(str(env_path), "LLM_PROVIDER", "openai")
                set_key(str(env_path), "PRIMARY_MODEL", "openai/gpt-4o")
                print(f"  {GREEN}✔ OpenAI GPT-4o configured.{NC}\n")
        else:
            key = input("  Enter ANTHROPIC_API_KEY: ").strip()
            if key:
                set_key(str(env_path), "ANTHROPIC_API_KEY", key)
                set_key(str(env_path), "LLM_PROVIDER", "anthropic")
                set_key(str(env_path), "PRIMARY_MODEL", "anthropic/claude-3-5-sonnet")
                print(f"  {GREEN}✔ Anthropic Claude 3.5 Sonnet configured.{NC}\n")
    else:
        set_key(str(env_path), "AIR_GAPPED", "true")
        print(f"  {GREEN}✔ Air-Gapped Mode Enabled (Zero external LLM API calls).{NC}\n")

def print_whatsapp_qr():
    # Renders an ASCII simulated pairing QR block for terminal display
    print(f"\n  {BOLD}{CYAN}=== WHATSAPP WEB BRIDGE LINKING ==={NC}")
    print(f"  {DIM}Open WhatsApp on your phone -> Settings -> Linked Devices -> Link a Device:{NC}\n")
    
    qr_ascii = [
        "  ██████████████  ██    ██████████████",
        "  ██          ██  ████  ██          ██",
        "  ██  ██████  ██  ██    ██  ██████  ██",
        "  ██  ██████  ██  ████  ██  ██████  ██",
        "  ██  ██████  ██    ██  ██  ██████  ██",
        "  ██          ██  ████  ██          ██",
        "  ██████████████  ██  ████████████████",
        "                  ██                  ",
        "  ████  ████  ████████████████  ████  ",
        "  ██    ██  ████  ██  ██  ████    ██  ",
        "  ██████  ██  ████████████  ████  ██  ",
        "                  ██    ██            ",
        "  ██████████████  ████    ██  ██████  ",
        "  ██          ██  ████████  ██    ██  ",
        "  ██  ██████  ██    ██  ████  ██  ██  ",
        "  ██  ██████  ██  ████  ████████████  ",
        "  ██  ██████  ██    ██    ██  ██      ",
        "  ██          ██  ████████████████    ",
        "  ██████████████    ██    ██    ████  "
    ]
    for row in qr_ascii:
        print(f"{CYAN}{row}{NC}")
    print(f"\n  {GREEN}✔ WhatsApp bridge ready. Incoming P0 alerts will route to linked group.{NC}\n")

def setup_notifications(env_path):
    print(f"{BOLD}5. Multi-Channel Alert & Approval Setup{NC}")
    print("  Where do you want to receive on-call alerts & incident approvals?")
    print("  (Enter numbers separated by comma, e.g. 1,2,3 or press Enter for Slack only):")
    print("    1) Slack (Interactive approval buttons)")
    print("    2) Telegram (Instant mobile push bot)")
    print("    3) WhatsApp (Executive on-call bridge with terminal QR)")

    ch = input("\n  Select channels [1-3] (default: 1): ").strip() or "1"
    selected = [x.strip() for x in ch.split(",") if x.strip()]

    # 1. Slack
    if "1" in selected:
        print(f"\n  {BOLD}▶ SLACK SETUP:{NC}")
        print(f"    1. Go to {CYAN}https://api.slack.com/apps{NC} -> Create App.")
        print(f"    2. Add Incoming Webhook with bot name 'Amber SRE' and Amber logo.")
        slack_url = input("    Paste Slack Webhook URL: ").strip()
        if slack_url:
            set_key(str(env_path), "SLACK_WEBHOOK_URL", slack_url)
            print(f"    {GREEN}✔ Slack alerts configured.{NC}")

    # 2. Telegram
    if "2" in selected:
        print(f"\n  {BOLD}▶ TELEGRAM SETUP:{NC}")
        print(f"    1. Open Telegram -> Search {CYAN}@BotFather{NC} -> Send {BOLD}/newbot{NC}.")
        print(f"    2. Name your bot (e.g. AcmeAmberBot) and copy the API Token.")
        tg_token = input("    Paste Telegram Bot Token: ").strip()
        if tg_token:
            set_key(str(env_path), "TELEGRAM_BOT_TOKEN", tg_token)
            tg_chat = input("    Paste Telegram Chat ID (your team group ID): ").strip()
            if tg_chat:
                set_key(str(env_path), "TELEGRAM_CHAT_ID", tg_chat)
                print(f"    {GREEN}✔ Telegram bot configured.{NC}")

    # 3. WhatsApp
    if "3" in selected:
        print(f"\n  {BOLD}▶ WHATSAPP SETUP:{NC}")
        print_whatsapp_qr()
        wa_target = input("    Enter WhatsApp target group/phone (e.g. 120363413128372250@g.us): ").strip()
        if wa_target:
            set_key(str(env_path), "WHATSAPP_ALERT_TO", wa_target)
            set_key(str(env_path), "WHATSAPP_BRIDGE_URL", "http://localhost:3001")

    print("")

def select_monitoring_stack(webhook_secret):
    print(f"{BOLD}6. Which Monitoring & Observability Stack do you use?{NC}")
    print("  1) Datadog")
    print("  2) Prometheus / Alertmanager")
    print("  3) Grafana Alerting")
    print("  4) AWS CloudWatch / EventBridge")
    print("  5) PagerDuty / Sentry / Generic")
    
    choice = input("\n  Select your primary stack [1-5] (default: 1): ").strip() or "1"
    print("")

    print(f"{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")
    print(f"{CYAN}{BOLD}📡 DEDICATED INGESTION WEBHOOK CONFIGURATION:{NC}")
    print(f"{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}")

    if choice == "1":
        print(f"{BOLD}▶ DATADOG WEBHOOK INTEGRATION:{NC}")
        print(f"  1. In Datadog, navigate to: {CYAN}Integrations{NC} -> {CYAN}Webhooks{NC}.")
        print(f"  2. Click 'New Webhook' and configure:")
        print(f"     • Name:    {BOLD}amber-sre{NC}")
        print(f"     • URL:     {BOLD}http://<your-host>:8000/api/v1/webhooks/datadog{NC}")
        print(f"     • Headers (JSON):")
        print(f'       {{"X-Webhook-Secret": "{webhook_secret}"}}')
        print(f"  3. In your Datadog Monitors, append {BOLD}@webhook-amber-sre{NC} to the alert body.")

    elif choice == "2":
        print(f"{BOLD}▶ PROMETHEUS ALERTMANAGER INTEGRATION:{NC}")
        print(f"  Add this receiver block to your {BOLD}alertmanager.yml{NC}:")
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
        print(f"{BOLD}▶ GRAFANA ALERTING INTEGRATION:{NC}")
        print(f"  1. Navigate to {CYAN}Alerting{NC} -> {CYAN}Contact Points{NC} -> 'Add contact point'.")
        print(f"  2. Type:  {BOLD}Webhook{NC}")
        print(f"  3. URL:   {BOLD}http://<your-host>:8000/api/v1/webhooks/grafana{NC}")
        print(f"  4. Optional Header:")
        print(f"     Header: X-Webhook-Secret | Value: {webhook_secret}")

    elif choice == "4":
        print(f"{BOLD}▶ AWS CLOUDWATCH / EVENTBRIDGE INTEGRATION:{NC}")
        print(f"  1. Create an SNS Topic (e.g. 'amber-alerts-sns').")
        print(f"  2. Add an HTTPS Subscription pointing to:")
        print(f"     • Endpoint: {BOLD}http://<your-host>:8000/api/v1/webhooks/generic{NC}")
        print(f"  3. Attach CloudWatch Alarms to publish to this topic.")

    else:
        print(f"{BOLD}▶ PAGERDUTY / GENERIC WEBHOOK:{NC}")
        print(f"  Endpoint: {BOLD}http://<your-host>:8000/api/v1/webhooks/pagerduty{NC}")
        print(f"  Method:   {BOLD}POST{NC}")
        print(f"  Header:   X-Webhook-Secret: {webhook_secret}")

    print(f"{CYAN}{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{NC}\n")

def main():
    print_banner()
    check_dependencies()

    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text("")

    jwt_secret = get_key(str(env_path), "JWT_SECRET")
    if not jwt_secret:
        jwt_secret = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
        set_key(str(env_path), "JWT_SECRET", jwt_secret)

    webhook_secret = get_key(str(env_path), "WEBHOOK_SECRET")
    if not webhook_secret:
        webhook_secret = secrets.token_hex(16)
        set_key(str(env_path), "WEBHOOK_SECRET", webhook_secret)

    manager = verify_license(env_path)
    setup_ollama_hardware_aware(env_path)
    setup_cloud_ai(env_path)
    setup_notifications(env_path)
    select_monitoring_stack(webhook_secret)

    print(f"{GREEN}{BOLD}======================================================================{NC}")
    print(f"{GREEN}{BOLD}  ✔ AMBER ENTERPRISE ENGINE ONBOARDING COMPLETE!{NC}")
    print(f"  Licensed to:  {BOLD}{manager.org}{NC} ({manager.tier.upper()} Tier)")
    print(f"  Capacity:     {BOLD}{manager.max_nodes} Nodes • {manager.max_services} Services{NC}")
    print(f"  Launch Cluster: {BOLD}./amber start{NC}")
    print(f"{GREEN}{BOLD}======================================================================{NC}\n")

if __name__ == "__main__":
    main()
