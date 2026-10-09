from langgraph.graph import END, StateGraph

from .investigation import investigation_node
from .rag import rag_node
from .state import AmberGraphState
from .triage import triage_node


async def guardrail_node(state: AmberGraphState) -> dict:
    """
    Validates proposed actions, blocks HIGH risk without approval.
    """
    proposed_tools = state.get("proposed_tools", [])
    requires_approval = any(tool.get("risk_level") == "HIGH" for tool in proposed_tools)
    
    return {
        "requires_approval": requires_approval,
        "current_node": "guardrail"
    }

def should_execute(state: AmberGraphState) -> str:
    """
    Routing function to determine next step after guardrail.
    """
    if state.get("requires_approval"):
        return "await_approval"
    return "execute"

def build_graph():
    builder = StateGraph(AmberGraphState)
    
    # Add nodes
    builder.add_node("triage", triage_node)
    builder.add_node("rag", rag_node)
    builder.add_node("investigation", investigation_node)
    builder.add_node("guardrail", guardrail_node)
    
    # Define edges
    builder.set_entry_point("triage")
    builder.add_edge("triage", "rag")
    builder.add_edge("rag", "investigation")
    builder.add_edge("investigation", "guardrail")
    
    # Conditional edge from guardrail
    builder.add_conditional_edges(
        "guardrail",
        should_execute,
        {
            "await_approval": END,
            "execute": END
        }
    )
    
    return builder.compile()

# Compile the graph globally
incident_graph = build_graph()

async def run_incident_graph(incident_id: str, alert_payload: dict, source: str) -> AmberGraphState:
    """
    Main entry point for running the incident graph.
    """
    initial_state = {
        "incident_id": incident_id,
        "alert_payload": alert_payload,
        "alert_source": source
    }
    
    result = await incident_graph.ainvoke(initial_state)
    return result
