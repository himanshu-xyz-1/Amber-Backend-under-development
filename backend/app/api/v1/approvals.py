from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.auth.security import require_api_key, AuthenticatedUser
from backend.app.core.database import get_db
from backend.app.models.tool_invocation import ToolInvocation, InvocationStatus
from backend.app.schemas.approval import ApprovalRequest, ApprovalResponse
from backend.app.services.approval_service import execute_tool_approval, ApprovalExecutionError

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.post("", response_model=ApprovalResponse)
async def submit_approval(
    request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_api_key)
):
    """
    Executes or rejects a pending human-in-the-loop remediation tool.
    Guarded by API Key/Bearer authentication and cryptographic payload SHA-256 verification.
    """
    if current_user.role and current_user.role.upper() in ["DEVELOPER", "VIEWER"]:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Developers / Viewers cannot approve state-mutating remediation actions. Required role: SRE, LEAD, or ADMIN."
        )

    try:
        invocation = await execute_tool_approval(
            tool_invocation_id=str(request.tool_invocation_id),
            action=request.action,
            db=db,
            approved_by_id=current_user.user_id or request.approved_by_id,
            payload_sha256=request.payload_sha256,
            approver_label=current_user.identity,
        )
        return invocation
    except ApprovalExecutionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/pending", response_model=List[ApprovalResponse])
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_api_key)
):
    """
    Returns pending approvals. Requires administrative API Key or Bearer token authentication.
    """
    result = await db.execute(
        select(ToolInvocation)
        .filter(ToolInvocation.status == InvocationStatus.PENDING_APPROVAL)
        .order_by(ToolInvocation.created_at.desc())
    )
    return result.scalars().all()


@router.get("/audit")
async def get_audit_trail(
    limit: int = 10,
    format: str = "json",
    download: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_api_key),
):
    """
    Retrieves the historical HITL remediation audit trail.
    Supports JSON and formatted text log outputs with optional attachment download.
    """
    import json
    from datetime import datetime, timezone
    from fastapi.responses import Response

    safe_limit = max(1, min(100, limit))
    result = await db.execute(
        select(ToolInvocation)
        .order_by(ToolInvocation.created_at.desc())
        .limit(safe_limit)
    )
    invocations = result.scalars().all()

    records = [
        {
            "invocation_id": str(inv.id),
            "tool_name": inv.tool_name,
            "tool_args": inv.tool_args,
            "risk_level": inv.risk_level.value if hasattr(inv.risk_level, "value") else str(inv.risk_level),
            "status": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
            "approved_by_id": str(inv.approved_by_id) if inv.approved_by_id else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "approved_at": inv.approved_at.isoformat() if inv.approved_at else None,
            "executed_at": inv.executed_at.isoformat() if inv.executed_at else None,
            "health_check_passed": inv.health_check_passed,
            "payload_sha256": inv.payload_sha256,
            "execution_result": inv.execution_result,
            "error_message": inv.error_message,
        }
        for inv in invocations
    ]

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format.lower() == "text":
        lines = [
            f"# AMBER SRE AUDIT LOG TRAIL — {len(records)} ENTRIES",
            f"# Generated at: {datetime.now(timezone.utc).isoformat()} | Requester: {current_user.identity}",
            "# " + "=" * 70,
            ""
        ]
        for idx, rec in enumerate(records, 1):
            health = "PASSED" if rec["health_check_passed"] else ("FAILED" if rec["health_check_passed"] is False else "N/A")
            lines.append(f"[{idx}] {rec['created_at'] or 'UNKNOWN'} | Tool: {rec['tool_name']} | Status: {rec['status']}")
            lines.append(f"    Approver: {rec['approved_by_id'] or 'Authorized SRE'} | Hash: {rec['payload_sha256'] or 'N/A'}")
            lines.append(f"    Health Probe: {health} | Args: {json.dumps(rec['tool_args'] or {})}")
            if rec["error_message"]:
                lines.append(f"    Error: {rec['error_message']}")
            lines.append("")

        text_content = "\n".join(lines)
        headers = {}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="amber_audit_{timestamp_str}.log"'
        return Response(content=text_content, media_type="text/plain; charset=utf-8", headers=headers)

    # JSON format
    json_bytes = json.dumps({"total": len(records), "limit": safe_limit, "audit_trail": records}, indent=2).encode("utf-8")
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="amber_audit_{timestamp_str}.json"'
    return Response(content=json_bytes, media_type="application/json", headers=headers)

