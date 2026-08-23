"""
Manual Verification Script: Comprehensive End-to-End Test for Phases 1 through 9.

This script executes and logs every stage of the Engineering Agent lifecycle:
  1. AgentRun Creation & Lifecycle State (Phase 1)
  2. Repository Context Assembly (Phase 3: Requirement Analysis, Hybrid Retrieval, RIM, Budget, Understanding Contract)
  3. Planning Orchestration & Validation (Phase 4: Plan, PlanTask DAG, PlanValidator -> AWAITING_APPROVAL)
  4. Human Plan Rejection & Revision (Phase 4: Plan v1 -> Plan v2 revision)
  5. Explicit Human Approval Boundary (Phase 4: Plan v2 APPROVED; Invariant: Zero execution during approval!)
  6. Start Plan Execution (Phase 5: AWAITING_APPROVAL -> EXECUTING, unlock initial tasks to READY)
  7. Sequential Task Orchestration via EngineeringAgentTaskExecutor (Phase 5 + Phase 6: Loop -> COMPLETED_FOR_VERIFICATION)
  8. Phase 6: Direct EngineeringAgentLoop Multi-Turn Execution (Tool Proposal -> Observation -> Completion Protocol)
  9. Phase 6: Repetition Loop Detector Guardrail (3 identical calls -> REPEATED_TOOL_CALL_LIMIT)
  10. Phase 6: Protocol Guardrail (Plain 'Done' Rejection -> Malformed feedback)
  11. Phase 7: VerificationDispatcher Multi-Vector Mesh (Static -> Dynamic -> Contract -> Judge -> Evidence-backed PASS)
  12. Phase 7: Defect Extraction & Failure Normalization (Failure -> Structured VerificationDefects for Phase 8)
  13. Phase 8: Failure Diagnosis, Context Assembly, Agentic Repair & Re-Verification Loop (Diagnosis -> Repair -> Reverify PASS)
  14. Phase 8: Bounded Repair Attempt Limit & BLOCKED Transition on Unresolvable Defect (Exhausts limit -> BLOCKED)
  15. Phase 9: Context-Aware ExecutionPolicy (Allowed inspection vs Blocked destructive commands vs Approval-required operations)
  16. Phase 9: Human Action Approval Request & Resolution (Create approval -> Pause -> User approves -> Resume)
  17. Phase 9: Human Action Rejection & Agent Observation Feedback (User rejects -> Structured observation returned)
  18. Phase 9: Safe Cancellation Controller (Explicit human stop -> Safe interruption across all subsystems -> CANCELLED)
  19. Repository Tools (read_file with bounded lines)
  20. Workspace Isolated File & Patch Tools (create_file, modify_file, get_diff)
  21. Terminal Tools (detect_commands via sandbox)
  22. Verification Mesh Tools (verify_static AST integrity)
  23. Git Tools (create_checkpoint, git_status)
  24. Tool Policy Safety Enforcement (BLOCKED policy blocks handler execution)
  25. Database Event Audit & History (AgentEvent log inspection including Phases 6-9 events)
  26. Terminal State Locking (COMPLETED state locks execution)

Run via uv:
  uv run python scripts/manual_test_flow.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agent.engineering_agent import EngineeringAgent, EngineeringAgentError
from backend.agent.loop import (
    AgentExecutionResult,
    AgentLoopConfig,
    CompletionSignal,
    CriterionEvaluation,
    EngineeringAgentLoop,
    LoopGuardrails,
    ModelAdapter,
    StopReason,
)
from backend.agent.planning.contracts import PlanStatus, PlanTask, PlanTaskStatus
from backend.agent.repair import (
    Defect,
    DiagnosisCategory,
    DiagnosisContext,
    FailureCategory,
    FailureDiagnosisController,
    RepairAttempt,
    RepairAttemptTracker,
    RepairConfig,
    RepairController,
    RepairResult,
    RepairStatus,
)
from backend.agent.safety import (
    AgentSafetyConfig,
    ApprovalActionType,
    ApprovalController,
    ApprovalStatus,
    CancellationController,
    CancellationToken,
    ExecutionPolicy,
    PolicyAction,
    PolicyDecision,
    RiskLevel,
)
from backend.agent.tasks import (
    DefaultVerificationDispatcher,
    EngineeringAgentTaskExecutor,
    TaskExecutionContext,
    TaskExecutionResult,
    TaskOrchestrator,
)
from backend.agent.tools.contracts import AgentToolContext, ToolErrorCode
from backend.agent.tools import create_default_tool_registry
from backend.agent.verification import (
    DefectCategory,
    DefectSeverity,
    VerificationCheck,
    VerificationDefect,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
    VerificationStrategy,
    VerificationType,
    VerificationDispatcher,
)
from backend.database import Base, SessionLocal, engine
from backend.models.implementation import (
    AgentEvent,
    AgentEventType,
    AgentRun,
    AgentState,
    ApprovalRequest,
    PolicyDecisionRecord,
)


class MockScriptModelAdapter(ModelAdapter):
    """Mock model adapter returning scripted JSON proposals for automated walkthrough."""

    def __init__(self, responses: List[str]):
        super().__init__()
        self.responses = list(responses)
        self.call_idx = 0

    async def call_model(self, messages) -> str:
        if self.call_idx < len(self.responses):
            resp = self.responses[self.call_idx]
            self.call_idx += 1
            return resp
        return json.dumps({
            "action": "complete",
            "summary": "Completed fallback implementation",
            "acceptance_criteria_status": [
                {
                    "criterion": "Default criterion",
                    "status": "satisfied",
                    "evidence": "Verified in sandbox worktree",
                }
            ],
            "verification_requested": True,
        })


def print_banner(text: str):
    line = "=" * 80
    print(f"\n{line}\n  {text}\n{line}")


def print_step_header(num: int, title: str):
    print(f"\n{'-'*80}")
    print(f" [STEP {num:02d}] {title}")
    print(f"{'-'*80}")


def print_kv(key: str, value: any, indent: int = 4):
    prefix = " " * indent
    if isinstance(value, (dict, list)):
        formatted = json.dumps(value, indent=indent + 4)
        print(f"{prefix}* {key}:\n{formatted}")
    else:
        print(f"{prefix}* {key:<30}: {value}")


def main():
    print_banner(
        "GITONBOARD ENGINEERING AGENT -- COMPLETE SYSTEM VERIFICATION\n"
        "  COVERS: PHASES 1 (LIFECYCLE), 2 (TOOLS), 3 (CONTEXT), 4 (PLANNING), 5 (ORCHESTRATOR),\n"
        "          PHASE 6 (LOOP), PHASE 7 (VERIFICATION), PHASE 8 (REPAIR), PHASE 9 (SAFETY & APPROVAL)"
    )

    # 0. Initialize Database
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    with tempfile.TemporaryDirectory() as tmpdir:
        wt_path = Path(tmpdir).resolve()
        
        # Initialize a temporary git sandbox worktree
        subprocess.run(["git", "init"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Verification Agent"], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "agent@gitonboard.local"], cwd=wt_path, capture_output=True, check=True)
        
        sample_file = wt_path / "main.py"
        sample_file.write_text("def run_app():\n    '''Main entrypoint'''\n    print('GitOnBoard App Running')\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=wt_path, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial test commit"], cwd=wt_path, capture_output=True, check=True)

        print_kv("Sandbox Worktree Root", str(wt_path))

        # 1. Initialize Agent and Create Run (Phase 1)
        print_step_header(1, "Initialize EngineeringAgent & Create AgentRun (Phase 1)")
        agent = EngineeringAgent()
        run = agent.create_run(
            db=db,
            repository_id="manual-test-repo",
            user_requirement="Add authentication validation and calculator utilities to repository",
        )
        run.worktree_path = str(wt_path)
        db.add(run)
        db.commit()

        print_kv("Agent Run ID", run.id)
        print_kv("Repository ID", run.repository_id)
        print_kv("User Requirement", run.user_requirement)
        print_kv("Initial Lifecycle State", run.current_state.value)
        print_kv("Legacy Status Mapping", run.status.value)
        assert run.current_state == AgentState.UNDERSTANDING

        # 2. Context Assembly (Phase 3)
        print_step_header(2, "Repository Context Assembly (Phase 3: ContextAssembler)")
        ctx = agent.assemble_repository_context(db, run_id=run.id)
        
        print_kv("Context Schema Version", ctx.version)
        print_kv("Understanding Contract Status", ctx.contract.completeness.value)
        print_kv("Contract Explanation", ctx.contract.explanation)
        print_kv("Satisfied Categories", ctx.contract.satisfied_categories)
        print_kv("Missing Categories", ctx.contract.missing_categories)
        print_kv("Explicit Unknowns", ctx.unknowns)
        print_kv("Total Evidence Items Gathered", len(ctx.evidence))
        for idx, ev in enumerate(ctx.evidence, 1):
            print(f"      [{idx}] source='{ev.source_type}' id='{ev.source_id}' relevance={ev.relevance:.2f} -> {ev.summary}")
        
        print_kv("Bounded Summary in metadata_json", run.metadata_json.get("repository_context"))
        assert len(ctx.evidence) > 0

        # 3. Planning Orchestration & Plan Validation (Phase 4)
        print_step_header(3, "Planning Orchestration & Plan Validation (Phase 4: PlanningOrchestrator)")
        plan_v1 = agent.create_plan(db, run_id=run.id)
        
        print_kv("Plan ID", plan_v1.plan_id)
        print_kv("Plan Version", plan_v1.version)
        print_kv("Plan Status", plan_v1.status.value)
        print_kv("Plan Valid", plan_v1.validation.valid if plan_v1.validation else False)
        print_kv("Task Count", len(plan_v1.tasks))
        for idx, t in enumerate(plan_v1.tasks, 1):
            print(f"      [{idx}] {t.task_id}: '{t.title}' -> deps={t.dependencies}, verif='{t.verification_strategy}'")
        
        print_kv("Post-Planning Run State", run.current_state.value)
        assert run.current_state == AgentState.AWAITING_APPROVAL
        assert plan_v1.status == PlanStatus.READY_FOR_APPROVAL

        # 4. Human Review Boundary: Plan Rejection & Revision (Phase 4)
        print_step_header(4, "Human Review Boundary: Plan Rejection & Revision (Phase 4)")
        agent.reject_plan(db, run_id=run.id, reason="Please refine calculator task acceptance criteria")
        print_kv("Post-Rejection Run State", run.current_state.value)
        assert run.current_state == AgentState.PLANNING

        # Create revised Plan v2
        plan_v2 = agent.create_plan(db, run_id=run.id)
        print_kv("Revised Plan ID", plan_v2.plan_id)
        print_kv("Revised Plan Version", plan_v2.version)
        print_kv("Revised Plan Status", plan_v2.status.value)
        print_kv("Post-Revision Run State", run.current_state.value)
        assert plan_v2.version == 2
        assert run.current_state == AgentState.AWAITING_APPROVAL

        # 5. Explicit Human Approval Boundary (Phase 4)
        print_step_header(5, "Explicit Human Approval Boundary (Phase 4)")
        agent.approve_plan(db, run_id=run.id)
        approved_plan = agent.get_plan(db, run_id=run.id)
        print_kv("Approved Plan Status", approved_plan.status.value)
        print_kv("Run State Post-Approval", run.current_state.value)
        assert approved_plan.status == PlanStatus.APPROVED
        assert run.current_state == AgentState.AWAITING_APPROVAL

        # CRITICAL SAFETY INVARIANT: Verify no workspace modification occurred during planning/approval
        git_check = subprocess.run(["git", "status", "--porcelain"], cwd=wt_path, capture_output=True, text=True)
        assert git_check.stdout.strip() == ""
        print_kv("Non-Execution Invariant", "PASSED -> Git working tree is 100% clean. Zero code executed during planning/approval.")

        # 6. Start Plan Execution (Phase 5: TaskOrchestrator Initiation)
        print_step_header(6, "Start Plan Execution (Phase 5: AWAITING_APPROVAL -> EXECUTING)")
        agent.start_plan_execution(db, run_id=run.id)
        print_kv("Current State", run.current_state.value)
        assert run.current_state == AgentState.EXECUTING

        # 7. Sequential Task Orchestration & Execution via TaskExecutor (Phase 5)
        print_step_header(7, "Sequential Task Orchestration & Execution (Phase 5)")
        tasks = agent.get_plan_tasks(db, run_id=run.id)
        print_kv("Total Tasks to Orchestrate", len(tasks))
        
        executed_tasks = []
        while True:
            next_task = agent.get_next_task(db, run_id=run.id)
            if not next_task:
                print("      * No more tasks ready for execution (DAG complete).")
                break
            
            print(f"\n      --> Executing eligible task: [{next_task.task_id}] '{next_task.title}' (step {next_task.step_number})")
            task_result, exec_result = agent.execute_next_task(db, run_id=run.id)
            print_kv("Task Execution Status", task_result.status.value, indent=10)
            print_kv("Execution Summary", exec_result.summary, indent=10)
            print_kv("Elapsed Time", f"{exec_result.duration_ms:.1f} ms", indent=10)
            assert task_result.status == PlanTaskStatus.PASSED
            executed_tasks.append(task_result)

        assert len(executed_tasks) == len(tasks)
        print_kv("All Tasks Passed", "PASSED -> Every task completed through TaskExecutor and VerificationDispatcher.")

        # 8. Phase 6: Direct EngineeringAgentLoop Multi-Turn Execution
        print_step_header(8, "Phase 6: EngineeringAgentLoop Multi-Turn Controlled Execution")
        test_task_def = PlanTask(
            task_id="task-p6-demo",
            step_number=1,
            title="Implement Calculator Module",
            description="Add calculator.py with add/multiply functions and docstrings",
            affected_files=["calculator.py"],
            acceptance_criteria=[
                "calculator.py exists with add() and multiply()",
                "functions include complete docstrings",
            ],
            verification_strategy="verify_static",
        )
        task_exec_ctx = TaskExecutionContext(
            agent_run_id=run.id,
            plan_id=approved_plan.plan_id,
            task_id="task-p6-demo",
            repository_id=run.repository_id,
            worktree_path=str(wt_path),
            task_definition=test_task_def,
        )

        scripted_responses = [
            # Turn 1: Model requests read_file to inspect main.py
            json.dumps({
                "action": "tool_call",
                "tool_name": "read_file",
                "arguments": {"path": "main.py"},
            }),
            # Turn 2: Model requests create_file to write calculator.py
            json.dumps({
                "action": "tool_call",
                "tool_name": "create_file",
                "arguments": {
                    "path": "calculator.py",
                    "content": "def add(a: int, b: int) -> int:\n    '''Adds two integers.'''\n    return a + b\n\ndef multiply(a: int, b: int) -> int:\n    '''Multiplies two integers.'''\n    return a * b\n",
                },
            }),
            # Turn 3: Model requests completion with structured criterion evaluations
            json.dumps({
                "action": "complete",
                "summary": "Implemented calculator.py with typed add and multiply functions and docstrings.",
                "acceptance_criteria_status": [
                    {
                        "criterion": "calculator.py exists with add() and multiply()",
                        "status": "satisfied",
                        "evidence": "Created calculator.py with def add and def multiply",
                    },
                    {
                        "criterion": "functions include complete docstrings",
                        "status": "satisfied",
                        "evidence": "Added triple-quoted docstrings to all functions",
                    },
                ],
                "verification_requested": True,
            }),
        ]

        p6_adapter = MockScriptModelAdapter(scripted_responses)
        p6_loop = EngineeringAgentLoop(
            tool_registry=agent.tools,
            model_adapter=p6_adapter,
            event_coordinator=agent.events,
            config=AgentLoopConfig(max_agent_turns=10),
        )

        p6_result: AgentExecutionResult = p6_loop.run(task_context=task_exec_ctx, db=db, run_model=run)

        print_kv("P6 Loop Status", p6_result.status)
        print_kv("P6 Stop Reason", p6_result.stop_reason.value)
        print_kv("Iterations Completed", p6_result.iterations)
        print_kv("Tool Calls Invoked", p6_result.tool_call_count)
        print_kv("Changed Files", p6_result.changed_files)
        print_kv("Captured Unified Diff", "\n" + (p6_result.diff or "(clean diff)"))
        print_kv("Completion Summary", p6_result.completion_signal.summary if p6_result.completion_signal else None)
        assert p6_result.status == "COMPLETED_FOR_VERIFICATION"
        assert p6_result.stop_reason == StopReason.COMPLETED_FOR_VERIFICATION
        assert len(p6_result.changed_files) > 0
        assert (wt_path / "calculator.py").exists()

        # 9. Phase 6: Repetition Loop Detector Guardrail
        print_step_header(9, "Phase 6: Repetition Loop Detection Guardrail (3-strike limit)")
        repeat_call = json.dumps({
            "action": "tool_call",
            "tool_name": "read_file",
            "arguments": {"path": "main.py"},
        })
        repeat_adapter = MockScriptModelAdapter([repeat_call, repeat_call, repeat_call, repeat_call])
        repeat_loop = EngineeringAgentLoop(
            tool_registry=agent.tools,
            model_adapter=repeat_adapter,
            config=AgentLoopConfig(max_repeated_tool_calls=3, max_agent_turns=10),
        )
        repeat_res = repeat_loop.run(task_context=task_exec_ctx, db=db, run_model=run)
        print_kv("Repetition Test Status", repeat_res.status)
        print_kv("Repetition Stop Reason", repeat_res.stop_reason.value)
        print_kv("Repetition Error", repeat_res.error)
        assert repeat_res.status == "FAILED"
        assert repeat_res.stop_reason == StopReason.REPEATED_TOOL_CALL_LIMIT
        print_kv("Loop Detection Guardrail", "PASSED -> Terminated loop when agent repeated identical call 3 times.")

        # 10. Phase 6: Protocol Guardrail (Plain 'Done' Rejection)
        print_step_header(10, "Phase 6: Protocol Guardrail (Plain 'Done' String Rejection)")
        parsed_done = p6_adapter.parse_response("Done.")
        print_kv("Plain 'Done' Is Malformed", parsed_done.is_malformed)
        print_kv("Parse Error Feedback", parsed_done.parse_error)
        assert parsed_done.is_malformed is True
        print_kv("Protocol Safety Invariant", "PASSED -> Plain string 'Done' rejected as malformed. Structured criteria evidence required.")

        # 11. Phase 7: VerificationDispatcher Multi-Vector Mesh (Static -> Dynamic -> Contract -> Judge)
        print_step_header(11, "Phase 7: VerificationDispatcher Multi-Vector Mesh Execution")
        p7_dispatcher = VerificationDispatcher(event_coordinator=agent.events)
        p7_exec_res = TaskExecutionResult(
            task_id="task-p6-demo",
            success=True,
            summary=p6_result.completion_signal.summary,
            changed_files=p6_result.changed_files,
        )

        p7_verif_result = p7_dispatcher.verify(
            task_context=task_exec_ctx,
            execution_result=p7_exec_res,
            db=db,
            run_model=run,
        )

        print_kv("Phase 7 Verification Verdict", p7_verif_result.status.value)
        print_kv("Phase 7 Passed Property", p7_verif_result.passed)
        print_kv("Checks Evaluated", len(p7_verif_result.checks))
        print_kv("Passed Checks", p7_verif_result.passed_checks)
        print_kv("Evidence Records Persisted", len(p7_verif_result.evidence))
        for idx, ev in enumerate(p7_verif_result.evidence, 1):
            print(f"      [{idx}] check_id='{ev.check_id}' status={ev.status.value} duration={ev.duration_ms:.1f}ms")
        print_kv("Executive Summary", p7_verif_result.summary)
        assert p7_verif_result.passed is True
        assert p7_verif_result.status == VerificationStatus.PASSED
        assert len(p7_verif_result.evidence) > 0

        # 12. Phase 7: Defect Extraction & Failure Normalization (Phase 8 Handoff)
        print_step_header(12, "Phase 7: Defect Extraction & Failure Normalization (Phase 8 Handoff)")
        broken_file = wt_path / "broken.py"
        broken_file.write_text("def broken_syntax(:\n    return False\n", encoding="utf-8")
        
        broken_task_def = PlanTask(
            task_id="task-p7-defect-demo",
            step_number=2,
            title="Broken Syntax Task",
            description="Introduces syntax defect",
            affected_files=["broken.py"],
            verification_strategy="verify_static",
        )
        broken_ctx = TaskExecutionContext(
            agent_run_id=run.id,
            plan_id=approved_plan.plan_id,
            task_id="task-p7-defect-demo",
            repository_id=run.repository_id,
            worktree_path=str(wt_path),
            task_definition=broken_task_def,
        )
        broken_exec_res = TaskExecutionResult(
            task_id="task-p7-defect-demo",
            success=True,
            summary="Attempted implementation",
            changed_files=["broken.py"],
        )

        broken_verif_res = p7_dispatcher.verify(
            task_context=broken_ctx,
            execution_result=broken_exec_res,
            db=db,
            run_model=run,
        )

        print_kv("Broken Task Verdict", broken_verif_res.status.value)
        print_kv("Broken Task Passed", broken_verif_res.passed)
        print_kv("Defects Captured Count", len(broken_verif_res.defects))
        for idx, d in enumerate(broken_verif_res.defects, 1):
            print(f"      [{idx}] type='{d.type}' sev='{d.severity}' file='{d.file}' -> {d.message}")
        
        assert broken_verif_res.passed is False
        assert broken_verif_res.status == VerificationStatus.FAILED
        assert len(broken_verif_res.defects) > 0
        print_kv("Defect Normalization Invariant", "PASSED -> Structured defects extracted without guessing or repair; ready for Phase 8.")

        # 13. Phase 8: Failure Diagnosis, Context Assembly, Agentic Repair & Re-Verification Loop
        print_step_header(13, "Phase 8: Failure Diagnosis, Context Assembly, Agentic Repair & Re-Verification")
        
        repair_script = [
            json.dumps({
                "action": "tool_call",
                "tool_name": "modify_file",
                "arguments": {
                    "path": "broken.py",
                    "content": "def broken_syntax():\n    '''Repaired syntax function'''\n    return True\n",
                },
            }),
            json.dumps({
                "action": "complete",
                "summary": "Fixed invalid syntax in broken.py",
                "acceptance_criteria_status": [
                    {
                        "criterion": "broken.py has valid syntax",
                        "status": "satisfied",
                        "evidence": "Repaired function header syntax",
                    }
                ],
                "verification_requested": True,
            }),
        ]
        p8_adapter = MockScriptModelAdapter(repair_script)
        p8_loop = EngineeringAgentLoop(
            tool_registry=agent.tools,
            model_adapter=p8_adapter,
            event_coordinator=agent.events,
            config=AgentLoopConfig(max_agent_turns=5),
        )
        p8_repair_controller = RepairController(
            agent_loop=p8_loop,
            verification_dispatcher=p7_dispatcher,
            event_coordinator=agent.events,
            config=RepairConfig(max_repair_attempts=3),
        )

        p8_repair_result = p8_repair_controller.repair_task(
            task_context=broken_ctx,
            initial_verification_result=broken_verif_res,
            db=db,
            run_model=run,
        )

        print_kv("Phase 8 Repair Status", p8_repair_result.status.value)
        print_kv("Phase 8 Repaired & Passed", p8_repair_result.passed)
        print_kv("Attempts Utilized", p8_repair_result.attempts_used)
        print_kv("Repaired Changed Files", p8_repair_result.changed_files)
        print_kv("Executive Summary", p8_repair_result.summary)
        assert p8_repair_result.passed is True
        assert p8_repair_result.status == RepairStatus.PASSED
        assert p8_repair_result.attempts_used == 1

        broken_file.unlink()

        # 14. Phase 8: Bounded Repair Attempt Limit & BLOCKED Transition on Unresolvable Defect
        print_step_header(14, "Phase 8: Bounded Repair Attempt Limit & BLOCKED Transition (Safely Halts)")
        unfixable_file = wt_path / "unfixable.py"
        unfixable_file.write_text("def unfixable():\n    syntax error here((\n", encoding="utf-8")

        unfixable_task_def = PlanTask(
            task_id="task-p8-unfixable-demo",
            step_number=3,
            title="Unfixable Task",
            description="Exhausts attempt limit",
            affected_files=["unfixable.py"],
            verification_strategy="verify_static",
        )
        unfixable_ctx = TaskExecutionContext(
            agent_run_id=run.id,
            plan_id=approved_plan.plan_id,
            task_id="task-p8-unfixable-demo",
            repository_id=run.repository_id,
            worktree_path=str(wt_path),
            task_definition=unfixable_task_def,
        )
        unfixable_exec_res = TaskExecutionResult(
            task_id="task-p8-unfixable-demo",
            success=True,
            summary="Attempted unfixable implementation",
            changed_files=["unfixable.py"],
        )
        unfixable_verif_res = p7_dispatcher.verify(
            task_context=unfixable_ctx,
            execution_result=unfixable_exec_res,
            db=db,
            run_model=run,
        )

        stagnant_adapter = MockScriptModelAdapter([
            json.dumps({
                "action": "complete",
                "summary": "Did not fix syntax",
                "acceptance_criteria_status": [{"criterion": "unfixable", "status": "failed", "evidence": "still broken"}],
                "verification_requested": True,
            })
        ])
        stagnant_loop = EngineeringAgentLoop(
            tool_registry=agent.tools,
            model_adapter=stagnant_adapter,
            event_coordinator=agent.events,
            config=AgentLoopConfig(max_agent_turns=5),
        )
        bounded_repair_controller = RepairController(
            agent_loop=stagnant_loop,
            verification_dispatcher=p7_dispatcher,
            event_coordinator=agent.events,
            config=RepairConfig(max_repair_attempts=2),
        )

        blocked_repair_res = bounded_repair_controller.repair_task(
            task_context=unfixable_ctx,
            initial_verification_result=unfixable_verif_res,
            db=db,
            run_model=run,
        )

        print_kv("Bounded Repair Verdict", blocked_repair_res.status.value)
        print_kv("Bounded Repair Passed", blocked_repair_res.passed)
        print_kv("Attempts Utilized", blocked_repair_res.attempts_used)
        print_kv("Stop Reason", blocked_repair_res.stop_reason)
        print_kv("Executive Summary", blocked_repair_res.summary)
        assert blocked_repair_res.passed is False
        assert blocked_repair_res.status == RepairStatus.BLOCKED
        assert blocked_repair_res.attempts_used == 2
        print_kv("Bounded Autonomy Invariant", "PASSED -> Task transitioned to BLOCKED after 2 failed attempts; halted safely without infinite loop.")

        unfixable_file.unlink()

        # 15. Phase 9: Context-Aware ExecutionPolicy Evaluation
        print_step_header(15, "Phase 9: Context-Aware ExecutionPolicy & Worktree Containment")
        exec_policy = ExecutionPolicy()
        tool_ctx = AgentToolContext(
            worktree_path=str(wt_path),
            repository_id=run.repository_id,
            agent_run_id=run.id,
        )

        # 15a. Allowed read-only & safe modifications
        d_read = exec_policy.evaluate("read_file", tool_ctx, {"path": "main.py"})
        assert d_read.action == PolicyAction.ALLOWED
        print_kv("read_file Policy Decision", f"{d_read.action.value} (Risk: {d_read.risk_level.value})")

        # 15b. Blocked critical commands
        d_sudo = exec_policy.evaluate("execute_command", tool_ctx, {"command": "sudo rm -rf /"})
        assert d_sudo.action == PolicyAction.BLOCKED
        assert d_sudo.risk_level == RiskLevel.CRITICAL
        print_kv("sudo rm -rf / Decision", f"{d_sudo.action.value} (Risk: {d_sudo.risk_level.value}) -> {d_sudo.reason}")

        # 15c. Approval required dangerous Git commands
        d_reset = exec_policy.evaluate("execute_command", tool_ctx, {"command": "git reset --hard HEAD~1"})
        assert d_reset.action == PolicyAction.APPROVAL_REQUIRED
        assert d_reset.risk_level == RiskLevel.HIGH
        print_kv("git reset --hard Decision", f"{d_reset.action.value} (Risk: {d_reset.risk_level.value}) -> {d_reset.reason}")

        # 15d. Blocked path traversal escaping worktree
        d_trav = exec_policy.evaluate("read_file", tool_ctx, {"path": "../../etc/shadow"})
        assert d_trav.action == PolicyAction.BLOCKED
        print_kv("Path Traversal Decision", f"{d_trav.action.value} -> {d_trav.reason}")

        # 16. Phase 9: Human Action Approval Request & Resolution (Approve -> Execute)
        print_step_header(16, "Phase 9: Human Action Approval Request & Resolution (Approve -> Resume)")
        appr_req = agent.request_action_approval(
            db=db,
            run_id=run.id,
            action_description="Reset worktree after defective repair attempt",
            risk_level=RiskLevel.HIGH,
            action_type=ApprovalActionType.GIT_OPERATION,
            command="git reset --hard HEAD",
            reason="Worktree restoration needed",
        )
        print_kv("Approval Request ID", appr_req.id)
        print_kv("Initial Status", appr_req.status.value)
        print_kv("Run State During Pause", run.current_state.value)
        assert appr_req.status == ApprovalStatus.PENDING
        assert run.current_state == AgentState.AWAITING_APPROVAL

        # User approves the action
        approved_action = agent.approve_action(db=db, approval_id=appr_req.id, resolved_by="developer_alice")
        print_kv("Resolved Status", approved_action.status.value)
        print_kv("Resolved By", approved_action.resolved_by)
        print_kv("Run State Post-Approval", run.current_state.value)
        assert approved_action.status == ApprovalStatus.APPROVED
        assert run.current_state == AgentState.EXECUTING
        print_kv("Action Approval Flow", "PASSED -> Paused in AWAITING_APPROVAL, resumed to EXECUTING upon human approval.")

        # 17. Phase 9: Human Action Rejection & Observation Feedback
        print_step_header(17, "Phase 9: Human Action Rejection & Structured Feedback")
        rej_req = agent.request_action_approval(
            db=db,
            run_id=run.id,
            action_description="Delete production credentials file",
            risk_level=RiskLevel.CRITICAL,
            action_type=ApprovalActionType.FILE_MODIFICATION,
            command="rm .env.production",
            reason="Clean credentials",
        )
        print_kv("Rejection Request ID", rej_req.id)
        print_kv("Run State Paused", run.current_state.value)
        assert run.current_state == AgentState.AWAITING_APPROVAL

        # User rejects the action
        rejected_action = agent.reject_action(
            db=db, approval_id=rej_req.id, reason="Production credentials must not be deleted", resolved_by="secops_bob"
        )
        print_kv("Resolved Status", rejected_action.status.value)
        print_kv("Rejection Reason", rejected_action.rejection_reason)
        print_kv("Run State Post-Rejection", run.current_state.value)
        assert rejected_action.status == ApprovalStatus.REJECTED
        assert run.current_state == AgentState.EXECUTING
        print_kv("Action Rejection Flow", "PASSED -> Rejection recorded, run resumed in EXECUTING with feedback.")

        # 18. Phase 9: Safe Cancellation Controller & Subsystem Interruption
        print_step_header(18, "Phase 9: Safe Cancellation Controller & Subsystem Interruption")
        cancel_token = agent.cancellation_controller.get_or_create_token(run.id)
        assert cancel_token.is_cancelled is False

        # Create sub-run for cancellation demo
        cancel_demo_run = agent.create_run(
            db=db,
            repository_id="manual-test-repo",
            user_requirement="Demo run for cancellation testing",
            custom_run_id="run-cancel-demo",
        )
        agent.transition_state(db, cancel_demo_run.id, to_state=AgentState.EXECUTING, reason="Starting long task")
        assert cancel_demo_run.current_state == AgentState.EXECUTING

        # Human operator triggers cancellation
        agent.cancel_run(db, cancel_demo_run.id, reason="User clicked Stop button in UI")
        print_kv("Cancelled Run State", cancel_demo_run.current_state.value)
        print_kv("Cancellation Reason", cancel_demo_run.cancellation_reason)
        print_kv("Completed Timestamp", str(cancel_demo_run.completed_at))
        assert cancel_demo_run.current_state == AgentState.CANCELLED
        assert cancel_demo_run.cancellation_reason == "User clicked Stop button in UI"
        print_kv("Cancellation Guardrail", "PASSED -> Run immediately transitioned to CANCELLED without false PASSED.")

        # 19. Repository Tools (Phase 2)
        print_step_header(19, "Invoke Repository Tools (read_file with bounded range)")
        res_read = agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="read_file",
            arguments={"path": "main.py", "start_line": 1, "end_line": 10},
        )
        print_kv("read_file Status", "SUCCESS" if res_read.success else "FAILED")
        print_kv("read_file Duration", f"{res_read.metadata.get('duration_ms')} ms")
        print_kv("Lines Returned", res_read.data.get("total_lines"))
        print_kv("Raw Content", "\n" + res_read.data.get("content", "").strip())
        assert res_read.success

        # 20. Workspace Tools (Phase 2)
        print_step_header(20, "Invoke Workspace Isolated Tools (create_file, modify_file, get_diff)")
        res_mod = agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="modify_file",
            arguments={"path": "calculator.py", "content": "def add(a, b):\n    '''Add two numbers'''\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"},
        )
        print_kv("modify_file Status", "SUCCESS" if res_mod.success else "FAILED")
        print_kv("Modified Bytes", res_mod.data.get("bytes_written"))
        assert res_mod.success

        res_diff = agent.invoke_tool(db, run_id=run.id, tool_name="get_diff", arguments={})
        print_kv("get_diff Status", "SUCCESS" if res_diff.success else "FAILED")
        print_kv("Modified Files", res_diff.data.get("modified_files"))
        print_kv("Unified Diff Output", "\n" + res_diff.data.get("diff", "(empty diff)"))
        assert res_diff.success

        # 21. Terminal Tools (Phase 2)
        print_step_header(21, "Invoke Terminal Tools (detect_commands in sandbox)")
        res_detect = agent.invoke_tool(db, run_id=run.id, tool_name="detect_commands", arguments={})
        print_kv("detect_commands Status", "SUCCESS" if res_detect.success else "FAILED")
        print_kv("Detected Build/Test Tools", res_detect.data.get("detected_commands"))
        assert res_detect.success

        # 22. Verification Tools (Phase 2)
        print_step_header(22, "Invoke Verification Mesh (verify_static AST & Import Integrity)")
        res_verify = agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="verify_static",
            arguments={"files": ["calculator.py", "main.py"]},
        )
        print_kv("verify_static Status", "SUCCESS" if res_verify.success else "FAILED")
        print_kv("Verification Verdict Passed", res_verify.data.get("passed"))
        print_kv("Defects Detected", res_verify.data.get("defects"))
        assert res_verify.success

        # 23. Git Tools (Phase 2)
        print_step_header(23, "Invoke Git Tools (create_checkpoint, git_status)")
        res_cp = agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="create_checkpoint",
            arguments={"message": "Phase 9 verification checkpoint"},
        )
        print_kv("create_checkpoint Status", "SUCCESS" if res_cp.success else "FAILED")
        print_kv("Commit SHA", res_cp.data.get("commit_sha"))
        assert res_cp.success

        res_status = agent.invoke_tool(db, run_id=run.id, tool_name="git_status", arguments={})
        print_kv("git_status Is Clean", res_status.data.get("is_clean"))
        print_kv("git status porcelain", res_status.data.get("porcelain_output", "(clean)"))
        assert res_status.success

        # 24. Tool Policy Safety Enforcement (Phase 2 Invariant)
        print_step_header(24, "Policy Safety Enforcement (BLOCKED Policy Invariant)")
        agent.tools.policy.set_policy("delete_file", PolicyAction.BLOCKED, reason="Deletion of files is forbidden in this environment")
        res_blocked = agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="delete_file",
            arguments={"path": "calculator.py"},
        )
        print_kv("delete_file Status", "REJECTED (EXPECTED)" if not res_blocked.success else "UNEXPECTED SUCCESS")
        print_kv("Rejection Error Code", res_blocked.error.code)
        print_kv("Rejection Message", res_blocked.error.message)
        assert not res_blocked.success
        assert res_blocked.error.code == "POLICY_BLOCKED"
        assert (wt_path / "calculator.py").exists()
        print_kv("Filesystem Safety Invariant", "PASSED -> 'calculator.py' remains intact on disk; handler NEVER ran.")

        # 25. Inspect Persisted Agent Events (PostgreSQL Audit)
        print_step_header(25, "Inspect Persisted Agent Events Audit Log (Phases 1-9)")
        events = db.query(AgentEvent).filter(AgentEvent.agent_run_id == run.id).order_by(AgentEvent.id).all()
        print_kv("Total Events Recorded in Database", len(events))
        print(f"\n    {'ID':<5} | {'EVENT TYPE':<34} | {'MESSAGE'}")
        print(f"    {'-'*5}-+-{'-'*34}-+-{'-'*40}")
        for evt in events:
            evt_name = evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type)
            print(f"    {evt.id:<5} | {evt_name:<34} | {evt.message}")

        # 26. Lifecycle Completion & Terminal State Locking (Phase 1)
        print_step_header(26, "Lifecycle Completion (EXECUTING -> VERIFYING -> COMPLETED)")
        agent.transition_state(db, run.id, to_state=AgentState.VERIFYING, reason="Running automated verification suite")
        agent.transition_state(db, run.id, to_state=AgentState.COMPLETED, reason="All goals and tests verified successfully")
        print_kv("Final Lifecycle State", run.current_state.value)
        print_kv("Final Legacy Status", run.status.value)
        assert run.current_state == AgentState.COMPLETED

        # Verify terminal state locking
        try:
            agent.invoke_tool(db, run.id, "read_file", {"path": "main.py"})
            print_kv("Terminal State Guard", "FAILED: Tool was executed on completed run!")
            sys.exit(1)
        except EngineeringAgentError as err:
            print_kv("Terminal State Guard", f"PASSED -> Rejected subsequent invocation: {err}")

        # 27. Phase 10: Workspace API Snapshot & Live Event Contract Verification
        print_step_header(27, "Phase 10: Workspace Snapshot & Live Event Contract API Verification")
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.database import get_db

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app) as client:
            res_ws = client.get(f"/api/v1/agent/runs/{run.id}/workspace")
            print_kv("GET /workspace HTTP Status", res_ws.status_code)
            assert res_ws.status_code == 200
            ws_data = res_ws.json()

            print_kv("Workspace Run ID", ws_data["run"]["id"])
            print_kv("Workspace Run State", ws_data["run"]["current_state"])
            print_kv("Plan Present in Snapshot", ws_data["plan"] is not None)
            print_kv("Total Tasks in Snapshot", len(ws_data["tasks"]))
            print_kv("Modified Files in Changes", ws_data["changes"]["modified_files"])
            print_kv("Latest Events Count", len(ws_data["latest_events"]))

            # Verify Event ID and Sequence Number Contract (Guardrail 4)
            if ws_data["latest_events"]:
                first_evt = ws_data["latest_events"][0]
                print_kv("First Event ID", first_evt["event_id"])
                print_kv("First Event Sequence", first_evt["sequence"])
                print_kv("First Event Type", first_evt["event_type"])
                assert "event_id" in first_evt
                assert "sequence" in first_evt
                assert first_evt["sequence"] == 1
            
            print_kv("Phase 10 Workspace Invariant", "PASSED -> Authoritative atomic snapshot and sequence contract verified cleanly.")
        app.dependency_overrides.clear()

    db.close()

    print_banner("ALL FLOWS (PHASES 1 THROUGH 10) VERIFIED AND PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
