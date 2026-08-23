"""
AgentGraphState: Lean execution state for the LangGraph workflow boundary.

Authority rule:
- The PostgreSQL `AgentRun` ORM model remains the authoritative persistent source of truth.
- `AgentGraphState` holds the active execution state inside the LangGraph runtime.
- State transitions are strictly validated and recorded via `EngineeringAgent.transition_state`
  (which enforces `AgentStateMachine`), keeping `AgentRun` and graph execution synchronized.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict
from sqlalchemy.orm import Session

from backend.models.implementation import AgentRun, AgentState, AgentRunStatus

logger = logging.getLogger(__name__)


class AgentGraphState(TypedDict, total=False):
    """
    In-flight execution state passed across LangGraph nodes.
    """
    run_id: str
    repository_id: str
    user_requirement: str
    current_state: str
    status: str
    is_cancelled: bool
    error_message: Optional[str]
    intent: Optional[str]
    intent_confidence: Optional[float]
    intent_reason: Optional[str]
    classification_method: Optional[str]
    node_history: List[str]
    metadata: Dict[str, Any]


def agent_run_to_graph_state(run: AgentRun) -> AgentGraphState:
    """
    Constructs an AgentGraphState dictionary from an authoritative AgentRun database entity.
    """
    current_state_val = (
        run.current_state.value
        if isinstance(run.current_state, AgentState)
        else str(run.current_state)
    )
    status_val = (
        run.status.value
        if isinstance(run.status, AgentRunStatus)
        else str(run.status)
    )
    metadata = dict(run.metadata_json or {})
    intent_meta = metadata.get("intent") or {}

    return AgentGraphState(
        run_id=run.id,
        repository_id=run.repository_id or "",
        user_requirement=run.user_requirement or "",
        current_state=current_state_val,
        status=status_val,
        is_cancelled=bool(run.cancellation_reason or current_state_val == AgentState.CANCELLED.value),
        error_message=run.error_message,
        intent=intent_meta.get("intent"),
        intent_confidence=intent_meta.get("confidence"),
        intent_reason=intent_meta.get("reason"),
        classification_method=intent_meta.get("classification_method"),
        node_history=[],
        metadata=metadata,
    )


def sync_graph_state_to_run(
    db: Session,
    run_id: str,
    state: AgentGraphState,
) -> AgentRun:
    """
    Synchronizes updated execution fields from AgentGraphState back to AgentRun.
    """
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        raise ValueError(f"AgentRun '{run_id}' not found for synchronization")

    if state.get("error_message") is not None:
        run.error_message = state["error_message"]

    existing_meta = dict(run.metadata_json or {})
    if state.get("metadata") is not None:
        existing_meta.update(state["metadata"])

    if state.get("intent") is not None:
        existing_meta["intent"] = {
            "intent": state["intent"],
            "confidence": state.get("intent_confidence", 1.0),
            "reason": state.get("intent_reason"),
            "classification_method": state.get("classification_method", "deterministic"),
        }

    run.metadata_json = existing_meta

    db.commit()
    db.refresh(run)
    return run
