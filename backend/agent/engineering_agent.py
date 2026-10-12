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
from pathlib import Path
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.config import settings
from backend.agent.event_coordinator import AgentEventCoordinator
from backend.agent.state_machine import AgentStateMachine, InvalidStateTransitionError
from backend.agent.context.assembler import ContextAssembler
from backend.agent.context.contracts import (
    ContextAssemblyRequest,
    ContextBudget,
    RepositoryContext,
)
from backend.agent.planning.contracts import Plan, PlanStatus, PlanTask, PlanTaskStatus
from backend.agent.planning.orchestrator import PlanningOrchestrator
from backend.agent.tasks import (
    DefaultTaskExecutor,
    DefaultVerificationDispatcher,
    TaskExecutionContext,
    TaskExecutionResult,
    TaskExecutor,
    TaskOrchestrator,
    VerificationDispatcher,
)

from backend.agent.tools.contracts import (
    AgentToolContext,
    ToolErrorCode,
    ToolResult,
)
from backend.agent.tools.registry import AgentToolRegistry
from backend.agent.tools import create_default_tool_registry
from backend.agent.safety import (
    ApprovalActionType,
    ApprovalController,
    ApprovalStatus,
    CancellationController,
    CancellationToken,
    ExecutionPolicy,
    PolicyAction,
    RiskLevel,
)
from backend.models.implementation import (
    AgentEventType,
    AgentRun,
    AgentRunStatus,
    AgentState,
    AgentStateTransition,
    ApprovalRequest,
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
        llm_service: Optional[Any] = None,
        task_orchestrator: Optional[TaskOrchestrator] = None,
        approval_controller: Optional[ApprovalController] = None,
        cancellation_controller: Optional[CancellationController] = None,
    ):
        self.events = event_coordinator or AgentEventCoordinator()
        self.state_machine = AgentStateMachine()
        self.tools = tool_registry or create_default_tool_registry()
        self.llm_service = llm_service

        # Initialize TaskOrchestrator with appropriate executor
        if task_orchestrator is None:
            # Use EngineeringAgentTaskExecutor for real execution (requires LLM)
            # Fall back to DefaultTaskExecutor for testing/stub mode
            from backend.agent.tasks.executor import EngineeringAgentTaskExecutor, DefaultTaskExecutor
            executor: Any = DefaultTaskExecutor()  # Default stub for testing

            # If LLM service is available, use the real executor
            if llm_service is not None:
                executor = EngineeringAgentTaskExecutor(loop=None, agent_loop=None, llm_service=llm_service)

            task_orchestrator = TaskOrchestrator(executor=executor)

        self.task_orchestrator = task_orchestrator
        self.approval_controller = approval_controller or ApprovalController(event_coordinator=self.events)
        self.cancellation_controller = cancellation_controller or CancellationController(event_coordinator=self.events)
        from backend.agent.plan_ops import EngineeringAgentPlanOps
        from backend.agent.task_ops import EngineeringAgentTaskOps
        self._plan_ops = EngineeringAgentPlanOps(self)
        self._task_ops = EngineeringAgentTaskOps(self)

    def _get_run(self, db: Session, run_id: str) -> AgentRun:
        """Retrieves an AgentRun by ID or raises RunNotFoundError."""
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            raise RunNotFoundError(f"AgentRun '{run_id}' not found")
        return run


    def create_run(
        self,
        db: Session,
        repository_id: str,
        user_requirement: str,
        config: Optional[Dict[str, Any]] = None,
        custom_run_id: Optional[str] = None,
        implementation_id: Optional[str] = None,
        user_id: Optional[int] = None,
        worktree_path: Optional[str] = None,
    ) -> AgentRun:
        """
        Initializes and persists a new AgentRun, transitioning it from IDLE to UNDERSTANDING.
        """
        if not user_requirement or not user_requirement.strip():
            raise EngineeringAgentError("User requirement cannot be empty")

        run_id = custom_run_id or f"run_{uuid.uuid4().hex[:12]}"
        task_id = run_id

        if not worktree_path and repository_id:
            from pathlib import Path
            from backend.config import settings
            clean_name = repository_id.split("/")[-1].replace(".git", "")
            candidates = [
                Path(settings.worktrees_dir) / clean_name,
                Path("data/worktrees") / clean_name,
                Path("/home/dheeraj/repository_intelligence_platform/data/worktrees") / clean_name,
            ]
            for c in candidates:
                if c.exists() and c.is_dir():
                    worktree_path = str(c.resolve())
                    break

        run = AgentRun(
            id=run_id,
            task_id=task_id,
            repository_id=repository_id,
            user_id=user_id,
            user_requirement=user_requirement.strip(),
            implementation_id=implementation_id,
            current_state=AgentState.IDLE,
            status=AgentRunStatus.QUEUED,
            worktree_path=worktree_path,
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
        Cancels an in-flight AgentRun across all active subsystems and returns the updated AgentRun.
        Idempotent if already cancelled. Rejects cancellation of completed/failed runs.
        """
        run = self.get_run(db, run_id)
        cancel_msg = reason or "User requested cancellation"
        return self.cancellation_controller.cancel_run(
            db, run_id, reason=cancel_msg, run_model=run
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

        meta = dict(run.metadata_json or {})
        actions_list = list(meta.get("actions", []))
        actions_list.append(
            {
                "action_type": action_type,
                "status": status_str,
                "duration_ms": round(duration_ms, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        meta["actions"] = actions_list
        from sqlalchemy.orm.attributes import flag_modified
        run.metadata_json = meta
        flag_modified(run, "metadata_json")
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
        started_payload: Dict[str, Any] = {
            "tool_name": tool_name,
            "tool": tool_name,
            "arguments": safe_args_meta,
            "status": "running",
        }
        if tool_name == "read_file":
            started_payload["activity_type"] = "reading"
            started_payload["path"] = safe_args_meta.get("path") or safe_args_meta.get("file_path")
            if "start_line" in safe_args_meta:
                started_payload["start_line"] = safe_args_meta["start_line"]
            if "end_line" in safe_args_meta:
                started_payload["end_line"] = safe_args_meta["end_line"]
        elif tool_name in ("search_code", "search_symbols"):
            started_payload["activity_type"] = "searching"
            started_payload["query"] = safe_args_meta.get("query") or safe_args_meta.get("pattern") or ""
        elif tool_name in ("get_symbol", "get_callers", "get_callees", "trace_feature"):
            started_payload["activity_type"] = "inspecting"
            started_payload["symbol"] = safe_args_meta.get("name") or safe_args_meta.get("symbol_name") or safe_args_meta.get("seed_id") or ""
            if "path" in safe_args_meta:
                started_payload["path"] = safe_args_meta["path"]
        elif tool_name in ("create_file", "modify_file", "write_file", "apply_patch"):
            started_payload["activity_type"] = "writing"
            started_payload["path"] = safe_args_meta.get("path") or safe_args_meta.get("file_path")
        elif tool_name == "delete_file":
            started_payload["activity_type"] = "deleting"
            started_payload["path"] = safe_args_meta.get("path")
        elif tool_name in ("verify_dynamic", "run_tests"):
            started_payload["activity_type"] = "testing"
            started_payload["task"] = safe_args_meta.get("test_command") or "Run tests"
        elif tool_name in ("verify_static", "verify_contract", "judge_verification"):
            started_payload["activity_type"] = "verifying"
            started_payload["task"] = tool_name.replace("verify_", "").replace("_", " ").title()
        else:
            started_payload["activity_type"] = "tool"

        self.events.emit_event(
            db,
            run,
            AgentEventType.TOOL_CALL_STARTED,
            f"Invoking tool '{tool_name}'",
            started_payload,
        )

        # 3. Dispatch through central tool registry
        result = self.tools.invoke(tool_name, args, context)

        # 4. Map event type based on tool execution result
        completed_payload: Dict[str, Any] = dict(started_payload)
        if result.error and result.error.code == ToolErrorCode.POLICY_BLOCKED.value:
            event_type = AgentEventType.TOOL_CALL_BLOCKED
            msg = f"Tool '{tool_name}' blocked: {result.error.message}"
            completed_payload["status"] = "blocked"
            completed_payload["error_code"] = result.error.code
        elif result.error and result.error.code == ToolErrorCode.APPROVAL_REQUIRED.value:
            event_type = AgentEventType.TOOL_CALL_APPROVAL_REQUIRED
            msg = f"Tool '{tool_name}' requires approval: {result.error.message}"
            completed_payload["status"] = "approval_required"
        elif not result.success:
            event_type = AgentEventType.TOOL_CALL_FAILED
            msg = f"Tool '{tool_name}' failed: {result.error.message if result.error else 'Unknown error'}"
            completed_payload["status"] = "failed"
            completed_payload["error_code"] = result.error.code if result.error else None
            completed_payload["error_message"] = result.error.message if result.error else "Unknown error"
        else:
            event_type = AgentEventType.TOOL_CALL_COMPLETED
            msg = f"Tool '{tool_name}' completed in {result.metadata.get('duration_ms', 0):.1f}ms"
            completed_payload["status"] = "completed"
            completed_payload["duration_ms"] = result.metadata.get("duration_ms", 0)
            if result.data and isinstance(result.data, dict) and "path" in result.data:
                completed_payload["path"] = result.data["path"]

        self.events.emit_event(
            db,
            run,
            event_type,
            msg,
            completed_payload,
        )

        if result.success and completed_payload.get("activity_type") == "writing" and completed_payload.get("path"):
            self.events.emit_event(
                db,
                run,
                AgentEventType.FILE_WRITTEN,
                f"Wrote {completed_payload['path']}",
                {"activity_type": "writing", "path": completed_payload["path"], "status": "completed"},
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
            if not analysis_id and run.repository_id:
                from backend.agent.modes import resolve_target_repository_and_analysis
                _, analysis_id, _ = resolve_target_repository_and_analysis(db, run.repository_id, getattr(run, "user_id", None))
                if analysis_id:
                    meta["analysis_id"] = analysis_id

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

    def get_repository_revision(
        self,
        repository_id: Optional[str] = None,
        worktree_path: Optional[str] = None,
    ) -> str:
        """
        Retrieves the deterministic Git commit SHA / repository revision snapshot.
        Checks active worktree, cloned repository directory, or deterministic fallback.
        """
        import subprocess
        # 1. If worktree_path provided and exists
        if worktree_path and Path(worktree_path).exists():
            try:
                res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=worktree_path, capture_output=True, text=True, timeout=5)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass

        # 2. If repository_id resolves to local repo
        if repository_id:
            storage_dir = getattr(settings, "storage_path", "data")
            candidate_paths = [
                Path(repository_id),
                Path(storage_dir) / "repos" / repository_id,
                Path(storage_dir) / repository_id,
            ]
            for cp in candidate_paths:
                if cp.exists():
                    try:
                        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cp, capture_output=True, text=True, timeout=5)
                        if res.returncode == 0 and res.stdout.strip():
                            return res.stdout.strip()
                    except Exception:
                        pass

        return f"rev:{repository_id or 'default'}"

    def revise_plan(
        self,
        db: Session,
        run_id: str,
        feedback: str,
        budget: Optional[ContextBudget] = None,
    ) -> Plan:
        """Revises an existing implementation plan based on user review comments."""
        return self._plan_ops.revise_plan(db, run_id, feedback, budget=budget)

    def create_plan(
        self,
        db: Session,
        run_id: str,
        budget: Optional[ContextBudget] = None,
        force_replan: bool = False,
    ) -> Plan:
        """Synthesizes, validates, and records a structured implementation plan."""
        return self._plan_ops.create_plan(db, run_id, budget=budget, force_replan=force_replan)

    def get_plan(self, db: Session, run_id: str) -> Optional[Plan]:
        """Retrieves the current Plan object from run metadata."""
        return self._plan_ops.get_plan(db, run_id)

    def assert_execution_authorized(
        self,
        db: Session,
        run_id: str,
        plan_id: Optional[str] = None,
        plan_version: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> None:
        """Server-side central execution authorization gate."""
        return self._plan_ops.assert_execution_authorized(
            db, run_id, plan_id=plan_id, plan_version=plan_version, user_id=user_id
        )

    def approve_plan(
        self,
        db: Session,
        run_id: str,
        resolved_by: str = "human_user",
        user_id: Optional[int] = None,
    ) -> AgentRun:
        """Explicitly approves the synthesized plan."""
        return self._plan_ops.approve_plan(db, run_id, resolved_by=resolved_by, user_id=user_id)

    def reject_plan(
        self,
        db: Session,
        run_id: str,
        reason: Optional[str] = None,
        resolved_by: str = "human_user",
        user_id: Optional[int] = None,
    ) -> AgentRun:
        """Explicitly rejects the synthesized plan."""
        return self._plan_ops.reject_plan(
            db, run_id, reason=reason, resolved_by=resolved_by, user_id=user_id
        )

    def start_plan_execution(
        self,
        db: Session,
        run_id: str,
        user_id: Optional[int] = None,
    ) -> AgentRun:
        """Initiates controlled execution of an approved implementation plan."""
        return self._task_ops.start_plan_execution(db, run_id, user_id=user_id)

    def get_plan_tasks(self, db: Session, run_id: str) -> List[PlanTask]:
        """Returns all PlanTask items with current lifecycle statuses for the run."""
        return self._task_ops.get_plan_tasks(db, run_id)

    def get_plan_task(self, db: Session, run_id: str, task_id: str) -> Optional[PlanTask]:
        """Retrieves a single PlanTask by task_id."""
        return self._task_ops.get_plan_task(db, run_id, task_id)

    def get_next_task(self, db: Session, run_id: str) -> Optional[PlanTask]:
        """Deterministically selects the next eligible task to execute according to DAG dependencies."""
        return self._task_ops.get_next_task(db, run_id)

    def execute_next_task(
        self,
        db: Session,
        run_id: str,
    ) -> Tuple[Optional[PlanTask], Optional[TaskExecutionResult]]:
        """Executes the next eligible task sequentially."""
        return self._task_ops.execute_next_task(db, run_id)

    def complete_run(
        self,
        db: Session,
        run_id: str,
        success: bool = True,
        failure_reason: Optional[str] = None,
    ) -> AgentRun:
        """Marks a run as COMPLETED or FAILED after all tasks have been executed and verified."""
        return self._task_ops.complete_run(
            db, run_id, success=success, failure_reason=failure_reason
        )

    def recover_in_flight_runs(self, db: Session) -> List[str]:
        """Restart recovery: Detects non-terminal runs interrupted by a server reboot."""
        return self._task_ops.recover_in_flight_runs(db)

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 9: Human Action Approval & Safety Control
    # ──────────────────────────────────────────────────────────────────────────

    def request_action_approval(
        self,
        db: Session,
        run_id: str,
        action_description: str,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
        action_type: ApprovalActionType = ApprovalActionType.TOOL_EXECUTION,
        task_id: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        requested_operation: Optional[Dict[str, Any]] = None,
        affected_files: Optional[List[str]] = None,
        command: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> ApprovalRequest:
        """
        Creates and persists a first-class ApprovalRequest.
        Pauses run lifecycle state to AWAITING_APPROVAL if currently EXECUTING.
        """
        run = self._get_run(db, run_id)
        if run.current_state == AgentState.EXECUTING:
            self.transition_state(
                db, run_id, to_state=AgentState.AWAITING_APPROVAL, reason=f"Action requires human approval: {action_description}"
            )

        req = self.approval_controller.create_approval_request(
            db=db,
            agent_run_id=run_id,
            action_type=action_type,
            action_description=action_description,
            risk_level=risk_level,
            task_id=task_id,
            tool_call_id=tool_call_id,
            requested_operation=requested_operation,
            affected_files=affected_files,
            command=command,
            reason=reason,
            run_model=run,
        )
        return req

    def approve_action(
        self,
        db: Session,
        approval_id: str,
        resolved_by: str = "human_user",
    ) -> ApprovalRequest:
        """
        Approves a pending action request.
        Resumes run state from AWAITING_APPROVAL -> EXECUTING once all approvals are resolved.
        """
        req = self.approval_controller.approve_request(
            db=db, approval_id=approval_id, resolved_by=resolved_by
        )
        run = self._get_run(db, req.agent_run_id)
        if run.current_state == AgentState.AWAITING_APPROVAL:
            pending = self.approval_controller.get_pending_approvals(db, req.agent_run_id)
            if not pending:
                self.transition_state(
                    db, req.agent_run_id, to_state=AgentState.EXECUTING, reason="Action approved by user"
                )
        return req

    def reject_action(
        self,
        db: Session,
        approval_id: str,
        reason: str,
        resolved_by: str = "human_user",
    ) -> ApprovalRequest:
        """
        Rejects a pending action request.
        Resumes run state from AWAITING_APPROVAL -> EXECUTING so agent can adapt with a structured rejection observation.
        """
        req = self.approval_controller.reject_request(
            db=db, approval_id=approval_id, reason=reason, resolved_by=resolved_by
        )
        run = self._get_run(db, req.agent_run_id)
        if run.current_state == AgentState.AWAITING_APPROVAL:
            pending = self.approval_controller.get_pending_approvals(db, req.agent_run_id)
            if not pending:
                self.transition_state(
                    db, req.agent_run_id, to_state=AgentState.EXECUTING, reason=f"Action rejected by user: {reason}"
                )
        return req

    def get_pending_approvals(self, db: Session, run_id: str) -> List[ApprovalRequest]:
        """Queries all pending approval requests for a run."""
        return self.approval_controller.get_pending_approvals(db, run_id)




