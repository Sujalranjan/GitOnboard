# Function Analysis

**Confidence:** High Confidence  
**Cross-reference:** [04-function-call-graph.md](./04-function-call-graph.md), [06-dead-code-report.md](./06-dead-code-report.md)

---

## Backend: `backend/main.py`

| Function | Signature | Status | Notes |
|----------|-----------|--------|-------|
| `cleanup_tmp_dirs()` | `() → None` | ✅ Used | Called in lifespan startup |
| `lifespan(app)` | `async (FastAPI) → AsyncGenerator` | ✅ Used | FastAPI `@asynccontextmanager` lifespan |
| `read_root()` | `() → dict` | ✅ Used | `GET /` endpoint |

---

## Backend: `backend/config.py`

| Class/Property | Status | Notes |
|----------------|--------|-------|
| `Settings` | ✅ Used | Pydantic BaseSettings |
| `Settings.database_url` | ✅ Used | `@property` — used by `database.py` |
| `Settings.frontend_url` | ✅ Used | `@property` — used by `routers/auth.py` |
| `settings` (singleton) | ✅ Used | Imported by config consumers |

---

## Backend: `backend/task_manager.py`

| Function | Status | Notes |
|----------|--------|-------|
| `TaskManager.__init__()` | ✅ Used | |
| `TaskManager.set_loop()` | ✅ Used | Called in lifespan |
| `TaskManager._key()` | ✅ Used | Internal helper |
| `TaskManager.notify()` | ✅ Used | Called by `set_task_status()` in repo.py |
| `TaskManager.get_all()` | ✅ Used | Called by SSE endpoint and `get_tasks` |
| `TaskManager.subscribe()` | ✅ Used | Called by `stream_tasks()` |
| `TaskManager.unsubscribe()` | ✅ Used | Called in SSE `finally` block |
| `task_manager` (singleton) | ✅ Used | Imported by main.py and repo.py |

---

## Backend: `backend/llm_service.py`

| Function | Status | Notes |
|----------|--------|-------|
| `LLMService.__init__()` | ✅ Used | |
| `LLMService.generate_summary()` | ✅ Used | Called by `generate_summary` route handler |
| `LLMService.generate_explanation()` | ✅ Used | Called by `explain_trace` route handler |
| `LLMService._build_prompt()` | ✅ Used | Called internally by `generate_summary` |
| `llm_service` (singleton) | ✅ Used | Imported lazily inside repo.py handlers |

---

## Backend: `backend/dependencies/auth.py`

| Function | Status | Notes |
|----------|--------|-------|
| `get_current_user(request, db)` | ✅ Used | `Depends()` in every authenticated route. Reads `access_token` cookie, decodes JWT, queries User. |

---

## Backend: `backend/services/github.py`

| Function | Signature | Status | Notes |
|----------|-----------|--------|-------|
| `get_github_client(token)` | `(str) → AsyncContextManager[httpx.AsyncClient]` | ✅ Used | Called by `check_repo_limits` and `download_repo_zipball` |
| `check_repo_limits(owner, repo, branch, token)` | `async (...) → dict` | ✅ Used | Called by `import_repo` |
| `download_repo_zipball(owner, repo, branch, target_dir, token)` | `async (...) → int` | ✅ Used | Called by `AnalysisWorker.process()` |
| `fetch_file_content(owner, repo, branch, filepath, token)` | `async (...) → str` | ✅ Used | Called by `parse_repo_file` route |

---

## Backend: `backend/services/github_oauth.py`

| Function | Status | Notes |
|----------|--------|-------|
| `get_github_login_url()` | ✅ Used | Called by `github_login` route |
| `exchange_code_for_token(code)` | ✅ Used | Called by `github_callback` |
| `fetch_user_profile(access_token)` | ✅ Used | Called by `github_callback` |
| `get_or_create_user(db, github_data, access_token)` | ✅ Used | Called by `github_callback` |
| `create_jwt(user)` | ✅ Used | Called by `github_callback` |

---

## Backend: `backend/services/worker.py`

| Function | Status | Notes |
|----------|--------|-------|
| `_serialize_dataclass(obj)` | ⚠️ Partially Used | Defined but `run_analysis()` now returns `{"core_model": bytes}` — the dict branch using this serializer is never hit because all results are `bytes`. Function is effectively dead. |
| `AnalysisWorker.process(job_id)` | ✅ Used | Core background job processor |
| `run_analysis()` [inner closure] | ✅ Used | Called via `asyncio.to_thread` |

---

## Backend: `backend/routers/repo.py` — Selected Key Functions

| Function | Route | Status | Notes |
|----------|-------|--------|-------|
| `get_tasks()` | GET `/{repo_name}/tasks` | ✅ Used | Returns task status snapshot |
| `stream_tasks()` | GET `/{repo_name}/tasks/stream` | ✅ Used | SSE stream handler |
| `import_repo()` | POST `/import` | ✅ Used | |
| `reanalyze_repo()` | POST `/{repo_name}/reanalyze` | ✅ Used | |
| `list_repos()` | GET `/` | ✅ Used | |
| `delete_repo()` | DELETE `/{repo_name}` | ✅ Used | |
| `_get_latest_analysis()` | (helper) | ✅ Used | 15+ callers in same file |
| `scan_repo()` | GET `/{repo_name}/scan` | ✅ Used | |
| `parse_repo_file()` | GET `/{repo_name}/parse` | ✅ Used | |
| `get_dependencies()` | GET `/{repo_name}/dependencies` | ✅ Used | |
| `get_call_graph()` | GET `/{repo_name}/call-graph` | ✅ Used | |
| `get_symbols()` | GET `/{repo_name}/symbols` | ✅ Used | |
| `get_stats()` | GET `/{repo_name}/stats` | ✅ Used | |
| `get_health_findings()` | GET `/{repo_name}/health/findings` | ✅ Used | |
| `get_health_cycles()` | GET `/{repo_name}/health/cycles` | ⚠️ Low Usage | Not called by any frontend component |
| `get_health_scores()` | GET `/{repo_name}/health/scores` | ✅ Used | |
| `get_health_metrics()` | GET `/{repo_name}/health/metrics` | ✅ Used | |
| `get_or_build_model()` | (helper) | ✅ Used (critical) | Called 20+ times, deserializes full RIM each call |
| `get_task_status()` | (helper) | ✅ Used | DB query for task status |
| `set_task_status()` | (helper) | ✅ Used | DB write + SSE notify |
| `get_architecture()` | GET `/{repo_name}/architecture` | ✅ Used | |
| `index_repo()` | POST `/{repo_name}/index` | ✅ Used | |
| `search_repo()` | GET `/{repo_name}/search` | ✅ Used | |
| `index_symbols()` | POST `/{repo_name}/symbols/index` | ⚠️ Unused frontend | Frontend uses `SymbolExplorer` which calls `/symbols/search` directly without indexing |
| `search_symbols()` | GET `/{repo_name}/symbols/search` | ✅ Used | |
| `get_summary()` | GET `/{repo_name}/summary` | ✅ Used | |
| `generate_summary()` | POST `/{repo_name}/summary/generate` | ✅ Used | |
| `semantic_status()` | GET `/{repo_name}/semantic-status` | ✅ Used | |
| `semantic_index()` | POST `/{repo_name}/semantic-index` | ✅ Used | |
| `semantic_search()` | GET `/{repo_name}/semantic-search` | ✅ Used | |
| `graph_search()` | GET `/{repo_name}/graph/search` | ✅ Used | |
| `graph_query()` | POST `/{repo_name}/graph/query` | ✅ Used | |
| `get_health_layers()` | GET `/{repo_name}/health/layers` | ⚠️ Unused frontend | No component calls this |
| `get_health_dependencies()` | GET `/{repo_name}/health/dependencies` | ⚠️ Unused frontend | No component calls this |
| `get_health_dead_code()` | GET `/{repo_name}/health/dead-code` | ⚠️ Unused frontend | No component calls this |
| `get_health_smells()` | GET `/{repo_name}/health/smells` | ✅ Used | Called by RepositoryAnalysis.jsx |
| `trace_feature()` | GET `/{repo_name}/trace` | ✅ Used | |
| `explain_trace()` | POST `/{repo_name}/trace/explain` | ✅ Used | |
| `enqueue_job()` | (helper) | ⚠️ **DEAD** | Defined at line 97, never called anywhere |
| `get_chroma_collection()` | (helper) | ✅ Used | Called by semantic_search and trace_feature |

---

## Frontend: `services/api.js`

| Function | Status | Notes |
|----------|--------|-------|
| `fetchAPI(endpoint, options)` | ✅ Used | Base HTTP function — used by `repository.js` |

## Frontend: `services/repository.js`

| Function | Status | Notes |
|----------|--------|-------|
| `repositoryService.getAll()` | ✅ Used | Dashboard, RepositoryList |
| `repositoryService.delete()` | ✅ Used | Dashboard |
| `repositoryService.scan()` | ✅ Used | repo page, ExplorerView |
| `repositoryService.parseFile()` | ✅ Used | ExplorerView |
| `repositoryService.import()` | ✅ Used | Dashboard |
| `repositoryService.reanalyze()` | ✅ Used | Dashboard, RepositoryOverview |

## Frontend: `hooks/useTaskStatus.js`

| Function | Status | Notes |
|----------|--------|-------|
| `useTaskStatus(repoName, taskName)` | ✅ Used | Used by Search, SemanticSearch, RepositorySummary |

## Frontend: `utils/graphBuilder.js`

| Function | Status |
|----------|--------|
| `buildVisibleGraph()` | ✅ Used by DependencyGraph.jsx |

## Frontend: `utils/layout.js`

| Function | Status |
|----------|--------|
| `layoutGraph()` | ✅ Used by DependencyGraph.jsx |
| `applyLocalRelaxation()` | ✅ Used by DependencyGraph.jsx |
| `checkIntersection()` (internal) | ✅ Used internally |

## Frontend: `utils/vfs.js`

| Function | Status |
|----------|--------|
| `buildVFS()` | ✅ Used by DependencyGraph.jsx |
| `buildNodePathMap()` | ✅ Used |
| `calculateVisualComplexity()` | ✅ Used |
| `getAutoExpandedPaths()` | ✅ Used |

## Frontend: `utils/graph.js`

| Status | Evidence |
|--------|---------|
| ⚠️ **ENTIRELY DEAD** | No component imports from `utils/graph.js`. Grep confirms zero imports. |
