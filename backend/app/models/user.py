import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.app.core.database import Base


class UserRole(enum.Enum):
    SRE = "SRE"
    LEAD = "LEAD"
    DEVELOPER = "DEVELOPER"
    ADMIN = "ADMIN"


class User(Base):
    """
    SRE & Machine Service Identity model.
    Binds on-call SREs to their verified Slack, and Telegram notification handles
    with scoped API keys for programmatic automation.
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.SRE)
    api_key_hash = Column(String(255), nullable=True)
    slack_user_id = Column(String(100), nullable=True)
    telegram_handle = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    tool_invocations = relationship("ToolInvocation", back_populates="approver")
    created_runbooks = relationship("Runbook", back_populates="creator")
