"""
LangGraph workflow builder for Phase 1.

Minimal graph topology:
  START ──► entry_node ──► legacy_agent_node ──► END

This graph acts as a clean orchestration boundary around the existing
`EngineeringAgent.create_plan` lifecycle without duplicating domain logic.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, START, END

from backend.agent.graph.state import AgentGraphState, sync_graph_state_to_run
from backend.agent.engineering_agent import EngineeringAgent, EngineeringAgentError
from backend.database import SessionLocal
from backend.models.implementation import AgentState

logger = logging.getLogger(__name__)


def build_agent_graph(agent_service: Optional[EngineeringAgent] = None):
    """
    Compiles and returns the Phase 1 LangGraph workflow.
    """
    service = agent_service or EngineeringAgent()
    workflow = StateGraph(AgentGraphState)

    def entry_node(state: AgentGraphState) -> Dict[str, Any]:
        """
        Validates state prerequisites and logs entry telemetry.
        """
        run_id = state.get("run_id")
        history = list(state.get("node_history") or [])
        history.append("entry_node")

        if not run_id:
            logger.error("LangGraph entry_node received state without run_id")
            return {
                "error_message": "Missing run_id in graph state",
                "node_history": history,
            }

        logger.info(f"LangGraph entry_node initialized for run '{run_id}'")
        return {
            "node_history": history,
        }

    def legacy_agent_node(state: AgentGraphState) -> Dict[str, Any]:
        """
        Executes the existing EngineeringAgent planning lifecycle within a DB session.
        Handles errors observably without fallback masking.
        """
        run_id = state.get("run_id")
        history = list(state.get("node_history") or [])
        history.append("legacy_agent_node")

        if not run_id:
            return {
                "error_message": "Invalid run_id in legacy_agent_node",
                "node_history": history,
            }

        if state.get("is_cancelled"):
            logger.info(f"Skipping legacy_agent_node for cancelled run '{run_id}'")
            return {
                "node_history": history,
            }

        with SessionLocal() as db:
            try:
                logger.info(f"LangGraph legacy_agent_node executing create_plan for run '{run_id}'")
                plan = service.create_plan(db=db, run_id=run_id)
                run = service.get_run(db, run_id)

                current_state_val = (
                    run.current_state.value
                    if isinstance(run.current_state, AgentState)
                    else str(run.current_state)
                )

                return {
                    "current_state": current_state_val,
                    "status": run.status.value if hasattr(run.status, "value") else str(run.status),
                    "node_history": history,
                }
            except Exception as err:
                logger.error(f"LangGraph legacy_agent_node execution error on run '{run_id}': {err}", exc_info=True)
                error_msg = str(err)
                try:
                    # Transition to FAILED state observably in database
                    run = service.get_run(db, run_id)
                    if not service.state_machine.is_terminal(run.current_state):
                        service.transition_state(
                            db,
                            run_id=run_id,
                            to_state=AgentState.FAILED,
                            reason=f"Graph node error: {error_msg}",
                        )
                except Exception as transition_err:
                    logger.warning(f"Could not transition run '{run_id}' to FAILED: {transition_err}")

                return {
                    "error_message": error_msg,
                    "current_state": AgentState.FAILED.value,
                    "node_history": history,
                }

    # Add nodes and edges
    workflow.add_node("entry_node", entry_node)
    workflow.add_node("legacy_agent_node", legacy_agent_node)

    workflow.add_edge(START, "entry_node")
    workflow.add_edge("entry_node", "legacy_agent_node")
    workflow.add_edge("legacy_agent_node", END)

    return workflow.compile()
