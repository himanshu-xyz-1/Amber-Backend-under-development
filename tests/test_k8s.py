from unittest.mock import MagicMock, patch

import pytest

from backend.app.core.k8s import (
    k8s_check_deployment_health,
    k8s_restart_pod,
    k8s_rollback_deployment,
    k8s_rollout_restart_deployment,
)
from backend.app.tools.base import tool_registry


@pytest.mark.asyncio
async def test_k8s_tools_registered():
    tools = [t["name"] for t in tool_registry.list_tools()]
    assert "rollback_deployment" in tools
    assert "restart_service_pod" in tools
    assert "rollout_restart_deployment" in tools
    assert "fetch_pod_logs" in tools


@pytest.mark.asyncio
async def test_k8s_restart_pod_mock_mode():
    res = await k8s_restart_pod(pod_name="payment-svc-7d8b9-x2p1", namespace="production")
    assert res["pod_name"] == "payment-svc-7d8b9-x2p1"
    assert "status" in res


@pytest.mark.asyncio
async def test_k8s_restart_pod_live_client():
    mock_core = MagicMock()
    mock_pod = MagicMock()
    mock_pod.status.pod_ip = "10.244.1.42"
    mock_pod.spec.node_name = "node-worker-01"
    mock_core.read_namespaced_pod.return_value = mock_pod

    with patch("backend.app.core.k8s.init_k8s_client", return_value=(mock_core, MagicMock())):
        res = await k8s_restart_pod(pod_name="api-gateway-1234", namespace="production")
        assert res["status"] == "POD_TERMINATION_TRIGGERED"
        assert res["previous_ip"] == "10.244.1.42"
        mock_core.delete_namespaced_pod.assert_called_once()


@pytest.mark.asyncio
async def test_k8s_rollout_restart_live_client():
    mock_apps = MagicMock()
    mock_dep = MagicMock()
    mock_dep.metadata.generation = 4
    mock_apps.patch_namespaced_deployment.return_value = mock_dep

    with patch("backend.app.core.k8s.init_k8s_client", return_value=(MagicMock(), mock_apps)):
        res = await k8s_rollout_restart_deployment(deployment_name="checkout-svc", namespace="production")
        assert res["status"] == "ROLLOUT_RESTART_TRIGGERED"
        assert res["generation"] == 4
        mock_apps.patch_namespaced_deployment.assert_called_once()


@pytest.mark.asyncio
async def test_k8s_rollback_deployment_live_client():
    mock_apps = MagicMock()
    
    # Current deployment
    mock_dep = MagicMock()
    mock_dep.metadata.annotations = {"deployment.kubernetes.io/revision": "3"}
    mock_c = MagicMock()
    mock_c.image = "checkout:v3.0.0"
    mock_dep.spec.template.spec.containers = [mock_c]
    mock_apps.read_namespaced_deployment.return_value = mock_dep

    # ReplicaSets
    rs1 = MagicMock()
    ref1 = MagicMock()
    ref1.kind = "Deployment"
    ref1.name = "checkout-svc"
    rs1.metadata.owner_references = [ref1]
    rs1.metadata.annotations = {"deployment.kubernetes.io/revision": "1"}
    c1 = MagicMock()
    c1.image = "checkout:v1.0.0"
    rs1.spec.template.spec.containers = [c1]

    rs2 = MagicMock()
    ref2 = MagicMock()
    ref2.kind = "Deployment"
    ref2.name = "checkout-svc"
    rs2.metadata.owner_references = [ref2]
    rs2.metadata.annotations = {"deployment.kubernetes.io/revision": "2"}
    c2 = MagicMock()
    c2.image = "checkout:v2.0.0"
    rs2.spec.template.spec.containers = [c2]

    mock_rs_list = MagicMock()
    mock_rs_list.items = [rs1, rs2]
    mock_apps.list_namespaced_replica_set.return_value = mock_rs_list

    with patch("backend.app.core.k8s.init_k8s_client", return_value=(MagicMock(), mock_apps)):
        res = await k8s_rollback_deployment(deployment_name="checkout-svc", namespace="production")
        assert res["status"] == "ROLLBACK_COMPLETED"
        assert res["current_revision"] == "3"
        assert res["rolled_back_revision"] == "2"
        mock_apps.patch_namespaced_deployment.assert_called_once()


@pytest.mark.asyncio
async def test_k8s_check_deployment_health():
    mock_core = MagicMock()
    mock_apps = MagicMock()

    mock_dep = MagicMock()
    mock_dep.spec.replicas = 3
    mock_dep.status.ready_replicas = 3
    mock_dep.status.available_replicas = 3
    mock_dep.status.updated_replicas = 3

    c1 = MagicMock()
    c1.type = "Available"
    c1.status = "True"
    mock_dep.status.conditions = [c1]
    mock_apps.read_namespaced_deployment.return_value = mock_dep

    with patch("backend.app.core.k8s.init_k8s_client", return_value=(mock_core, mock_apps)):
        health = await k8s_check_deployment_health(deployment_name="auth-svc", namespace="production")
        assert health["healthy"] is True
        assert health["ready_replicas"] == 3
