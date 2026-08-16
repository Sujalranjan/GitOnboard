import asyncio
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

from backend.models.user import User
from backend.models.repository import TaskStatus
from backend.task_manager import task_manager

def enqueue_job(job_id: int):
    from backend.main import repo_queue
    asyncio.create_task(repo_queue.enqueue(job_id))

def get_task_status(repo_name: str, task_name: str, current_user: User, db: Session = None, max_age_seconds: int = 180):
    if db is None:
        return None
    row = db.query(TaskStatus).filter(
        TaskStatus.user_id == current_user.id,
        TaskStatus.repo_name == repo_name,
        TaskStatus.task_name == task_name
    ).first()
    if not row:
        return None
        
    # Auto-recover orphaned 'processing' tasks that haven't updated in max_age_seconds
    if row.status == "processing" and row.updated_at:
        now = datetime.now(timezone.utc)
        # Ensure row.updated_at is timezone-aware
        row_time = row.updated_at if row.updated_at.tzinfo else row.updated_at.replace(tzinfo=timezone.utc)
        if (now - row_time).total_seconds() > max_age_seconds:
            row.status = "failed"
            row.updated_at = now
            db.commit()
            return "failed"
            
    return row.status
    
def set_task_status(repo_name: str, task_name: str, status: str, current_user: User, db: Session = None):
    if db is None:
        return
    row = db.query(TaskStatus).filter(
        TaskStatus.user_id == current_user.id,
        TaskStatus.repo_name == repo_name,
        TaskStatus.task_name == task_name
    ).first()
    now = datetime.now(timezone.utc)
    if row:
        row.status = status
        row.updated_at = now
    else:
        row = TaskStatus(
            user_id=current_user.id,
            repo_name=repo_name,
            task_name=task_name,
            status=status,
            updated_at=now
        )
        db.add(row)
    db.commit()
    
    # Notify SSE subscribers instantly (no polling needed)
    task_manager.notify(current_user.id, repo_name, task_name, status)
