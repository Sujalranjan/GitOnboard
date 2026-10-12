"""
Serializers and workspace helper functions for the Engineering Agent Router.
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import List

from backend.models.implementation import AgentEvent, AgentRun, ApprovalRequest
from backend.routers.agent_schemas import (
    AgentRunDetailResponse,
    AgentRunResponse,
    ApprovalRequestItem,
    EventItem,
    StateTransitionItem,
    WorkspaceChangesResponse,
)

logger = logging.getLogger(__name__)


def serialize_run(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=run.id,
        task_id=run.task_id,
        repository_id=run.repository_id,
        user_requirement=run.user_requirement,
        current_state=run.current_state.value if hasattr(run.current_state, "value") else str(run.current_state),
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        started_at=run.started_at.isoformat() if run.started_at else "",
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        cancellation_reason=run.cancellation_reason,
        error_message=run.error_message,
    )


def serialize_event(e: AgentEvent, seq: int = 0) -> EventItem:
    return EventItem(
        event_id=e.id,
        sequence=seq,
        agent_run_id=e.agent_run_id,
        task_id=getattr(e.agent_run, "task_id", None) if e.agent_run else None,
        event_type=e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type),
        message=e.message,
        payload=e.payload or {},
        created_at=e.created_at.isoformat() if e.created_at else "",
        timestamp=e.created_at.isoformat() if e.created_at else "",
    )


def serialize_approval_request(a: ApprovalRequest) -> ApprovalRequestItem:
    return ApprovalRequestItem(
        id=a.id,
        agent_run_id=a.agent_run_id,
        task_id=a.task_id,
        action_type=a.action_type.value if hasattr(a.action_type, "value") else str(a.action_type),
        action_description=a.action_description,
        risk_level=a.risk_level.value if hasattr(a.risk_level, "value") else str(a.risk_level),
        command=a.command,
        reason=a.reason,
        status=a.status.value if hasattr(a.status, "value") else str(a.status),
        requested_at=a.requested_at.isoformat() if a.requested_at else "",
        resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
        resolved_by=a.resolved_by,
        rejection_reason=a.rejection_reason,
    )


def compute_workspace_changes(run: AgentRun) -> WorkspaceChangesResponse:
    if not run.worktree_path or not os.path.exists(run.worktree_path):
        return WorkspaceChangesResponse(agent_run_id=run.id, worktree_path=run.worktree_path)

    try:
        st_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=run.worktree_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        mod_files: List[str] = []
        add_files: List[str] = []
        del_files: List[str] = []
        if st_proc.returncode == 0:
            for line in st_proc.stdout.splitlines():
                if not line.strip():
                    continue
                status_code = line[:2].strip()
                fpath = line[3:].strip()
                if "M" in status_code:
                    mod_files.append(fpath)
                elif "A" in status_code or "?" in status_code:
                    add_files.append(fpath)
                elif "D" in status_code:
                    del_files.append(fpath)
                else:
                    mod_files.append(fpath)

        diff_proc = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=run.worktree_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        diff_str = diff_proc.stdout if diff_proc.returncode == 0 else ""
        if not diff_str:
            diff_proc2 = subprocess.run(
                ["git", "diff"],
                cwd=run.worktree_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            diff_str = diff_proc2.stdout if diff_proc2.returncode == 0 else ""

        return WorkspaceChangesResponse(
            agent_run_id=run.id,
            worktree_path=run.worktree_path,
            modified_files=mod_files,
            added_files=add_files,
            deleted_files=del_files,
            diff=diff_str,
        )
    except Exception as err:
        logger.warning(f"Failed to compute workspace changes for run '{run.id}': {err}")
        return WorkspaceChangesResponse(agent_run_id=run.id, worktree_path=run.worktree_path)


def serialize_run_detail(run: AgentRun) -> AgentRunDetailResponse:
    transitions = [
        StateTransitionItem(
            from_state=t.from_state.value if hasattr(t.from_state, "value") else str(t.from_state),
            to_state=t.to_state.value if hasattr(t.to_state, "value") else str(t.to_state),
            reason=t.reason,
            timestamp=t.timestamp.isoformat() if t.timestamp else "",
        )
        for t in (run.transitions or [])
    ]
    events = [serialize_event(e, idx + 1) for idx, e in enumerate(run.events or [])]
    return AgentRunDetailResponse(
        id=run.id,
        task_id=run.task_id,
        repository_id=run.repository_id,
        user_requirement=run.user_requirement,
        current_state=run.current_state.value if hasattr(run.current_state, "value") else str(run.current_state),
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        started_at=run.started_at.isoformat() if run.started_at else "",
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        cancellation_reason=run.cancellation_reason,
        error_message=run.error_message,
        transitions=transitions,
        events=events,
        metadata=run.metadata_json or {},
    )
