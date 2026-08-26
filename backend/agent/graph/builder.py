"""
LangGraph workflow builder with Intent Routing (Phase 2).

Pure intent routing topology:
  START ──► entry_node ──► intent_router_node ──► [conditional edge]
                                │
   ┌──────────────┬─────────────┼─────────────┬──────────────┬──────────────┐
   ▼              ▼             ▼             ▼              ▼              ▼
chat_terminal explore_terminal explain_term  plan_terminal implement_term clarify_terminal
   │              │             │             │              │              │
   └──────────────┴─────────────┼─────────────┴──────────────┴──────────────┘
                                ▼
                               END
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, START, END

from backend.agent.graph.state import AgentGraphState, sync_graph_state_to_run
from backend.agent.intent import Intent, IntentRouter
from backend.agent.engineering_agent import EngineeringAgent
from backend.database import SessionLocal
from backend.models.implementation import AgentState, AgentEventType
from backend.config import settings
from backend.agent.safety import ApprovalActionType, RiskLevel
from backend.agent.modes import execute_chat, execute_explore, execute_explain, execute_plan, execute_implement

logger = logging.getLogger(__name__)


def build_agent_graph(
    agent_service: Optional[EngineeringAgent] = None,
    intent_router: Optional[IntentRouter] = None,
):
    """
    Compiles and returns the clean Phase 2 LangGraph workflow with intent classification.
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

        if state.get("is_cancelled"):
            return {
                "node_history": history,
            }

        result = router.classify(user_req)
        logger.info(
            f"LangGraph intent_router_node classified run '{run_id}' as '{result.intent.value}' "
            f"(confidence={result.confidence:.2f}, method='{result.classification_method}')"
        )

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
        run_id = state.get("run_id")
        user_req = state.get("user_requirement", "")
        history = list(state.get("node_history") or [])
        history.append("chat_terminal")

        result = execute_chat(user_requirement=user_req)
        msg = result.get("response", "Chat processed.")
        logger.info(f"LangGraph chat_terminal completed for run '{run_id}' using model '{result.get('model')}'")

        with SessionLocal() as db:
            try:
                run = service.get_run(db, run_id)
                sync_graph_state_to_run(db, run_id=run_id, state={"metadata": {"response": msg, "model": result.get("model")}})
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.AGENT_MESSAGE,
                        message=msg,
                        payload={"response": msg, "intent": "chat", "model": result.get("model")},
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
            "metadata": {"response": msg, "model": result.get("model")},
            "node_history": history,
        }

    def explore_terminal(state: AgentGraphState) -> Dict[str, Any]:
        run_id = state.get("run_id")
        user_req = state.get("user_requirement", "")
        repo_id = state.get("repository_id", "")
        history = list(state.get("node_history") or [])
        history.append("explore_terminal")

        with SessionLocal() as db:
            result = execute_explore(user_requirement=user_req, repository_id=repo_id, db=db)
            msg = result.get("response", "Exploration processed.")
            logger.info(f"LangGraph explore_terminal completed for run '{run_id}' using model '{result.get('model')}'")

            try:
                run = service.get_run(db, run_id)
                sync_graph_state_to_run(db, run_id=run_id, state={"metadata": {"response": msg, "model": result.get("model"), "entities": result.get("entities", [])}})
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.AGENT_MESSAGE,
                        message=msg,
                        payload={"response": msg, "intent": "explore", "model": result.get("model"), "entities": result.get("entities", [])},
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
            "metadata": {"response": msg, "model": result.get("model"), "entities": result.get("entities", [])},
            "node_history": history,
        }

    def explain_terminal(state: AgentGraphState) -> Dict[str, Any]:
        run_id = state.get("run_id")
        user_req = state.get("user_requirement", "")
        repo_id = state.get("repository_id", "")
        history = list(state.get("node_history") or [])
        history.append("explain_terminal")

        with SessionLocal() as db:
            result = execute_explain(user_requirement=user_req, repository_id=repo_id, db=db)
            msg = result.get("response", "Explanation processed.")
            logger.info(f"LangGraph explain_terminal completed for run '{run_id}' using model '{result.get('model')}'")

            try:
                run = service.get_run(db, run_id)
                sync_graph_state_to_run(db, run_id=run_id, state={"metadata": {"response": msg, "model": result.get("model"), "evidence": result.get("evidence", [])}})
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.AGENT_MESSAGE,
                        message=msg,
                        payload={"response": msg, "intent": "explain", "model": result.get("model"), "evidence": result.get("evidence", [])},
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
            "metadata": {"response": msg, "model": result.get("model"), "evidence": result.get("evidence", [])},
            "node_history": history,
        }

    def plan_terminal(state: AgentGraphState) -> Dict[str, Any]:
        run_id = state.get("run_id")
        user_req = state.get("user_requirement", "")
        repo_id = state.get("repository_id", "")
        history = list(state.get("node_history") or [])
        history.append("plan_terminal")

        with SessionLocal() as db:
            result = execute_plan(
                user_requirement=user_req,
                repository_id=repo_id,
                agent_run_id=run_id,
                db=db,
            )
            msg = result.get("response", "Planning processed.")
            plan_data = result.get("plan")
            logger.info(f"LangGraph plan_terminal completed for run '{run_id}' using model '{result.get('model')}'")

            try:
                run = service.get_run(db, run_id)
                meta_update = {
                    "response": msg,
                    "model": result.get("model"),
                    "plan": plan_data,
                    "evidence": result.get("evidence", []),
                    "unknowns": result.get("unknowns", []),
                    "risks": result.get("risks", []),
                }
                sync_graph_state_to_run(db, run_id=run_id, state={"metadata": meta_update})
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.PLANNING_COMPLETED,
                        message=f"Repository-aware implementation plan synthesized for '{user_req}'.",
                        payload={"task_count": len(plan_data.get("tasks", [])) if plan_data else 0, "is_valid": result.get("is_valid", False)},
                    )
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.AGENT_MESSAGE,
                        message=msg,
                        payload={"response": msg, "intent": "plan", "model": result.get("model"), "plan": plan_data},
                    )
                if not service.state_machine.is_terminal(run.current_state):
                    service.transition_state(
                        db,
                        run_id=run_id,
                        to_state=AgentState.COMPLETED,
                        reason="Repository-aware plan synthesis completed",
                    )
            except Exception as err:
                logger.warning(f"Error updating run state in plan_terminal: {err}")

        return {
            "current_state": AgentState.COMPLETED.value,
            "status": "COMPLETED",
            "metadata": {
                "response": msg,
                "model": result.get("model"),
                "plan": plan_data,
                "evidence": result.get("evidence", []),
            },
            "node_history": history,
        }

    def implement_terminal(state: AgentGraphState) -> Dict[str, Any]:
        run_id = state.get("run_id")
        user_req = state.get("user_requirement", "")
        repo_id = state.get("repository_id", "")
        history = list(state.get("node_history") or [])
        history.append("implement_terminal")

        with SessionLocal() as db:
            result = execute_implement(
                user_requirement=user_req,
                repository_id=repo_id,
                agent_run_id=run_id,
                db=db,
            )
            msg = result.get("response", "Implementation plan synthesized.")
            plan_data = result.get("plan")
            logger.info(f"LangGraph implement_terminal completed for run '{run_id}' using model '{result.get('model')}'")

            try:
                run = service.get_run(db, run_id)
                meta_update = {
                    "response": msg,
                    "model": result.get("model"),
                    "plan": plan_data,
                    "evidence": result.get("evidence", []),
                    "unknowns": result.get("unknowns", []),
                    "risks": result.get("risks", []),
                }
                sync_graph_state_to_run(db, run_id=run_id, state={"metadata": meta_update})
                if run.current_state in (AgentState.IDLE, AgentState.UNDERSTANDING, AgentState.PLANNING):
                    service.transition_state(
                        db,
                        run_id=run_id,
                        to_state=AgentState.AWAITING_APPROVAL,
                        reason="Implementation plan synthesized; awaiting user approval",
                    )
                if hasattr(service, "approval_controller") and service.approval_controller is not None and plan_data:
                    try:
                        service.approval_controller.request_approval(
                            db,
                            agent_run_id=run.id,
                            action_type=ApprovalActionType.PLAN_APPROVAL,
                            description=f"Approve implementation plan v{plan_data.get('version', 1)} ({plan_data.get('plan_id', 'plan')}) with {len(plan_data.get('tasks', []))} tasks",
                            requested_operation={
                                "plan_id": plan_data.get("plan_id"),
                                "version": plan_data.get("version", 1),
                                "task_count": len(plan_data.get("tasks", [])),
                                "repository_revision": plan_data.get("repository_revision"),
                            },
                            risk_level=RiskLevel.HIGH,
                            run_model=run,
                        )
                    except Exception as err:
                        logger.debug(f"Approval request already registered or error: {err}")
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.PLANNING_COMPLETED,
                        message=f"Implementation plan synthesized for '{user_req}'.",
                        payload={"task_count": len(plan_data.get("tasks", [])) if plan_data else 0, "is_valid": result.get("is_valid", False)},
                    )
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.PLAN_READY_FOR_APPROVAL,
                        message="Plan is ready for human approval.",
                        payload={"plan_id": plan_data.get("plan_id") if plan_data else None},
                    )
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.AGENT_MESSAGE,
                        message=msg,
                        payload={"response": msg, "intent": "implement", "model": result.get("model"), "plan": plan_data},
                    )
            except Exception as err:
                logger.warning(f"Error updating run state in implement_terminal: {err}")

        return {
            "current_state": AgentState.AWAITING_APPROVAL.value,
            "status": "AWAITING_APPROVAL",
            "metadata": {
                "response": msg,
                "model": result.get("model"),
                "plan": plan_data,
                "evidence": result.get("evidence", []),
            },
            "node_history": history,
        }

    def clarify_terminal(state: AgentGraphState) -> Dict[str, Any]:
        run_id = state.get("run_id")
        history = list(state.get("node_history") or [])
        history.append("clarify_terminal")

        msg = (
            f"Your request '{state.get('user_requirement', '')}' is ambiguous or underspecified. "
            "Please specify which files, functions, or features you want to modify or inspect."
        )
        logger.info(f"LangGraph clarify_terminal completed for run '{run_id}' using model '{settings.model_terminal_clarify}'")

        with SessionLocal() as db:
            try:
                run = service.get_run(db, run_id)
                sync_graph_state_to_run(db, run_id=run_id, state={"metadata": {"response": msg, "model": settings.model_terminal_clarify}})
                if hasattr(service, "events") and service.events is not None:
                    service.events.emit_event(
                        db=db,
                        run_id=run_id,
                        event_type=AgentEventType.AGENT_MESSAGE,
                        message=msg,
                        payload={"response": msg, "intent": "clarify", "model": settings.model_terminal_clarify},
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
            "metadata": {"response": msg, "model": settings.model_terminal_clarify},
            "node_history": history,
        }

    # Add all 6 intent terminals
    workflow.add_node("entry_node", entry_node)
    workflow.add_node("intent_router_node", intent_router_node)
    workflow.add_node("chat_terminal", chat_terminal)
    workflow.add_node("explore_terminal", explore_terminal)
    workflow.add_node("explain_terminal", explain_terminal)
    workflow.add_node("plan_terminal", plan_terminal)
    workflow.add_node("implement_terminal", implement_terminal)
    workflow.add_node("clarify_terminal", clarify_terminal)

    # Base transition to intent router
    workflow.add_edge(START, "entry_node")
    workflow.add_edge("entry_node", "intent_router_node")

    # Conditional routing strictly to intent terminals
    def route_by_intent(state: AgentGraphState) -> str:
        intent = state.get("intent", Intent.CLARIFY.value)
        if intent == Intent.CHAT.value:
            return "chat_terminal"
        elif intent == Intent.EXPLORE.value:
            return "explore_terminal"
        elif intent == Intent.EXPLAIN.value:
            return "explain_terminal"
        elif intent == Intent.PLAN.value:
            return "plan_terminal"
        elif intent == Intent.IMPLEMENT.value:
            return "implement_terminal"
        elif intent == Intent.CLARIFY.value:
            return "clarify_terminal"
        return "clarify_terminal"

    workflow.add_conditional_edges(
        "intent_router_node",
        route_by_intent,
        {
            "chat_terminal": "chat_terminal",
            "explore_terminal": "explore_terminal",
            "explain_terminal": "explain_terminal",
            "plan_terminal": "plan_terminal",
            "implement_terminal": "implement_terminal",
            "clarify_terminal": "clarify_terminal",
        },
    )

    # Terminal transitions to END
    workflow.add_edge("chat_terminal", END)
    workflow.add_edge("explore_terminal", END)
    workflow.add_edge("explain_terminal", END)
    workflow.add_edge("plan_terminal", END)
    workflow.add_edge("implement_terminal", END)
    workflow.add_edge("clarify_terminal", END)

    return workflow.compile()
