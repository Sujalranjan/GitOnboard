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
                executor = EngineeringAgentTaskExecutor(loop=None, agent_loop=None)

            task_orchestrator = TaskOrchestrator(executor=executor)

        self.task_orchestrator = task_orchestrator
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
        worktree_path: Optional[str] = None,
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
        """
        Revises an existing implementation plan based on user review comments.
        Incorporates feedback into the run requirement, creates an incremented plan version,
        and returns the newly synthesized plan in AWAITING_APPROVAL state.
        """
        run = self.get_run(db, run_id)
        if self.state_machine.is_terminal(run.current_state):
            raise EngineeringAgentError(
                f"Cannot revise plan on run '{run_id}' in terminal state '{run.current_state.value}'"
            )

        from sqlalchemy.orm.attributes import flag_modified
        current_req = run.user_requirement or ""
        run.user_requirement = f"{current_req}\n\n[Review Feedback / Revision]: {feedback.strip()}"
        flag_modified(run, "user_requirement")
        db.add(run)
        db.commit()
        db.refresh(run)

        return self.create_plan(db, run_id, budget=budget, force_replan=True)

    def create_plan(
        self,
        db: Session,
        run_id: str,
        budget: Optional[ContextBudget] = None,
        force_replan: bool = False,
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
        if not force_replan and run.current_state == AgentState.AWAITING_APPROVAL and existing_plan and (existing_plan.validation and existing_plan.validation.valid):
            existing_app = db.query(ApprovalRequest).filter(
                ApprovalRequest.agent_run_id == run.id,
                ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
                ApprovalRequest.status.in_([ApprovalStatus.PENDING, ApprovalStatus.APPROVED]),
            ).first()
            if existing_app:
                logger.info(f"Plan and ApprovalRequest already active for run '{run_id}' in AWAITING_APPROVAL. Returning existing plan.")
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

            # Capture repository revision at plan synthesis time
            repo_revision = self.get_repository_revision(run.repository_id, run.worktree_path)

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
                repository_revision=repo_revision,
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

                # Persist plan to history table for long-term audit trail
                try:
                    from backend.models.implementation import AgentRunPlanHistory, AgentRunPlanHistoryStatus

                    # Create new history record for this plan FIRST (before updating previous plans)
                    # This avoids FK constraint violations on the self-referential FK
                    plan_history = AgentRunPlanHistory(
                        agent_run_id=run.id,
                        plan_id=plan.plan_id,
                        version=plan.version,
                        status=AgentRunPlanHistoryStatus.READY_FOR_APPROVAL,
                        plan_json=plan.model_dump(mode="json"),
                    )
                    db.add(plan_history)
                    db.commit()

                    # Now mark previous plan versions as SUPERSEDED (after new plan exists)
                    prev_plans = db.query(AgentRunPlanHistory).filter(
                        AgentRunPlanHistory.agent_run_id == run.id,
                        AgentRunPlanHistory.version < plan.version,
                    ).all()
                    for prev_plan in prev_plans:
                        if prev_plan.status != AgentRunPlanHistoryStatus.SUPERSEDED:
                            prev_plan.status = AgentRunPlanHistoryStatus.SUPERSEDED
                            prev_plan.superseded_at = plan.updated_at
                            prev_plan.superseded_by_plan_id = plan.plan_id
                            db.add(prev_plan)
                    db.commit()
                except Exception as err:
                    logger.warning(f"Failed to persist plan to history table for run '{run_id}': {err}")
                    # Don't fail plan creation if history persistence fails

                # Invalidate any previous approvals (PENDING or APPROVED) for older plan revisions
                prev_approvals = db.query(ApprovalRequest).filter(
                    ApprovalRequest.agent_run_id == run.id,
                    ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
                    ApprovalRequest.status.in_([ApprovalStatus.PENDING, ApprovalStatus.APPROVED]),
                ).all()
                for pa in prev_approvals:
                    pa.status = ApprovalStatus.EXPIRED
                    db.add(pa)
                db.commit()

                # CRITICAL STATE INVARIANT FIX:
                # Transition run to AWAITING_APPROVAL AFTER all plan prerequisites are persisted.
                # This ensures the invariant: Plan.status == READY_FOR_APPROVAL AND Run.state == AWAITING_APPROVAL
                # The approval endpoint (/plan/approve) requires this state to proceed.
                db.refresh(run)
                if run.current_state == AgentState.PLANNING:
                    self.transition_state(
                        db,
                        run.id,
                        to_state=AgentState.AWAITING_APPROVAL,
                        reason=f"Plan v{plan.version} created and validated with {len(plan.tasks)} tasks; awaiting user review",
                    )
                elif run.current_state != AgentState.AWAITING_APPROVAL:
                    logger.warning(f"Run '{run_id}' in unexpected state {run.current_state.value} during plan validation; expected PLANNING or AWAITING_APPROVAL")

                # Create plan-specific ApprovalRequest bound to exact plan_id, version, and repository revision
                aff_files = [
                    a.get("file") if isinstance(a, dict) else getattr(a, "file", str(a))
                    for a in (plan.affected_areas or [])
                ]
                self.approval_controller.create_approval_request(
                    db=db,
                    agent_run_id=run.id,
                    action_type=ApprovalActionType.PLAN_APPROVAL,
                    action_description=f"Approve implementation plan v{plan.version} ({plan.plan_id}) with {len(plan.tasks)} tasks",
                    risk_level=RiskLevel.HIGH,
                    requested_operation={
                        "plan_id": plan.plan_id,
                        "version": plan.version,
                        "repository_id": run.repository_id or "default",
                        "repository_revision": plan.repository_revision,
                        "task_count": len(plan.tasks),
                    },
                    affected_files=aff_files,
                    reason=f"Human authorization required for plan v{plan.version} ({plan.requirement[:60]})",
                    metadata={"plan_id": plan.plan_id, "version": plan.version, "repository_revision": plan.repository_revision},
                    run_model=run,
                )
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

    def assert_execution_authorized(
        self,
        db: Session,
        run_id: str,
        plan_id: Optional[str] = None,
        plan_version: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> None:
        """
        Server-side central execution authorization gate.
        Enforces:
          1. Requester ownership: If user_id is provided, verifies user owns the run.
          2. Run state: Run exists and is in a valid execution state (AWAITING_APPROVAL or EXECUTING).
          3. Plan validation: Plan exists, is marked APPROVED, and has valid validation result.
          4. Persisted approval: A persisted ApprovalRequest with status == APPROVED exists for this run and plan identity.
          5. Plan identity & version matching: Plan ID and Version match between approval and active plan (prevents stale approval).
          6. Repository revision binding: Approved repository revision matches current repository revision.
        Raises EngineeringAgentError if any authorization condition fails.
        """
        run = self.get_run(db, run_id)
        if user_id is not None and run.user_id is not None and run.user_id != user_id:
            raise EngineeringAgentError(f"Execution not authorized: User '{user_id}' does not own run '{run_id}'")

        if run.current_state not in (AgentState.AWAITING_APPROVAL, AgentState.EXECUTING):
            raise EngineeringAgentError(
                f"Execution not authorized: Run '{run_id}' is in state '{run.current_state.value}', expected EXECUTING or AWAITING_APPROVAL"
            )

        plan = self.get_plan(db, run_id)
        if not plan:
            raise EngineeringAgentError(f"Execution not authorized: No plan found for run '{run_id}'")

        if plan.status != PlanStatus.APPROVED:
            raise EngineeringAgentError(
                f"Execution not authorized: Plan '{plan.plan_id}' has status '{plan.status.value}', expected APPROVED"
            )

        if not plan.validation or not plan.validation.valid:
            raise EngineeringAgentError(f"Execution not authorized: Plan '{plan.plan_id}' failed validation")

        approval = (
            db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.agent_run_id == run_id,
                ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
                ApprovalRequest.status == ApprovalStatus.APPROVED,
            )
            .order_by(ApprovalRequest.resolved_at.desc(), ApprovalRequest.requested_at.desc())
            .first()
        )

        if not approval:
            raise EngineeringAgentError(
                f"Execution not authorized: No valid APPROVED ApprovalRequest found in database for run '{run_id}'"
            )

        op = approval.requested_operation or {}
        approved_plan_id = op.get("plan_id")
        approved_version = op.get("version")

        if approved_plan_id and approved_plan_id != plan.plan_id:
            raise EngineeringAgentError(
                f"Execution not authorized: Approval plan ID mismatch (approved '{approved_plan_id}' != active '{plan.plan_id}')"
            )

        if approved_version is not None and approved_version != plan.version:
            raise EngineeringAgentError(
                f"Execution not authorized: Approval plan version mismatch (approved v{approved_version} != active v{plan.version})"
            )

        if plan_id and plan_id != plan.plan_id:
            raise EngineeringAgentError(
                f"Execution not authorized: Target plan ID mismatch ('{plan_id}' != active '{plan.plan_id}')"
            )

        if plan_version is not None and plan_version != plan.version:
            raise EngineeringAgentError(
                f"Execution not authorized: Target plan version mismatch (v{plan_version} != active v{plan.version})"
            )

        # Enforce repository revision binding
        approved_revision = op.get("repository_revision") or getattr(plan, "repository_revision", None)
        current_revision = self.get_repository_revision(run.repository_id, run.worktree_path)
        if approved_revision and current_revision and approved_revision != current_revision:
            raise EngineeringAgentError(
                f"Execution not authorized: Repository revision mismatch (approved '{approved_revision}' != current '{current_revision}')"
            )

    def approve_plan(
        self,
        db: Session,
        run_id: str,
        resolved_by: str = "human_user",
        user_id: Optional[int] = None,
    ) -> AgentRun:
        """
        Explicitly approves the synthesized plan.
        CRITICAL INVARIANT: Approval does NOT execute tasks (PLAN_APPROVED != TASK_EXECUTION_STARTED).
        Run remains in AWAITING_APPROVAL state until Phase 5 TaskOrchestrator initiates execution.
        Safe & Idempotent: Repeated approval requests on already approved/executing runs return without duplicate execution.
        """
        run = self.get_run(db, run_id)
        if user_id is not None and run.user_id is not None and run.user_id != user_id:
            raise EngineeringAgentError(f"Approval not authorized: User '{user_id}' does not own run '{run_id}'")

        if run.current_state == AgentState.EXECUTING:
            logger.info(f"Run '{run_id}' is already in EXECUTING state. Returning current state idempotently.")
            return run

        if run.current_state != AgentState.AWAITING_APPROVAL:
            raise EngineeringAgentError(
                f"Cannot approve plan for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.AWAITING_APPROVAL.value}' state."
            )

        plan = self.get_plan(db, run_id)
        if not plan:
            raise EngineeringAgentError(f"No plan found to approve for run '{run_id}'")

        if plan.status == PlanStatus.APPROVED:
            logger.info(f"Plan '{plan.plan_id}' is already APPROVED for run '{run_id}'. Returning current state idempotently.")
            return run

        if plan.status != PlanStatus.READY_FOR_APPROVAL:
            raise EngineeringAgentError(
                f"Plan '{plan.plan_id}' is in status '{plan.status.value}'. Only plans in READY_FOR_APPROVAL can be approved."
            )

        # Mark plan as approved with audit trail
        from sqlalchemy.orm.attributes import flag_modified
        now = datetime.now(timezone.utc)
        plan.status = PlanStatus.APPROVED
        plan.resolved_by = resolved_by
        plan.resolved_at = now
        plan.updated_at = now

        meta = run.metadata_json or {}
        meta["plan"] = plan.model_dump(mode="json")
        run.metadata_json = meta
        flag_modified(run, "metadata_json")
        db.add(run)
        db.commit()

        # Update plan history record to mark as APPROVED
        try:
            from backend.models.implementation import AgentRunPlanHistory, AgentRunPlanHistoryStatus
            plan_history = db.query(AgentRunPlanHistory).filter(
                AgentRunPlanHistory.plan_id == plan.plan_id
            ).first()
            if plan_history:
                plan_history.status = AgentRunPlanHistoryStatus.APPROVED
                plan_history.resolved_by = resolved_by
                plan_history.resolved_at = now
                db.add(plan_history)
                db.commit()
        except Exception as err:
            logger.warning(f"Failed to update plan history for approval of plan '{plan.plan_id}': {err}")

        # Resolve pending ApprovalRequest
        pending_approvals = self.approval_controller.get_pending_approvals(db, agent_run_id=run.id)
        plan_approval = next((a for a in pending_approvals if a.action_type == ApprovalActionType.PLAN_APPROVAL), None)
        if plan_approval:
            self.approval_controller.approve_request(db, approval_id=plan_approval.id, resolved_by=resolved_by, run_model=run)
        else:
            app_req = db.query(ApprovalRequest).filter(
                ApprovalRequest.agent_run_id == run_id,
                ApprovalRequest.action_type == ApprovalActionType.PLAN_APPROVAL,
            ).order_by(ApprovalRequest.requested_at.desc()).first()
            if app_req and app_req.status == ApprovalStatus.PENDING:
                self.approval_controller.approve_request(db, approval_id=app_req.id, resolved_by=resolved_by, run_model=run)
            elif not app_req:
                created_req = self.approval_controller.request_approval(
                    db,
                    agent_run_id=run.id,
                    action_type=ApprovalActionType.PLAN_APPROVAL,
                    description=f"Approve implementation plan v{plan.version} ({plan.plan_id}) with {len(plan.tasks)} tasks",
                    requested_operation={
                        "plan_id": plan.plan_id,
                        "version": plan.version,
                        "task_count": len(plan.tasks),
                        "repository_revision": plan.repository_revision,
                    },
                    risk_level=RiskLevel.HIGH,
                    run_model=run,
                )
                self.approval_controller.approve_request(db, approval_id=created_req.id, resolved_by=resolved_by, run_model=run)

        # Emit PLAN_APPROVED event
        self.events.emit_event(
            db,
            run,
            AgentEventType.PLAN_APPROVED,
            f"Plan v{plan.version} ('{plan.plan_id}') approved by {resolved_by}. Ready for task orchestration.",
            {
                "plan_id": plan.plan_id,
                "version": plan.version,
                "task_count": len(plan.tasks),
                "resolved_by": resolved_by,
            },
        )

        return run

    def reject_plan(
        self,
        db: Session,
        run_id: str,
        reason: Optional[str] = None,
        resolved_by: str = "human_user",
        user_id: Optional[int] = None,
    ) -> AgentRun:
        """
        Explicitly rejects the synthesized plan.
        CRITICAL INVARIANT: Rejection NEVER triggers task implementation.
        Transitions the run state to CANCELLED (terminal non-executing state).
        Safe & Idempotent: Repeated rejections on CANCELLED runs return current state without error.
        """
        run = self.get_run(db, run_id)
        if user_id is not None and run.user_id is not None and run.user_id != user_id:
            raise EngineeringAgentError(f"Rejection not authorized: User '{user_id}' does not own run '{run_id}'")

        if run.current_state == AgentState.CANCELLED:
            logger.info(f"Run '{run_id}' is already CANCELLED. Returning current state idempotently.")
            return run

        if run.current_state != AgentState.AWAITING_APPROVAL:
            raise EngineeringAgentError(
                f"Cannot reject plan for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.AWAITING_APPROVAL.value}' state."
            )

        plan = self.get_plan(db, run_id)
        if plan:
            from sqlalchemy.orm.attributes import flag_modified
            now = datetime.now(timezone.utc)
            plan.status = PlanStatus.REJECTED
            plan.resolved_by = resolved_by
            plan.resolved_at = now
            plan.rejection_reason = reason
            plan.updated_at = now
            meta = run.metadata_json or {}
            meta["plan"] = plan.model_dump(mode="json")
            run.metadata_json = meta
            flag_modified(run, "metadata_json")
            db.add(run)
            db.commit()

            # Update plan history record to mark as REJECTED
            try:
                from backend.models.implementation import AgentRunPlanHistory, AgentRunPlanHistoryStatus
                plan_history = db.query(AgentRunPlanHistory).filter(
                    AgentRunPlanHistory.plan_id == plan.plan_id
                ).first()
                if plan_history:
                    plan_history.status = AgentRunPlanHistoryStatus.REJECTED
                    plan_history.resolved_by = resolved_by
                    plan_history.resolved_at = now
                    plan_history.rejection_reason = reason
                    db.add(plan_history)
                    db.commit()
            except Exception as err:
                logger.warning(f"Failed to update plan history for rejection of plan '{plan.plan_id}': {err}")

        reject_msg = reason or "Plan rejected by user."

        # Resolve pending ApprovalRequest as REJECTED
        pending_approvals = self.approval_controller.get_pending_approvals(db, agent_run_id=run.id)
        for pa in pending_approvals:
            if pa.action_type == ApprovalActionType.PLAN_APPROVAL:
                self.approval_controller.reject_request(
                    db, approval_id=pa.id, reason=reject_msg, resolved_by=resolved_by, run_model=run
                )

        # Emit PLAN_REJECTED event
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

        # Transition state to CANCELLED (terminal non-executing state)
        self.transition_state(
            db,
            run.id,
            to_state=AgentState.CANCELLED,
            reason=f"Plan rejected: {reject_msg}",
        )

        return run

    def start_plan_execution(
        self,
        db: Session,
        run_id: str,
        user_id: Optional[int] = None,
    ) -> AgentRun:
        """
        Initiates controlled execution of an approved implementation plan.
        Strict preconditions:
          - AgentRun.current_state == AgentState.AWAITING_APPROVAL (or already EXECUTING idempotently)
          - Plan.status == PlanStatus.APPROVED
          - Plan.validation.valid is True
          - A persisted APPROVED ApprovalRequest exists matching active plan
          - Repository revision matches approved plan revision
        Transitions run state from AWAITING_APPROVAL -> EXECUTING and marks initial eligible tasks READY.
        """
        run = self.get_run(db, run_id)
        if user_id is not None and run.user_id is not None and run.user_id != user_id:
            raise EngineeringAgentError(f"Execution not authorized: User '{user_id}' does not own run '{run_id}'")

        if run.current_state == AgentState.EXECUTING:
            logger.info(f"Run '{run_id}' is already in EXECUTING state. Returning current state idempotently.")
            return run

        if run.current_state != AgentState.AWAITING_APPROVAL:
            raise EngineeringAgentError(
                f"Cannot start execution for run '{run_id}' in state '{run.current_state.value}'. "
                f"Run must be in '{AgentState.AWAITING_APPROVAL.value}' state."
            )

        # Enforce server-side execution authorization gate
        self.assert_execution_authorized(db, run_id, user_id=user_id)

        plan = self.get_plan(db, run_id)
        if not plan:
            raise EngineeringAgentError(f"No plan found for run '{run_id}'")

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

        # Enforce server-side execution authorization gate
        self.assert_execution_authorized(db, run_id)

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

    def complete_run(
        self,
        db: Session,
        run_id: str,
        success: bool = True,
        failure_reason: Optional[str] = None,
    ) -> AgentRun:
        """
        Marks a run as COMPLETED or FAILED after all tasks have been executed and verified.
        """
        run = self.get_run(db, run_id)

        if run.current_state not in (AgentState.EXECUTING, AgentState.VERIFYING):
            logger.warning(f"Run '{run_id}' is in state {run.current_state.value}, expected EXECUTING or VERIFYING")
            return run

        target_state = AgentState.COMPLETED if success else AgentState.FAILED
        reason = failure_reason or "All tasks completed" if success else "Task execution or verification failed"

        self.transition_state(db, run_id, target_state, reason)

        if not success:
            self.events.emit_event(
                db,
                run,
                AgentEventType.RUN_FAILED,
                f"Run failed: {failure_reason or 'One or more tasks failed'}",
                {"failure_reason": failure_reason},
            )
        else:
            self.events.emit_event(
                db,
                run,
                AgentEventType.RUN_COMPLETED,
                f"Run completed successfully with all tasks passed",
                {},
            )

        return run

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




