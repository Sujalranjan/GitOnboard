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
from backend.agent.context.assembler import ContextAssembler
from backend.agent.context.contracts import (
    ContextAssemblyRequest,
    ContextBudget,
    RepositoryContext,
)
from backend.agent.tools.contracts import (
    AgentToolContext,
    ToolErrorCode,
    ToolResult,
)
from backend.agent.tools.registry import AgentToolRegistry
from backend.agent.tools import create_default_tool_registry
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

    def __init__(
        self,
        event_coordinator: Optional[AgentEventCoordinator] = None,
        tool_registry: Optional[AgentToolRegistry] = None,
    ):
        self.events = event_coordinator or AgentEventCoordinator()
        self.state_machine = AgentStateMachine()
        self.tools = tool_registry or create_default_tool_registry()

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

    def invoke_tool(
        self,
        db: Session,
        run_id: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Executes a registered tool on behalf of the agent session.
        Enforces run state, builds execution context, emits lifecycle events,
        and logs tool call observation in run metadata.
        """
        run = self.get_run(db, run_id)

        # Invariant: Terminal state check
        if self.state_machine.is_terminal(run.current_state):
            raise EngineeringAgentError(
                f"Cannot invoke tool '{tool_name}' on run '{run_id}' in terminal state '{run.current_state.value}'"
            )

        args = arguments or {}

        # 1. Build authenticated execution context
        context = AgentToolContext(
            agent_run_id=run.id,
            repository_id=run.repository_id or "default",
            task_id=run.task_id,
            worktree_path=run.worktree_path,
            db=db,
            config=run.metadata_json or {},
        )

        # 2. Emit TOOL_CALL_STARTED
        safe_args_meta = {k: v for k, v in args.items() if k not in ("content", "patch_text")}
        self.events.emit_event(
            db,
            run,
            AgentEventType.TOOL_CALL_STARTED,
            f"Invoking tool '{tool_name}'",
            {"tool_name": tool_name, "arguments": safe_args_meta},
        )

        # 3. Dispatch through central tool registry
        result = self.tools.invoke(tool_name, args, context)

        # 4. Map event type based on tool execution result
        if result.error and result.error.code == ToolErrorCode.POLICY_BLOCKED.value:
            event_type = AgentEventType.TOOL_CALL_BLOCKED
            msg = f"Tool '{tool_name}' blocked: {result.error.message}"
        elif result.error and result.error.code == ToolErrorCode.APPROVAL_REQUIRED.value:
            event_type = AgentEventType.TOOL_CALL_APPROVAL_REQUIRED
            msg = f"Tool '{tool_name}' requires approval: {result.error.message}"
        elif not result.success:
            event_type = AgentEventType.TOOL_CALL_FAILED
            msg = f"Tool '{tool_name}' failed: {result.error.message if result.error else 'Unknown error'}"
        else:
            event_type = AgentEventType.TOOL_CALL_COMPLETED
            msg = f"Tool '{tool_name}' completed in {result.metadata.get('duration_ms', 0):.1f}ms"

        self.events.emit_event(
            db,
            run,
            event_type,
            msg,
            {
                "tool_name": tool_name,
                "success": result.success,
                "error_code": result.error.code if result.error else None,
                "duration_ms": result.metadata.get("duration_ms", 0),
            },
        )

        # 5. Record tool call in run metadata
        meta = run.metadata_json or {}
        tool_calls = meta.get("tool_calls", [])
        tool_calls.append(
            {
                "tool_name": tool_name,
                "success": result.success,
                "error": result.error.model_dump() if result.error else None,
                "duration_ms": result.metadata.get("duration_ms", 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        meta["tool_calls"] = tool_calls
        run.metadata_json = meta
        db.add(run)
        db.commit()

        return result

    def assemble_repository_context(
        self,
        db: Session,
        run_id: str,
        budget: Optional[ContextBudget] = None,
    ) -> RepositoryContext:
        """
        Assembles structured repository evidence for the run's requirement.
        Emits lifecycle events and persists a bounded, versioned summary in run metadata.
        """
        run = self.get_run(db, run_id)

        # Invariant: Terminal state check
        if self.state_machine.is_terminal(run.current_state):
            raise EngineeringAgentError(
                f"Cannot assemble context on run '{run_id}' in terminal state '{run.current_state.value}'"
            )

        # 1. Emit CONTEXT_ASSEMBLY_STARTED
        self.events.emit_event(
            db,
            run,
            AgentEventType.CONTEXT_ASSEMBLY_STARTED,
            f"Starting repository context assembly for requirement: '{run.user_requirement[:60]}...'",
            {"repository_id": run.repository_id},
        )

        try:
            # 2. Build assembly request
            meta = run.metadata_json or {}
            analysis_id = meta.get("analysis_id")
            request = ContextAssemblyRequest(
                repository_id=run.repository_id or "default",
                requirement=run.user_requirement,
                context_budget=budget,
                analysis_id=analysis_id,
                worktree_path=run.worktree_path,
            )

            # 3. Assemble context via ContextAssembler
            assembler = ContextAssembler()
            context = assembler.assemble(request, db=db)

            # 4. Emit CONTEXT_ASSEMBLY_COMPLETED
            self.events.emit_event(
                db,
                run,
                AgentEventType.CONTEXT_ASSEMBLY_COMPLETED,
                f"Repository context assembled ({context.contract.completeness.value}): "
                f"{len(context.evidence)} evidence items, {len(context.relevant_files)} files, {len(context.unknowns)} unknowns",
                {
                    "completeness": context.contract.completeness.value,
                    "evidence_count": len(context.evidence),
                    "files_count": len(context.relevant_files),
                    "symbols_count": len(context.relevant_symbols),
                    "unknown_count": len(context.unknowns),
                    "duration_ms": context.metadata.get("duration_ms", 0.0),
                },
            )

            # 5. Persist bounded, versioned summary in run metadata (preserves long-term database performance)
            meta["repository_context"] = context.to_bounded_summary()
            run.metadata_json = meta
            db.add(run)
            db.commit()

            return context
        except Exception as err:
            logger.error(f"Context assembly failed for run '{run_id}': {err}", exc_info=True)
            self.events.emit_event(
                db,
                run,
                AgentEventType.CONTEXT_ASSEMBLY_FAILED,
                f"Context assembly failed: {err}",
                {"error": str(err)},
            )
            raise EngineeringAgentError(f"Repository context assembly failed: {err}") from err

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
