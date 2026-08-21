"""
Manual Verification Script: Comprehensive End-to-End Test for Phase 1, Phase 2 & Phase 3.

This script executes and logs every stage of the Engineering Agent lifecycle:
  1. AgentRun Creation & Lifecycle State (Phase 1)
  2. Repository Context Assembly (Phase 3: Requirement Analysis, Hybrid Retrieval, RIM, Budget, Understanding Contract)
  3. State Machine Transitions (UNDERSTANDING -> PLANNING -> EXECUTING)
  4. Repository Tools (read_file with bounded lines)
  5. Workspace Isolated File & Patch Tools (create_file, modify_file, get_diff)
  6. Terminal Tools (detect_commands via sandbox)
  7. Verification Mesh Tools (verify_static AST integrity)
  8. Git Tools (create_checkpoint, git_status)
  9. Tool Policy Safety Enforcement (BLOCKED policy blocks handler execution)
  10. Database Event Audit & History (AgentEvent log inspection)
  11. Terminal State Locking (COMPLETED state locks execution)

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
    print_banner("GITONBOARD ENGINEERING AGENT — FULL END-TO-END VERIFICATION\n  COVERS: PHASE 1 (LIFECYCLE) + PHASE 2 (TOOLS) + PHASE 3 (CONTEXT ASSEMBLY)")

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

        # 3. State Machine Transitions (Phase 1)
        print_step_header(3, "State Machine Transitions (UNDERSTANDING -> PLANNING -> EXECUTING)")
        t1 = agent.transition_state(db, run.id, to_state=AgentState.PLANNING, reason="Synthesizing plan from assembled context")
        print_kv("Transition 1 Result", f"{t1.current_state.value} (reason: Synthesizing plan)")
        assert run.current_state == AgentState.PLANNING

        t2 = agent.transition_state(db, run.id, to_state=AgentState.EXECUTING, reason="Executing plan tool steps")
        print_kv("Transition 2 Result", f"{t2.current_state.value} (reason: Executing plan tool steps)")
        assert run.current_state == AgentState.EXECUTING

        # 4. Repository Tools (Phase 2)
        print_step_header(4, "Invoke Repository Tools (read_file with bounded range)")
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

        # 5. Workspace Tools (Phase 2)
        print_step_header(5, "Invoke Workspace Isolated Tools (create_file, modify_file, get_diff)")
        
        # 5.1 create_file
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

        # 5.2 modify_file
        res_mod = agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="modify_file",
            arguments={"path": "calculator.py", "content": "def add(a, b):\n    '''Add two numbers'''\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"},
        )
        print_kv("modify_file Status", "SUCCESS" if res_mod.success else "FAILED")
        print_kv("Modified Bytes", res_mod.data.get("bytes_written"))
        assert res_mod.success

        # 5.3 get_diff
        res_diff = agent.invoke_tool(db, run_id=run.id, tool_name="get_diff", arguments={})
        print_kv("get_diff Status", "SUCCESS" if res_diff.success else "FAILED")
        print_kv("Modified Files", res_diff.data.get("modified_files"))
        print_kv("Unified Diff Output", "\n" + res_diff.data.get("diff", "(empty diff)"))
        assert res_diff.success

        # 6. Terminal Tools (Phase 2)
        print_step_header(6, "Invoke Terminal Tools (detect_commands in sandbox)")
        res_detect = agent.invoke_tool(db, run_id=run.id, tool_name="detect_commands", arguments={})
        print_kv("detect_commands Status", "SUCCESS" if res_detect.success else "FAILED")
        print_kv("Detected Build/Test Tools", res_detect.data.get("detected_commands"))
        assert res_detect.success

        # 7. Verification Tools (Phase 2)
        print_step_header(7, "Invoke Verification Mesh (verify_static AST & Import Integrity)")
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

        # 8. Git Tools (Phase 2)
        print_step_header(8, "Invoke Git Tools (create_checkpoint, git_status)")
        res_cp = agent.invoke_tool(
            db,
            run_id=run.id,
            tool_name="create_checkpoint",
            arguments={"message": "Phase 2 & 3 verification checkpoint"},
        )
        print_kv("create_checkpoint Status", "SUCCESS" if res_cp.success else "FAILED")
        print_kv("Commit SHA", res_cp.data.get("commit_sha"))
        assert res_cp.success

        res_status = agent.invoke_tool(db, run_id=run.id, tool_name="git_status", arguments={})
        print_kv("git_status Is Clean", res_status.data.get("is_clean"))
        print_kv("git status porcelain", res_status.data.get("porcelain_output", "(clean)"))
        assert res_status.success

        # 9. Tool Policy Safety Enforcement (Phase 2 Invariant)
        print_step_header(9, "Policy Safety Enforcement (BLOCKED Policy Invariant)")
        # Dynamically set policy to BLOCKED for delete_file
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
        # Verify file still exists on disk (handler never executed)
        assert (wt_path / "calculator.py").exists()
        print_kv("Filesystem Safety Invariant", "PASSED -> 'calculator.py' remains intact on disk; handler NEVER ran.")

        # 10. Inspect Persisted Agent Events (PostgreSQL Audit)
        print_step_header(10, "Inspect Persisted Agent Events Audit Log")
        events = db.query(AgentEvent).filter(AgentEvent.agent_run_id == run.id).order_by(AgentEvent.id).all()
        print_kv("Total Events Recorded in Database", len(events))
        print(f"\n    {'ID':<5} | {'EVENT TYPE':<28} | {'MESSAGE'}")
        print(f"    {'-'*5}-+-{'-'*28}-+-{'-'*40}")
        for evt in events:
            evt_name = evt.event_type.value if hasattr(evt.event_type, "value") else str(evt.event_type)
            print(f"    {evt.id:<5} | {evt_name:<28} | {evt.message}")

        # 11. Lifecycle Completion & Terminal State Locking (Phase 1)
        print_step_header(11, "Lifecycle Completion (EXECUTING -> VERIFYING -> COMPLETED)")
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

    print_banner("ALL FLOWS (PHASE 1, PHASE 2 & PHASE 3) VERIFIED AND PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
