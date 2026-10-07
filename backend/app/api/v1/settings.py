from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any

from backend.app.auth.security import require_api_key
from backend.app.core.kill_switch import kill_switch
from backend.app.core.database import AsyncSessionLocal
from sqlalchemy import select, update
from backend.app.models.tool_invocation import ToolInvocation, InvocationStatus
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.post("/kill-switch")
async def engage_kill_switch(auth: str = Depends(require_api_key)) -> Dict[str, Any]:
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
async def disengage_kill_switch(auth: str = Depends(require_api_key)) -> Dict[str, Any]:
    """
    Disengage the emergency Kill-Switch and resume autonomous operations.
    """
    kill_switch.disengage()
    return {
        "status": "disengaged",
        "message": "✅ Normal operations resumed."
    }

@router.get("/kill-switch/status")
async def kill_switch_status(auth: str = Depends(require_api_key)) -> Dict[str, Any]:
    return {
        "engaged": kill_switch.is_engaged
    }
