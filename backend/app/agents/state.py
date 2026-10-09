from typing import TypedDict


class AmberGraphState(TypedDict, total=False):
    # Input
    incident_id: str
    alert_payload: dict
    alert_source: str
    
    # Triage Output
    severity: str  # P0, P1, P2, P3, P4
    triage_reasoning: str
    affected_service: str
    
    # RAG Output
    matched_runbooks: list[dict]  # [{title, content_snippet, confidence}]
    runbook_instructions: str
    
    # Investigation Output
    diagnostic_results: list[dict]  # [{tool_name, result, timestamp}]
    root_cause_summary: str
    
    # Remediation Proposal
    proposed_tools: list[dict]  # [{tool_name, args, risk_level, reversible}]
    remediation_plan: str
    
    # Guardrail & Approval
    requires_approval: bool
    approval_status: str  # pending, approved, rejected, expired
    payload_sha256: str
    
    # Execution & Verification
    execution_results: list[dict]
    health_check_passed: bool
    
    # Control Flow
    current_node: str
    error_message: str
    should_escalate: bool
    iteration_count: int
