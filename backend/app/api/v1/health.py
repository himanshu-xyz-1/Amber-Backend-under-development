from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import get_db

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("/liveness")
async def check_liveness() -> dict[str, Any]:
    return {"status": "alive", "app": "Amber", "version": "0.1.0"}

@router.get("/readiness")
async def check_readiness(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    # Check database
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"
        raise HTTPException(status_code=503, detail={"status": "not ready", "database": db_status})
    
    # Check redis if enabled
    if settings.REDIS_ENABLED:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await r.ping()
            await r.aclose()
            redis_status = "connected"
        except Exception:
            redis_status = "disconnected"
    else:
        redis_status = "disabled"

    # Check Kubernetes readiness
    from backend.app.core.k8s import is_k8s_available
    from backend.app.core.license import license_manager
    k8s_status = "connected" if is_k8s_available() else "standby"

    return {
        "status": "ready",
        "database": db_status,
        "redis": redis_status,
        "kubernetes": k8s_status,
        "license": license_manager.status,
    }
