"""
agent_events: Persists AgentRun/AgentEvent/FileChange rows for the Coding Agent
pipeline and publishes each event over the existing TaskManager SSE pub/sub
(the same mechanism /api/repos/{repo_name}/tasks/stream already uses) so a
future frontend can subscribe to live progress instead of only seeing the
final synchronous HTTP response.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.models.implementation import AgentEvent, AgentEventType, AgentRun, AgentRunStatus, FileChange
from backend.services.diff_parser import parse_unified_diff
from backend.task_manager import task_manager

logger = logging.getLogger(__name__)

# TaskManager is keyed by (user_id, repo_name). The pipeline router is not yet
# authenticated, so a fixed system user_id is used; task_id is folded into the
# channel key ("agent:{task_id}") to give each run its own isolated SSE channel.
_EVENT_CHANNEL_USER_ID = 0


def _channel(task_id: str) -> str:
    return f"agent:{task_id}"


def start_agent_run(
    db: Session,
    task_id: str,
    implementation_id: Optional[str] = None,
    worktree_path: Optional[str] = None,
    iteration: int = 1,
) -> AgentRun:
    run = AgentRun(
        implementation_id=implementation_id,
        task_id=task_id,
        status=AgentRunStatus.RUNNING,
        iteration=iteration,
        worktree_path=worktree_path,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    emit_event(db, run, AgentEventType.STARTED, f"Agent run started (iteration {iteration})")
    return run


def emit_event(
    db: Session,
    agent_run: AgentRun,
    event_type: AgentEventType,
    message: str,
    payload: Optional[Dict[str, Any]] = None,
) -> AgentEvent:
    event = AgentEvent(
        agent_run_id=agent_run.id,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    try:
        task_manager.notify(
            _EVENT_CHANNEL_USER_ID,
            _channel(agent_run.task_id),
            event_type.value,
            json.dumps(
                {
                    "event_type": event_type.value,
                    "message": message,
                    "payload": payload or {},
                    "created_at": event.created_at.isoformat() if event.created_at else datetime.now(timezone.utc).isoformat(),
                }
            ),
        )
    except Exception as err:
        logger.debug(f"agent_events: SSE notify failed for task '{agent_run.task_id}': {err}")

    return event


def persist_file_changes(db: Session, agent_run: AgentRun, diff_text: str) -> int:
    """Parses diff_text and persists FileChange rows against agent_run. Returns count persisted."""
    changes = parse_unified_diff(diff_text)
    for change in changes:
        db.add(
            FileChange(
                agent_run_id=agent_run.id,
                file_path=change.file_path,
                change_type=change.change_type,
                lines_added=change.lines_added,
                lines_removed=change.lines_removed,
                diff_patch=change.diff_patch,
            )
        )
    if changes:
        db.commit()
    return len(changes)


def complete_agent_run(
    db: Session,
    agent_run: AgentRun,
    status: AgentRunStatus,
    error_message: Optional[str] = None,
) -> AgentRun:
    agent_run.status = status
    agent_run.completed_at = datetime.now(timezone.utc)
    if error_message:
        agent_run.error_message = error_message
    db.add(agent_run)
    db.commit()
    db.refresh(agent_run)

    event_type = AgentEventType.FAILED if status == AgentRunStatus.FAILED else AgentEventType.FINISHED
    emit_event(db, agent_run, event_type, f"Agent run {status.value.lower()}", {"error": error_message} if error_message else None)
    return agent_run
