from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"

class IncidentStatus(str, Enum):
    TRIGGERED = "TRIGGERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    PROPOSED = "PROPOSED"
    EXECUTING = "EXECUTING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"

class IncidentCreate(BaseModel):
    title: str = Field(..., description="Title of the incident")
    description: str | None = Field(None, description="Detailed description of the incident")
    severity: Severity = Field(..., description="Severity level")
    source_service: str | None = Field(None, description="Service where the incident originated")

class IncidentUpdate(BaseModel):
    title: str | None = Field(None, description="Title of the incident")
    severity: Severity | None = Field(None, description="Severity level")
    status: IncidentStatus | None = Field(None, description="Current status of the incident")
    root_cause_summary: str | None = Field(None, description="Summary of the root cause")
    remediation_plan: dict[str, Any] | None = Field(None, description="Proposed remediation steps")

class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    title: str
    description: str | None = None
    severity: Severity
    status: IncidentStatus
    source_service: str | None = None
    root_cause_summary: str | None = None
    remediation_plan: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime | None = None
    resolved_at: datetime | None = None

class IncidentListResponse(BaseModel):
    total_count: int = Field(..., description="Total number of incidents")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of incidents per page")
    incidents: list[IncidentResponse] = Field(..., description="List of incidents")

class IncidentTimeline(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    incident_id: UUID
    event_type: str = Field(..., description="Type of the timeline event")
    description: str = Field(..., description="Description of the event")
    timestamp: datetime
    metadata: dict[str, Any] | None = None
