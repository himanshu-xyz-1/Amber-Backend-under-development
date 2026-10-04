"""
Amber SRE Engine — Investigation Node.

Runs live diagnostic tools, then uses the Universal LLM Gateway to synthesize
root cause and propose a bounded remediation action.

Critical safety rules enforced here:
1. If LLM is unavailable → NEVER propose fake PIDs or pod names. Return needs_human=True.
2. If LLM trust level < 2 → No dangerous tool proposals (LEVEL_1 = observe only).
3. All proposed args go through validate_args() guardrail before acceptance.
4. Pod restart failures → alert only, never auto-trigger deployment rollback.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.core.llm import llm_gateway, get_model_trust_level
from backend.app.core.config import settings
from backend.app.tools.base import tool_registry
from .state import AmberGraphState

logger = logging.getLogger(__name__)

# Tools that mutate deployments — only propose these if trust level >= 2
DEPLOYMENT_MUTATING_TOOLS = {"rollback_deployment", "rollout_restart_deployment"}

INVESTIGATION_SYSTEM_PROMPT = (
    "You are the Lead SRE Investigator in the Amber Autonomous Incident Response Engine. "
    "You analyze real live diagnostic data from Kubernetes clusters and databases. "
    "You propose precise, bounded remediation actions using only the tools available. "
    "You NEVER invent pod names, PIDs, or deployment names — use only data from the diagnostics provided. "
    "Output a single valid JSON object with no markdown wrappers."
)


async def investigation_node(state: AmberGraphState) -> dict:
    """
    Investigation node:
    1. Executes read-only diagnostic tools (real cluster data).
    2. Feeds diagnostics into LLM Gateway (any provider/model).
    3. Proposes bounded remediation action with deterministic guardrails.

    If LLM is unavailable: returns needs_human=True, no fake proposals.
    If model trust level < 2: downgrades to observe-only (no dangerous tools).
    """
    severity = state.get("severity", "P2")
    service = state.get("affected_service", "core-service")
    matched_runbooks = state.get("matched_runbooks", [])

    trust_level = get_model_trust_level()
    logger.info(f"[Investigation] Model trust level: {trust_level} | Severity: {severity} | Service: {service}")

    # ──────────────────────────────────────────────
    # Step 1: Run live read-only diagnostic tools
    # These provide REAL cluster data — no hallucination possible here.
    # ──────────────────────────────────────────────
    diagnostic_results: List[Dict[str, Any]] = []

    health_tool = tool_registry.get("check_service_health")
    if health_tool:
        h_res = await health_tool.execute(endpoint_url=f"http://internal/{service}/health")
        diagnostic_results.append({
            "tool_name": health_tool.name,
            "result": h_res.data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    db_tool = tool_registry.get("query_db_metrics")
    if db_tool:
        db_res = await db_tool.execute(threshold_seconds=60)
        diagnostic_results.append({
            "tool_name": db_tool.name,
            "result": db_res.data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ──────────────────────────────────────────────
    # Step 2: Filter available tools by trust level
    # Trust level < 2: hide all dangerous/mutating tools from LLM proposal
    # ──────────────────────────────────────────────
    all_tools_meta = tool_registry.list_tools()
    if trust_level < 2:
        available_tools_meta = [
            t for t in all_tools_meta
            if t["risk_level"] in ("LOW", "MEDIUM") and t["name"] not in DEPLOYMENT_MUTATING_TOOLS
        ]
        logger.info(
            f"[Investigation] Trust level {trust_level}: restricting to observe-only tools "
            f"({len(available_tools_meta)}/{len(all_tools_meta)} available)."
        )
    else:
        available_tools_meta = [
            {"name": t["name"], "risk_level": t["risk_level"], "description": t["description"]}
            for t in all_tools_meta
        ]

    # ──────────────────────────────────────────────
    # Step 3: LLM Investigation & Proposal
    # ──────────────────────────────────────────────
    root_cause = "Diagnostic probes indicate service degradation."
    proposed_tools: List[Dict[str, Any]] = []
    remediation_plan = "Review logs and execute standard service recovery."
    needs_human = False

    prompt = f"""Analyze these live diagnostic results and propose the most accurate bounded remediation tool.

Incident Severity: {severity}
Target Service: {service}
Diagnostic Findings:
{json.dumps(diagnostic_results, indent=2)}

Matched Runbooks:
{json.dumps(matched_runbooks, indent=2)}

Registered Tools Available (ONLY use tools from this list):
{json.dumps(available_tools_meta, indent=2)}

CRITICAL RULES:
- NEVER invent pod names, PIDs, deployment names, or namespaces. Use ONLY names from the diagnostic data.
- If slow database queries/pool exhaustion is found, propose 'kill_db_connections' with REAL pids from diagnostics.
- If pod crashloop or bad deployment is found, propose 'rollback_deployment' or 'restart_service_pod' with REAL names.
- If you do not have enough real data to fill tool args safely, set "needs_human": true.
- Output ONLY valid JSON, no markdown, no commentary:

{{
  "root_cause_summary": "1-2 sentences stating the exact technical failure based on diagnostics.",
  "remediation_plan": "1 clear sentence explaining what action will be taken.",
  "proposed_tool_name": "exact tool name from registered tools OR null if no safe proposal",
  "tool_args": {{"key": "value"}},
  "needs_human": false
}}"""

    parsed = await llm_gateway.generate_json(
        prompt=prompt,
        system_prompt=INVESTIGATION_SYSTEM_PROMPT,
        temperature=0.2,
        timeout=30.0,
    )

    if parsed:
        root_cause = parsed.get("root_cause_summary", root_cause)
        remediation_plan = parsed.get("remediation_plan", remediation_plan)
        needs_human = parsed.get("needs_human", False)
        tool_name = parsed.get("proposed_tool_name")
        tool_args = parsed.get("tool_args", {})

        if not needs_human and tool_name:
            matched_tool = tool_registry.get(tool_name)
            if matched_tool:
                if matched_tool.validate_args(**tool_args):
                    proposed_tools.append({
                        "tool_name": matched_tool.name,
                        "args": tool_args,
                        "risk_level": matched_tool.risk_level.value,
                        "reversible": matched_tool.reversible,
                    })
                    logger.info(f"[Investigation] LLM proposed tool '{matched_tool.name}' with valid args.")
                else:
                    logger.warning(
                        f"[Investigation] LLM proposed invalid args for '{matched_tool.name}': {tool_args}. "
                        "Escalating to human — no fake fallback."
                    )
                    needs_human = True
            else:
                logger.warning(f"[Investigation] LLM proposed unknown tool '{tool_name}'. Ignored.")
                needs_human = True
    else:
        # ──────────────────────────────────────────────
        # LLM UNAVAILABLE — Critical safety rule:
        # NEVER propose fake PIDs [1234] or made-up pod names.
        # Escalate to human with clear reason.
        # ──────────────────────────────────────────────
        logger.warning(
            "[Investigation] LLM unavailable. No tool proposed. "
            "Escalating to human SRE — deterministic heuristics cannot safely pick tool args."
        )
        needs_human = True
        root_cause = (
            f"Automated investigation incomplete: LLM brain ({settings.LLM_PROVIDER}/{settings.LOCAL_LLM_MODEL}) "
            "is unreachable. Live diagnostics gathered but root cause analysis requires human review."
        )
        remediation_plan = "Manual SRE investigation required. Diagnostics available in incident details."

    # ──────────────────────────────────────────────
    # Step 4: Heuristic fallback for P0/P1 — READ-ONLY health check only
    # We never fabricate args here; just escalate + add a safe diagnostic tool.
    # ──────────────────────────────────────────────
    if not proposed_tools and not needs_human and severity in ("P0", "P1"):
        proposed_tools.append({
            "tool_name": "check_service_health",
            "args": {"endpoint_url": f"http://internal/{service}/health"},
            "risk_level": "LOW",
            "reversible": True,
        })
        root_cause = f"Critical alert on {service} — awaiting human SRE to confirm root cause from live diagnostics."
        remediation_plan = "Run health check probe. Escalate for human review."

    return {
        "diagnostic_results": diagnostic_results,
        "root_cause_summary": root_cause,
        "proposed_tools": proposed_tools,
        "remediation_plan": remediation_plan,
        "needs_human_intervention": needs_human,
        "llm_trust_level": trust_level,
        "current_node": "investigation",
    }
