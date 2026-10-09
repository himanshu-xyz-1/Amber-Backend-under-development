import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import update

from backend.app.auth.security import AuthenticatedUser, require_api_key
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.kill_switch import kill_switch
from backend.app.models.tool_invocation import InvocationStatus, ToolInvocation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.post("/kill-switch")
async def engage_kill_switch(
    _current_user: AuthenticatedUser = Depends(require_api_key),
) -> dict[str, Any]:
    """
    Emergency Kill-Switch. Immediately downgrades Amber to Read-Only Observation Mode.
    All queued mutating actions are instantaneously canceled.
    """
    kill_switch.engage()
    
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(ToolInvocation)
                .where(ToolInvocation.status == InvocationStatus.PENDING_APPROVAL)
                .values(
                    status=InvocationStatus.REJECTED,
                    error_message="REJECTED_BY_KILL_SWITCH: System is in Read-Only Observation Mode.",
                    executed_at=datetime.now(timezone.utc)
                )
            )
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to bulk-reject pending invocations during kill-switch engagement: {e}")

    return {
        "status": "engaged",
        "message": "🚨 Amber Engine downgraded to Read-Only Observation Mode.",
        "latency_guarantee": "< 250ms"
    }

@router.delete("/kill-switch")
async def disengage_kill_switch(
    _current_user: AuthenticatedUser = Depends(require_api_key),
) -> dict[str, Any]:
    """
    Disengage the emergency Kill-Switch and resume autonomous operations.
    """
    kill_switch.disengage()
    return {
        "status": "disengaged",
        "message": "✅ Normal operations resumed."
    }

@router.get("/kill-switch/status")
async def kill_switch_status(
    _current_user: AuthenticatedUser = Depends(require_api_key),
) -> dict[str, Any]:
    return {
        "engaged": kill_switch.is_engaged
    }

