"""
Manual Verification Script: Comprehensive End-to-End Test for Phase 1, Phase 2, Phase 3, Phase 4 & Phase 5.

This script executes and logs every stage of the Engineering Agent lifecycle:
  1. AgentRun Creation & Lifecycle State (Phase 1)
  2. Repository Context Assembly (Phase 3: Requirement Analysis, Hybrid Retrieval, RIM, Budget, Understanding Contract)
  3. Planning Orchestration & Validation (Phase 4: Plan, PlanTask DAG, PlanValidator -> AWAITING_APPROVAL)
  4. Human Plan Rejection & Revision (Phase 4: Plan v1 -> Plan v2 revision)
  5. Explicit Human Approval Boundary (Phase 4: Plan v2 APPROVED; Invariant: Zero execution during approval!)
  6. Start Plan Execution (Phase 5: AWAITING_APPROVAL -> EXECUTING, unlock initial tasks to READY)
  7. Sequential Task Orchestration & Execution (Phase 5: TaskOrchestrator -> TaskExecutor -> VerificationDispatcher -> PASSED)
  8. Inspect Task DAG & Statuses (Phase 5: get_plan_tasks query)
  9. Repository Tools (read_file with bounded lines)
  10. Workspace Isolated File & Patch Tools (create_file, modify_file, get_diff)
  11. Terminal Tools (detect_commands via sandbox)
  12. Verification Mesh Tools (verify_static AST integrity)
  13. Git Tools (create_checkpoint, git_status)
  14. Tool Policy Safety Enforcement (BLOCKED policy blocks handler execution)
  15. Database Event Audit & History (AgentEvent log inspection)
  16. Terminal State Locking (COMPLETED state locks execution)

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

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agent.engineering_agent import EngineeringAgent, EngineeringAgentError
from backend.agent.planning.contracts import PlanStatus, PlanTaskStatus
from backend.agent.tools.policy import PolicyAction
from backend.agent.tools import create_default_tool_registry
from backend.database import Base, SessionLocal, engine
from backend.models.implementation import AgentEvent, AgentEventType, AgentRun, AgentState


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
        "  COVERS: PHASE 1 (LIFECYCLE) + PHASE 2 (TOOLS) + PHASE 3 (CONTEXT) + PHASE 4 (PLANNING) + PHASE 5 (TASK ORCHESTRATOR)"
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

        # 7. Sequential Task Orchestration & Verification (Phase 5)
        print_step_header(7, "Sequential Task Orchestration & Verification (Phase 5)")
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

        # 8. Query Task Graph & Detail (Phase 5)
        print_step_header(8, "Query Task Graph & Detail (Phase 5)")
        final_tasks = agent.get_plan_tasks(db, run_id=run.id)
        for t in final_tasks:
            print_kv(f"Task [{t.task_id}]", f"status={t.status.value} (deps={t.dependencies}, verif={t.verification_strategy})")
            assert t.status == PlanTaskStatus.PASSED

        # 9. Repository Tools (Phase 2)
        print_step_header(9, "Invoke Repository Tools (read_file with bounded range)")
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

        # 10. Workspace Tools (Phase 2)
        print_step_header(10, "Invoke Workspace Isolated Tools (create_file, modify_file, get_diff)")
        
        # 10.1 create_file
        res_create = agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="create_file",
            arguments={"path": "calculator.py", "content": "def add(a, b):\n    return a + b\n"},
        )
        print_kv("create_file Status", "SUCCESS" if res_create.success else "FAILED")
        print_kv("File Created", res_create.data.get("path"))
        print_kv("Bytes Written", res_create.data.get("bytes_written"))
        assert res_create.success
        assert (wt_path / "calculator.py").exists()

        # 10.2 modify_file
        res_mod = agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="modify_file",
            arguments={"path": "calculator.py", "content": "def add(a, b):\n    '''Add two numbers'''\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"},
        )
        print_kv("modify_file Status", "SUCCESS" if res_mod.success else "FAILED")
        print_kv("Modified Bytes", res_mod.data.get("bytes_written"))
        assert res_mod.success

        # 10.3 get_diff
        res_diff = agent.invoke_tool(db, run_id=run.id, tool_name="get_diff", arguments={})
        print_kv("get_diff Status", "SUCCESS" if res_diff.success else "FAILED")
        print_kv("Modified Files", res_diff.data.get("modified_files"))
        print_kv("Unified Diff Output", "\n" + res_diff.data.get("diff", "(empty diff)"))
        assert res_diff.success

        # 11. Terminal Tools (Phase 2)
        print_step_header(11, "Invoke Terminal Tools (detect_commands in sandbox)")
        res_detect = agent.invoke_tool(db, run_id=run.id, tool_name="detect_commands", arguments={})
        print_kv("detect_commands Status", "SUCCESS" if res_detect.success else "FAILED")
        print_kv("Detected Build/Test Tools", res_detect.data.get("detected_commands"))
        assert res_detect.success

        # 12. Verification Tools (Phase 2)
        print_step_header(12, "Invoke Verification Mesh (verify_static AST & Import Integrity)")
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

        # 13. Git Tools (Phase 2)
        print_step_header(13, "Invoke Git Tools (create_checkpoint, git_status)")
        res_cp = agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="create_checkpoint",
            arguments={"message": "Phase 5 verification checkpoint"},
        )
        print_kv("create_checkpoint Status", "SUCCESS" if res_cp.success else "FAILED")
        print_kv("Commit SHA", res_cp.data.get("commit_sha"))
        assert res_cp.success

        res_status = agent.invoke_tool(db, run_id=run.id, tool_name="git_status", arguments={})
        print_kv("git_status Is Clean", res_status.data.get("is_clean"))
        print_kv("git status porcelain", res_status.data.get("porcelain_output", "(clean)"))
        assert res_status.success

        # 14. Tool Policy Safety Enforcement (Phase 2 Invariant)
        print_step_header(14, "Policy Safety Enforcement (BLOCKED Policy Invariant)")
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

        # 15. Inspect Persisted Agent Events (PostgreSQL Audit)
        print_step_header(15, "Inspect Persisted Agent Events Audit Log")
        events = db.query(AgentEvent).filter(AgentEvent.agent_run_id == run.id).order_by(AgentEvent.id).all()
        print_kv("Total Events Recorded in Database", len(events))
        print(f"\n    {'ID':<5} | {'EVENT TYPE':<28} | {'MESSAGE'}")
        print(f"    {'-'*5}-+-{'-'*28}-+-{'-'*40}")
        for evt in events:
            evt_name = evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type)
            print(f"    {evt.id:<5} | {evt_name:<28} | {evt.message}")

        # 16. Lifecycle Completion & Terminal State Locking (Phase 1)
        print_step_header(16, "Lifecycle Completion (EXECUTING -> VERIFYING -> COMPLETED)")
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

    db.close()

    print_banner("ALL FLOWS (PHASE 1, PHASE 2, PHASE 3, PHASE 4 & PHASE 5) VERIFIED AND PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
