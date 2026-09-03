# Runtime Execution Flow

**Confidence:** Verified  
**Cross-reference:** [01-project-architecture.md](./01-project-architecture.md), [07-wiring-validation.md](./07-wiring-validation.md)

---

## 1. Application Startup Sequence

```
[uvicorn starts]
    │
    ├─ backend/main.py (module-level execution)
    │    ├─ setup_logging()                             [logger.py]
    │    ├─ worker = AnalysisWorker()                  [services/worker.py]
    │    ├─ repo_queue = InMemoryQueue(worker)         [services/queue.py]
    │    └─ FastAPI(lifespan=lifespan) created
    │
    ├─ lifespan() [asynccontextmanager, main.py:37]
    │    ├─ Base.metadata.create_all(bind=engine)      [Creates all SQL tables if not exist]
    │    ├─ task_manager.set_loop(asyncio.get_event_loop())  [task_manager.py]
    │    ├─ cleanup_tmp_dirs()                         [Removes /tmp/repo-analysis/* orphans]
    │    ├─ repo_queue.start()                         [InMemoryQueue.start() — starts asyncio queue consumer]
    │    └─ Job Recovery Loop                          [Queries AnalysisJob for unfinished jobs, re-enqueues]
    │
    ├─ Middleware Registration
    │    └─ CORSMiddleware(allow_origins=["*"])        [All origins allowed — ⚠️ insecure for production]
    │
    ├─ Router Registration [main.py:85-90]
    │    ├─ app.include_router(auth_router, prefix="/api")
    │    │    └─ Mounts at: /api/auth/github/login, /api/auth/github/callback, /api/auth/github/me, /api/auth/github/logout
    │    ├─ app.include_router(health_router, prefix="/api")
    │    │    └─ Mounts at: /api/health
    │    ├─ app.include_router(import_router, prefix="/api/import")
    │    │    └─ Mounts at: POST /api/import
    │    └─ app.include_router(repo_router, prefix="/api/repos")
    │         └─ Mounts at: /api/repos/* (30+ routes)
    │
    └─ [Application Ready — accepting requests]
```

**Files involved in startup:**
- `backend/main.py` (lines 1–93)
- `backend/logger.py` (`setup_logging`)
- `backend/database.py` (`engine`, `Base`)
- `backend/task_manager.py` (`task_manager`)
- `backend/services/queue.py` (`InMemoryQueue.start`)
- `backend/services/worker.py` (`AnalysisWorker`)
- `backend/routers/__init__.py`, `auth.py`, `health.py`, `repo.py`

---

## 2. HTTP Request Lifecycle

### Standard Authenticated Request (e.g., GET /api/repos)

```
Browser
  │ HTTP GET /api/repos (with cookie: access_token=<JWT>)
  ▼
Next.js Dev Server (localhost:3000)
  │ Rewrite rule: /api/* → http://127.0.0.1:8000/api/*  [next.config.ts]
  │ Forwards request with all headers (including Cookie)
  ▼
FastAPI (localhost:8000)
  │ CORSMiddleware checks origin
  │ Router dispatches to list_repos() handler  [repo.py:204]
  │ Depends(get_db) → SessionLocal()           [database.py]
  │ Depends(get_current_user)                  [dependencies/auth.py]
  │   └─ Reads cookie "access_token"
  │   └─ jwt.decode() → user_id
  │   └─ db.query(User).filter(User.id == user_id).first()
  │   └─ Returns User object
  │
  ├─ Handler executes list_repos(db, current_user)
  │   └─ db.query(Repository).filter(Repository.user_id == current_user.id).all()
  │   └─ For each repo: query Analysis, AnalysisArtifact for language
  │   └─ Returns {"repositories": [...]}
  ▼
Browser receives JSON response
```

### SSE (Server-Sent Events) Request Lifecycle

```
Browser (EventSource)
  │ GET /api/repos/{repo_name}/tasks/stream
  ▼
FastAPI stream_tasks()  [repo.py:41]
  │ Depends(get_current_user)  [auth cookie validated]
  │ Creates asyncio.Queue via task_manager.subscribe(user_id, repo_name)
  │ event_generator() starts:
  │   1. Sends current task state immediately (from memory or DB)
  │   2. Loops: await queue.get(timeout=30s)
  │      - If data: yield {"data": payload}
  │      - If timeout: yield {"comment": "keepalive"}
  │      - If client disconnects: break
  ▼
EventSource in browser receives events
  │ useTaskStatus.js: es.onmessage → JSON.parse → setStatus()
```

### Background Job Lifecycle (Repository Import)

```
Browser → POST /api/import {"url": "https://github.com/owner/repo"}
  │
  ▼
import_repo()  [repo.py:107]
  │ Validates URL starts with "https://github.com/"
  │ await check_repo_limits(owner, repo_name, token)  [github.py]
  │ Creates Repository record in DB if not exists
  │ Creates Analysis record (status="Queued")
  │ Creates AnalysisJob record (status="Queued")
  │ await repo_queue.enqueue(job.id)   [services/queue.py]
  │ Returns {"status": "Queued", ...}
  │
  └─ Background Thread (asyncio.to_thread via InMemoryQueue)
       ▼
  AnalysisWorker.process(job_id)  [services/worker.py]
       ├─ job.status = "Downloading"; db.commit()
       ├─ await download_repo_zipball(...)  [github.py]
       │    └─ Streams zipball, extracts to /tmp/repo-analysis/job_{id}_{repo}/
       ├─ job.status = "Analyzing"; db.commit()
       ├─ run_analysis() [in asyncio.to_thread]:
       │    ├─ AnalysisEngine.run(repo_name)
       │    ├─ PatternRecognitionEngine.run(model)
       │    ├─ CapabilityBuilderEngine.run(model)
       │    ├─ FeatureReconstructionEngine.run(model)
       │    └─ serialize_rim(model) → JSON bytes
       ├─ job.status = "Saving"; db.commit()
       ├─ Saves AnalysisArtifact(type="core_model", blob_data=json_bytes)
       ├─ analysis.status = "Completed"
       ├─ job.status = "Completed"; db.commit()
       └─ shutil.rmtree(target_dir)  [cleanup temp files]
```

**Note:** The worker does NOT call `task_manager.notify()` at any point. This means the frontend polling via `scan()` / SSE is required to know when analysis completes. The SSE stream has no producer other than the explicit `set_task_status()` calls from within background tasks triggered by individual endpoints (index, semantic-index, summary/generate).

---

## 3. Frontend Routing Lifecycle

```
User navigates to /dashboard
  ▼
app/dashboard/page.tsx (Client Component)
  │ useEffect → repositoryService.getAll() → GET /api/repos
  │ setRepos(data.repositories)
  ▼
User clicks repo card → navigate to /repository/{repoName}
  ▼
app/repository/[repoName]/layout.tsx (Server Component)
  │ Renders Sidebar with repoName
  │ Renders {children} (page.tsx)
  ▼
app/repository/[repoName]/page.tsx (Client Component)
  │ useEffect → repositoryService.scan(repoName) → GET /api/repos/{repoName}/scan
  │ If status="processing" → setTimeout(fetchScanData, 3000) [polling]
  │ If status="completed" → renders RepositoryOverview component
  ▼
User clicks Sidebar tab (e.g., "Health")
  ▼
Next.js navigates to /repository/{repoName}/health
  ▼
app/repository/[repoName]/[tab]/page.tsx
  │ switch(tab) → case 'health': return <RepositoryHealth repoName={repoName} />
  ▼
RepositoryHealth.jsx
  │ useEffect → fetch(`/api/repos/${repoName}/health/scores`)
  │ Renders health score UI
```
