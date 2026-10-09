import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.app.core.database import Base


class RiskLevel(enum.Enum):
    LOW = "LOW"
    HIGH = "HIGH"


class InvocationStatus(enum.Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ROLLED_BACK = "ROLLED_BACK"


class ToolInvocation(Base):
    """ToolInvocation model representing actions executed by the agent."""
    __tablename__ = "tool_invocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False, index=True)
    tool_name = Column(String(255), nullable=False)
    tool_args = Column(JSON, nullable=False)
    risk_level = Column(SQLEnum(RiskLevel), nullable=False, index=True)
    reversible = Column(Boolean, default=False)
    status = Column(SQLEnum(InvocationStatus), nullable=False, default=InvocationStatus.PENDING_APPROVAL, index=True)
    payload_sha256 = Column(String(64), nullable=True)
    execution_result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    health_check_passed = Column(Boolean, nullable=True)
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approval_expires_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="tool_invocations")
    approver = relationship("User", back_populates="tool_invocations")
