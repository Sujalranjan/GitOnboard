import asyncio
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from backend.models.user import User
from backend.models.repository import TaskStatus
from backend.task_manager import task_manager

def enqueue_job(job_id: int):
    from backend.main import repo_queue
    asyncio.create_task(repo_queue.enqueue(job_id))

def get_task_status(repo_name: str, task_name: str, current_user: User, db: Session = None):
    if db is None:
        return None
    row = db.query(TaskStatus).filter(
        TaskStatus.user_id == current_user.id,
        TaskStatus.repo_name == repo_name,
        TaskStatus.task_name == task_name
    ).first()
    return row.status if row else None
    
def set_task_status(repo_name: str, task_name: str, status: str, current_user: User, db: Session = None):
    if db is None:
        return
    row = db.query(TaskStatus).filter(
        TaskStatus.user_id == current_user.id,
        TaskStatus.repo_name == repo_name,
        TaskStatus.task_name == task_name
    ).first()
    if row:
        row.status = status
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = TaskStatus(
            user_id=current_user.id,
            repo_name=repo_name,
            task_name=task_name,
            status=status
        )
        db.add(row)
    db.commit()
    
    # Notify SSE subscribers instantly (no polling needed)
    task_manager.notify(current_user.id, repo_name, task_name, status)
