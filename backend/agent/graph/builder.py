"""
LangGraph workflow builder with Intent Routing (Phase 2).

Graph topology:
  START ──► entry_node ──► intent_router_node ──► [conditional edge]
                                │
                 ┌──────────────┼──────────────┬──────────────┐
                 ▼              ▼              ▼              ▼
            chat_terminal explore_terminal explain_terminal clarify_terminal
                 │              │              │              │
                 └──────────────┼──────────────┴──────────────┘
                                ▼
                               END
                                ▲
                 ┌──────────────┴──────────────┐
                 │ (Plan / Implement bridge)   │
                 ▼                             ▼
             PLAN branch                 IMPLEMENT branch
                 │                             │
                 └──────────────┬──────────────┘
                                ▼
                        legacy_agent_node
                                │
                                ▼
                               END
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, START, END

from backend.agent.graph.state import AgentGraphState, sync_graph_state_to_run
from backend.agent.intent import Intent, IntentRouter
from backend.agent.engineering_agent import EngineeringAgent, EngineeringAgentError
from backend.database import SessionLocal
from backend.models.implementation import AgentState, AgentEventType

logger = logging.getLogger(__name__)


def build_agent_graph(
    agent_service: Optional[EngineeringAgent] = None,
    intent_router: Optional[IntentRouter] = None,
):
    """
    Compiles and returns the Phase 2 LangGraph workflow with intent classification.
    """
    service = agent_service or EngineeringAgent()
    router = intent_router or IntentRouter()
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

    def intent_router_node(state: AgentGraphState) -> Dict[str, Any]:
        """
        Classifies user requirement using two-stage IntentRouter.
        """
        run_id = state.get("run_id")
        user_req = state.get("user_requirement", "")
        history = list(state.get("node_history") or [])
        history.append("intent_router_node")

        # Invariant: If intent is already pre-set or run cancelled, pass through
        if state.get("is_cancelled"):
            return {
                "node_history": history,
            }

        result = router.classify(user_req)
        logger.info(
            f"LangGraph intent_router_node classified run '{run_id}' as '{result.intent.value}' "
            f"(confidence={result.confidence:.2f}, method='{result.classification_method}')"
        )

        # Sync intent to database record and emit live event
        with SessionLocal() as db:
            try:
                sync_graph_state_to_run(
                    db,
                    run_id=run_id,
                    state={
                        "intent": result.intent.value,
                        "intent_confidence": result.confidence,
                        "intent_reason": result.reason,
                        "classification_method": result.classification_method,
                    },
                )
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.INTENT_CLASSIFIED,
                        message=f"Intent: {result.intent.value.upper()} ({result.confidence:.0%}) - {result.reason}",
                        payload={
                            "intent": result.intent.value,
                            "confidence": result.confidence,
                            "reason": result.reason,
                            "method": result.classification_method,
                        },
                    )
            except Exception as err:
                logger.warning(f"Could not sync intent to database for run '{run_id}': {err}")

        return {
            "intent": result.intent.value,
            "intent_confidence": result.confidence,
            "intent_reason": result.reason,
            "classification_method": result.classification_method,
            "node_history": history,
        }

    def chat_terminal(state: AgentGraphState) -> Dict[str, Any]:
        """
        Terminal handler for non-mutating CHAT requests.
        Never invokes planning or creates worktrees.
        """
        run_id = state.get("run_id")
        history = list(state.get("node_history") or [])
        history.append("chat_terminal")

        msg = "Hello! I am your Repository Intelligence Assistant. You can ask me to explore files, explain architectures, or plan code implementations."
        logger.info(f"LangGraph chat_terminal completed for run '{run_id}'")

        with SessionLocal() as db:
            try:
                run = service.get_run(db, run_id)
                sync_graph_state_to_run(db, run_id=run_id, state={"metadata": {"response": msg}})
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.AGENT_MESSAGE,
                        message=msg,
                        payload={"response": msg, "intent": "chat"},
                    )
                if not service.state_machine.is_terminal(run.current_state):
                    service.transition_state(
                        db,
                        run_id=run_id,
                        to_state=AgentState.COMPLETED,
                        reason="Chat terminal response completed",
                    )
            except Exception as err:
                logger.warning(f"Error updating run state in chat_terminal: {err}")

        return {
            "current_state": AgentState.COMPLETED.value,
            "status": "COMPLETED",
            "metadata": {"response": msg},
            "node_history": history,
        }

    def explore_terminal(state: AgentGraphState) -> Dict[str, Any]:
        """
        Terminal handler for non-mutating EXPLORE requests.
        """
        run_id = state.get("run_id")
        history = list(state.get("node_history") or [])
        history.append("explore_terminal")

        msg = f"Exploration query recognized for: '{state.get('user_requirement', '')}'. The repository knowledge graph and symbol lookup are being cataloged."
        logger.info(f"LangGraph explore_terminal completed for run '{run_id}'")

        with SessionLocal() as db:
            try:
                run = service.get_run(db, run_id)
                sync_graph_state_to_run(db, run_id=run_id, state={"metadata": {"response": msg}})
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.AGENT_MESSAGE,
                        message=msg,
                        payload={"response": msg, "intent": "explore"},
                    )
                if not service.state_machine.is_terminal(run.current_state):
                    service.transition_state(
                        db,
                        run_id=run_id,
                        to_state=AgentState.COMPLETED,
                        reason="Exploration request processed",
                    )
            except Exception as err:
                logger.warning(f"Error updating run state in explore_terminal: {err}")

        return {
            "current_state": AgentState.COMPLETED.value,
            "status": "COMPLETED",
            "metadata": {"response": msg},
            "node_history": history,
        }

    def explain_terminal(state: AgentGraphState) -> Dict[str, Any]:
        """
        Terminal handler for non-mutating EXPLAIN requests.
        """
        run_id = state.get("run_id")
        history = list(state.get("node_history") or [])
        history.append("explain_terminal")

        msg = f"Explanation query recognized for: '{state.get('user_requirement', '')}'. The codebase architecture models and call graphs are available for inspection."
        logger.info(f"LangGraph explain_terminal completed for run '{run_id}'")

        with SessionLocal() as db:
            try:
                run = service.get_run(db, run_id)
                sync_graph_state_to_run(db, run_id=run_id, state={"metadata": {"response": msg}})
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.AGENT_MESSAGE,
                        message=msg,
                        payload={"response": msg, "intent": "explain"},
                    )
                if not service.state_machine.is_terminal(run.current_state):
                    service.transition_state(
                        db,
                        run_id=run_id,
                        to_state=AgentState.COMPLETED,
                        reason="Explanation request processed",
                    )
            except Exception as err:
                logger.warning(f"Error updating run state in explain_terminal: {err}")

        return {
            "current_state": AgentState.COMPLETED.value,
            "status": "COMPLETED",
            "metadata": {"response": msg},
            "node_history": history,
        }

    def clarify_terminal(state: AgentGraphState) -> Dict[str, Any]:
        """
        Terminal handler for ambiguous/underspecified CLARIFY requests.
        """
        run_id = state.get("run_id")
        history = list(state.get("node_history") or [])
        history.append("clarify_terminal")

        msg = (
            f"Your request '{state.get('user_requirement', '')}' is ambiguous or underspecified. "
            "Please specify which files, functions, or features you want to modify or inspect."
        )
        logger.info(f"LangGraph clarify_terminal completed for run '{run_id}'")

        with SessionLocal() as db:
            try:
                run = service.get_run(db, run_id)
                sync_graph_state_to_run(db, run_id=run_id, state={"metadata": {"response": msg}})
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.AGENT_MESSAGE,
                        message=msg,
                        payload={"response": msg, "intent": "clarify"},
                    )
                if not service.state_machine.is_terminal(run.current_state):
                    service.transition_state(
                        db,
                        run_id=run_id,
                        to_state=AgentState.COMPLETED,
                        reason="Clarification prompt delivered",
                    )
            except Exception as err:
                logger.warning(f"Error updating run state in clarify_terminal: {err}")

        return {
            "current_state": AgentState.COMPLETED.value,
            "status": "COMPLETED",
            "metadata": {"response": msg},
            "node_history": history,
        }

    def legacy_agent_node(state: AgentGraphState) -> Dict[str, Any]:
        """
        Executes the existing EngineeringAgent planning lifecycle within a DB session
        for PLAN and IMPLEMENT requests.
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

    # Add all nodes
    workflow.add_node("entry_node", entry_node)
    workflow.add_node("intent_router_node", intent_router_node)
    workflow.add_node("chat_terminal", chat_terminal)
    workflow.add_node("explore_terminal", explore_terminal)
    workflow.add_node("explain_terminal", explain_terminal)
    workflow.add_node("clarify_terminal", clarify_terminal)
    workflow.add_node("legacy_agent_node", legacy_agent_node)

    # Base transition to intent router
    workflow.add_edge(START, "entry_node")
    workflow.add_edge("entry_node", "intent_router_node")

    # Conditional routing based on classified intent
    def route_by_intent(state: AgentGraphState) -> str:
        intent = state.get("intent", Intent.CLARIFY.value)
        if intent == Intent.CHAT.value:
            return "chat_terminal"
        elif intent == Intent.EXPLORE.value:
            return "explore_terminal"
        elif intent == Intent.EXPLAIN.value:
            return "explain_terminal"
        elif intent == Intent.CLARIFY.value:
            return "clarify_terminal"
        elif intent in (Intent.PLAN.value, Intent.IMPLEMENT.value):
            return "legacy_agent_node"
        return "clarify_terminal"

    workflow.add_conditional_edges(
        "intent_router_node",
        route_by_intent,
        {
            "chat_terminal": "chat_terminal",
            "explore_terminal": "explore_terminal",
            "explain_terminal": "explain_terminal",
            "clarify_terminal": "clarify_terminal",
            "legacy_agent_node": "legacy_agent_node",
        },
    )

    # Terminal transitions to END
    workflow.add_edge("chat_terminal", END)
    workflow.add_edge("explore_terminal", END)
    workflow.add_edge("explain_terminal", END)
    workflow.add_edge("clarify_terminal", END)
    workflow.add_edge("legacy_agent_node", END)

    return workflow.compile()
