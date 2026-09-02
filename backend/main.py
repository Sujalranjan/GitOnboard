import backend.models  # Register all models with Base.metadata
from fastapi import FastAPI, HTTPException, APIRouter, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response
from contextlib import asynccontextmanager
import logging
import uuid
import time
from pathlib import Path
import shutil
import asyncio

from backend.config import settings
from backend.logger import setup_logging, set_correlation_context, emit_execution_log, sanitize_log_data
from backend.database import engine, Base, SessionLocal
from backend.models.user import User
from backend.models.repository import Repository, AnalysisJob

from backend.services.queue import InMemoryQueue
from backend.services.worker import AnalysisWorker
from backend.task_manager import task_manager

setup_logging()
logger = logging.getLogger(__name__)

# Initialize Queue
worker = AnalysisWorker()
repo_queue = InMemoryQueue(worker)

def cleanup_tmp_dirs():
    base_tmp = Path("/tmp/repo-analysis")
    if base_tmp.exists() and base_tmp.is_dir():
        for child in base_tmp.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            except Exception:
                pass

def ensure_db_schema_up_to_date(bind_engine):
    from sqlalchemy import text
    try:
        with bind_engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE files ADD COLUMN IF NOT EXISTS size INTEGER DEFAULT 0;
                ALTER TABLE files ADD COLUMN IF NOT EXISTS blob_name VARCHAR;
                ALTER TABLE files ADD COLUMN IF NOT EXISTS snapshot_id VARCHAR;
                ALTER TABLE files ADD COLUMN IF NOT EXISTS content_type VARCHAR;
                ALTER TABLE files ADD COLUMN IF NOT EXISTS is_binary BOOLEAN DEFAULT false;
                ALTER TABLE files ADD COLUMN IF NOT EXISTS is_generated BOOLEAN DEFAULT false;
                ALTER TABLE files ADD COLUMN IF NOT EXISTS is_test BOOLEAN DEFAULT false;
                ALTER TABLE files ADD COLUMN IF NOT EXISTS is_documentation BOOLEAN DEFAULT false;
                ALTER TABLE files ADD COLUMN IF NOT EXISTS is_agent_instruction BOOLEAN DEFAULT false;

                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS implementation_id VARCHAR;
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS task_id VARCHAR;
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS repository_id VARCHAR;
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS user_requirement TEXT;
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS plan JSONB;
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS current_state VARCHAR DEFAULT 'IDLE';
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'QUEUED';
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS iteration INTEGER DEFAULT 1;
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS worktree_path VARCHAR;
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS error_message TEXT;
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS metadata JSONB;
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
                ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE;

                ALTER TABLE agent_events ADD COLUMN IF NOT EXISTS sequence INTEGER;
                ALTER TABLE agent_events ADD COLUMN IF NOT EXISTS agent_run_id VARCHAR;
                ALTER TABLE agent_events ADD COLUMN IF NOT EXISTS task_id VARCHAR;
                ALTER TABLE agent_events ADD COLUMN IF NOT EXISTS event_type VARCHAR;
                ALTER TABLE agent_events ADD COLUMN IF NOT EXISTS message TEXT;
                ALTER TABLE agent_events ADD COLUMN IF NOT EXISTS payload JSONB;
                ALTER TABLE agent_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

                ALTER TABLE agent_events ALTER COLUMN event_type TYPE VARCHAR USING event_type::VARCHAR;
                ALTER TABLE agent_runs ALTER COLUMN current_state TYPE VARCHAR USING current_state::VARCHAR;
                ALTER TABLE agent_runs ALTER COLUMN status TYPE VARCHAR USING status::VARCHAR;
                ALTER TABLE agent_state_transitions ALTER COLUMN from_state TYPE VARCHAR USING from_state::VARCHAR;
                ALTER TABLE agent_state_transitions ALTER COLUMN to_state TYPE VARCHAR USING to_state::VARCHAR;
                ALTER TABLE implementations ALTER COLUMN repository_id DROP NOT NULL;
            """))
            conn.commit()
    except Exception as e:
        logger.warning(f"Note on schema auto-migration: {e}")

def drop_legacy_fk_constraints(bind_engine):
    try:
        from sqlalchemy import text
        with bind_engine.connect() as conn:
            conn.execute(text("ALTER TABLE relationships DROP CONSTRAINT IF EXISTS relationships_from_symbol_id_fkey;"))
            conn.execute(text("ALTER TABLE relationships DROP CONSTRAINT IF EXISTS relationships_to_symbol_id_fkey;"))
            conn.execute(text("ALTER TABLE routes DROP CONSTRAINT IF EXISTS routes_symbol_id_fkey;"))
            conn.execute(text("ALTER TABLE routes DROP CONSTRAINT IF EXISTS routes_handler_symbol_id_fkey;"))
            conn.execute(text("ALTER TABLE database_objects DROP CONSTRAINT IF EXISTS database_objects_symbol_id_fkey;"))
            conn.execute(text("ALTER TABLE capability_members DROP CONSTRAINT IF EXISTS capability_members_symbol_id_fkey;"))
            conn.execute(text("ALTER TABLE evidence DROP CONSTRAINT IF EXISTS evidence_symbol_id_fkey;"))
            conn.commit()
    except Exception as e:
        logger.warning(f"Note on legacy FK constraint drop: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up application...")

    # Retry database connection on startup (handles docker compose race conditions)
    max_retries = 10
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            Base.metadata.create_all(bind=engine)
            ensure_db_schema_up_to_date(engine)
            drop_legacy_fk_constraints(engine)
            break
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Database connection failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"Failed to connect to database after {max_retries} attempts")
                raise
    
    # Wire the running event loop into TaskManager so background
    # threads can safely push SSE notifications via call_soon_threadsafe
    task_manager.set_loop(asyncio.get_event_loop())
    
    # Cleanup orphaned temp directories
    cleanup_tmp_dirs()
    
    # Start worker queue
    repo_queue.start()
    
    # Recover unfinished jobs
    db = SessionLocal()
    try:
        unfinished_jobs = db.query(AnalysisJob).filter(
            AnalysisJob.status.in_(["Queued", "Downloading", "Analyzing", "Saving"])
        ).all()
        for job in unfinished_jobs:
            logger.info(f"Recovering unfinished job {job.id}")
            job.status = "Queued"
            db.commit()
            await repo_queue.enqueue(job.id)

        # Recover in-flight agent runs after server restart
        try:
            from backend.agent.engineering_agent import EngineeringAgent
            recovered_agent_runs = EngineeringAgent().recover_in_flight_runs(db)
            if recovered_agent_runs:
                logger.info(f"Recovered {len(recovered_agent_runs)} in-flight agent run(s)")
        except Exception as err:
            logger.warning(f"Note on agent run restart recovery: {err}")
    except Exception as e:
        logger.error(f"Failed to recover jobs: {e}")
    finally:
        db.close()
        
    yield
    # Shutdown
    logger.info("Shutting down application...")
    try:
        from backend.routers.sandbox import sandbox_manager
        await sandbox_manager.close_all_sessions()
    except Exception as e:
        logger.debug(f"Error during sandbox cleanup: {e}")


app = FastAPI(
    title=settings.app_name,
    description="Repository Intelligence Platform API (MVP)",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID"],
)

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    # Extract or generate correlation ID
    correlation_id = request.headers.get("X-Correlation-ID") or request.headers.get("x-correlation-id") or str(uuid.uuid4())
    
    # Try to extract repository or task ID from path if present
    path = request.url.path
    repo_id = None
    task_id = None
    parts = path.strip("/").split("/")
    if "repos" in parts:
        try:
            repo_idx = parts.index("repos")
            if repo_idx + 1 < len(parts):
                repo_id = parts[repo_idx + 1]
        except (ValueError, IndexError):
            pass
    if "task" in parts:
        try:
            task_idx = parts.index("task")
            if task_idx + 1 < len(parts):
                task_id = parts[task_idx + 1]
        except (ValueError, IndexError):
            pass

    set_correlation_context(correlation_id=correlation_id, repo_id=repo_id, task_id=task_id)

    start_time = time.time()
    try:
        response: Response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000
        response.headers["X-Correlation-ID"] = correlation_id

        # Emit structured execution log for non-health endpoints (skip noisy status checks)
        if not path.endswith("/health") and path != "/" and "semantic-status" not in path:
            emit_execution_log(
                event_type="http_request",
                status=str(response.status_code),
                correlation_id=correlation_id,
                repo_id=repo_id,
                task_id=task_id,
                details={
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            )
        return response
    except Exception as exc:
        duration_ms = (time.time() - start_time) * 1000
        emit_execution_log(
            event_type="http_error",
            status="500",
            correlation_id=correlation_id,
            repo_id=repo_id,
            task_id=task_id,
            details={
                "method": request.method,
                "path": path,
                "error": str(exc),
                "duration_ms": round(duration_ms, 2),
            }
        )
        raise exc

from backend.routers import auth_router, health_router, agent_router
from backend.routers.implementation import router as implementation_router
from backend.routers.repo import repo_router, import_router
from backend.routers.verification import router as verification_router
from backend.routers.sandbox import router as sandbox_router

app.include_router(auth_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(import_router, prefix="/api/import")
app.include_router(repo_router, prefix="/api/repos")

app.include_router(agent_router)
app.include_router(implementation_router)
app.include_router(verification_router)
app.include_router(sandbox_router)

@app.get("/", include_in_schema=False)
def read_root():
    return {"message": "Welcome to Repository Intelligence Platform API"}
