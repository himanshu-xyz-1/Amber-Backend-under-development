import logging
import time
from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.k8s import (
    k8s_restart_pod,
    k8s_rollback_deployment,
    k8s_rollout_restart_deployment,
    k8s_check_deployment_health,
    K8sExecutionError,
)
from backend.app.tools.base import BaseTool, RiskLevel, ToolResult, tool_registry

logger = logging.getLogger(__name__)


class KillDatabaseConnections(BaseTool):
    """
    Production database connection remediation tool.
    Terminates hanging, leaked, or idle-in-transaction PostgreSQL connections by PID.
    Guarded by strict PID validation rules (never pid 1, max 5 batch limit)
    and parameterized SQL statements to prevent injection.
    """
    @property
    def name(self) -> str:
        return "kill_db_connections"

    @property
    def description(self) -> str:
        return "Terminate specific hanging database connections by PID"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.HIGH

    @property
    def reversible(self) -> bool:
        return False

    @property
    def max_execution_seconds(self) -> int:
        return 10

    def validate_args(self, **kwargs) -> bool:
        # Strict key whitelist to prevent prompt injection or bypass via extra arguments
        allowed_keys = {"pids", "target_db_url"}
        if settings.ENVIRONMENT == "test":
            allowed_keys.add("mock")

        for key in kwargs:
            if key not in allowed_keys:
                logger.warning(f"KillDatabaseConnections rejected unknown argument: '{key}'")
                return False

        if "mock" in kwargs and settings.ENVIRONMENT != "test":
            logger.error("KillDatabaseConnections: 'mock' parameter is strictly forbidden outside test environment.")
            return False

        if "pids" not in kwargs or not isinstance(kwargs["pids"], list):
            return False
        pids = kwargs["pids"]
        if not pids or len(pids) > 5:
            return False
        for pid in pids:
            if not isinstance(pid, int) or pid <= 1:
                return False
        return True

    async def execute(self, **kwargs) -> ToolResult:
        start_time = time.time()
        pids: List[int] = kwargs.get("pids", [])
        target_db_url = kwargs.get("target_db_url")
        terminated_pids = []
        failed_pids = []

        # Allow explicit mock execution ONLY in test environment
        if kwargs.get("mock") is True:
            if settings.ENVIRONMENT != "test":
                return ToolResult(
                    success=False,
                    data={"terminated_pids": [], "failed_pids": pids},
                    error="Security violation: 'mock' parameter is strictly forbidden outside test environment.",
                    execution_time_ms=(time.time() - start_time) * 1000
                )
            return ToolResult(
                success=True,
                data={"terminated_pids": pids, "failed_pids": [], "execution_status": "SUCCESS"},
                error=None,
                execution_time_ms=(time.time() - start_time) * 1000
            )

        active_before = None
        active_after = None

        custom_engine = None
        if target_db_url:
            try:
                custom_engine = create_async_engine(target_db_url)
            except Exception as e:
                logger.error(f"Cannot connect to target database '{target_db_url}': {e}")
                return ToolResult(
                    success=False,
                    data={"terminated_pids": [], "failed_pids": pids},
                    error=f"Could not connect to target database: {str(e)}",
                    execution_time_ms=(time.time() - start_time) * 1000
                )
        elif settings.ENVIRONMENT not in ("test", "development"):
            # Mandatory safety check: never terminate connections on Amber's own database in production
            return ToolResult(
                success=False,
                data={"terminated_pids": [], "failed_pids": pids},
                error="Safety refusal: 'target_db_url' is mandatory in production. Amber refuses to terminate connections on its internal database.",
                execution_time_ms=(time.time() - start_time) * 1000
            )

        try:
            session_cm = AsyncSession(custom_engine) if custom_engine else AsyncSessionLocal()
            async with session_cm as session:
                is_postgres = bool(session.bind and "postgresql" in session.bind.dialect.name)
                if is_postgres:
                    # 1. Check count before termination if postgres
                    try:
                        count_res = await session.execute(text("SELECT count(*) FROM pg_stat_activity WHERE state IS NOT NULL;"))
                        active_before = count_res.scalar()
                    except Exception:
                        pass

                    # 2. Terminate target PIDs using bound parameters
                    for pid in pids:
                        try:
                            res = await session.execute(
                                text("SELECT pg_terminate_backend(:pid);"),
                                {"pid": pid}
                            )
                            success = res.scalar()
                            if success:
                                terminated_pids.append(pid)
                            else:
                                failed_pids.append(pid)
                        except Exception as err:
                            logger.warning(f"Could not terminate PID {pid}: {err}")
                            failed_pids.append(pid)
                    await session.commit()

                    # 3. Check count after termination if postgres
                    try:
                        count_after_res = await session.execute(text("SELECT count(*) FROM pg_stat_activity WHERE state IS NOT NULL;"))
                        active_after = count_after_res.scalar()
                    except Exception:
                        pass
                else:
                    dialect_name = session.bind.dialect.name if session.bind else "unknown"
                    logger.error(f"Target database is not PostgreSQL ({dialect_name}). Connection termination is PostgreSQL-only.")
                    failed_pids = list(pids)
                    terminated_pids = []
        except Exception as e:
            logger.error(f"Direct connection execution error: {e}")
            failed_pids = list(pids)
            terminated_pids = []
        finally:
            if custom_engine:
                await custom_engine.dispose()

        data = {
            "terminated_pids": terminated_pids,
            "failed_pids": failed_pids,
            "active_connections_before": active_before,
            "active_connections_after": active_after,
            "execution_status": "SUCCESS" if (terminated_pids and not failed_pids) else ("PARTIAL" if terminated_pids else "FAILED")
        }

        execution_time_ms = (time.time() - start_time) * 1000
        # True success requires at least one terminated PID and ZERO failed PIDs
        is_success = bool(terminated_pids) and not bool(failed_pids)
        error_msg = None
        if failed_pids:
            error_msg = f"Failed to terminate PIDs: {failed_pids}"

        return ToolResult(
            success=is_success,
            data=data,
            error=error_msg,
            execution_time_ms=execution_time_ms
        )


class RollbackDeployment(BaseTool):
    """
    Production Kubernetes deployment rollback engine.
    Executes programmatic rollout undo via the Kubernetes API, restoring the previous stable ReplicaSet.
    Includes automated post-fix health probing to verify replica recovery.
    """
    @property
    def name(self) -> str:
        return "rollback_deployment"

    @property
    def description(self) -> str:
        return "Rollback a Kubernetes deployment to a previous stable revision with health verification"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.HIGH

    @property
    def reversible(self) -> bool:
        return True

    @property
    def max_execution_seconds(self) -> int:
        return 60

    def validate_args(self, **kwargs) -> bool:
        if "deployment_name" not in kwargs or not isinstance(kwargs["deployment_name"], str):
            return False
        dep_name = kwargs["deployment_name"].strip()
        if not dep_name or len(dep_name) > 253:
            return False
        # If live Kubernetes cluster is connected, verify that the deployment exists
        namespace = kwargs.get("namespace", "production")
        from backend.app.core.k8s import is_k8s_available, k8s_deployment_exists
        if is_k8s_available() and not k8s_deployment_exists(dep_name, namespace=namespace):
            logger.warning(f"Guardrail rejected rollback: deployment '{dep_name}' not found in namespace '{namespace}'.")
            return False
        return True

    async def execute(self, **kwargs) -> ToolResult:
        start_time = time.time()
        deployment = kwargs["deployment_name"]
        target_revision = kwargs.get("target_revision", "previous")
        namespace = kwargs.get("namespace", "production")

        try:
            # 1. Execute live Kubernetes rollback
            rollback_data = await k8s_rollback_deployment(
                deployment_name=deployment,
                namespace=namespace,
                target_revision=target_revision if target_revision != "previous" else None
            )

            # 2. Automated post-fix health verification
            health_check = await k8s_check_deployment_health(
                deployment_name=deployment,
                namespace=namespace
            )

            rollback_data["post_remediation_health"] = health_check
            is_healthy = health_check.get("healthy", True)

            execution_time_ms = (time.time() - start_time) * 1000
            return ToolResult(
                success=is_healthy,
                data=rollback_data,
                error=None if is_healthy else "Rollback initiated but deployment replica readiness check failed.",
                execution_time_ms=execution_time_ms
            )
        except K8sExecutionError as e:
            execution_time_ms = (time.time() - start_time) * 1000
            return ToolResult(
                success=False,
                data={"deployment_name": deployment, "namespace": namespace, "status": "ROLLBACK_FAILED"},
                error=str(e.message),
                execution_time_ms=execution_time_ms
            )


class RestartServicePod(BaseTool):
    """
    Production single-pod restarter.
    Invokes Kubernetes CoreV1 API to terminate the pod, triggering an immediate
    healthy replica spin-up by the managing ReplicaSet controller.
    """
    @property
    def name(self) -> str:
        return "restart_service_pod"

    @property
    def description(self) -> str:
        return "Restart a specific Kubernetes pod by triggering controller recreation"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.HIGH

    @property
    def reversible(self) -> bool:
        return True

    @property
    def max_execution_seconds(self) -> int:
        return 30

    def validate_args(self, **kwargs) -> bool:
        if "pod_name" not in kwargs or not isinstance(kwargs["pod_name"], str):
            return False
        pod_name = kwargs["pod_name"].strip()
        if not pod_name or len(pod_name) > 253:
            return False
        # If live Kubernetes cluster is connected, verify that the pod exists
        namespace = kwargs.get("namespace", "production")
        from backend.app.core.k8s import is_k8s_available, k8s_pod_exists
        if is_k8s_available() and not k8s_pod_exists(pod_name, namespace=namespace):
            logger.warning(f"Guardrail rejected pod restart: pod '{pod_name}' not found in namespace '{namespace}'.")
            return False
        return True

    async def execute(self, **kwargs) -> ToolResult:
        start_time = time.time()
        pod_name = kwargs["pod_name"]
        namespace = kwargs.get("namespace", "production")

        try:
            # Execute live Kubernetes pod termination
            pod_data = await k8s_restart_pod(pod_name=pod_name, namespace=namespace)
            execution_time_ms = (time.time() - start_time) * 1000
            return ToolResult(
                success=True,
                data=pod_data,
                error=None,
                execution_time_ms=execution_time_ms
            )
        except K8sExecutionError as e:
            execution_time_ms = (time.time() - start_time) * 1000
            return ToolResult(
                success=False,
                data={"pod_name": pod_name, "namespace": namespace, "status": "RESTART_FAILED"},
                error=str(e.message),
                execution_time_ms=execution_time_ms
            )


class RolloutRestartDeployment(BaseTool):
    """
    Production deployment rollout restarter (kubectl rollout restart).
    Performs zero-downtime rolling restart of all pods in a deployment.
    """
    @property
    def name(self) -> str:
        return "rollout_restart_deployment"

    @property
    def description(self) -> str:
        return "Zero-downtime rolling restart of all pods in a deployment"

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.HIGH

    @property
    def reversible(self) -> bool:
        return True

    @property
    def max_execution_seconds(self) -> int:
        return 45

    def validate_args(self, **kwargs) -> bool:
        return "deployment_name" in kwargs and isinstance(kwargs["deployment_name"], str)

    async def execute(self, **kwargs) -> ToolResult:
        start_time = time.time()
        deployment = kwargs["deployment_name"]
        namespace = kwargs.get("namespace", "production")

        try:
            restart_data = await k8s_rollout_restart_deployment(
                deployment_name=deployment,
                namespace=namespace
            )
            execution_time_ms = (time.time() - start_time) * 1000
            return ToolResult(
                success=True,
                data=restart_data,
                error=None,
                execution_time_ms=execution_time_ms
            )
        except K8sExecutionError as e:
            execution_time_ms = (time.time() - start_time) * 1000
            return ToolResult(
                success=False,
                data={"deployment_name": deployment, "namespace": namespace, "status": "ROLLOUT_FAILED"},
                error=str(e.message),
                execution_time_ms=execution_time_ms
            )


# Register remediation tools into global registry
tool_registry.register(KillDatabaseConnections())
tool_registry.register(RollbackDeployment())
tool_registry.register(RestartServicePod())
tool_registry.register(RolloutRestartDeployment())
