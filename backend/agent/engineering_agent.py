"""
EngineeringAgent: Top-level orchestration boundary for GitOnBoard engineering agent runs.

Phase 1 Responsibilities:
  - Establish, manage, and drive an AgentRun lifecycle.
  - Enforce AgentStateMachine transition rules.
  - Centralize event emission through AgentEventCoordinator.
  - Execute thin controlled actions (e.g. safe repository inspection via RepositoryToolLayer).
  - Provide deterministic restart safety and recovery.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.agent.event_coordinator import AgentEventCoordinator
from backend.agent.state_machine import AgentStateMachine, InvalidStateTransitionError
from backend.models.implementation import (
    AgentEventType,
    AgentRun,
    AgentRunStatus,
    AgentState,
    AgentStateTransition,
    map_agent_state_to_legacy_status,
)
from backend.repository_tools.tools import RepositoryToolLayer

logger = logging.getLogger(__name__)


class EngineeringAgentError(Exception):
    """Base exception for EngineeringAgent operational errors."""
    pass


class RunNotFoundError(EngineeringAgentError):
    """Raised when the specified agent_run_id does not exist."""
    pass


class EngineeringAgent:
    """
    Controlled execution shell and orchestration boundary for EngineeringAgent sessions.
    """

    def __init__(self, event_coordinator: Optional[AgentEventCoordinator] = None):
        self.events = event_coordinator or AgentEventCoordinator()
        self.state_machine = AgentStateMachine()

    def create_run(
        self,
        db: Session,
        repository_id: str,
        user_requirement: str,
        config: Optional[Dict[str, Any]] = None,
        custom_run_id: Optional[str] = None,
        implementation_id: Optional[str] = None,
    ) -> AgentRun:
        """
        Initializes and persists a new AgentRun, transitioning it from IDLE to UNDERSTANDING.
        """
        if not user_requirement or not user_requirement.strip():
            raise EngineeringAgentError("User requirement cannot be empty")

        run_id = custom_run_id or f"run_{uuid.uuid4().hex[:12]}"
        task_id = run_id

        run = AgentRun(
            id=run_id,
            task_id=task_id,
            repository_id=repository_id,
            user_requirement=user_requirement.strip(),
            implementation_id=implementation_id,
            current_state=AgentState.IDLE,
            status=AgentRunStatus.QUEUED,
            metadata_json=config or {},
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        # Emit initial STARTED event
        self.events.emit_event(
            db,
            run,
            AgentEventType.STARTED,
            f"EngineeringAgent run initialized for repository '{repository_id}'",
            {"repository_id": repository_id, "user_requirement": user_requirement[:200]},
        )

        # Transition IDLE -> UNDERSTANDING
        run = self.transition_state(
            db,
            run_id=run.id,
            to_state=AgentState.UNDERSTANDING,
            reason="Initial requirement comprehension started",
        )

        return run

    def get_run(self, db: Session, run_id: str) -> AgentRun:
        """Retrieves an AgentRun by ID or raises RunNotFoundError."""
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            # Fallback lookup by task_id
            run = db.query(AgentRun).filter(AgentRun.task_id == run_id).first()
        if not run:
            raise RunNotFoundError(f"AgentRun '{run_id}' not found")
        return run

    def transition_state(
        self,
        db: Session,
        run_id: str,
        to_state: AgentState | str,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentRun:
        """
        Validates and applies a state transition, updating both authoritative
        current_state and legacy status, recording the transition in DB,
        and emitting an event.
        """
        run = self.get_run(db, run_id)
        from_state = run.current_state

        # Validate transition using AgentStateMachine
        validated_to_state = self.state_machine.validate_transition(from_state, to_state)

        # Record transition history
        transition_record = AgentStateTransition(
            agent_run_id=run.id,
            from_state=from_state,
            to_state=validated_to_state,
            reason=reason or f"Transition to {validated_to_state.value}",
            metadata_json=metadata or {},
            timestamp=datetime.now(timezone.utc),
        )
        db.add(transition_record)

        # Mutate run state
        run.current_state = validated_to_state
        run.status = map_agent_state_to_legacy_status(validated_to_state)
        run.updated_at = datetime.now(timezone.utc)

        # Terminal state timestamping
        if self.state_machine.is_terminal(validated_to_state):
            run.completed_at = datetime.now(timezone.utc)

        db.add(run)
        db.commit()
        db.refresh(run)

        # Emit state transition event
        self.events.emit_event(
            db,
            run,
            AgentEventType.STATE_TRANSITION,
            f"State changed: {from_state.value} -> {validated_to_state.value}",
            {
                "from_state": from_state.value,
                "to_state": validated_to_state.value,
                "reason": reason,
                "metadata": metadata or {},
            },
        )

        return run

    def cancel_run(
        self,
        db: Session,
        run_id: str,
        reason: Optional[str] = None,
    ) -> AgentRun:
        """
        Cancels an in-flight AgentRun.
        Transitions the run to terminal CANCELLED state and records cancellation reason.
        """
        run = self.get_run(db, run_id)

        # Terminal state guard
        if self.state_machine.is_terminal(run.current_state):
            raise InvalidStateTransitionError(
                run.current_state,
                AgentState.CANCELLED,
                f"Cannot cancel run '{run_id}' already in terminal state '{run.current_state.value}'",
            )

        cancel_msg = reason or "Run cancelled by user request"
        run.cancellation_reason = cancel_msg
        db.add(run)
        db.commit()

        run = self.transition_state(
            db,
            run_id=run.id,
            to_state=AgentState.CANCELLED,
            reason=cancel_msg,
            metadata={"cancelled_at": datetime.now(timezone.utc).isoformat()},
        )

        self.events.emit_event(
            db,
            run,
            AgentEventType.CANCELLED,
            f"Agent run cancelled: {cancel_msg}",
            {"reason": cancel_msg},
        )

        return run

    def execute_controlled_action(
        self,
        db: Session,
        run_id: str,
        action_type: str = "inspect_repository",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Phase 1 thin controlled action proof:
        Executes a deterministic repository operation (e.g. RepositoryToolLayer inspection),
        captures output, records observation in AgentRun metadata, and emits action events.
        """
        run = self.get_run(db, run_id)
        if self.state_machine.is_terminal(run.current_state):
            raise EngineeringAgentError(f"Cannot execute action on run in terminal state '{run.current_state.value}'")

        params = parameters or {}
        repo_name = run.repository_id or "default"

        # Emit ACTION_STARTED
        self.events.emit_event(
            db,
            run,
            AgentEventType.ACTION_STARTED,
            f"Executing controlled action '{action_type}'",
            {"action_type": action_type, "parameters": params},
        )

        start_time = datetime.now(timezone.utc)
        result_data: Dict[str, Any] = {}

        try:
            # Deterministic repository inspection
            tool_layer = RepositoryToolLayer(repo_name=repo_name, db=db)

            if action_type == "inspect_repository":
                query = params.get("query", run.user_requirement or "")
                search_results = tool_layer.search_repository(query=query, limit=params.get("limit", 5))
                files_found = tool_layer.find_files(pattern=params.get("pattern", "*"), limit=5)
                result_data = {
                    "search_matches": search_results,
                    "sample_files": files_found,
                    "repository": repo_name,
                    "inspected_query": query,
                }
            elif action_type == "read_file":
                file_path = params.get("path", "")
                if file_path:
                    read_res = tool_layer.read_file(
                        path=file_path,
                        start_line=params.get("start_line", 1),
                        end_line=params.get("end_line", 50),
                    )
                    result_data = {"file_read": read_res}
                else:
                    result_data = {"error": "Missing 'path' parameter for read_file action"}
            elif action_type == "get_symbol":
                symbol_name = params.get("symbol", "")
                symbols = tool_layer.get_symbol(symbol_name)
                result_data = {"symbols": symbols}
            else:
                # Generic echo observation for custom proof actions
                result_data = {
                    "action": action_type,
                    "status": "COMPLETED",
                    "parameters": params,
                    "echo": f"Controlled action '{action_type}' executed deterministically",
                }

            status_str = "SUCCESS"
        except Exception as err:
            logger.warning(f"Controlled action '{action_type}' failed: {err}")
            result_data = {"error": str(err)}
            status_str = "FAILED"

        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        # Persist observation in AgentRun metadata
        meta = run.metadata_json or {}
        actions_list = meta.get("actions", [])
        actions_list.append(
            {
                "action_type": action_type,
                "status": status_str,
                "duration_ms": round(duration_ms, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        meta["actions"] = actions_list
        run.metadata_json = meta
        db.add(run)
        db.commit()

        # Emit ACTION_COMPLETED
        self.events.emit_event(
            db,
            run,
            AgentEventType.ACTION_COMPLETED,
            f"Controlled action '{action_type}' finished ({status_str}) in {duration_ms:.1f}ms",
            {"action_type": action_type, "status": status_str, "result_summary": list(result_data.keys())},
        )

        return {
            "run_id": run.id,
            "action_type": action_type,
            "status": status_str,
            "duration_ms": round(duration_ms, 2),
            "result": result_data,
        }

    def recover_in_flight_runs(self, db: Session) -> List[str]:
        """
        Restart recovery: Detects non-terminal runs interrupted by a server reboot
        and transitions them safely to FAILED with explicit failure reason,
        preventing orphaned or false-positive active states.
        """
        active_states = [
            AgentState.IDLE,
            AgentState.UNDERSTANDING,
            AgentState.PLANNING,
            AgentState.AWAITING_APPROVAL,
            AgentState.EXECUTING,
            AgentState.VERIFYING,
        ]

        orphaned = db.query(AgentRun).filter(AgentRun.current_state.in_(active_states)).all()
        recovered_ids: List[str] = []

        for run in orphaned:
            logger.warning(f"EngineeringAgent recovery: Terminating interrupted run '{run.id}' (state: {run.current_state.value})")
            run.error_message = "Server restart interrupted active execution"
            run.completed_at = datetime.now(timezone.utc)
            run.current_state = AgentState.FAILED
            run.status = AgentRunStatus.FAILED
            run.updated_at = datetime.now(timezone.utc)

            transition = AgentStateTransition(
                agent_run_id=run.id,
                from_state=run.current_state,
                to_state=AgentState.FAILED,
                reason="Server restart recovery",
                timestamp=datetime.now(timezone.utc),
            )
            db.add(transition)
            db.add(run)
            recovered_ids.append(run.id)

        if recovered_ids:
            db.commit()
            logger.info(f"EngineeringAgent recovery: Successfully recovered {len(recovered_ids)} interrupted run(s)")

        return recovered_ids
