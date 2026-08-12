import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional
from sqlalchemy.orm import Session
from backend.database import SessionLocal
from backend.models.repository import AnalysisJob

logger = logging.getLogger(__name__)

class WorkerInterface(ABC):
    @abstractmethod
    async def process(self, job_id: int):
        pass

class QueueInterface(ABC):
    @abstractmethod
    async def enqueue(self, job_id: int):
        pass

class InMemoryQueue(QueueInterface):
    def __init__(self, worker: WorkerInterface):
        self.queue = asyncio.Queue()
        self.worker = worker
        self._task = None
        self.active_tasks = {}

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._process_loop())

    async def enqueue(self, job_id: int):
        await self.queue.put(job_id)

    def cancel(self, job_id: int):
        if job_id in self.active_tasks:
            self.active_tasks[job_id].cancel()
            return True
        return False

    async def _process_loop(self):
        while True:
            job_id = await self.queue.get()
            
            # Check if job was cancelled while in queue
            from backend.database import SessionLocal
            from backend.models.repository import AnalysisJob, Analysis
            from datetime import datetime, timezone
            
            db = SessionLocal()
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job and job.status == "Cancelled":
                db.close()
                self.queue.task_done()
                continue
            db.close()
            
            task = asyncio.create_task(self.worker.process(job_id))
            self.active_tasks[job_id] = task
            try:
                await task
            except asyncio.CancelledError:
                logger.info(f"Job {job_id} was cancelled by user")
                
                # Update DB state for cancellation
                db = SessionLocal()
                try:
                    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
                    if job:
                        job.status = "Cancelled"
                        job.completed_at = datetime.now(timezone.utc)
                        analysis = db.query(Analysis).filter(Analysis.id == job.analysis_id).first()
                        if analysis:
                            analysis.status = "Cancelled"
                        db.commit()
                except Exception as e:
                    logger.error(f"Error marking job {job_id} as cancelled: {e}")
                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Error processing job {job_id}: {e}")
            finally:
                self.active_tasks.pop(job_id, None)
                self.queue.task_done()

# We will instantiate the queue and worker in main.py
