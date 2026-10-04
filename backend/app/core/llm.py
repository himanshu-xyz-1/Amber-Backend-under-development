"""
Amber Universal LLM Gateway — The Lego Brain Socket.

Any OpenAI-compatible local model (Ollama, vLLM, TGI, LM Studio, custom GPU cluster)
or cloud provider (Anthropic via Amber proxy, OpenAI, Gemini) can be plugged in here.

Client just sets 3 env vars:
  LLM_PROVIDER=local
  LOCAL_LLM_ENDPOINT=http://ollama:11434/v1   (or http://gpu-cluster.internal:8000/v1)
  LOCAL_LLM_MODEL=qwen2.5-coder:14b           (any model name — qwen4, deepseek-r1, llama3.3:70b, etc.)

To swap model: change LOCAL_LLM_MODEL in .env and restart. Nothing else changes.

Safety guarantees:
- AIR_GAPPED=true hard-blocks ALL cloud provider calls at code level.
- If LLM is down/missing: returns None so deterministic heuristics take over (no crash).
- Auto-strips <think> tokens from reasoning models (DeepSeek-R1, QwQ, etc).
- JSON extraction with auto-repair: handles markdown wrappers, trailing text, etc.
- context_length=16384 set on local calls to prevent silent log truncation.
- 1 auto-retry on malformed JSON with explicit error feedback to model.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Model Certification Registry
# Trust levels gate what actions Amber will auto-propose.
# LEVEL_1: Observe only — root cause diagnosis, no dangerous tool proposals.
# LEVEL_2: High trust — full proposals, human approval still required.
# LEVEL_3: Enterprise — full proposals + auto-fix eligible (if client enables it).
# ──────────────────────────────────────────────
MODEL_TRUST_REGISTRY: Dict[str, int] = {
    # Certified Observe Only — Level 1
    "qwen2.5-coder:7b": 1,
    "llama3.1:8b": 1,
    "phi4:3.8b": 1,
    # Certified — Level 2 (Standard Production HITL: 14B–32B)
    "qwen2.5-coder:14b": 2,
    "phi4:14b": 2,
    "phi-4:14b": 2,
    "mistral-small:24b": 2,
    "mistral-small3.2:24b": 2,
    "qwen2.5-coder:32b": 2,
    # Certified — Level 3 (Enterprise Autonomous: 70B+ / Frontier Cloud)
    "qwen2.5:72b": 3,
    "llama3.1:70b": 3,
    "llama3.3:70b-instruct-q4_K_M": 3,
    "llama3.3:70b": 3,
    "qwen2.5:72b-instruct": 3,
    # Cloud Frontier Models — Level 3 (via Amber Proxy or BYOK)
    "claude-3-5-sonnet-latest": 3,
    "claude-3-5-sonnet-20241022": 3,
    "claude-3-7-sonnet-20250219": 3,
    "gpt-4o-latest": 3,
    "gpt-4o": 3,
    "gemini-2.5-flash": 3,
    "gemini-2.5-pro": 3,
    "gemini-2.0-flash": 3,
}

# Dynamically augment registry from evals/certified_models.json if available
try:
    from pathlib import Path
    _evals_file = Path(__file__).resolve().parent.parent.parent.parent / "evals" / "certified_models.json"
    if _evals_file.exists():
        with open(_evals_file, "r") as _f:
            _eval_data = json.load(_f)
            for _m, _meta in _eval_data.get("certified_models", {}).items():
                MODEL_TRUST_REGISTRY[_m] = _meta.get("trust_level", 1)
except Exception as _e:
    logger.debug(f"Could not load evals/certified_models.json: {_e}")

# Any model NOT in this registry gets LEVEL_1 (observe only, no dangerous proposals)
DEFAULT_TRUST_LEVEL = 1


def get_model_trust_level() -> int:
    """
    Returns the trust level for the currently configured model.
    LEVEL_1 (Observe Only):
      - Models < 14B (e.g. 1.5B, 3B, 7B, 8B, gpt-4o-mini, haiku)
      - Unknown / uncertified models
    LEVEL_2 (High Trust / Assisted HITL):
      - Certified 14B–32B models (e.g. qwen2.5-coder:14b, qwen2.5-coder:32b, phi4:14b, mistral-small:24b)
      - Proposes remediation tools with strict argument validation; requires human approval.
    LEVEL_3 (Enterprise Autonomous):
      - Certified 70B+ models (e.g. llama3.3:70b, qwen2.5:72b)
      - Frontier Cloud models (Claude 3.5/3.7 Sonnet, GPT-4o, Gemini 2.0 Flash / 1.5 Pro)
    """
    provider = settings.LLM_PROVIDER.lower()
    if provider == "local":
        model = settings.LOCAL_LLM_MODEL.lower().strip()
    elif provider == "anthropic":
        model = settings.ANTHROPIC_MODEL.lower().strip()
    elif provider == "openai":
        model = settings.OPENAI_MODEL.lower().strip()
    elif provider == "gemini":
        model = settings.GEMINI_MODEL.lower().strip()
    else:
        return DEFAULT_TRUST_LEVEL

    # 1. Cloud Provider Explicit Trust Rules
    if provider == "openai":
        if "mini" in model or "gpt-3.5" in model:
            return 1
        if any(f in model for f in ["gpt-4o", "gpt-4-turbo", "o1", "o3"]):
            return 3
        return 1

    if provider == "anthropic":
        if "haiku" in model:
            return 1
        if any(f in model for f in ["sonnet", "opus"]):
            return 3
        return 1

    if provider == "gemini":
        if "flash-8b" in model:
            return 1
        if any(f in model for f in ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-2.5-flash", "gemini-pro"]):
            return 3
        return 1

    # 2. Local Model Size and Family Parsing (Zero loose prefix bug)
    if model in MODEL_TRUST_REGISTRY:
        return MODEL_TRUST_REGISTRY[model]

    # Extract parameter size via regex (e.g., ":14b", ":70b", ":8b", ":1.5b")
    size_match = re.search(r":(\d+(?:\.\d+)?)b", model)
    if size_match:
        try:
            param_size = float(size_match.group(1))
            if param_size < 14.0:
                # 1.5b, 3b, 7b, 8b are ALWAYS Level 1 (observe only)
                return 1
            elif 14.0 <= param_size < 65.0:
                # Certified 14B - 32B coding/SRE model families get Level 2
                if any(fam in model for fam in ["qwen2.5-coder", "phi4", "phi-4", "mistral-small", "codellama"]):
                    return 2
                return 1
            else:
                # 65B - 72B+ enterprise model families get Level 3
                if any(fam in model for fam in ["llama3.1", "llama3.3", "llama-3.1", "llama-3.3", "qwen2.5"]):
                    return 3
                return 2
        except ValueError:
            pass

    return DEFAULT_TRUST_LEVEL


def _strip_thinking_tokens(text: str) -> str:
    """Remove <think>...</think> blocks from reasoning models (DeepSeek-R1, QwQ, etc)."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    """
    Robust JSON extractor. Handles:
    - Pure JSON
    - ```json ... ``` markdown wrappers
    - JSON embedded in surrounding prose
    Returns None if no valid JSON found.
    """
    # Strip thinking tokens first
    text = _strip_thinking_tokens(raw)

    # Try pure parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code block wrappers
    text_clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text_clean = re.sub(r"\s*```$", "", text_clean.strip())
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass

    # Find first JSON object in text using brace matching
    brace_depth = 0
    start_idx = None
    for i, ch in enumerate(text):
        if ch == "{":
            if start_idx is None:
                start_idx = i
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0 and start_idx is not None:
                candidate = text[start_idx : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start_idx = None
    return None


class LLMGateway:
    """
    Universal Lego Brain Socket for Amber SRE Engine.

    One generate_json() call. Works with any provider or model.
    If provider is misconfigured or model is down: returns None gracefully.
    """

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float = 0.2,
        timeout: float = 45.0,
        _retry: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Send a prompt to the configured LLM and return a parsed JSON dict.

        Returns None if:
        - LLM is unreachable / not running
        - AIR_GAPPED=True and provider is cloud
        - JSON cannot be parsed after 1 retry
        """
        provider = settings.LLM_PROVIDER.lower()

        # Hard-block cloud providers in air-gapped mode
        if settings.AIR_GAPPED and provider in ("anthropic", "openai", "gemini"):
            logger.error(
                f"[AIR-GAPPED] Blocked outbound call to cloud provider '{provider}'. "
                "Set LLM_PROVIDER=local to use a local model."
            )
            return None

        try:
            if provider == "local":
                raw = await self._call_local(prompt, system_prompt, temperature, timeout)
            elif provider == "anthropic":
                raw = await self._call_anthropic(prompt, system_prompt, temperature, timeout)
            elif provider == "openai":
                raw = await self._call_openai(prompt, system_prompt, temperature, timeout)
            elif provider == "gemini":
                raw = await self._call_gemini(prompt, system_prompt, temperature, timeout)
            else:
                logger.error(f"Unknown LLM_PROVIDER: '{provider}'. Valid: local, anthropic, openai, gemini.")
                return None
        except Exception as e:
            logger.warning(f"[LLMGateway] Provider '{provider}' call failed: {e}")
            return None

        if raw is None:
            return None

        result = _extract_json(raw)
        if result is not None:
            return result

        # 1 auto-retry: tell model its JSON was broken
        if _retry:
            logger.warning("[LLMGateway] JSON parse failed. Retrying with repair hint...")
            retry_prompt = (
                f"{prompt}\n\n"
                "CRITICAL: Your previous response could not be parsed as JSON. "
                "Return ONLY a raw valid JSON object. No markdown, no ```json, no preamble."
            )
            return await self.generate_json(
                retry_prompt, system_prompt, temperature, timeout, _retry=False
            )

        logger.error(f"[LLMGateway] JSON extraction failed after retry. Raw response: {raw[:300]}")
        return None

    # ──────────────────────────────────────────────
    # Provider Implementations
    # ──────────────────────────────────────────────

    async def _call_local(
        self, prompt: str, system_prompt: str, temperature: float, timeout: float
    ) -> Optional[str]:
        """
        Calls local endpoint. Supports:
        1. Native Ollama (/api/chat) with options.num_ctx and think: false
        2. OpenAI-compatible (/v1/chat/completions) for vLLM / LocalAI / GPU clusters
        """
        endpoint = settings.LOCAL_LLM_ENDPOINT.rstrip("/")
        model = settings.LOCAL_LLM_MODEL

        # If endpoint is an Ollama server, use native /api/chat
        # which reliably honors num_ctx and natively disables thinking tokens.
        is_ollama = "11434" in endpoint or endpoint.endswith("/v1")

        if is_ollama:
            base_url = endpoint[:-3] if endpoint.endswith("/v1") else endpoint
            url = f"{base_url}/api/chat"
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "num_ctx": settings.LOCAL_LLM_CONTEXT_LENGTH,
                    "temperature": temperature,
                },
                "think": False,
            }
            async with httpx.AsyncClient(timeout=timeout) as client:
                try:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    if "message" in data and "content" in data["message"]:
                        return data["message"]["content"]
                except httpx.ConnectError:
                    logger.warning(
                        f"[LLMGateway/local] Cannot connect to local LLM at '{endpoint}'. "
                        "Is Ollama running? Falling back to heuristics."
                    )
                    return None
                except Exception as e:
                    logger.debug(f"[LLMGateway/local] Native /api/chat failed ({e}), trying /v1 fallback...")

        # Standard OpenAI-compatible /v1/chat/completions fallback (vLLM / Triton / etc.)
        url = f"{endpoint}/chat/completions" if not endpoint.endswith("/chat/completions") else endpoint
        payload = {
            "model": model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "num_ctx": settings.LOCAL_LLM_CONTEXT_LENGTH,
            },
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except httpx.ConnectError:
                logger.warning(
                    f"[LLMGateway/local] Cannot connect to local LLM at '{endpoint}'. "
                    "Is Ollama/vLLM running? Falling back to heuristics."
                )
                return None
            except httpx.HTTPStatusError as e:
                logger.warning(f"[LLMGateway/local] HTTP {e.response.status_code}: {e.response.text[:200]}")
                return None

    async def _call_anthropic(
        self, prompt: str, system_prompt: str, temperature: float, timeout: float
    ) -> Optional[str]:
        """
        Calls Claude via Amber AI Proxy (client license key auth) or direct BYOK.
        Client's .env NEVER holds our Anthropic master key — proxy handles that.
        """
        # Use Amber proxy if configured (enterprise managed), else direct BYOK
        proxy_url = getattr(settings, "AMBER_AI_PROXY_URL", None)
        if proxy_url:
            endpoint = proxy_url.rstrip("/")
            headers = {
                "Authorization": f"Bearer {settings.AMBER_LICENSE_KEY}",
                "Content-Type": "application/json",
            }
        else:
            # Direct BYOK — client provides their own Anthropic key
            if not settings.ANTHROPIC_API_KEY:
                logger.error("[LLMGateway/anthropic] No ANTHROPIC_API_KEY or AMBER_AI_PROXY_URL configured.")
                return None
            endpoint = "https://api.anthropic.com"
            headers = {
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }

        payload = {
            "model": settings.ANTHROPIC_MODEL,
            "max_tokens": 2048,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            resp = await client.post(f"{endpoint}/v1/messages", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

    async def _call_openai(
        self, prompt: str, system_prompt: str, temperature: float, timeout: float
    ) -> Optional[str]:
        """Calls OpenAI GPT-4o (or compatible) endpoint."""
        if not settings.OPENAI_API_KEY:
            logger.error("[LLMGateway/openai] No OPENAI_API_KEY configured.")
            return None

        payload = {
            "model": settings.OPENAI_MODEL,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _call_gemini(
        self, prompt: str, system_prompt: str, temperature: float, timeout: float
    ) -> Optional[str]:
        """Calls Google Gemini via REST using secure x-goog-api-key header (no key in URL)."""
        if not settings.GEMINI_API_KEY:
            logger.error("[LLMGateway/gemini] No GEMINI_API_KEY configured.")
            return None

        model = settings.GEMINI_MODEL
        # Pass API key via header to prevent credential leakage in logs or URL traces
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {
            "x-goog-api-key": settings.GEMINI_API_KEY,
            "Content-Type": "application/json",
        }

        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def health_check(self) -> Dict[str, Any]:
        """
        Checks if the configured LLM brain is reachable and returns model info.
        Used at startup and by the /health endpoint.
        """
        provider = settings.LLM_PROVIDER.lower()
        trust_level = get_model_trust_level()

        if provider == "local":
            endpoint = settings.LOCAL_LLM_ENDPOINT.rstrip("/")
            model = settings.LOCAL_LLM_MODEL
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{endpoint}/models")
                    resp.raise_for_status()
                return {
                    "status": "connected",
                    "provider": "local",
                    "model": model,
                    "endpoint": endpoint,
                    "trust_level": trust_level,
                    "context_length": settings.LOCAL_LLM_CONTEXT_LENGTH,
                }
            except Exception as e:
                return {
                    "status": "disconnected",
                    "provider": "local",
                    "model": model,
                    "endpoint": endpoint,
                    "error": str(e),
                    "trust_level": 0,
                    "message": "Local LLM not running. Amber core is still active. Heuristics will handle triage.",
                }
        else:
            return {
                "status": "cloud",
                "provider": provider,
                "model": {
                    "anthropic": settings.ANTHROPIC_MODEL,
                    "openai": settings.OPENAI_MODEL,
                    "gemini": settings.GEMINI_MODEL,
                }.get(provider, "unknown"),
                "trust_level": trust_level,
                "air_gapped_blocked": settings.AIR_GAPPED,
            }


# Global singleton Lego Brain Socket
llm_gateway = LLMGateway()
