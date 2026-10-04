"""
Tests for the Universal LLM Gateway (core/llm.py).

Tests:
- JSON extraction handles markdown wrappers, prose, thinking tokens
- Air-gapped mode blocks cloud providers
- Trust level lookup works for known and unknown models
- Local provider connection failure returns None gracefully (no crash)
- Auto-rollback loop prevention (rollback_family check in approval_service)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ──────────────────────────────────────────────
# JSON Extraction Tests
# ──────────────────────────────────────────────

class TestJsonExtraction:

    def test_pure_json(self):
        from backend.app.core.llm import _extract_json
        result = _extract_json('{"severity": "P1", "reasoning": "crashloop detected"}')
        assert result == {"severity": "P1", "reasoning": "crashloop detected"}

    def test_markdown_json_block(self):
        from backend.app.core.llm import _extract_json
        raw = '```json\n{"severity": "P0", "reasoning": "db down"}\n```'
        result = _extract_json(raw)
        assert result is not None
        assert result["severity"] == "P0"

    def test_prose_with_embedded_json(self):
        from backend.app.core.llm import _extract_json
        raw = 'Here is my analysis:\n{"severity": "P2", "reasoning": "lag detected"}\nHope that helps.'
        result = _extract_json(raw)
        assert result is not None
        assert result["severity"] == "P2"

    def test_thinking_tokens_stripped(self):
        from backend.app.core.llm import _extract_json
        raw = '<think>Let me analyze this incident carefully...</think>\n{"severity": "P1", "reasoning": "OOM"}'
        result = _extract_json(raw)
        assert result is not None
        assert result["severity"] == "P1"

    def test_invalid_json_returns_none(self):
        from backend.app.core.llm import _extract_json
        result = _extract_json("This is just text with no JSON at all.")
        assert result is None

    def test_broken_json_returns_none(self):
        from backend.app.core.llm import _extract_json
        result = _extract_json('{"severity": "P1", "reasoning":}')
        assert result is None


class TestThinkingTokenStrip:

    def test_strips_think_block(self):
        from backend.app.core.llm import _strip_thinking_tokens
        raw = "<think>This is reasoning</think>Final answer"
        assert _strip_thinking_tokens(raw) == "Final answer"

    def test_strips_multiline_think(self):
        from backend.app.core.llm import _strip_thinking_tokens
        raw = "<think>\nLine 1\nLine 2\n</think>\n{\"result\": true}"
        assert _strip_thinking_tokens(raw).strip() == '{"result": true}'

    def test_no_think_passthrough(self):
        from backend.app.core.llm import _strip_thinking_tokens
        raw = "Normal text without thinking tokens"
        assert _strip_thinking_tokens(raw) == raw


# ──────────────────────────────────────────────
# Trust Level Tests
# ──────────────────────────────────────────────

class TestTrustLevel:

    def test_certified_model_returns_correct_level(self):
        from unittest.mock import patch
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "local"
            mock_settings.LOCAL_LLM_MODEL = "qwen2.5-coder:14b"
            from backend.app.core.llm import get_model_trust_level
            assert get_model_trust_level() == 2

    def test_enterprise_model_returns_level_3(self):
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "local"
            mock_settings.LOCAL_LLM_MODEL = "llama3.3:70b"
            from backend.app.core.llm import get_model_trust_level
            assert get_model_trust_level() == 3

    def test_unknown_model_returns_level_1(self):
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "local"
            mock_settings.LOCAL_LLM_MODEL = "some-random-uncertified-model:latest"
            from backend.app.core.llm import get_model_trust_level
            assert get_model_trust_level() == 1

    def test_cloud_anthropic_returns_level_3(self):
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "anthropic"
            mock_settings.ANTHROPIC_MODEL = "claude-3-7-sonnet-20250219"
            from backend.app.core.llm import get_model_trust_level
            assert get_model_trust_level() == 3

    def test_llama3_8b_is_level_1_not_level_3(self):
        """Regression test: llama3.1:8b must be Level 1, not matching 70B Level 3."""
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "local"
            mock_settings.LOCAL_LLM_MODEL = "llama3.1:8b"
            from backend.app.core.llm import get_model_trust_level
            assert get_model_trust_level() == 1

    def test_qwen2_5_7b_is_level_1_not_level_3(self):
        """Regression test: qwen2.5:7b must be Level 1, not matching 72B Level 3."""
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "local"
            mock_settings.LOCAL_LLM_MODEL = "qwen2.5:7b"
            from backend.app.core.llm import get_model_trust_level
            assert get_model_trust_level() == 1

    def test_qwen2_5_coder_1_5b_is_level_1_not_level_2(self):
        """Regression test: qwen2.5-coder:1.5b must be Level 1, not matching 14B Level 2."""
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "local"
            mock_settings.LOCAL_LLM_MODEL = "qwen2.5-coder:1.5b"
            from backend.app.core.llm import get_model_trust_level
            assert get_model_trust_level() == 1

    def test_gpt_4o_mini_is_level_1_not_level_3(self):
        """Regression test: gpt-4o-mini must be Level 1, not matching gpt-4o Level 3."""
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "openai"
            mock_settings.OPENAI_MODEL = "gpt-4o-mini"
            from backend.app.core.llm import get_model_trust_level
            assert get_model_trust_level() == 1

    def test_claude_haiku_is_level_1_not_level_3(self):
        """Regression test: Claude Haiku is fast/light and must be Level 1."""
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "anthropic"
            mock_settings.ANTHROPIC_MODEL = "claude-3-5-haiku-20241022"
            from backend.app.core.llm import get_model_trust_level
            assert get_model_trust_level() == 1

    def test_gemini_flash_8b_is_level_1(self):
        """Regression test: Gemini Flash 8B must be Level 1."""
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "gemini"
            mock_settings.GEMINI_MODEL = "gemini-1.5-flash-8b"
            from backend.app.core.llm import get_model_trust_level
            assert get_model_trust_level() == 1


# ──────────────────────────────────────────────
# Air-Gapped Mode Tests
# ──────────────────────────────────────────────

class TestAirGappedMode:

    @pytest.mark.asyncio
    async def test_air_gapped_blocks_anthropic(self):
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "anthropic"
            mock_settings.AIR_GAPPED = True
            from backend.app.core.llm import LLMGateway
            gw = LLMGateway()
            result = await gw.generate_json("test", "system")
            assert result is None

    @pytest.mark.asyncio
    async def test_air_gapped_blocks_openai(self):
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "openai"
            mock_settings.AIR_GAPPED = True
            from backend.app.core.llm import LLMGateway
            gw = LLMGateway()
            result = await gw.generate_json("test", "system")
            assert result is None

    @pytest.mark.asyncio
    async def test_air_gapped_allows_local(self):
        """Local provider should work even in air-gapped mode."""
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "local"
            mock_settings.AIR_GAPPED = True
            mock_settings.LOCAL_LLM_ENDPOINT = "http://ollama:11434/v1"
            mock_settings.LOCAL_LLM_MODEL = "qwen2.5-coder:14b"
            mock_settings.LOCAL_LLM_CONTEXT_LENGTH = 16384

            from backend.app.core.llm import LLMGateway

            gw = LLMGateway()
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "choices": [{"message": {"content": '{"severity": "P1"}'}}]
                }
                mock_resp.raise_for_status = MagicMock()
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                result = await gw.generate_json("test prompt", "system prompt")
                assert result == {"severity": "P1"}


# ──────────────────────────────────────────────
# Local LLM Graceful Failure Tests
# ──────────────────────────────────────────────

class TestLocalLLMGracefulFailure:

    @pytest.mark.asyncio
    async def test_connection_refused_returns_none(self):
        """If Ollama is not running, gateway returns None instead of crashing."""
        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "local"
            mock_settings.AIR_GAPPED = False
            mock_settings.LOCAL_LLM_ENDPOINT = "http://ollama:11434/v1"
            mock_settings.LOCAL_LLM_MODEL = "qwen2.5-coder:14b"
            mock_settings.LOCAL_LLM_CONTEXT_LENGTH = 16384

            from backend.app.core.llm import LLMGateway
            import httpx

            gw = LLMGateway()
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
                mock_client_cls.return_value = mock_client

                result = await gw.generate_json("test", "system", _retry=False)
                assert result is None  # No crash, returns None


# ──────────────────────────────────────────────
# Auto-Rollback Loop Prevention Tests
# ──────────────────────────────────────────────

class TestAutoRollbackLoopPrevention:
    """
    Tests the critical rollback ping-pong bug fix in approval_service.py.
    If the failing tool is already rollback_deployment, auto-rollback must be SKIPPED.
    """

    @pytest.mark.asyncio
    async def test_rollback_of_rollback_is_skipped(self):
        """
        rollback_deployment fails → auto-rollback should NOT trigger another rollback.
        Without the fix: it would undo the rollback, restoring the broken version!
        """
        from unittest.mock import AsyncMock, MagicMock, patch
        from backend.app.services.approval_service import execute_tool_approval
        from backend.app.models.tool_invocation import InvocationStatus
        import uuid

        mock_invocation = MagicMock()
        mock_invocation.id = uuid.uuid4()
        mock_invocation.status = InvocationStatus.PENDING_APPROVAL
        mock_invocation.tool_name = "rollback_deployment"  # ← Already a rollback!
        mock_invocation.tool_args = {"deployment_name": "api-service", "namespace": "production"}
        mock_invocation.payload_sha256 = None
        mock_invocation.approval_expires_at = None
        mock_invocation.incident_id = None

        mock_tool = AsyncMock()
        mock_tool.validate_args.return_value = True
        mock_tool_result = MagicMock()
        mock_tool_result.success = False  # ← rollback itself failed
        mock_tool_result.data = {"error": "K8s API timeout"}
        mock_tool_result.error = "K8s API timeout"
        mock_tool.execute = AsyncMock(return_value=mock_tool_result)

        with patch("backend.app.services.approval_service.tool_registry") as mock_registry, \
             patch("backend.app.services.approval_service.settings") as mock_settings:

            mock_settings.AUTO_ROLLBACK_ENABLED = True  # Even with auto-rollback ON
            mock_registry.get.side_effect = lambda name: mock_tool if name == "rollback_deployment" else None

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_invocation
            mock_db.execute = AsyncMock(return_value=mock_result)

            await execute_tool_approval(
                tool_invocation_id=str(mock_invocation.id),
                action="approve",
                db=mock_db,
            )

            # rollback_deployment should be called exactly ONCE (the original action)
            # NOT twice (which would undo the rollback)
            assert mock_tool.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_pod_restart_failure_does_not_trigger_deployment_rollback(self):
        """
        restart_service_pod fails → NO deployment rollback should be triggered.
        Pod restarts are pod-level operations; auto-rollback only applies to deployments.
        """
        from unittest.mock import AsyncMock, MagicMock, patch
        from backend.app.services.approval_service import execute_tool_approval
        from backend.app.models.tool_invocation import InvocationStatus
        import uuid

        mock_invocation = MagicMock()
        mock_invocation.id = uuid.uuid4()
        mock_invocation.status = InvocationStatus.PENDING_APPROVAL
        mock_invocation.tool_name = "restart_service_pod"  # ← Pod restart
        mock_invocation.tool_args = {"pod_name": "api-service-xyz-123", "namespace": "production"}
        # ↑ Note: NO deployment_name — so auto-rollback should never fire
        mock_invocation.payload_sha256 = None
        mock_invocation.approval_expires_at = None
        mock_invocation.incident_id = None

        mock_pod_tool = AsyncMock()
        mock_pod_tool.validate_args.return_value = True
        mock_pod_result = MagicMock()
        mock_pod_result.success = False
        mock_pod_result.data = {"error": "Pod not found"}
        mock_pod_result.error = "Pod not found"
        mock_pod_tool.execute = AsyncMock(return_value=mock_pod_result)

        rollback_called = False

        async def fake_rollback(**kwargs):
            nonlocal rollback_called
            rollback_called = True
            raise AssertionError("Rollback should NOT be called for pod restart failure!")

        with patch("backend.app.services.approval_service.tool_registry") as mock_registry, \
             patch("backend.app.services.approval_service.settings") as mock_settings:

            mock_settings.AUTO_ROLLBACK_ENABLED = True
            mock_registry.get.return_value = mock_pod_tool

            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_invocation
            mock_db.execute = AsyncMock(return_value=mock_result)

            await execute_tool_approval(
                tool_invocation_id=str(mock_invocation.id),
                action="approve",
                db=mock_db,
            )

            assert not rollback_called, "Deployment rollback triggered for pod restart failure — BUG!"

    @pytest.mark.asyncio
    async def test_auto_rollback_disabled_by_default(self):
        """AUTO_ROLLBACK_ENABLED defaults to False. Rollback should NOT fire."""
        from backend.app.core.config import settings
        assert settings.AUTO_ROLLBACK_ENABLED is False, (
            "AUTO_ROLLBACK_ENABLED must default to False. Human approval is sovereign."
        )


# ──────────────────────────────────────────────
# Webhook Fail-Closed Tests
# ──────────────────────────────────────────────

class TestWebhookFailClosed:

    @pytest.mark.asyncio
    async def test_missing_secret_production_rejects(self):
        """In production, missing WEBHOOK_SECRET must reject requests (fail-closed)."""
        from fastapi import HTTPException
        from unittest.mock import MagicMock, patch

        with patch("backend.app.auth.security.settings") as mock_settings:
            mock_settings.WEBHOOK_SECRET = None
            mock_settings.ENVIRONMENT = "production"

            from backend.app.auth.security import require_webhook_auth
            mock_request = MagicMock()

            with pytest.raises(HTTPException) as exc_info:
                await require_webhook_auth(request=mock_request)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_missing_secret_dev_allows(self):
        """In development mode, missing WEBHOOK_SECRET allows requests (with warning)."""
        with patch("backend.app.auth.security.settings") as mock_settings:
            mock_settings.WEBHOOK_SECRET = None
            mock_settings.ENVIRONMENT = "development"

            from backend.app.auth.security import require_webhook_auth
            mock_request = MagicMock()
            result = await require_webhook_auth(request=mock_request)
            assert result is True


# ──────────────────────────────────────────────
# Gemini Header Auth & Ollama Tests
# ──────────────────────────────────────────────

class TestGeminiAndOllamaProtocols:

    @pytest.mark.asyncio
    async def test_gemini_passes_key_in_header_not_url(self):
        """Verify Gemini API key is sent in x-goog-api-key header and never in the URL."""
        from backend.app.core.llm import LLMGateway
        from unittest.mock import AsyncMock, MagicMock, patch

        with patch("backend.app.core.llm.settings") as mock_settings:
            mock_settings.LLM_PROVIDER = "gemini"
            mock_settings.GEMINI_API_KEY = "test-secret-gemini-key"
            mock_settings.GEMINI_MODEL = "gemini-2.0-flash"
            mock_settings.AIR_GAPPED = False

            gw = LLMGateway()
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "candidates": [{"content": {"parts": [{"text": '{"severity": "P1"}'}]}}]
                }
                mock_resp.raise_for_status = MagicMock()
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                await gw.generate_json("test prompt", "system prompt")

                # Verify post call arguments
                call_args = mock_client.post.call_args
                url = call_args[0][0]
                # CRITICAL: API key must NOT be in URL (no ?key=)
                assert "key=" not in url, "Gemini API key leaked in URL!"
                assert "test-secret-gemini-key" not in url

                # Verify header contains x-goog-api-key
                headers = mock_client_cls.call_args.kwargs.get("headers", {})
                assert headers.get("x-goog-api-key") == "test-secret-gemini-key"

    @pytest.mark.asyncio
    async def test_air_gapped_dispatcher_suppresses_external_channels(self):
        """When AIR_GAPPED is True, dispatcher must not call external Slack/Telegram/WhatsApp APIs."""
        from backend.app.integrations.dispatcher import dispatch_incident_notifications
        from unittest.mock import patch

        with patch("backend.app.core.config.settings.AIR_GAPPED", True):
            result = await dispatch_incident_notifications(
                incident_data={"id": "test-inc-1", "title": "Test outage"}
            )
            assert result == {"slack": False, "telegram": False, "whatsapp": False}

