"""
Amber SRE Engine — Incidents API.

Auth policy:
- GET /incidents, GET /incidents/{id}: Public read (dashboard display).
- POST /incidents, PATCH /incidents/{id}: Require API key (no unauthorized incident creation/modification).
- GET /incidents/{id}/timeline, /post-mortem: Public read.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.auth.security import AuthenticatedUser, require_api_key
from backend.app.core.database import get_db
from backend.app.models.alert import Alert
from backend.app.models.incident import Incident, IncidentSeverity, IncidentStatus
from backend.app.models.tool_invocation import ToolInvocation
from backend.app.schemas.approval import ApprovalResponse
from backend.app.schemas.incident import (
    IncidentCreate,
    IncidentResponse,
    IncidentUpdate,
)
from backend.app.services.post_mortem import generate_incident_post_mortem

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_api_key),
):
    """List incidents. Requires API key or authenticated bearer token."""
    query = select(Incident).order_by(Incident.created_at.desc())
    if status:
        query = query.filter(Incident.status == status)
    if severity:
        query = query.filter(Incident.severity == severity)

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_api_key),
):
    """Get incident details. Requires API key or authenticated bearer token."""
    result = await db.execute(select(Incident).filter(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.post("", response_model=IncidentResponse, status_code=201)
async def create_incident(
    incident_in: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_api_key),
):
    """Create a new incident. Requires API key authentication."""
    incident = Incident(
        title=incident_in.title,
        description=incident_in.description,
        severity=IncidentSeverity[incident_in.severity.value],
        status=IncidentStatus.TRIGGERED,
        source_service=incident_in.source_service,
    )
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    return incident


@router.patch("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: UUID,
    incident_in: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_api_key),
):
    """Update an incident. Requires API key authentication."""
    result = await db.execute(select(Incident).filter(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    update_data = incident_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "severity" and value is not None:
            setattr(incident, key, IncidentSeverity[value])
        elif key == "status" and value is not None:
            setattr(incident, key, IncidentStatus[value])
        else:
            setattr(incident, key, value)

    await db.commit()
    await db.refresh(incident)
    return incident


@router.delete("/{incident_id}", status_code=204)
async def delete_incident(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_api_key),
):
    """Soft-delete an incident to preserve the immutable audit trail."""
    result = await db.execute(select(Incident).filter(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    # Soft delete: mark as cancelled and log approver identity in description
    incident.status = IncidentStatus.CANCELLED
    incident.description = f"[ARCHIVED by {current_user.identity}] {incident.description or ''}".strip()
    await db.commit()


@router.get("/{incident_id}/timeline", response_model=list[ApprovalResponse])
async def get_incident_timeline(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_api_key),
):
    """Get incident remediation timeline. Requires API key."""
    result = await db.execute(
        select(ToolInvocation)
        .filter(ToolInvocation.incident_id == incident_id)
        .order_by(ToolInvocation.created_at.asc())
    )
    return result.scalars().all()


@router.get("/{incident_id}/post-mortem")
async def get_incident_post_mortem_report(
    incident_id: UUID,
    format: str | None = Query("markdown", description="Format: 'markdown' or 'json'"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_api_key),
):
    """
    Generates an executive-ready Markdown or JSON Incident Post-Mortem report. Requires API key.
    """
    inc_res = await db.execute(select(Incident).filter(Incident.id == incident_id))
    incident = inc_res.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    alerts_res = await db.execute(select(Alert).filter(Alert.incident_id == incident_id))
    alerts = alerts_res.scalars().all()

    inv_res = await db.execute(
        select(ToolInvocation)
        .filter(ToolInvocation.incident_id == incident_id)
        .order_by(ToolInvocation.created_at.asc())
    )
    invocations = inv_res.scalars().all()

    md_content = generate_incident_post_mortem(incident, alerts=alerts, invocations=invocations)
    if format == "json":
        return {
            "incident_id": str(incident_id),
            "title": incident.title,
            "severity": incident.severity.value,
            "status": incident.status.value,
            "post_mortem_markdown": md_content
        }

    return PlainTextResponse(content=md_content, media_type="text/markdown")
