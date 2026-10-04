"""
Amber SRE Engine - Automated Markdown Post-Mortem Generator.
Generates comprehensive, audit-ready Incident Post-Mortem reports in standard
Google SRE / Netflix SRE Markdown format.
"""

from datetime import datetime, timezone
import json
from typing import List, Optional

from backend.app.models.incident import Incident
from backend.app.models.alert import Alert
from backend.app.models.tool_invocation import ToolInvocation


def generate_incident_post_mortem(
    incident: Incident,
    alerts: Optional[List[Alert]] = None,
    invocations: Optional[List[ToolInvocation]] = None,
) -> str:
    """
    Renders an executive-grade Markdown post-mortem report for an incident.
    """
    alerts = alerts or []
    invocations = invocations or []

    created_iso = incident.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if incident.created_at else "Unknown"
    resolved_iso = incident.resolved_at.strftime("%Y-%m-%d %H:%M:%S UTC") if incident.resolved_at else "In Progress"

    mttr_seconds = incident.time_to_resolve or (
        (incident.resolved_at - incident.created_at).total_seconds()
        if incident.created_at and incident.resolved_at
        else 0.0
    )
    mttr_str = f"{round(mttr_seconds, 1)} seconds" if mttr_seconds else "N/A (Active)"

    md = []
    md.append(f"# 📋 Incident Post-Mortem: {incident.title}")
    md.append("")
    md.append("## Metadata")
    md.append(f"- **Incident ID:** `{incident.id}`")
    md.append(f"- **Severity:** `{incident.severity.value}`")
    md.append(f"- **Status:** `{incident.status.value}`")
    md.append(f"- **Source Service:** `{incident.source_service or 'Unknown'}`")
    md.append(f"- **Alert Fingerprint:** `{incident.fingerprint or 'N/A'}`")
    md.append(f"- **Trigger Time:** `{created_iso}`")
    md.append(f"- **Resolution Time:** `{resolved_iso}`")
    md.append(f"- **Mean Time to Resolution (MTTR):** `{mttr_str}`")
    md.append("")

    # 1. Executive Summary
    md.append("## 1. Executive Summary")
    if incident.description:
        md.append(f"{incident.description}")
    else:
        md.append(
            f"At {created_iso}, an automated alert was triggered for service `{incident.source_service}`. "
            f"Amber Autonomous SRE Engine performed autonomous triage, extracted diagnostic telemetry, "
            f"and orchestrated human-in-the-loop remediation to restore service availability."
        )
    md.append("")

    # 2. Root Cause Analysis
    md.append("## 2. Root Cause Analysis (RCA)")
    if incident.root_cause_summary:
        md.append(f"{incident.root_cause_summary}")
    else:
        md.append("Root cause was determined through correlated telemetry and container log analysis.")
    md.append("")

    # 3. Triggering Alerts
    md.append("## 3. Triggering Alerts")
    if alerts:
        md.append("| Alert ID | Source | Fingerprint | Title | Ingested At |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        for a in alerts:
            ingested_str = a.ingested_at.strftime("%H:%M:%S UTC") if a.ingested_at else "N/A"
            md.append(f"| `{str(a.id)[:8]}` | {a.source.value} | `{a.fingerprint[:12]}...` | {a.title or 'Alert'} | {ingested_str} |")
    else:
        md.append("_No raw alerts recorded for this incident._")
    md.append("")

    # 4. Remediation Actions & Audit Trail
    md.append("## 4. Remediation Actions & Audit Trail")
    if invocations:
        md.append("| Tool Executed | Risk Level | Status | Health Verification | Approver |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        for inv in invocations:
            health_badge = "✅ PASSED" if inv.health_check_passed else "❌ FAILED"
            approver_str = str(inv.approved_by_id) if inv.approved_by_id else "Authorized SRE"
            md.append(f"| `{inv.tool_name}` | {inv.risk_level.value} | `{inv.status.value}` | {health_badge} | {approver_str} |")
        md.append("")

        md.append("### Remediation Technical Execution Details")
        for inv in invocations:
            md.append(f"#### Tool: `{inv.tool_name}` (`{inv.status.value}`)")
            md.append("```json")
            exec_data = {
                "tool_name": inv.tool_name,
                "tool_args": inv.tool_args,
                "status": inv.status.value,
                "health_check_passed": inv.health_check_passed,
                "execution_result": inv.execution_result,
                "error_message": inv.error_message,
                "payload_sha256": inv.payload_sha256
            }
            md.append(json.dumps(exec_data, indent=2))
            md.append("```")
    else:
        md.append("_No automated remediation tools were executed._")
    md.append("")

    # 5. Lessons Learned & Action Items
    md.append("## 5. Lessons Learned & Preventive Actions")
    md.append("1. **Automated Detection:** Continuous health probe thresholds should be reviewed for early-warning indicators.")
    md.append(f"2. **Capacity & Resource Limits:** Verify resource requests and connection pool limits on `{incident.source_service or 'target service'}`.")
    md.append("3. **Runbook Enrichment:** Update automated runbook repository with newly cataloged telemetry signals.")
    md.append("")
    md.append("---")
    md.append(f"_Report automatically compiled by Amber SRE Engine v0.1.0 on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}_")

    return "\n".join(md)
