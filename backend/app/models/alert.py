import enum
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.app.core.database import Base


class AlertSource(enum.Enum):
    PAGERDUTY = "PAGERDUTY"
    SENTRY = "SENTRY"
    DATADOG = "DATADOG"
    CLOUDWATCH = "CLOUDWATCH"
    PROMETHEUS = "PROMETHEUS"
    GENERIC = "GENERIC"


class Alert(Base):
    """Alert model representing raw and sanitized webhooks from monitoring sources."""
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True, index=True)
    source = Column(SQLEnum(AlertSource), nullable=False, index=True)
    source_alert_id = Column(String(255), nullable=True)
    fingerprint = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    raw_payload = Column(JSON, nullable=False)
    sanitized_payload = Column(JSON, nullable=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    incident = relationship("Incident", back_populates="alerts")
