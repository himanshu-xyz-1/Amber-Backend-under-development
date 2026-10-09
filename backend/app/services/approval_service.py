"""
Amber SRE Engine - Approval & Remediation Execution Service.
Shared service for executing human-in-the-loop (HITL) remediations
across Web Dashboard, Telegram Bot, and Slack integrations.
"""

import inspect
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.core.config import settings
from backend.app.core.kill_switch import kill_switch
from backend.app.models.incident import Incident, IncidentStatus
from backend.app.models.tool_invocation import (
    InvocationStatus,
    RiskLevel,
    ToolInvocation,
)
from backend.app.tools.base import tool_registry

logger = logging.getLogger(__name__)


class ApprovalExecutionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def execute_tool_approval(
    tool_invocation_id: str,
    action: str,
    db: AsyncSession,
    approved_by_id: uuid.UUID | None = None,
    payload_sha256: str | None = None,
    approver_label: str = "Authorized SRE",
) -> ToolInvocation:
    """
    Validates and executes or rejects a tool invocation.
    Ensures cryptographic hash verification and 10-minute TTL enforcement.
    Updates the parent incident status upon successful remediation.
    """
    try:
        inv_uuid = uuid.UUID(str(tool_invocation_id))
    except ValueError:
        raise ApprovalExecutionError("Invalid tool invocation UUID format.", status_code=400)

    result = await db.execute(
        select(ToolInvocation)
        .filter(ToolInvocation.id == inv_uuid)
        .with_for_update()
    )
    invocation = result.scalar_one_or_none()

    if not invocation:
        raise ApprovalExecutionError(f"Tool invocation '{tool_invocation_id}' not found.", status_code=404)

    if invocation.status in [InvocationStatus.EXECUTED, InvocationStatus.EXECUTING, InvocationStatus.APPROVED]:
        logger.info(f"Tool invocation '{tool_invocation_id}' is already approved/executed ({invocation.status.value}); returning cached execution.")
        return invocation

    if invocation.status != InvocationStatus.PENDING_APPROVAL:
        raise ApprovalExecutionError(
            f"Invocation cannot be approved: current status is {invocation.status.value}.",
            status_code=400
        )

    # 1. Cryptographic hash verification on approval
    if action == "approve" and invocation.payload_sha256:
        if not payload_sha256:
            raise ApprovalExecutionError(
                "Cryptographic verification required: payload_sha256 argument hash is mandatory.",
                status_code=403
            )
        if invocation.payload_sha256 != payload_sha256:
            raise ApprovalExecutionError(
                "Cryptographic payload mismatch! Potential argument tampering.",
                status_code=403
            )

    # 2. Check 10-minute TTL expiry
    now_utc = datetime.now(timezone.utc)
    if invocation.approval_expires_at:
        expiry = (
            invocation.approval_expires_at
            if invocation.approval_expires_at.tzinfo
            else invocation.approval_expires_at.replace(tzinfo=timezone.utc)
        )
        if expiry < now_utc:
            invocation.status = InvocationStatus.EXPIRED
            await db.commit()
            raise ApprovalExecutionError(
                "Approval request has expired (10-minute TTL exceeded).",
                status_code=400
            )

    # 3. Action handling
    if action == "approve":
        # Check Emergency Kill Switch
        if kill_switch.is_engaged:
            invocation.status = InvocationStatus.REJECTED
            invocation.error_message = "REJECTED_BY_KILL_SWITCH: System is in Read-Only Observation Mode."
            invocation.executed_at = now_utc
            await db.commit()
            raise ApprovalExecutionError("Action rejected: System kill switch is engaged.", status_code=403)

        invocation.status = InvocationStatus.APPROVED
        invocation.approved_by_id = approved_by_id
        invocation.approved_at = now_utc

        tool = tool_registry.get(invocation.tool_name)
        if tool:
            tool_args = invocation.tool_args or {}

            # Enforce Commercial License feature gate for remediation actions in production
            from backend.app.core.license import license_manager
            if invocation.risk_level == RiskLevel.HIGH and not license_manager.is_valid and settings.ENVIRONMENT not in ("test", "development"):
                invocation.status = InvocationStatus.FAILED
                invocation.error_message = "Automated high-risk remediation is locked in Community Edition. Active Enterprise license required."
                invocation.executed_at = datetime.now(timezone.utc)
                await db.commit()
                raise ApprovalExecutionError("Automated remediation locked: requires active Amber Enterprise license.", status_code=403)

            # Enforce argument validation guardrail before execution
            val_result = tool.validate_args(**tool_args)
            if inspect.iscoroutine(val_result):
                is_valid = await val_result
            else:
                is_valid = bool(val_result)

            if not is_valid:
                invocation.status = InvocationStatus.FAILED
                invocation.error_message = f"Tool argument validation guardrail rejected args for '{invocation.tool_name}'."
                invocation.executed_at = datetime.now(timezone.utc)
            else:
                invocation.status = InvocationStatus.EXECUTING
                try:
                    tool_res = await tool.execute(**tool_args)
                    invocation.execution_result = tool_res.data
                    invocation.health_check_passed = tool_res.success
                    invocation.executed_at = datetime.now(timezone.utc)
                    invocation.status = InvocationStatus.EXECUTED if tool_res.success else InvocationStatus.FAILED
                    if not tool_res.success:
                        invocation.error_message = tool_res.error

                        # ──────────────────────────────────────────────────────────────
                        # Auto-Rollback Guardrail — 4 conditions must ALL be true:
                        # 1. AUTO_ROLLBACK_ENABLED is explicitly True (default: False)
                        # 2. The failing tool was NOT itself a rollback/rollout-restart
                        #    (prevents ping-pong loop that would undo the rollback!)
                        # 3. The tool operated on a deployment_name (not a pod — pod
                        #    restart failures NEVER trigger deployment rollback, as the
                        #    human only approved a pod restart, not a deployment change)
                        # 4. A rollback_deployment tool is registered
                        # ──────────────────────────────────────────────────────────────
                        is_rollback_family = invocation.tool_name in (
                            "rollback_deployment", "rollout_restart_deployment"
                        )
                        dep_name = tool_args.get("deployment_name")

                        if (
                            settings.AUTO_ROLLBACK_ENABLED
                            and not is_rollback_family
                            and dep_name
                        ):
                            ns = tool_args.get("namespace", "production")
                            logger.warning(
                                f"[Auto-Rollback] Remediation '{invocation.tool_name}' failed post-fix "
                                f"health check on deployment '{dep_name}'. Triggering rollback..."
                            )
                            rollback_tool = tool_registry.get("rollback_deployment")
                            if rollback_tool:
                                try:
                                    rb_res = await rollback_tool.execute(deployment_name=dep_name, namespace=ns)
                                    invocation.execution_result = {
                                        **(invocation.execution_result or {}),
                                        "auto_rollback_triggered": True,
                                        "auto_rollback_success": rb_res.success,
                                        "auto_rollback_details": rb_res.data,
                                    }
                                    logger.info(f"[Auto-Rollback] Completed with success={rb_res.success}.")
                                except Exception as rb_err:
                                    logger.error(f"[Auto-Rollback] Execution error: {rb_err}")
                        elif is_rollback_family:
                            logger.warning(
                                f"[Auto-Rollback] Skipped — failing tool '{invocation.tool_name}' is already "
                                "in the rollback family. Running rollback on a failed rollback would undo it."
                            )
                        elif not dep_name:
                            logger.warning(
                                f"[Auto-Rollback] Skipped — tool '{invocation.tool_name}' has no "
                                "deployment_name arg. Pod-level failures require human review, not deployment rollback."
                            )

                except Exception as e:
                    logger.exception(f"Error executing approved tool {invocation.tool_name}")
                    invocation.status = InvocationStatus.FAILED
                    invocation.error_message = str(e)
                    invocation.executed_at = datetime.now(timezone.utc)
        else:
            invocation.status = InvocationStatus.FAILED
            invocation.error_message = f"Tool '{invocation.tool_name}' not found in registry"

        # Update parent incident if remediation was executed
        if invocation.incident_id:
            inc_res = await db.execute(
                select(Incident)
                .filter(Incident.id == invocation.incident_id)
                .with_for_update()
            )
            incident = inc_res.scalar_one_or_none()
            if incident:
                if invocation.status == InvocationStatus.EXECUTED:
                    incident.status = IncidentStatus.RESOLVED
                    incident.resolved_at = datetime.now(timezone.utc)
                    logger.info(
                        f"Remediation '{invocation.tool_name}' completed for incident '{incident.id}' "
                        f"(approver: {approver_label})."
                    )
                elif invocation.status == InvocationStatus.FAILED:
                    if invocation.execution_result and invocation.execution_result.get("auto_rollback_triggered"):
                        incident.status = IncidentStatus.ESCALATED
                        incident.remediation_plan = {
                            "status": "AUTO_ROLLED_BACK",
                            "reason": "Post-fix health verification failed; deployment safely rolled back to stable revision.",
                            "details": invocation.execution_result
                        }
                    else:
                        incident.status = IncidentStatus.FAILED

    elif action == "reject":
        invocation.status = InvocationStatus.REJECTED
        if invocation.incident_id:
            inc_res = await db.execute(
                select(Incident)
                .filter(Incident.id == invocation.incident_id)
                .with_for_update()
            )
            incident = inc_res.scalar_one_or_none()
            if incident and incident.status == IncidentStatus.PROPOSED:
                incident.status = IncidentStatus.ESCALATED
    else:
        raise ApprovalExecutionError("Invalid action: must be 'approve' or 'reject'.", status_code=400)

    await db.commit()
    await db.refresh(invocation)
    return invocation
