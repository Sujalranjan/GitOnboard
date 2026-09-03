# Wiring Validation

**Confidence:** Verified  
**Cross-reference:** [02-runtime-flow.md](./02-runtime-flow.md), [07-wiring-validation.md](./07-wiring-validation.md)

---

## 1. Dependency Injection Wiring (`Depends()`)

Every FastAPI route that uses `Depends()` was traced to its provider.

### `Depends(get_db)` — Database Session

| Provider | File | Wires To |
|----------|------|---------|
| `get_db()` | `backend/database.py` | `SessionLocal()` → yields `Session` → `session.close()` in finally |

**Status:** ✅ Correctly wired. Session is yielded and closed in a `finally` block.

### `Depends(get_current_user)` — Authentication

| Provider | File | Mechanism |
|----------|------|-----------|
| `get_current_user(request, db)` | `backend/dependencies/auth.py` | Reads `request.cookies.get("access_token")` → `jwt.decode(token, settings.jwt_secret)` → `db.query(User).filter(User.id == user_id).first()` |

**Status:** ✅ Correctly wired in all authenticated routes. Raises `HTTPException(401)` if token missing/invalid/user not found.

**⚠️ Warning:** JWT `algorithms` not explicitly set. `jwt.decode()` called without `algorithms` kwarg — may fail with newer PyJWT versions that require it. Verify PyJWT version compatibility.

### `Depends(get_current_user)` — Optional Auth (auth routes)

`/api/auth/github/me` and `/api/auth/github/logout` also use `get_current_user`. This is correct behavior.

---

## 2. Router Registration

All routers are registered in `backend/main.py`:

| Router Variable | Import Source | Prefix | Status |
|-----------------|---------------|--------|--------|
| `auth_router` | `routers.auth` | `/api` | ✅ Registered |
| `health_router` | `routers.health` | `/api` | ✅ Registered |
| `import_router` | `routers.repo` | `/api/import` | ✅ Registered |
| `repo_router` | `routers.repo` | `/api/repos` | ✅ Registered |

**Evidence:** `backend/main.py` lines 85-90:
```python
app.include_router(auth_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(import_router, prefix="/api/import")
app.include_router(repo_router, prefix="/api/repos")
```

---

## 3. Middleware Registration

| Middleware | Config | Status |
|-----------|--------|--------|
| `CORSMiddleware` | `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]` | ✅ Registered, ⚠️ `allow_origins=["*"]` with `allow_credentials=True` is invalid per CORS spec — browsers will reject preflight for credentialed cross-origin requests. Should use explicit frontend URL. |

**Evidence:** `backend/main.py` line 77:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    ...
)
```

---

## 4. Lifespan Event Wiring

| Event | Handler | Status |
|-------|---------|--------|
| Startup | `cleanup_tmp_dirs()` | ✅ |
| Startup | `Base.metadata.create_all(bind=engine)` | ✅ |
| Startup | `task_manager.set_loop()` | ✅ |
| Startup | `repo_queue.start()` | ✅ |
| Startup | Job recovery loop | ✅ |
| Shutdown | `repo_queue.stop()` | ✅ |

---

## 5. SSE Pub/Sub Wiring

```
set_task_status(repo_name, task_name, status, current_user, db)
  └─ task_manager.notify(current_user.id, repo_name, task_name, status)
       └─ Puts to asyncio.Queue for any subscribers at key (user_id, repo_name)

stream_tasks(repo_name, db, current_user)
  └─ task_manager.subscribe(current_user.id, repo_name)  → asyncio.Queue
  └─ event_generator():
       1. Gets current state: task_manager.get_all(user_id, repo_name)
       2. Loops: await queue.get(timeout=30)
       3. Yields SSE event

useTaskStatus(repoName, taskName) [frontend]
  └─ new EventSource("/api/repos/{repoName}/tasks/stream")
  └─ es.onmessage → JSON.parse(tasks) → tasks[taskName] → setStatus()
```

**Status:** ✅ Pub/sub mechanism is correctly wired end-to-end.

**⚠️ Bug (W-01):** `SemanticSearch.jsx` uses `useTaskStatus(repoName, 'semantic')` but backend sets task with name `'semantic_index'`. The key `'semantic'` will never match, so `tasks['semantic']` is always `undefined`, and the UI spinner never clears via SSE.

---

## 6. Background Task Queue Wiring

| Component | File | Status |
|-----------|------|--------|
| `InMemoryQueue.__init__()` | `services/queue.py` | ✅ Correctly configured |
| `InMemoryQueue.start()` | `services/queue.py` | ✅ Called at startup |
| `InMemoryQueue.stop()` | `services/queue.py` | ✅ Called at shutdown |
| `InMemoryQueue.enqueue(job_id)` | `services/queue.py` | ✅ Called from `import_repo()` |
| `AnalysisWorker.process(job_id)` | `services/worker.py` | ✅ Called by queue consumer |

**⚠️ Bug (W-02):** `enqueue_job()` in `repo.py` calls `asyncio.create_task(repo_queue.enqueue(job_id))`. 
1. `enqueue_job()` is never called (see D-15 in dead code report).
2. If it were called, `asyncio.create_task()` from a synchronous context would raise `RuntimeError: no running event loop`.

This is dead but dangerous. The actual call site (in `import_repo`) correctly uses `await repo_queue.enqueue(job.id)` in an async handler.

---

## 7. GitHub OAuth Flow Wiring

```
1. Browser → Button click → window.location.href = "http://localhost:8000/api/auth/github/login"
   ⚠️ BUG: Hard-coded URL, bypasses Next.js proxy

2. FastAPI GET /api/auth/github/login
   → get_github_login_url() → redirects to https://github.com/login/oauth/authorize

3. GitHub → GET /api/auth/github/callback?code=...&state=...
   → exchange_code_for_token(code) → GitHub POST /login/oauth/access_token
   → fetch_user_profile(token) → GitHub GET /user
   → get_or_create_user(db, data, token)
   → create_jwt(user) → JWT token (HS256)
   → response.set_cookie("access_token", jwt, httponly=True)
   → response.redirect_response to frontend_url

4. All subsequent requests: cookie "access_token" sent → get_current_user()
```

**Status:** ✅ Correct flow for HttpOnly cookie auth. ⚠️ Step 1 is broken for non-local environments.

---

## 8. ChromaDB Wiring

| Component | Status | Notes |
|-----------|--------|-------|
| `chromadb.PersistentClient(path=DATA_REPOS_PATH/chroma)` | ✅ Used | Created inside `semantic_index` and `get_chroma_collection` |
| `client.get_or_create_collection("repo_index")` | ✅ Used | Per-repo collection named `{repo_name}_index` (verified in semantic_index) |
| `get_chroma_collection()` | ✅ Used | Raises 404 if collection not found (i.e., not indexed yet) |
| `collection.add()` | ✅ Used | In background semantic indexing |
| `collection.query()` | ✅ Used | In `semantic_search` and `trace_feature` |

**⚠️ Bug (W-03):** `get_chroma_collection()` uses `client.get_collection(f"{repo_name}_index")` but `semantic_index()` creates with `client.get_or_create_collection(f"{repo_name}_index")`. Confirmed consistent. However, if semantic search is called before indexing, `get_collection()` will raise a `ValueError` (not caught as an HTTPException), causing a 500 error. Frontend `SemanticSearch.jsx` checks status first, so this is partially mitigated.
