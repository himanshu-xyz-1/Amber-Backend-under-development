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
