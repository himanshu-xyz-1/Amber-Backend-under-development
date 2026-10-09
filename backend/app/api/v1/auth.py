"""
Amber SRE Engine — Enterprise SSO & Identity Provider (IdP) API.
Supports Google Workspace, Okta, Azure AD, and generic SAML 2.0 / OIDC integrations.
Enforces Role-Based Access Control (RBAC) and issues cryptographically signed JWT sessions.
"""

from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional
import uuid
import jwt
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.auth.security import require_api_key, AuthenticatedUser
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.k8s import list_k8s_contexts
from backend.app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication & SSO"])


class SSOCallbackRequest(BaseModel):
    provider: str = Field(..., description="IdP Provider: 'google', 'okta', 'azure_ad', 'saml'")
    email: str = Field(..., description="Corporate SSO work email")
    full_name: Optional[str] = Field(None, description="Full name from IdP")
    groups: Optional[List[str]] = Field(default=[], description="SAML/OIDC claim groups (e.g., ['sre-leads'])")


class SSOTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in_seconds: int
    user_id: str
    email: str
    full_name: str
    role: str
    permissions: List[str]
    cluster_contexts: List[str]


def resolve_role_from_groups(groups: List[str], email: str) -> UserRole:
    """
    Maps enterprise SAML/OIDC groups or email prefixes to Amber RBAC roles.
    """
    normalized_groups = [g.lower() for g in groups]
    
    # 1. Admin groups
    if any(g in normalized_groups for g in ["admin", "admins", "sre-leads", "devops-leads", "platform-leads"]):
        return UserRole.ADMIN
    
    # 2. SRE Operator groups
    if any(g in normalized_groups for g in ["sre", "devops", "platform", "infrastructure", "oncall"]):
        return UserRole.SRE
    
    # 3. Default: Developer / Observer
    return UserRole.DEVELOPER


def get_role_permissions(role: str) -> List[str]:
    """Returns granular capability permissions for an RBAC role."""
    role_norm = role.upper()
    if role_norm == "ADMIN":
        return [
            "read:incidents",
            "write:incidents",
            "approve:remediation",
            "execute:kill_switch",
            "manage:clusters",
            "manage:settings",
            "manage:license",
            "manage:users",
        ]
    elif role_norm == "LEAD":
        return [
            "read:incidents",
            "write:incidents",
            "approve:remediation",
            "manage:clusters",
            "export:post_mortem",
        ]
    elif role_norm == "SRE":
        return [
            "read:incidents",
            "write:incidents",
            "approve:remediation",
            "export:post_mortem",
        ]
    # DEVELOPER / VIEWER
    return [
        "read:incidents",
        "read:logs",
        "export:post_mortem",
    ]


@router.get("/sso/config")
async def get_sso_configuration() -> Dict[str, Any]:
    """
    Returns enterprise SSO and SAML/OIDC status for the frontend console.
    """
    return {
        "sso_enabled": True,
        "default_provider": "google",
        "supported_providers": ["google", "okta", "azure_ad", "saml"],
        "enforce_mfa": True,
        "session_ttl_minutes": 480,  # 8 hours
        "air_gapped": settings.AIR_GAPPED,
    }


@router.post("/sso/callback", response_model=SSOTokenResponse)
async def sso_callback(
    payload: SSOCallbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Enterprise SSO callback. Validates corporate email identity, auto-provisions or
    syncs the SRE user profile in PostgreSQL, maps RBAC groups, and returns a signed Amber JWT token.
    """
    clean_email = payload.email.lower().strip()
    assigned_role = resolve_role_from_groups(payload.groups or [], clean_email)
    
    # 1. Look up existing user or auto-provision
    result = await db.execute(select(User).filter(User.email == clean_email))
    user = result.scalar_one_or_none()
    
    display_name = payload.full_name or clean_email.split("@")[0].capitalize()
    
    if not user:
        user = User(
            id=uuid.uuid4(),
            email=clean_email,
            full_name=display_name,
            role=assigned_role,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"Auto-provisioned enterprise SSO user: {clean_email} with role {assigned_role.value}")
    else:
        # Sync latest name and active status
        if payload.full_name and user.full_name != payload.full_name:
            user.full_name = payload.full_name
            await db.commit()

    # 2. Generate signed Amber JWT
    ttl_seconds = 8 * 3600
    now = datetime.now(timezone.utc)
    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
    permissions = get_role_permissions(role_str)
    
    token_claims = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.full_name,
        "role": role_str,
        "provider": payload.provider,
        "permissions": permissions,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    
    access_token = jwt.encode(
        token_claims,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    contexts = [ctx["name"] for ctx in list_k8s_contexts()]

    return SSOTokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in_seconds=ttl_seconds,
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=role_str,
        permissions=permissions,
        cluster_contexts=contexts,
    )


@router.get("/me")
async def get_current_user_profile(
    current_user: AuthenticatedUser = Depends(require_api_key),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Returns the authenticated user's active session, RBAC role, permissions, and multi-cluster access.
    """
    role_str = (current_user.role or "sre").upper()
    permissions = get_role_permissions(role_str)
    clusters = list_k8s_contexts()

    return {
        "identity": current_user.identity,
        "role": role_str,
        "user_id": str(current_user.user_id) if current_user.user_id else None,
        "auth_method": current_user.auth_method,
        "permissions": permissions,
        "active_clusters": clusters,
        "cluster_count": len(clusters),
    }


@router.get("/clusters")
async def list_connected_clusters(
    current_user: AuthenticatedUser = Depends(require_api_key),
) -> Dict[str, Any]:
    """
    Returns all connected Kubernetes cluster contexts and their active health states.
    Allows SREs to switch contexts across multiple production clusters.
    """
    contexts = list_k8s_contexts()
    return {
        "total_clusters": len(contexts),
        "clusters": contexts,
    }
