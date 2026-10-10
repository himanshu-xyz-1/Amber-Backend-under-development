"""
Tests for Amber Enterprise License Verification Engine.
Uses ephemeral in-memory Ed25519 keypair so tests run self-contained in CI
without requiring any founder private keys on disk.
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

import backend.app.core.license as license_module
from backend.app.core.license import LicenseManager

# ──────────────────────────────────────────────────────────────────────
# Ephemeral Ed25519 Keypair for CI test isolation
# ──────────────────────────────────────────────────────────────────────
_TEST_PRIV_KEY = ed25519.Ed25519PrivateKey.generate()
_TEST_PUB_KEY = _TEST_PRIV_KEY.public_key()
_TEST_PUB_KEY_PEM = _TEST_PUB_KEY.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)


def _issue_test_token(org: str, tier: str, days: int, custom_nodes: int = 100, custom_services: int = 20) -> str:
    """Helper that generates cryptographically signed test license tokens in memory."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=days)
    payload = {
        "org": org,
        "tier": tier,
        "max_nodes": custom_nodes,
        "max_services": custom_services,
        "features": ["triage", "root_cause_analysis", "post_mortem", "slack_approvals", "telegram_bot", ""auto_remediation", "hitl_sha256"],
        "issued_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "issuer": "Amber Test CI"
    }
    payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    signature = _TEST_PRIV_KEY.sign(payload_json)
    sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    return f"amb_live_{payload_b64}.{sig_b64}"


@pytest.fixture(autouse=True)
def patch_license_public_key(monkeypatch):
    """Patches LicenseManager to verify against the ephemeral test public key."""
    monkeypatch.setattr(license_module, "AMBER_MASTER_PUBLIC_KEY_PEM", _TEST_PUB_KEY_PEM)


def test_valid_enterprise_license_verification():
    token = _issue_test_token(org="Test Corp", tier="autonomous", days=30, custom_nodes=250)
    manager = LicenseManager(token=token)
    assert manager.is_valid is True
    assert manager.status == "active"
    assert manager.org == "Test Corp"
    assert manager.tier == "autonomous"
    assert manager.max_nodes == 250
    assert manager.is_feature_enabled("telegram_bot") is True
    assert manager.is_feature_enabled("") is True
    assert manager.is_feature_enabled("slack_approvals") is True
    assert manager.days_remaining >= 29


def test_expired_license_rejection():
    token = _issue_test_token(org="Expired Corp", tier="observe", days=-1)
    manager = LicenseManager(token=token)
    assert manager.is_valid is False
    assert manager.status == "expired"
    assert manager.is_feature_enabled("telegram_bot") is False
    assert "expired" in manager.error_message.lower()


def test_tampered_license_rejection():
    token = _issue_test_token(org="Legit Corp", tier="autonomous", days=30)
    # Tamper with token characters
    tampered_token = token[:-4] + "ABCD"
    manager = LicenseManager(token=tampered_token)
    assert manager.is_valid is False
    assert manager.status == "invalid"
    assert manager.is_feature_enabled("auto_remediation") is False


def test_community_mode_when_no_token():
    manager = LicenseManager(token="")
    assert manager.is_valid is False
    assert manager.status == "community"
    assert manager.tier == "community"
    assert manager.is_feature_enabled("slack_approvals") is False
    assert manager.is_feature_enabled("") is False
    assert manager.is_feature_enabled("telegram_bot") is False


def test_license_status_api():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/license/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "contact_url" in data
    assert "get_key_url" in data


def test_license_activate_api():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    client = TestClient(app)
    headers = {"X-API-Key": "test_amber_api_key_2026"}

    # 1. Invalid key fails with 400 Bad Request
    bad_res = client.post("/api/v1/license/activate", json={"license_key": "bad_key"}, headers=headers)
    assert bad_res.status_code == 400

    # 2. Valid key succeeds
    token = _issue_test_token(org="API Test Corp", tier="response", days=14)
    good_res = client.post("/api/v1/license/activate", json={"license_key": token}, headers=headers)
    assert good_res.status_code == 200
    assert good_res.json()["success"] is True
    assert good_res.json()["details"]["org"] == "API Test Corp"


def test_infrastructure_limits_enforcement():
    token = _issue_test_token(org="Scale Corp", tier="autonomous", days=30, custom_nodes=100, custom_services=20)
    manager = LicenseManager(token=token)
    assert manager.is_valid is True

    # Under limit
    ok, err = manager.check_infrastructure_limits(node_count=50, service_count=10)
    assert ok is True
    assert err is None

    # Over node limit
    ok, err = manager.check_infrastructure_limits(node_count=150, service_count=10)
    assert ok is False
    assert "node limit exceeded" in err.lower()

    # Over service limit
    ok, err = manager.check_infrastructure_limits(node_count=50, service_count=25)
    assert ok is False
    assert "service limit exceeded" in err.lower()
