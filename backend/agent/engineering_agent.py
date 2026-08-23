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
        self.task_orchestrator = task_orchestrator or TaskOrchestrator()
        self.approval_controller = approval_controller or ApprovalController(event_coordinator=self.events)
        self.cancellation_controller = cancellation_controller or CancellationController(event_coordinator=self.events)

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
            user_id=user_id,
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

    def create_plan(
        self,
        db: Session,
        run_id: str,
        budget: Optional[ContextBudget] = None,
    ) -> Plan:
        """
        Synthesizes, validates, and records a structured implementation plan.
        Transitions the agent run to AWAITING_APPROVAL upon successful validation.
        """
        run = self.get_run(db, run_id)

        # Invariant: Terminal state check
        if self.state_machine.is_terminal(run.current_state):
            raise EngineeringAgentError(
                f"Cannot create plan on run '{run_id}' in terminal state '{run.current_state.value}'"
            )

        # Idempotency / Deduplication: If already in AWAITING_APPROVAL with a valid plan, return existing plan
        existing_plan = self.get_plan(db, run_id)
        if run.current_state == AgentState.AWAITING_APPROVAL and existing_plan and (existing_plan.validation and existing_plan.validation.valid):
            logger.info(f"Plan already synthesized and validated for run '{run_id}' in AWAITING_APPROVAL. Returning existing plan.")
            return existing_plan

        # Transition to PLANNING state if currently in IDLE, UNDERSTANDING, or AWAITING_APPROVAL (replanning)
        if run.current_state in (AgentState.IDLE, AgentState.UNDERSTANDING, AgentState.AWAITING_APPROVAL):
            self.transition_state(db, run.id, to_state=AgentState.PLANNING, reason="Starting plan synthesis")
            db.refresh(run)

        # 1. Emit PLANNING_STARTED
        self.events.emit_event(
            db,
            run,
            AgentEventType.PLANNING_STARTED,
            f"Starting implementation plan synthesis for requirement: '{run.user_requirement[:60]}...'",
            {"repository_id": run.repository_id},
        )

        try:
            # 2. Assemble/fetch repository context
            context = self.assemble_repository_context(db, run.id, budget=budget)

            # Determine plan revision version
            meta = run.metadata_json or {}
            existing_plan_data = meta.get("plan")
            current_version = existing_plan_data.get("version", 0) if isinstance(existing_plan_data, dict) else 0
            new_version = current_version + 1

            # 3. Invoke PlanningOrchestrator
            orchestrator = PlanningOrchestrator(llm_service=self.llm_service)
            plan = orchestrator.create_plan(
                context=context,
                agent_run_id=run.id,
                repository_id=run.repository_id or "default",
                requirement=run.user_requirement,
                db=db,
                version=new_version,
            )

            # 4. Handle validation outcome
            if plan.validation and plan.validation.valid:
                self.events.emit_event(
                    db,
                    run,
                    AgentEventType.PLANNING_COMPLETED,
                    f"Implementation plan v{plan.version} synthesized and validated with {len(plan.tasks)} tasks.",
                    {
                        "plan_id": plan.plan_id,
                        "version": plan.version,
                        "task_count": len(plan.tasks),
                        "unknown_count": len(plan.unknowns),
                    },
                )
                self.events.emit_event(
                    db,
                    run,
                    AgentEventType.PLAN_READY_FOR_APPROVAL,
                    f"Plan v{plan.version} is ready for human approval.",
                    {"plan_id": plan.plan_id, "version": plan.version},
                )

                # Persist full plan artifact and bounded summary
                from sqlalchemy.orm.attributes import flag_modified
                meta["plan"] = plan.model_dump(mode="json")
                run.metadata_json = meta
                flag_modified(run, "metadata_json")
                db.add(run)
                db.commit()

                # Transition to AWAITING_APPROVAL only if still in PLANNING state
                db.refresh(run)
                if run.current_state == AgentState.PLANNING:
                    self.transition_state(
                        db,
                        run.id,
                        to_state=AgentState.AWAITING_APPROVAL,
                        reason=f"Plan v{plan.version} created and validated with {len(plan.tasks)} tasks; awaiting user review",
                    )
                elif run.current_state == AgentState.AWAITING_APPROVAL:
                    logger.info(f"Run '{run_id}' already transitioned to AWAITING_APPROVAL by concurrent operation")
            else:
                from sqlalchemy.orm.attributes import flag_modified
                err_msg = "; ".join(plan.validation.errors) if plan.validation else "Validation failed"
                self.events.emit_event(
                    db,
                    run,
                    AgentEventType.PLANNING_FAILED,
                    f"Plan validation failed: {err_msg}",
                    {"errors": plan.validation.errors if plan.validation else []},
                )
                meta["plan"] = plan.model_dump(mode="json")
                run.metadata_json = meta
                flag_modified(run, "metadata_json")
                db.add(run)
                db.commit()

            return plan

        except Exception as err:
            logger.error(f"Plan creation failed for run '{run_id}': {err}", exc_info=True)
            self.events.emit_event(
                db,
                run,
                AgentEventType.PLANNING_FAILED,
                f"Planning failed: {err}",
                {"error": str(err)},
            )
            raise EngineeringAgentError(f"Plan synthesis failed: {err}") from err

    def get_plan(self, db: Session, run_id: str) -> Optional[Plan]:
        """
        Retrieves the current Plan object from run metadata.
        """
        run = self.get_run(db, run_id)
        meta = run.metadata_json or {}
        plan_dict = meta.get("plan")
        if plan_dict and isinstance(plan_dict, dict):
            try:
                return Plan.model_validate(plan_dict)
            except Exception as err:
                logger.warning(f"Failed to parse Plan model from metadata for run '{run_id}': {err}")
        return None

    def approve_plan(self, db: Session, run_id: str) -> AgentRun:
        """
        Explicitly approves the synthesized plan.
        CRITICAL INVARIANT: Approval does NOT execute tasks (PLAN_APPROVED != TASK_EXECUTION_STARTED).
        Run remains in AWAITING_APPROVAL state until Phase 5 TaskOrchestrator initiates execution.
        """
        run = self.get_run(db, run_id)

        if run.current_state != AgentState.AWAITING_APPROVAL:
            raise EngineeringAgentError(
                f"Cannot approve plan for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.AWAITING_APPROVAL.value}' state."
            )

        plan = self.get_plan(db, run_id)
        if not plan:
            raise EngineeringAgentError(f"No plan found to approve for run '{run_id}'")

        if plan.status != PlanStatus.READY_FOR_APPROVAL:
            raise EngineeringAgentError(
                f"Plan '{plan.plan_id}' is in status '{plan.status.value}'. Only plans in READY_FOR_APPROVAL can be approved."
            )

        # Mark plan as approved
        from sqlalchemy.orm.attributes import flag_modified
        plan.status = PlanStatus.APPROVED
        plan.updated_at = datetime.now(timezone.utc)

        meta = run.metadata_json or {}
        meta["plan"] = plan.model_dump(mode="json")
        run.metadata_json = meta
        flag_modified(run, "metadata_json")
        db.add(run)
        db.commit()

        # Emit PLAN_APPROVED event
        self.events.emit_event(
            db,
            run,
            AgentEventType.PLAN_APPROVED,
            f"Plan v{plan.version} ('{plan.plan_id}') approved by user. Ready for Phase 5 task orchestration.",
            {
                "plan_id": plan.plan_id,
                "version": plan.version,
                "task_count": len(plan.tasks),
            },
        )

        return run

    def reject_plan(self, db: Session, run_id: str, reason: Optional[str] = None) -> AgentRun:
        """
        Explicitly rejects the synthesized plan.
        Transitions the run state to PLANNING for revision.
        CRITICAL INVARIANT: Rejection NEVER triggers task implementation.
        """
        run = self.get_run(db, run_id)

        if run.current_state != AgentState.AWAITING_APPROVAL:
            raise EngineeringAgentError(
                f"Cannot reject plan for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.AWAITING_APPROVAL.value}' state."
            )

        plan = self.get_plan(db, run_id)
        if plan:
            from sqlalchemy.orm.attributes import flag_modified
            plan.status = PlanStatus.REJECTED
            plan.updated_at = datetime.now(timezone.utc)
            meta = run.metadata_json or {}
            meta["plan"] = plan.model_dump(mode="json")
            run.metadata_json = meta
            flag_modified(run, "metadata_json")
            db.add(run)
            db.commit()


        # Emit PLAN_REJECTED event
        reject_msg = reason or "Plan rejected by user."
        self.events.emit_event(
            db,
            run,
            AgentEventType.PLAN_REJECTED,
            f"Plan rejected by user: {reject_msg}",
            {
                "plan_id": plan.plan_id if plan else None,
                "reason": reject_msg,
            },
        )

        # Transition state back to PLANNING for plan revision
        self.transition_state(
            db,
            run.id,
            to_state=AgentState.PLANNING,
            reason=f"Plan rejected: {reject_msg}; awaiting revision",
        )

        return run

    def start_plan_execution(self, db: Session, run_id: str) -> AgentRun:
        """
        Initiates controlled execution of an approved implementation plan.
        Strict preconditions:
          - AgentRun.current_state == AgentState.AWAITING_APPROVAL
          - Plan.status == PlanStatus.APPROVED
          - Plan.validation.valid is True
        Transitions run state from AWAITING_APPROVAL -> EXECUTING and marks initial eligible tasks READY.
        """
        run = self.get_run(db, run_id)

        if run.current_state != AgentState.AWAITING_APPROVAL:
            raise EngineeringAgentError(
                f"Cannot start execution for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.AWAITING_APPROVAL.value}' state."
            )

        plan = self.get_plan(db, run_id)
        if not plan:
            raise EngineeringAgentError(f"No plan found for run '{run_id}'")

        if plan.status != PlanStatus.APPROVED:
            raise EngineeringAgentError(
                f"Cannot execute unapproved plan '{plan.plan_id}' with status '{plan.status.value}'. "
                f"Plan must be explicitly APPROVED before execution."
            )

        if not plan.validation or not plan.validation.valid:
            raise EngineeringAgentError(f"Cannot execute invalid plan '{plan.plan_id}'.")

        # Evaluate dependencies to unlock initial eligible tasks to READY
        self.task_orchestrator.evaluate_dependencies(plan)

        # Persist updated plan in run metadata
        from sqlalchemy.orm.attributes import flag_modified
        meta = run.metadata_json or {}
        meta["plan"] = plan.model_dump(mode="json")
        run.metadata_json = meta
        flag_modified(run, "metadata_json")
        db.add(run)
        db.commit()

        # Transition run state AWAITING_APPROVAL -> EXECUTING
        self.transition_state(
            db,
            run.id,
            to_state=AgentState.EXECUTING,
            reason=f"Plan '{plan.plan_id}' approved; starting controlled execution of {len(plan.tasks)} tasks",
        )

        # Emit TASK_READY events for initial ready tasks
        for task in plan.tasks:
            if task.status == PlanTaskStatus.READY:
                self.events.emit_event(
                    db,
                    run,
                    AgentEventType.TASK_READY,
                    f"Task '{task.task_id}' ('{task.title}') is READY for execution.",
                    {"task_id": task.task_id, "step_number": task.step_number},
                )

        return run

    def get_plan_tasks(self, db: Session, run_id: str) -> List[PlanTask]:
        """
        Returns all PlanTask items with current lifecycle statuses for the run.
        """
        plan = self.get_plan(db, run_id)
        if not plan:
            return []
        # Keep dependencies evaluated
        self.task_orchestrator.evaluate_dependencies(plan)
        return plan.tasks

    def get_plan_task(self, db: Session, run_id: str, task_id: str) -> Optional[PlanTask]:
        """
        Retrieves a single PlanTask by task_id.
        """
        plan = self.get_plan(db, run_id)
        if not plan:
            return None
        return next((t for t in plan.tasks if t.task_id == task_id), None)

    def get_next_task(self, db: Session, run_id: str) -> Optional[PlanTask]:
        """
        Deterministically selects the next eligible task to execute according to DAG dependencies.
        """
        run = self.get_run(db, run_id)
        plan = self.get_plan(db, run_id)
        if not plan:
            return None
        return self.task_orchestrator.select_next_task(plan)

    def execute_next_task(
        self,
        db: Session,
        run_id: str,
    ) -> Tuple[Optional[PlanTask], Optional[TaskExecutionResult]]:
        """
        Executes the next eligible task sequentially:
          1. Selects next READY task deterministically: (step_number, task_id)
          2. Transitions task READY -> RUNNING
          3. Executes task via TaskExecutor boundary
          4. Transitions task RUNNING -> VERIFYING (or FAILED)
          5. Evaluates verification criteria via VerificationDispatcher
          6. Transitions task VERIFYING -> PASSED (or FAILED)
          7. Unlocks downstream dependencies or marks downstream BLOCKED
          8. Persists plan state in run metadata and emits audit events
        """
        run = self.get_run(db, run_id)
        if run.current_state != AgentState.EXECUTING:
            raise EngineeringAgentError(
                f"Cannot execute tasks for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.EXECUTING.value}' state."
            )

        plan = self.get_plan(db, run_id)
        if not plan or plan.status != PlanStatus.APPROVED:
            raise EngineeringAgentError(f"No approved plan found for run '{run_id}'")

        next_task = self.task_orchestrator.select_next_task(plan)
        if not next_task:
            return None, None

        task_id = next_task.task_id

        # Emit NEXT_TASK_SELECTED event
        self.events.emit_event(
            db,
            run,
            AgentEventType.NEXT_TASK_SELECTED,
            f"Selected next eligible task '{task_id}': '{next_task.title}'",
            {"task_id": task_id, "step_number": next_task.step_number},
        )

        # 1. Start task (READY -> RUNNING)
        self.task_orchestrator.start_task(plan, task_id)
        self.events.emit_event(
            db,
            run,
            AgentEventType.TASK_STARTED,
            f"Started executing task '{task_id}': '{next_task.title}'",
            {"task_id": task_id, "step_number": next_task.step_number},
        )

        # Build execution context
        repo_ctx = (run.metadata_json or {}).get("repository_context", {})
        exec_ctx = TaskExecutionContext(
            agent_run_id=run.id,
            plan_id=plan.plan_id,
            task_id=task_id,
            repository_id=run.repository_id,
            worktree_path=run.worktree_path,
            task_definition=next_task,
            repository_context_summary=repo_ctx,
            execution_config=(run.metadata_json or {}).get("config", {}),
        )

        # 2. Execute task via TaskExecutor boundary
        exec_result = self.task_orchestrator.executor.execute(exec_ctx)
        self.task_orchestrator.complete_task_execution(plan, task_id, exec_result)

        if exec_result.success:
            self.events.emit_event(
                db,
                run,
                AgentEventType.TASK_EXECUTION_COMPLETED,
                f"Task '{task_id}' execution completed in {exec_result.duration_ms:.1f}ms: {exec_result.summary}",
                {"task_id": task_id, "duration_ms": exec_result.duration_ms, "changed_files": exec_result.changed_files},
            )

            # 3. Verification Handoff
            self.events.emit_event(
                db,
                run,
                AgentEventType.TASK_VERIFYING,
                f"Verifying task '{task_id}' criteria ({next_task.verification_strategy})...",
                {"task_id": task_id, "verification_strategy": next_task.verification_strategy},
            )
            passed, v_err = self.task_orchestrator.verifier.verify_task(exec_ctx, exec_result)
            self.task_orchestrator.record_verification_result(plan, task_id, passed, v_err)

            if passed:
                self.events.emit_event(
                    db,
                    run,
                    AgentEventType.TASK_PASSED,
                    f"Task '{task_id}' passed verification criteria.",
                    {"task_id": task_id},
                )
            else:
                self.events.emit_event(
                    db,
                    run,
                    AgentEventType.TASK_FAILED,
                    f"Task '{task_id}' failed verification: {v_err}",
                    {"task_id": task_id, "failure_reason": v_err},
                )
        else:
            self.events.emit_event(
                db,
                run,
                AgentEventType.TASK_EXECUTION_FAILED,
                f"Task '{task_id}' execution failed: {exec_result.error}",
                {"task_id": task_id, "error": exec_result.error},
            )
            self.events.emit_event(
                db,
                run,
                AgentEventType.TASK_FAILED,
                f"Task '{task_id}' failed: {exec_result.error}",
                {"task_id": task_id, "failure_reason": exec_result.error},
            )

        # Emit events for any newly blocked or ready tasks
        for t in plan.tasks:
            if t.task_id != task_id:
                if t.status == PlanTaskStatus.BLOCKED and not t.metadata.get("blocked_event_emitted"):
                    t.metadata["blocked_event_emitted"] = True
                    self.events.emit_event(
                        db,
                        run,
                        AgentEventType.TASK_BLOCKED,
                        f"Task '{t.task_id}' is BLOCKED: {t.blocked_reason}",
                        {"task_id": t.task_id, "blocked_reason": t.blocked_reason},
                    )
                elif t.status == PlanTaskStatus.READY and not t.metadata.get("ready_event_emitted"):
                    t.metadata["ready_event_emitted"] = True
                    self.events.emit_event(
                        db,
                        run,
                        AgentEventType.TASK_READY,
                        f"Task '{t.task_id}' ('{t.title}') is now READY.",
                        {"task_id": t.task_id},
                    )

        # Persist updated plan
        from sqlalchemy.orm.attributes import flag_modified
        meta = run.metadata_json or {}
        meta["plan"] = plan.model_dump(mode="json")
        run.metadata_json = meta
        flag_modified(run, "metadata_json")
        db.add(run)
        db.commit()

        if self.task_orchestrator.all_tasks_passed(plan):
            logger.info(f"All {len(plan.tasks)} tasks in plan '{plan.plan_id}' passed! Ready for Phase 7 final verification.")

        return self.task_orchestrator._find_task(plan, task_id), exec_result

    def recover_in_flight_runs(self, db: Session) -> List[str]:
        """
        Restart recovery: Detects non-terminal runs interrupted by a server reboot
        and transitions them safely to FAILED with explicit failure reason,
        preventing orphaned or false-positive active states.
        Preserves truthful task states by marking active in-flight tasks as BLOCKED/FAILED.
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
            
            # Inspect plan tasks and mark any RUNNING / VERIFYING task as BLOCKED
            meta = run.metadata_json or {}
            plan_dict = meta.get("plan")
            if plan_dict and isinstance(plan_dict, dict):
                try:
                    plan = Plan.model_validate(plan_dict)
                    for t in plan.tasks:
                        if t.status in (PlanTaskStatus.RUNNING, PlanTaskStatus.VERIFYING):
                            t.status = PlanTaskStatus.BLOCKED
                            t.blocked_reason = "Server restart interrupted active task execution"
                            t.completed_at = datetime.now(timezone.utc)
                    meta["plan"] = plan.model_dump(mode="json")
                    run.metadata_json = meta
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(run, "metadata_json")
                except Exception as err:
                    logger.warning(f"Recovery: failed to update plan tasks for run '{run.id}': {err}")

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




