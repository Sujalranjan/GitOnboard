import json
import asyncio
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.models.repository import TaskStatus
from backend.dependencies.auth import get_current_user
from backend.task_manager import task_manager
from sse_starlette.sse import EventSourceResponse

tasks_router = APIRouter(tags=["tasks"])

@tasks_router.get("/{repo_name}/tasks")
def get_tasks(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Return current snapshot from in-memory store (fast path)
    # Falls back to DB if process was restarted and memory was cleared
    mem = task_manager.get_all(current_user.id, repo_name)
    if mem:
        return mem
    rows = db.query(TaskStatus).filter(
        TaskStatus.user_id == current_user.id,
        TaskStatus.repo_name == repo_name
    ).all()
    return {row.task_name: row.status for row in rows}


@tasks_router.get("/{repo_name}/tasks/stream")
async def stream_tasks(repo_name: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """SSE endpoint — browser subscribes once, server pushes on every task status change."""

    async def event_generator():
        queue = task_manager.subscribe(current_user.id, repo_name)
        logger = logging.getLogger(__name__)
        logger.info(f"[SSE] Client connected: user_id={current_user.id}, repo_name={repo_name}")

        try:
            # Send current state immediately on connect so browser isn't blank
            current = task_manager.get_all(current_user.id, repo_name)
            if not current:
                # Fallback: load from DB (e.g. after backend restart)
                rows = db.query(TaskStatus).filter(
                    TaskStatus.user_id == current_user.id,
                    TaskStatus.repo_name == repo_name
                ).all()
                current = {row.task_name: row.status for row in rows}
                # Seed TaskManager with DB state so future notifies work
                for task_name, status in current.items():
                    task_manager._statuses.setdefault(
                        task_manager._key(current_user.id, repo_name), {}
                    )[task_name] = status

            logger.info(f"[SSE] Initial state: {current}")
            yield {"data": json.dumps(current)}

            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"[SSE] Client disconnected: user_id={current_user.id}, repo_name={repo_name}")
                    break

                try:
                    # Wait for next notification from background task
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                    logger.info(f"[SSE] Sending event to client: payload={payload}")
                    yield {"data": payload}
                except asyncio.TimeoutError:
                    # Send a heartbeat comment to keep connection alive
                    logger.debug(f"[SSE] Sending keepalive heartbeat")
                    yield {"comment": "keepalive"}
        finally:
            task_manager.unsubscribe(current_user.id, repo_name, queue)
            logger.info(f"[SSE] Subscription cleaned up: user_id={current_user.id}, repo_name={repo_name}")

    return EventSourceResponse(event_generator())
