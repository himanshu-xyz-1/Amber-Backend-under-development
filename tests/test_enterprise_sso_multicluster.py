import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.core.k8s import (
    k8s_check_deployment_health,
    k8s_restart_pod,
    k8s_rollout_restart_deployment,
    list_k8s_contexts,
)
from backend.app.main import app


def test_sso_configuration_endpoint():
    client = TestClient(app)
    res = client.get("/api/v1/auth/sso/config")
    assert res.status_code == 200
    data = res.json()
    assert data["sso_enabled"] is True
    assert "google" in data["supported_providers"]
    assert "okta" in data["supported_providers"]
    assert "saml" in data["supported_providers"]


def test_sso_callback_provisions_user_and_issues_jwt():
    client = TestClient(app)

    # 1. Login with SRE Lead / Admin groups
    admin_payload = {
        "provider": "okta",
        "email": "devops.lead@enterprise-client.com",
        "full_name": "DevOps Lead",
        "groups": ["sre-leads", "infrastructure"]
    }
    res = client.post("/api/v1/auth/sso/callback", json=admin_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "devops.lead@enterprise-client.com"
    assert data["role"] == "ADMIN"
    assert "access_token" in data
    assert "approve:remediation" in data["permissions"]
    assert "manage:clusters" in data["permissions"]

    admin_token = data["access_token"]

    # 2. Verify /auth/me returns profile using Bearer JWT
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["role"] == "ADMIN"
    assert me_data["auth_method"] == "jwt"
    assert len(me_data["active_clusters"]) >= 1


def test_sso_developer_role_mapping_and_rbac():
    client = TestClient(app)

    # Login as normal developer (not in SRE group)
    dev_payload = {
        "provider": "google",
        "email": "junior.dev@enterprise-client.com",
        "full_name": "Junior Developer",
        "groups": ["frontend-team"]
    }
    res = client.post("/api/v1/auth/sso/callback", json=dev_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == "DEVELOPER"
    assert "approve:remediation" not in data["permissions"]
    assert "read:incidents" in data["permissions"]

    dev_token = data["access_token"]

    # Developer attempting to submit a mutating approval must be rejected with 403 Forbidden
    approval_payload = {
        "tool_invocation_id": "00000000-0000-0000-0000-000000000001",
        "action": "approve",
        "payload_sha256": "abcdef123456"
    }
    appr_res = client.post(
        "/api/v1/approvals",
        json=approval_payload,
        headers={"Authorization": f"Bearer {dev_token}"}
    )
    assert appr_res.status_code == 403
    assert "Forbidden" in appr_res.json()["detail"]


def test_connected_clusters_endpoint():
    client = TestClient(app)
    orig_key = settings.AMBER_API_KEY
    try:
        settings.AMBER_API_KEY = "mock_secret_cluster_test"
        res = client.get(
            "/api/v1/auth/clusters",
            headers={"X-API-Key": "mock_secret_cluster_test"}
        )
        assert res.status_code == 200
        data = res.json()
        assert "clusters" in data
        assert data["total_clusters"] >= 1
    finally:
        settings.AMBER_API_KEY = orig_key


@pytest.mark.asyncio
async def test_k8s_multi_cluster_context_support():
    # Verify list contexts returns list
    contexts = list_k8s_contexts()
    assert isinstance(contexts, list)
    assert len(contexts) >= 1
    assert "name" in contexts[0]

    # Verify operations accept cluster context without breaking
    pod_res = await k8s_restart_pod(
        pod_name="payment-svc-xyz",
        namespace="production",
        context="us-east-prod"
    )
    assert pod_res["pod_name"] == "payment-svc-xyz"
    assert pod_res["cluster_context"] == "us-east-prod"

    rollout_res = await k8s_rollout_restart_deployment(
        deployment_name="checkout-api",
        namespace="production",
        context="eu-central-1"
    )
    assert rollout_res["deployment_name"] == "checkout-api"
    assert rollout_res["cluster_context"] == "eu-central-1"

    health_res = await k8s_check_deployment_health(
        deployment_name="checkout-api",
        namespace="production",
        context="ap-south-1"
    )
    assert health_res["deployment_name"] == "checkout-api"
    assert health_res["cluster_context"] == "ap-south-1"
