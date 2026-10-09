"""
Amber Core Security & Authentication Module.
Provides API key, Bearer JWT, and Webhook secret authentication dependencies
for REST endpoints, approvals, and dynamic license activation.
"""

import hashlib
import hmac
import logging
from typing import Optional, List
import uuid

from fastapi import Depends, HTTPException, Header, Query, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)


def hash_api_key(raw_key: str) -> str:
    """Computes a secure SHA-256 hash of a raw API key."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


class AuthenticatedUser(BaseModel):
    identity: str
    role: str = "sre_admin"
    user_id: Optional[uuid.UUID] = None
    auth_method: str = "api_key"


async def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_approver_email: Optional[str] = Header(None, alias="X-Approver-Email"),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> AuthenticatedUser:
    """
    Enforces authentication for administrative & approval REST routes.
    Accepts:
    1. Per-User Scoped API Key ('amb_usr_...') verified against users table
    2. Master System API Key ('X-API-Key' / 'Bearer')
    3. Signed JWT Token ('Authorization: Bearer <jwt>')
    """
    token = x_api_key or (bearer.credentials if bearer else None)

    if not token:
        if settings.ENVIRONMENT in ("development", "test") and not settings.AMBER_API_KEY:
            approver = x_approver_email or "dev-local-sre"
            return AuthenticatedUser(identity=approver, role="admin", auth_method="dev_local")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: Missing 'X-API-Key' or 'Authorization: Bearer' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    clean_token = token.strip()

    # 1. Per-User Scoped API Key Verification (SHA-256 hash match against users table)
    token_hash = hash_api_key(clean_token)
    try:
        from backend.app.core.database import AsyncSessionLocal
        from backend.app.models.user import User
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            user_res = await session.execute(
                select(User).filter(User.api_key_hash == token_hash, User.is_active == True)
            )
            matched_user = user_res.scalars().first()
            if matched_user:
                role_val = matched_user.role.value if hasattr(matched_user.role, "value") else str(matched_user.role)
                return AuthenticatedUser(
                    identity=f"user:{matched_user.email}",
                    role=role_val,
                    user_id=matched_user.id,
                    auth_method="user_api_key",
                )
    except Exception as db_err:
        logger.debug(f"Per-user API key lookup skipped: {db_err}")

    # 2. Signed JWT Token Check
    try:
        import jwt
        payload = jwt.decode(
            clean_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        sub = payload.get("sub") or payload.get("email") or "jwt:authenticated-user"
        role = payload.get("role", "sre")
        user_id_str = payload.get("user_id")
        user_id_val = uuid.UUID(user_id_str) if user_id_str else None
        return AuthenticatedUser(
            identity=f"user:{sub}",
            role=role,
            user_id=user_id_val,
            auth_method="jwt"
        )
    except Exception:
        pass

    # 3. Master System API Key Check
    configured_key = settings.AMBER_API_KEY
    if configured_key and hmac.compare_digest(clean_token, configured_key.strip()):
        if x_approver_email:
            clean_email = x_approver_email.strip().lower()
            try:
                from backend.app.core.database import AsyncSessionLocal
                from backend.app.models.user import User
                from sqlalchemy import select
                async with AsyncSessionLocal() as session:
                    user_res = await session.execute(
                        select(User).filter(User.email == clean_email, User.is_active == True)
                    )
                    verified_user = user_res.scalars().first()
                    if verified_user:
                        role_val = verified_user.role.value if hasattr(verified_user.role, "value") else str(verified_user.role)
                        return AuthenticatedUser(
                            identity=f"user:{verified_user.email}",
                            role=role_val,
                            user_id=verified_user.id,
                            auth_method="verified_api_approver"
                        )
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Unregistered approver identity: '{clean_email}' does not match any active SRE user account."
                        )
            except HTTPException:
                raise
            except Exception as db_err:
                if settings.ENVIRONMENT not in ("test", "development"):
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Approver identity verification failed: {db_err}"
                    )
                logger.debug(f"User DB verification skipped: {db_err}")

        return AuthenticatedUser(identity="api-key:system-admin", role="admin", auth_method="api_key")

    # In dev/test when no AMBER_API_KEY configured
    if settings.ENVIRONMENT in ("development", "test") and not configured_key:
        approver = x_approver_email or "dev-local-sre"
        return AuthenticatedUser(identity=approver, role="admin", auth_method="dev_local")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key or Bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_webhook_auth(
    request: Request,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    token: Optional[str] = Query(None),
) -> bool:
    """
    Guards incoming webhook intake against unauthenticated spam and fake alert injection.
    Production behaviour (FAIL-CLOSED): WEBHOOK_SECRET must be configured.
    Development/test: allows unprotected webhooks for local testing.
    """
    secret = settings.WEBHOOK_SECRET

    if not secret:
        # Fail-closed in production — reject unauthenticated webhooks
        if settings.ENVIRONMENT not in ("development", "test"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Webhook intake is disabled: WEBHOOK_SECRET is not configured in production. "
                    "Set WEBHOOK_SECRET in your .env to enable webhook ingestion."
                ),
            )
        # Dev/test: allow without secret (log a loud warning)
        logger.warning(
            "[SECURITY] WEBHOOK_SECRET not set in development mode. "
            "All webhook intake is unauthenticated. NEVER deploy this to production."
        )
        return True

    provided_secret = x_webhook_secret or token
    if not provided_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook authentication failed: Missing 'X-Webhook-Secret' header or token.",
        )

    if not hmac.compare_digest(provided_secret.strip(), secret.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook authentication failed: Invalid secret.",
        )

    return True


def require_roles(allowed_roles: List[str]):
    """
    Enforces Role-Based Access Control (RBAC) on API routes.
    Validates that the authenticated user possesses an allowed role.
    Example: Depends(require_roles(["ADMIN", "LEAD", "SRE"]))
    """
    async def role_checker(user: AuthenticatedUser = Depends(require_api_key)) -> AuthenticatedUser:
        normalized_allowed = [r.strip().upper() for r in allowed_roles]
        user_role = (user.role or "").strip().upper()
        if user_role not in normalized_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Insufficient privileges. Required one of {allowed_roles}, but user role is '{user.role}'.",
            )
        return user
    return role_checker

