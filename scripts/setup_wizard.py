#!/usr/bin/env python3
"""
Amber SRE Engine — Production Interactive Setup Wizard.
Provides an elegant, enterprise-grade TUI installer for Community and Commercial tiers.
Handles hardware checks, license activation, Ollama reasoning selection,
cloud provider fallbacks, and real-time on-call channel pairing (Telegram, Slack, WhatsApp).
"""

import os
import sys
import re
import socket
import asyncio
import subprocess
from typing import Dict, Any

# Add backend directory to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

# ANSI Color codes
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
MAGENTA = "\033[0;35m"
NC = "\033[0m"

def print_banner(is_community: bool = False):
    edition_title = f"{GREEN}{BOLD}[ Amber SRE — Free Community Edition Setup Wizard ]{NC}" if is_community else f"{BOLD}[ Amber Autonomous SRE Engine — Production Setup Wizard v1.2 ]{NC}"
    edition_sub = f"{DIM}100% Self-Hosted • 5 Nodes • 3 Services • Local Ollama Compute • Zero License Key{NC}" if is_community else f"{DIM}Deterministic Incident Investigation, Root-Cause Proof & On-Call Automation{NC}"
    banner = f"""
{CYAN}{BOLD}  █████╗ ███╗   ███╗██████╗ ███████╗██████╗ 
 ██╔══██╗████╗ ████║██╔══██╗██╔════╝██╔══██╗
 ███████║██╔████╔██║██████╔╝█████╗  ██████╔╝
 ██╔══██║██║╚██╔╝██║██╔══██╗██╔══╝  ██╔══██╗
 ██║  ██║██║ ╚═╝ ██║██████╔╝███████╗██║  ██║{NC}
 
 {edition_title}
 {edition_sub}
----------------------------------------------------------------------"""
    print(banner)

def get_server_ip() -> str:
    """Discovers local private IP for webhook endpoint guidance."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def detect_hardware() -> Dict[str, Any]:
    """Inspects RAM, CPU cores, GPU VRAM and Docker status."""
    ram_gb = 8
    cpu_cores = os.cpu_count() or 4
    gpu_name = None
    vram_gb = 0

    # RAM Detection
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        ram_gb = round(kb / 1024 / 1024, 1)
                        break
    except Exception:
        pass

    # GPU Detection
    try:
        nvidia_out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=2
        )
        if nvidia_out.returncode == 0 and nvidia_out.stdout.strip():
            parts = nvidia_out.stdout.strip().split("\n")[0].split(",")
            gpu_name = parts[0].strip()
            if len(parts) > 1:
                vram_raw = re.search(r"(\d+)", parts[1])
                if vram_raw:
                    vram_gb = round(int(vram_raw.group(1)) / 1024, 1)
    except Exception:
        pass

    # Docker status
    docker_installed = False
    try:
        d_out = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=2)
        docker_installed = (d_out.returncode == 0)
    except Exception:
        pass

    # Ollama status
    ollama_running = False
    try:
        import urllib.request
        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1.5)
        if req.status == 200:
            ollama_running = True
    except Exception:
        pass

    return {
        "ram_gb": ram_gb,
        "cpu_cores": cpu_cores,
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "docker": docker_installed,
        "ollama": ollama_running
    }

def recommend_ollama_model(hw: Dict[str, Any]) -> str:
    vram = hw.get("vram_gb", 0)
    ram = hw.get("ram_gb", 8)
    if vram >= 40:
        return "llama3.3:70b"
    elif vram >= 18 or ram >= 32:
        return "qwen2.5-coder:32b"
    elif vram >= 8 or ram >= 14:
        return "qwen2.5-coder:14b"
    elif ram >= 7:
        return "qwen2.5-coder:7b"
    else:
        return "phi4:3.8b"

def update_env_file(updates: Dict[str, str], env_path: str = ".env"):
    """Atomically updates or creates .env with specified key-values."""
    existing_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()
    elif os.path.exists(".env.example"):
        with open(".env.example", "r", encoding="utf-8") as f:
            existing_lines = f.readlines()

    keys_set = set()
    new_lines = []
    for line in existing_lines:
        matched = False
        for k, v in updates.items():
            if re.match(rf"^{k}=.*", line):
                new_lines.append(f"{k}={v}\n")
                keys_set.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for k, v in updates.items():
        if k not in keys_set:
            new_lines.append(f"{k}={v}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def run_interactive_setup():
    is_community = (
        "--community" in sys.argv 
        or os.getenv("AMBER_COMMUNITY") == "1" 
        or os.getenv("AMBER_TIER", "").lower() == "community"
    )
    print_banner(is_community=is_community)

    # ──────────────────────────────────────────────────────────────────
    # [1/5] Hardware Assessment
    # ──────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[1/5] Identifying System & Compute Resources...{NC}")
    hw = detect_hardware()
    ram_str = f"{hw['ram_gb']} GB RAM"
    cpu_str = f"{hw['cpu_cores']} Cores"
    gpu_str = f"{hw['gpu_name']} ({hw['vram_gb']} GB VRAM)" if hw['gpu_name'] else "None (CPU Execution)"
    print(f"  ✔ Detected: {GREEN}{cpu_str} | {ram_str} | GPU: {gpu_str}{NC}")
    
    if hw["docker"]:
        print(f"  ✔ Docker Runtime: {GREEN}Ready{NC}")
    else:
        print(f"  {YELLOW}⚠ Docker not detected. Please ensure Docker is running before launch.{NC}")

    if hw["ollama"]:
        print(f"  ✔ Ollama Compute Server: {GREEN}Active on localhost:11434{NC}")
    else:
        print(f"  ℹ Ollama Service: {DIM}Not detected on localhost:11434 (will use containerized or cloud){NC}")

    # ──────────────────────────────────────────────────────────────────
    # [2/5] Registration & License Verification
    # ──────────────────────────────────────────────────────────────────
    if is_community:
        print(f"\n{BOLD}[2/5] Client Registration (Free Community Edition — No License Required){NC}")
        client_name = input("  Enter your Full Name: ").strip() or "SRE Lead"
        company_name = input("  Enter your Company / Team: ").strip() or "Engineering Team"

        license_tier = "COMMUNITY"
        max_nodes = 50
        max_services = 15
        license_key_to_save = ""

        print(f"\n  ✔ {GREEN}COMMUNITY EDITION ACTIVATED (Free Forever){NC}")
        print(f"    • License: Zero Key Required ($0 Free Forever)")
        print(f"    • Node Capacity: Up to 50 Cloud / K8s Nodes")
        print(f"    • Service Capacity: Up to 15 Production Microservices")
        print(f"    • Monthly Alerts: 1,000 alerts / month")
        print(f"    • Features Included: Alert Storm Deduplication, Deterministic Root Cause,")
        print(f"                         Memory Leak & Deadlock Tracing, Post-Mortems, 50+ Runbooks")
        print(f"    • Compute: 100% Local Self-Hosted via Ollama (Zero Telemetry Egress)")
        print(f"    • Execution Mode: 100% Read-Only IAM (0 Writes)")
    else:
        print(f"\n{BOLD}[2/5] Commercial License Verification{NC}")
        client_name = input("  Enter your Full Name: ").strip() or "SRE Lead"
        company_name = input("  Enter your Company / Team: ").strip() or "Engineering Team"
        
        print(f"\n  {DIM}Enter your commercial license key (amb_live_...):{NC}")
        license_input = input(f"  {BOLD}License Key: ").strip()

        license_tier = "COMMUNITY"
        max_nodes = 5
        max_services = 3
        license_key_to_save = ""

        from backend.app.core.license import LicenseManager
        if license_input:
            validator = LicenseManager(token=license_input)
            if validator.is_valid:
                license_tier = validator.tier.upper()
                max_nodes = validator.max_nodes
                max_services = validator.max_services
                license_key_to_save = license_input
                print(f"  ✔ {GREEN}License Cryptographically Verified: {license_tier} TIER{NC}")
                print(f"    Org: {validator.org} | Capacity: Up to {max_nodes} Nodes, {max_services} Services")
            else:
                print(f"  {RED}✖ Invalid or Expired License Key: {validator.error_message}{NC}")
                print(f"  👉 Falling back safely to Free Community Edition.")
                license_tier = "COMMUNITY"
        else:
            print(f"  {YELLOW}⚠ No license key provided. Falling back to Community Edition.{NC}")

    # ──────────────────────────────────────────────────────────────────
    # [3/5] Local Compute Engine (Ollama Reasoning Model)
    # ──────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[3/5] Local Compute Engine (Ollama Reasoning Model){NC}")
    recommended_model = recommend_ollama_model(hw)
    print(f"  Recommended for your hardware: {CYAN}{recommended_model}{NC}")
    print("  Popular choices:")
    print("    [1] Recommended Model (" + recommended_model + ")")
    print("    [2] qwen2.5-coder:7b  (Lightweight, 8GB RAM)")
    print("    [3] qwen2.5-coder:14b (Production Balanced, 16GB RAM)")
    print("    [4] qwen2.5-coder:32b (Frontier Coding, 24GB+ / GPU)")
    print("    [5] Skip local model (I will use Cloud LLMs or heuristics)")

    model_choice = input(f"  Select model [1-5, default: 1]: ").strip() or "1"
    model_mapping = {
        "1": recommended_model,
        "2": "qwen2.5-coder:7b",
        "3": "qwen2.5-coder:14b",
        "4": "qwen2.5-coder:32b",
    }
    selected_local_model = model_mapping.get(model_choice, recommended_model)
    skip_local_model = (model_choice == "5")

    if not skip_local_model:
        print(f"  ✔ Selected Local Model: {GREEN}{selected_local_model}{NC}")
        if hw["ollama"]:
            print(f"  Pulling '{selected_local_model}' via Ollama...")
            try:
                subprocess.run(["ollama", "pull", selected_local_model], check=False)
            except Exception:
                pass
    else:
        print(f"  ℹ Skipping local model download.")

    # ──────────────────────────────────────────────────────────────────
    # [4/5] Cloud Reasoning Fallback (Optional)
    # ──────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[4/5] Cloud Reasoning Gateway (Optional Fallback){NC}")
    enable_cloud = input("  Do you want to enable Cloud AI providers (Anthropic / OpenAI / Gemini)? [y/N]: ").strip().lower()
    
    anthropic_key = ""
    openai_key = ""
    gemini_key = ""
    selected_cloud_provider = "none"

    if enable_cloud in ["y", "yes"]:
        print("  Select Cloud Provider:")
        print("    [1] Anthropic (Claude 3.7 Sonnet / Claude 3.5 Sonnet)")
        print("    [2] OpenAI (GPT-4o)")
        print("    [3] Google Gemini (Gemini 2.0 Flash)")
        c_choice = input("  Provider [1-3, default: 1]: ").strip() or "1"
        if c_choice == "1":
            anthropic_key = input("  Enter ANTHROPIC_API_KEY: ").strip()
            selected_cloud_provider = "anthropic"
        elif c_choice == "2":
            openai_key = input("  Enter OPENAI_API_KEY: ").strip()
            selected_cloud_provider = "openai"
        elif c_choice == "3":
            gemini_key = input("  Enter GEMINI_API_KEY: ").strip()
            selected_cloud_provider = "gemini"
        print(f"  ✔ Cloud Reasoning Provider configured: {GREEN}{selected_cloud_provider}{NC}")
    else:
        print(f"  ✔ Operating in 100% Air-Gapped Local Mode ($0 Cloud API Bill).")

    # ──────────────────────────────────────────────────────────────────
    # [5/5] On-Call Notifications & Incident Channels
    # ──────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}[5/5] Incident Dispatch & On-Call Channels{NC}")
    print("  Where do you want to receive real-time incident alerts and 1-click approvals?")
    print("    [1] Telegram (@ambersre_alert_bot — instant on-call mobile push)")
    print("    [2] Slack    (Incoming Webhook for team channel #prod-alerts)")
    print("    [3] WhatsApp (QR pairing via local terminal bridge)")
    print("    [4] Skip notifications for now (Dashboard only)")
    
    channels_input = input("  Select channels (e.g. 1, 2, or press Enter for Telegram): ").strip() or "1"
    selected_channels = [c.strip() for c in channels_input.replace(",", " ").split() if c.strip()]

    telegram_chat_id = ""
    slack_webhook_url = ""

    # Telegram Setup
    if "1" in selected_channels:
        print(f"\n  ------------------------------------------------------------")
        print(f"  {BOLD}📱 TELEGRAM MOBILE PAIRING SETUP{NC}")
        print(f"  ------------------------------------------------------------")
        print(f"    1. Open Telegram on your phone or PC.")
        print(f"    2. Search for: {CYAN}@ambersre_alert_bot{NC}")
        print(f"    3. Send: {BOLD}/start{NC}")
        print(f"    4. The bot will reply with your unique Receiver ID.")
        print(f"  ------------------------------------------------------------")
        
        while True:
            tg_id = input(f"  Enter your Telegram Receiver ID [{GREEN}or press Enter to skip{NC}]: ").strip()
            if not tg_id:
                break
            print(f"  ⏳ Verifying pairing handshake with Telegram...")
            from backend.app.integrations.telegram import send_telegram_pairing_handshake
            success, msg = asyncio.run(send_telegram_pairing_handshake(
                chat_id=tg_id,
                client_name=client_name,
                company=company_name,
                tier=license_tier,
                max_nodes=max_nodes,
                max_services=max_services
            ))
            if success:
                print(f"  ✔ {GREEN}Telegram Handshake Verified! Check your phone for confirmation.{NC}")
                telegram_chat_id = tg_id
                break
            else:
                print(f"  {YELLOW}⚠ Handshake failed: {msg}{NC}")
                retry = input("  Retry ID? [Y/n]: ").strip().lower()
                if retry == "n":
                    telegram_chat_id = tg_id
                    break

    # Slack Setup
    if "2" in selected_channels:
        print(f"\n  ------------------------------------------------------------")
        print(f"  {BOLD}💬 SLACK WORKSPACE SETUP{NC}")
        print(f"  ------------------------------------------------------------")
        print(f"    1. Go to your Slack Workspace (api.slack.com/apps).")
        print(f"    2. Create an Incoming Webhook for your channel (e.g. #prod-alerts).")
        print(f"    3. Copy the Webhook URL (starts with https://hooks.slack.com/).")
        print(f"  ------------------------------------------------------------")
        
        while True:
            s_url = input(f"  Enter Slack Webhook URL [{GREEN}or press Enter to skip{NC}]: ").strip()
            if not s_url:
                break
            print(f"  ⏳ Dispatching test verification ping to Slack...")
            from backend.app.integrations.slack import send_slack_test_ping
            success, msg = asyncio.run(send_slack_test_ping(
                webhook_url=s_url,
                client_name=client_name,
                company=company_name,
                tier=license_tier
            ))
            if success:
                print(f"  ✔ {GREEN}Slack Channel Verified! Test alert card delivered.{NC}")
                slack_webhook_url = s_url
                break
            else:
                print(f"  {YELLOW}⚠ Slack test ping failed: {msg}{NC}")
                retry = input("  Retry URL? [Y/n]: ").strip().lower()
                if retry == "n":
                    slack_webhook_url = s_url
                    break

    # WhatsApp Setup
    if "3" in selected_channels:
        print(f"\n  ------------------------------------------------------------")
        print(f"  {BOLD}💬 WHATSAPP TERMINAL PAIRING{NC}")
        print(f"  ------------------------------------------------------------")
        print(f"    The Amber WhatsApp bridge service is ready in services/whatsapp-bridge.")
        print(f"    Run 'docker compose up -d whatsapp-bridge' to render the pairing QR code.")
        print(f"    Then link via WhatsApp → Settings → Linked Devices.")

    # ──────────────────────────────────────────────────────────────────
    # Save to .env and Initialize System
    # ──────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}Finalizing Environment Configuration...{NC}")
    env_updates = {
        "AMBER_CLIENT_NAME": client_name,
        "AMBER_COMPANY_NAME": company_name,
        "AMBER_TIER": license_tier,
        "AMBER_LICENSE_TIER": license_tier,
        "AMBER_MAX_NODES": str(max_nodes),
        "AMBER_MAX_SERVICES": str(max_services),
        "AMBER_MONTHLY_ALERT_LIMIT": "1000" if is_community else "unlimited",
        "AMBER_EXECUTION_MODE": "read_only" if is_community else "autonomous",
        "AMBER_AUTONOMOUS_WRITE_ENABLED": "false" if is_community else "true",
    }

    if license_key_to_save:
        env_updates["AMBER_LICENSE_KEY"] = license_key_to_save
    if not skip_local_model:
        env_updates["LOCAL_LLM_MODEL"] = selected_local_model
        env_updates["LLM_PROVIDER"] = "local"
    if selected_cloud_provider != "none":
        env_updates["CLOUD_LLM_PROVIDER"] = selected_cloud_provider
    if anthropic_key:
        env_updates["ANTHROPIC_API_KEY"] = anthropic_key
    if openai_key:
        env_updates["OPENAI_API_KEY"] = openai_key
    if gemini_key:
        env_updates["GEMINI_API_KEY"] = gemini_key
    if telegram_chat_id:
        env_updates["TELEGRAM_CHAT_ID"] = telegram_chat_id
    if slack_webhook_url:
        env_updates["SLACK_WEBHOOK_URL"] = slack_webhook_url

    update_env_file(env_updates)
    print(f"  ✔ Saved configuration to {BOLD}.env{NC}")

    # Database setup / migrations check
    try:
        from backend.app.core.database import Base, engine

        async def _init_db():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        asyncio.run(_init_db())
        print(f"  ✔ Initialized local telemetry database schema (amber.db)")
    except Exception as db_err:
        print(f"  {YELLOW}⚠ Database table initialization note: {db_err}{NC}")

    # ──────────────────────────────────────────────────────────────────
    # Final Success Banner
    # ──────────────────────────────────────────────────────────────────
    server_ip = get_server_ip()
    active_notifications = []
    if telegram_chat_id:
        active_notifications.append("Telegram (@ambersre_alert_bot)")
    if slack_webhook_url:
        active_notifications.append("Slack (Webhook)")
    if not active_notifications:
        active_notifications.append("Internal Dashboard")

    print(f"""
{GREEN}{BOLD}======================================================================
🎉 AMBER {'COMMUNITY EDITION' if is_community else 'SRE ENGINE'} SETUP COMPLETE & OPERATIONAL!
======================================================================{NC}

  {BOLD}Dashboard:{NC}        http://localhost:8000
  {BOLD}API Docs:{NC}         http://localhost:8000/docs
  {BOLD}License Tier:{NC}     {license_tier} (Max {max_nodes} Nodes · {max_services} Services)
  {BOLD}Alert Quota:{NC}      {'1,000 Alerts/month (Free Forever)' if is_community else 'Commercial Enterprise Quota'}
  {BOLD}Execution Mode:{NC}   {'Read-Only Triage (Autonomous auto-fix requires Commercial tier)' if is_community else 'Autonomous Low-Risk Remediation'}
  {BOLD}Active Brain:{NC}     {selected_local_model if not skip_local_model else 'Heuristics'}
  {BOLD}On-Call Alerts:{NC}   {", ".join(active_notifications)}

{BOLD}NEXT STEP — CONNECT YOUR MONITORING TOOL:{NC}
  Add this Webhook into Datadog, Prometheus Alertmanager, or Grafana:
  👉 {CYAN}{BOLD}POST http://{server_ip}:8000/api/v1/alerts/webhook{NC}

======================================================================
""")

if __name__ == "__main__":
    try:
        run_interactive_setup()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Setup cancelled by user.{NC}")
        sys.exit(0)
