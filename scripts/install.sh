#!/usr/bin/env bash
# ==============================================================================
# Amber SRE Engine — Automated Installer with Universal LLM Setup
#
# Usage:
#   Online:      curl -fsSL https://ambersre.xyz/install.sh | bash
#   Offline:     ./scripts/install.sh --offline /path/to/amber-bundle.tar.gz
#   Skip LLM:   ./scripts/install.sh --no-llm
# ==============================================================================
set -euo pipefail

AMBER_DIR="${HOME}/.amber"
REPO_URL="https://github.com/himanshu-xyz-1/Amber-Backend.git"
OFFLINE_BUNDLE=""
SKIP_LLM=false

# Parse args
for arg in "$@"; do
    case "$arg" in
        --offline) OFFLINE_BUNDLE="${2:-}"; shift 2 || true ;;
        --no-llm)  SKIP_LLM=true ;;
    esac
done

# ──────────────────────────────────────────────────────────────────────
# Colour helpers
# ──────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[Amber]${NC} $*"; }
warn()  { echo -e "${YELLOW}[Amber WARN]${NC} $*"; }
error() { echo -e "${RED}[Amber ERROR]${NC} $*"; exit 1; }

echo ""
echo "============================================================"
echo "⚡ Amber Autonomous SRE Engine — Installer"
echo "============================================================"

# ──────────────────────────────────────────────────────────────────────
# Step 1: Hardware Detection
# ──────────────────────────────────────────────────────────────────────
detect_hardware() {
    RAM_GB=0
    VRAM_GB=0
    GPU_NAME=""
    CPU_CORES=$(nproc 2>/dev/null || echo 4)

    # RAM detection
    if command -v free &>/dev/null; then
        RAM_KB=$(free | awk '/^Mem:/{print $2}')
        RAM_GB=$(( RAM_KB / 1024 / 1024 ))
    fi

    # GPU detection (NVIDIA)
    if command -v nvidia-smi &>/dev/null; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "")
        VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1 | grep -o '[0-9]*' | head -1 || echo "0")
        VRAM_GB=$(( VRAM_MB / 1024 ))
    fi

    info "Detected: ${RAM_GB}GB RAM | ${CPU_CORES} CPUs | GPU: ${GPU_NAME:-None} (${VRAM_GB}GB VRAM)"
}

# ──────────────────────────────────────────────────────────────────────
# Step 2: LLM Model Recommendation based on hardware
# ──────────────────────────────────────────────────────────────────────
recommend_model() {
    if [[ $VRAM_GB -ge 48 ]]; then
        echo "qwen2.5-coder:32b"
    elif [[ $VRAM_GB -ge 24 ]]; then
        echo "qwen2.5-coder:14b"
    elif [[ $VRAM_GB -ge 8 ]]; then
        echo "qwen2.5-coder:7b"
    elif [[ $RAM_GB -ge 32 ]]; then
        echo "qwen2.5-coder:14b"
    elif [[ $RAM_GB -ge 16 ]]; then
        echo "qwen2.5-coder:7b"
    else
        echo "phi4:3.8b"
    fi
}

# ──────────────────────────────────────────────────────────────────────
# Step 3: Interactive LLM Selection
# ──────────────────────────────────────────────────────────────────────
select_llm() {
    detect_hardware
    RECOMMENDED=$(recommend_model)

    echo ""
    echo "========================================================"
    echo "  Amber LLM Brain Configuration"
    echo "========================================================"
    echo "  Detected: ${RAM_GB}GB RAM | GPU: ${GPU_NAME:-None} (${VRAM_GB}GB VRAM)"
    echo ""
    echo "  [1] Local Model via Ollama (any open-source model)"
    echo "      Auto-recommended: ${RECOMMENDED}"
    echo "  [2] External GPU Cluster (your own vLLM/OpenAI-compatible endpoint)"
    echo "  [3] Cloud — Claude 3.7 Sonnet (via Amber AI Proxy, requires license)"
    echo "  [4] Cloud — Gemini 2.5 Flash (requires GEMINI_API_KEY)"
    echo "  [5] Skip LLM now (Amber will run in heuristics-only mode)"
    echo "========================================================"
    echo ""
    read -rp "  Select [1-5] (default: 1): " LLM_CHOICE < /dev/tty || LLM_CHOICE="1"
    LLM_CHOICE="${LLM_CHOICE:-1}"

    case "$LLM_CHOICE" in
        1)
            echo ""
            echo "  Popular models (any Ollama model name works):"
            echo "    - phi4:3.8b         (~2.5GB VRAM, Dev/Testing)"
            echo "    - qwen2.5-coder:7b  (~5GB VRAM, Standard)"
            echo "    - qwen2.5-coder:14b (~10GB VRAM, Production) ← Recommended"
            echo "    - qwen2.5-coder:32b (~20GB VRAM, Pro)"
            echo "    - llama3.3:70b      (~45GB VRAM, Enterprise Multi-GPU)"
            echo "    - qwen4:latest      (when available)"
            echo "    - Or any other model you want!"
            echo ""
            read -rp "  Enter model name [${RECOMMENDED}]: " CHOSEN_MODEL < /dev/tty || CHOSEN_MODEL="${RECOMMENDED}"
            CHOSEN_MODEL="${CHOSEN_MODEL:-${RECOMMENDED}}"

            # Validate VRAM/RAM for known heavy models
            if [[ "$CHOSEN_MODEL" == *"70b"* ]] && [[ $VRAM_GB -lt 48 ]] && [[ $RAM_GB -lt 64 ]]; then
                warn "70B models need 48GB+ VRAM or 64GB+ RAM. Your machine has ${VRAM_GB}GB VRAM / ${RAM_GB}GB RAM."
                warn "It may run slowly (CPU mode). Consider a smaller model for production."
                read -rp "  Continue anyway? [y/N]: " CONFIRM < /dev/tty || CONFIRM="N"
                [[ "${CONFIRM:-N}" =~ ^[Yy]$ ]] || { info "Switching to ${RECOMMENDED}..."; CHOSEN_MODEL="$RECOMMENDED"; }
            fi

            set_env "LLM_PROVIDER" "local"
            set_env "LOCAL_LLM_MODEL" "$CHOSEN_MODEL"
            set_env "LOCAL_LLM_ENDPOINT" "http://ollama:11434/v1"
            LLM_PROVIDER_SELECTED="local"
            LLM_MODEL_SELECTED="$CHOSEN_MODEL"
            ;;
        2)
            echo ""
            read -rp "  Enter your vLLM/OpenAI-compatible endpoint URL: " CUSTOM_ENDPOINT < /dev/tty
            read -rp "  Enter model name (e.g. llama3.3-70b, qwen2.5-coder): " CUSTOM_MODEL < /dev/tty
            set_env "LLM_PROVIDER" "local"
            set_env "LOCAL_LLM_ENDPOINT" "$CUSTOM_ENDPOINT"
            set_env "LOCAL_LLM_MODEL" "$CUSTOM_MODEL"
            LLM_PROVIDER_SELECTED="custom_cluster"
            LLM_MODEL_SELECTED="$CUSTOM_MODEL"
            ;;
        3)
            set_env "LLM_PROVIDER" "anthropic"
            set_env "ANTHROPIC_MODEL" "claude-3-7-sonnet-20250219"
            warn "Cloud mode: requires AMBER_LICENSE_KEY or ANTHROPIC_API_KEY in .env"
            LLM_PROVIDER_SELECTED="anthropic"
            LLM_MODEL_SELECTED="claude-3-7-sonnet-20250219"
            ;;
        4)
            read -rp "  Enter your GEMINI_API_KEY: " GEMINI_KEY < /dev/tty
            set_env "LLM_PROVIDER" "gemini"
            set_env "GEMINI_API_KEY" "$GEMINI_KEY"
            set_env "GEMINI_MODEL" "gemini-2.0-flash"
            LLM_PROVIDER_SELECTED="gemini"
            LLM_MODEL_SELECTED="gemini-2.0-flash"
            ;;
        5)
            info "Skipping LLM. Amber will use deterministic heuristics for triage."
            SKIP_LLM=true
            LLM_PROVIDER_SELECTED="none"
            LLM_MODEL_SELECTED="heuristics-only"
            ;;
        *)
            error "Invalid selection."
            ;;
    esac
}

# ──────────────────────────────────────────────────────────────────────
# Helper: safely set .env value
# ──────────────────────────────────────────────────────────────────────
set_env() {
    local key="$1" val="$2"
    if grep -q "^${key}=" .env 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${val}|g" .env
    else
        echo "${key}=${val}" >> .env
    fi
}

# ──────────────────────────────────────────────────────────────────────
# Step 4: Docker check
# ──────────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    info "Docker not detected. Installing Docker Engine..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER" || true
fi

AMBER_VERSION="${AMBER_VERSION:-main}"

# ──────────────────────────────────────────────────────────────────────
# Step 5: Offline bundle verification OR version-pinned git clone
# ──────────────────────────────────────────────────────────────────────
if [[ -n "$OFFLINE_BUNDLE" ]]; then
    info "Offline install mode. Verifying bundle integrity: ${OFFLINE_BUNDLE}"
    if [[ -f "${OFFLINE_BUNDLE}.sha256" ]]; then
        info "Checking SHA-256 checksum..."
        sha256sum -c "${OFFLINE_BUNDLE}.sha256" || error "SHA-256 checksum verification failed for bundle!"
        info "Checksum verified: Integrity OK"
    else
        error "Security refusal: Missing mandatory '${OFFLINE_BUNDLE}.sha256' integrity checksum file."
    fi
    mkdir -p "$AMBER_DIR"
    tar -xzf "$OFFLINE_BUNDLE" -C "$AMBER_DIR" --strip-components=1
    cd "$AMBER_DIR"
    info "Loading Docker images from bundle..."
    docker load -i amber-images.tar 2>/dev/null || warn "No docker image tarball found in bundle."
else
    if [ -d "$AMBER_DIR" ]; then
        info "Updating existing Amber installation..."
        cd "$AMBER_DIR"
        git fetch origin --tags 2>/dev/null || true
        git checkout "$AMBER_VERSION" 2>/dev/null || git checkout tags/"$AMBER_VERSION" 2>/dev/null || git pull origin "$AMBER_VERSION" 2>/dev/null || true
    else
        info "Cloning Amber SRE repository (pinned version: ${AMBER_VERSION})..."
        git clone --depth 1 --branch "$AMBER_VERSION" "$REPO_URL" "$AMBER_DIR" || \
        error "Failed to clone verified release tag '${AMBER_VERSION}' from ${REPO_URL}. Unpinned clone refused."
        cd "$AMBER_DIR"
    fi
fi

# ──────────────────────────────────────────────────────────────────────
# Step 6: .env setup
# ──────────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    info "Generating cryptographic cluster keys..."
    cp .env.example .env
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || date +%s | sha256sum | base64 | head -c 32)
    PG_PASS=$(openssl rand -hex 16 2>/dev/null || date +%s | sha256sum | base64 | head -c 16)
    WEBHOOK_SECRET=$(openssl rand -hex 24 2>/dev/null || date +%s | sha256sum | base64 | head -c 24)
    AMBER_API_KEY=$(openssl rand -hex 32 2>/dev/null || date +%s | sha256sum | base64 | head -c 32)
    set_env "JWT_SECRET_KEY" "$JWT_SECRET"
    set_env "POSTGRES_PASSWORD" "$PG_PASS"
    set_env "WEBHOOK_SECRET" "$WEBHOOK_SECRET"
    set_env "AMBER_API_KEY" "$AMBER_API_KEY"
fi

# ──────────────────────────────────────────────────────────────────────
# Step 7: Interactive Setup Wizard (Community / Commercial, Ollama, Notifications)
# ──────────────────────────────────────────────────────────────────────
if [[ "$SKIP_LLM" == false ]]; then
    if [ -f "scripts/setup_wizard.py" ]; then
        if [ -e /dev/tty ]; then
            python3 scripts/setup_wizard.py < /dev/tty || python3 scripts/setup_wizard.py || select_llm
        else
            python3 scripts/setup_wizard.py || select_llm
        fi
    else
        select_llm
    fi
fi

# ──────────────────────────────────────────────────────────────────────
# Step 8: Start all services
# ──────────────────────────────────────────────────────────────────────
info "Starting Amber cluster (Postgres, Redis, Ollama, Backend, Telegram)..."

# If cloud/external LLM — skip the ollama service to save resources
if [[ "${LLM_PROVIDER_SELECTED:-local}" != "local" ]] || [[ "$SKIP_LLM" == true ]]; then
    docker compose up -d --scale ollama=0 2>/dev/null || docker compose up -d
else
    docker compose up -d
fi

# ──────────────────────────────────────────────────────────────────────
# Step 9: Pull model via Ollama (online mode only, local provider only)
# ──────────────────────────────────────────────────────────────────────
if [[ "${LLM_PROVIDER_SELECTED:-}" == "local" ]] && [[ "$SKIP_LLM" == false ]] && [[ -z "$OFFLINE_BUNDLE" ]]; then
    MODEL="${LLM_MODEL_SELECTED:-qwen2.5-coder:14b}"
    info "Pulling LLM model '${MODEL}' into Ollama (this may take a few minutes)..."
    # Wait for Ollama to be ready first
    for i in {1..20}; do
        if docker exec amber-ollama ollama list &>/dev/null 2>&1; then
            break
        fi
        sleep 3
    done
    docker exec amber-ollama ollama pull "$MODEL" && \
        info "Model '${MODEL}' ready!" || \
        warn "Model pull failed. Run manually: docker exec amber-ollama ollama pull ${MODEL}"
fi

# ──────────────────────────────────────────────────────────────────────
# Step 10: Readiness check
# ──────────────────────────────────────────────────────────────────────
info "Waiting for Amber backend to be ready..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:8000/api/v1/health/readiness 2>/dev/null | grep -q "ready"; then
        echo ""
        echo "============================================================"
        echo "✅ AMBER SRE ENGINE IS OPERATIONAL!"
        echo "============================================================"
        echo "• LLM Provider:      ${LLM_PROVIDER_SELECTED:-local}"
        echo "• LLM Model:         ${LLM_MODEL_SELECTED:-heuristics-only}"
        echo "• Local API Gateway: http://localhost:8000"
        echo "• Swagger Docs:      http://localhost:8000/docs"
        echo ""
        echo "🔑 Your AMBER_API_KEY is in .env — keep it secret!"
        echo "📖 Docs: https://ambersre.xyz/docs"
        echo "============================================================"
        echo ""
        echo "To change LLM model later:"
        echo "  Edit LOCAL_LLM_MODEL in .env, then:"
        echo "  docker exec amber-ollama ollama pull <new-model>"
        echo "  docker compose restart backend"
        echo "============================================================"
        exit 0
    fi
    sleep 2
done

warn "Amber is starting. Check logs: docker compose logs -f backend"
