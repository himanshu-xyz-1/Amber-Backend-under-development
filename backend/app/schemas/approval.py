from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    LOW = "LOW"
    HIGH = "HIGH"

class ApprovalStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ROLLED_BACK = "ROLLED_BACK"

class ApprovalRequest(BaseModel):
    tool_invocation_id: UUID = Field(..., description="ID of the tool invocation needing approval")
    action: str = Field(..., pattern="^(approve|reject)$", description="Action to take: approve or reject")
    payload_sha256: str | None = Field(None, description="SHA-256 payload hash verification")
    approved_by_id: UUID | None = Field(None, description="UUID of the approving user")

class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tool_name: str
    tool_args: dict[str, Any]
    risk_level: RiskLevel
    status: ApprovalStatus
    payload_sha256: str | None = None
    approval_expires_at: datetime | None = None
    execution_result: dict[str, Any] | None = None
    error_message: str | None = None
    health_check_passed: bool | None = None
    created_at: datetime
    approved_at: datetime | None = None
    executed_at: datetime | None = None

class RunbookMatch(BaseModel):
    title: str
    confidence_score: float
    matched_section: str

class MutationDiff(BaseModel):
    before_state: str
    proposed_command: str
    expected_after_state: str

class DeepProofBlock(BaseModel):
    live_evidence: list[str] = Field(..., description="List of evidence strings from diagnostic output")
    runbook_match: RunbookMatch = Field(..., description="Information about runbook match")
    mutation_diff: MutationDiff = Field(..., description="State changes expected")

class SlackApprovalCard(BaseModel):
    incident_id: UUID
    severity: str
    title: str
    root_cause: str
    proposed_action: str
    tool_name: str
    tool_args: dict[str, Any]
    payload_sha256: str
    ttl_minutes: int
    deep_proof: DeepProofBlock
