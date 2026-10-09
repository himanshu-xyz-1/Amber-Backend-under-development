import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.app.core.database import Base


class Runbook(Base):
    """Runbook model representing procedural playbooks for remediation."""
    __tablename__ = "runbooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(255), nullable=True)
    tags = Column(JSON, nullable=True)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Note: pgvector embedding column will be added later when pgvector extension is configured.

    creator = relationship("User", back_populates="created_runbooks")
