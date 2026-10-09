import enum
import uuid

from sqlalchemy import Column, DateTime, Float, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.app.core.database import Base


class IncidentSeverity(enum.Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class IncidentStatus(enum.Enum):
    TRIGGERED = "TRIGGERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    PROPOSED = "PROPOSED"
    EXECUTING = "EXECUTING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class Incident(Base):
    """Incident model representing an alert or collection of alerts."""
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(SQLEnum(IncidentSeverity), nullable=False, index=True)
    status = Column(SQLEnum(IncidentStatus), nullable=False, default=IncidentStatus.TRIGGERED, index=True)
    fingerprint = Column(String(255), index=True)
    source_service = Column(String(255), nullable=True)
    root_cause_summary = Column(Text, nullable=True)
    remediation_plan = Column(JSON, nullable=True)
    graph_state = Column(JSON, nullable=True)
    current_agent_node = Column(String(100), nullable=True)
    time_to_detect = Column(Float, nullable=True)
    time_to_resolve = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    alerts = relationship("Alert", back_populates="incident")
    tool_invocations = relationship("ToolInvocation", back_populates="incident")
