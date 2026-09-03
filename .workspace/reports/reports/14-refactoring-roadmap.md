# Refactoring Roadmap

**Confidence:** High Confidence  
**Cross-reference:** [12-architectural-smells.md](./12-architectural-smells.md), [13-risk-assessment.md](./13-risk-assessment.md)

---

## Priority 0 — Immediate Security Fixes (Do Today)

### Task 0.1: Rotate Committed Secrets
**Risk:** R-01  
**Files:** `.env`, GitHub OAuth settings  
1. Go to GitHub Developer Settings → OAuth Apps → Revoke `Ov23linDXTm2BnTp1U7e`
2. Generate new `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`
3. Generate a new `JWT_SECRET` (`openssl rand -base64 64`)
4. Add `.env` to `.gitignore`
5. Remove `.env` from git history: `git filter-repo --invert-paths --path .env`
6. Update `.env.example` if needed

**Effort:** 30 minutes

### Task 0.2: Fix Login URL
**Risk:** R-03  
**File:** `frontend/components/layout/Header.jsx:58`  
```jsx
// Before:
window.location.href = "http://localhost:8000/api/auth/github/login"
// After:
window.location.href = "/api/auth/github/login"
```
**Effort:** 2 minutes

### Task 0.3: Fix Docker Compose Database URL
**Risk:** R-02  
**File:** `docker-compose.yml:21`  
```yaml
# Before:
- DATABASE_URL=postgresql://myuser:mypassword@postgres:5432/repository_intelligence
# After:
- LOCAL_DATABASE_URL=postgresql+psycopg://myuser:mypassword@postgres:5432/repository_intelligence
```
**Effort:** 2 minutes

---

## Priority 1 — High Impact Bug Fixes (This Sprint)

### Task 1.1: Fix Semantic Search SSE Task Name
**Risk:** R-08  
**File:** `frontend/components/SemanticSearch.jsx:4`  
```jsx
// Before:
const taskStatus = useTaskStatus(repoName, 'semantic');
// After:
const taskStatus = useTaskStatus(repoName, 'semantic_index');
```
**Effort:** 2 minutes

### Task 1.2: Fix Repository Path Field
**Risk:** R-12  
**File:** `frontend/app/dashboard/page.tsx`  
Change `repo.repository_path` to `repo.url` or extract repo name from `repo.url` as needed. OR update the backend to return a `repository_path` field derived from `repo.url`.
**Effort:** 10 minutes

### Task 1.3: Fix CORS Configuration
**Risk:** R-07  
**File:** `backend/main.py`  
```python
# Before:
allow_origins=["*"],
# After:
allow_origins=[settings.frontend_url],
```
**Effort:** 2 minutes

### Task 1.4: Add JWT Expiration
**Risk:** R-04  
**File:** `backend/services/github_oauth.py`  
```python
payload = {
    "user_id": user.id,
    "exp": datetime.utcnow() + timedelta(days=7)
}
```
**Effort:** 5 minutes

### Task 1.5: Add `algorithms` to JWT Decode
**Risk:** R-10 (PyJWT)  
**File:** `backend/dependencies/auth.py`  
```python
# Before:
decoded = jwt.decode(token, settings.jwt_secret)
# After:
decoded = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
```
**Effort:** 2 minutes

### Task 1.6: Add Cookie Security Flags
**Risk:** R-15  
**File:** `backend/routers/auth.py` (wherever `set_cookie` is called)  
```python
response.set_cookie(
    "access_token", jwt_token,
    httponly=True,
    secure=settings.deployment_type == "PROD",
    samesite="lax"
)
```
**Effort:** 5 minutes

---

## Priority 2 — Performance & Reliability (Next Sprint)

### Task 2.1: Cache `get_or_build_model()`
**Risk:** R-05  
**File:** `backend/routers/repo.py`  

Implement a module-level LRU cache:
```python
from functools import lru_cache
_model_cache: dict[tuple, QueryLayer] = {}  # (repo_name, analysis_id) → QueryLayer

def get_or_build_model(repo_name: str, db: Session, current_user: User) -> QueryLayer:
    repo, analysis = _get_latest_analysis(repo_name, db, current_user)
    cache_key = (repo_name, analysis.id)
    if cache_key in _model_cache:
        return _model_cache[cache_key]
    # ... deserialize and build ...
    _model_cache[cache_key] = query_layer
    return query_layer
```
Note: Invalidate `_model_cache` entries when a new analysis completes.  
**Effort:** 2 hours

### Task 2.2: Fix ChromaDB Multi-User Isolation
**Risk:** R-06  
**File:** `backend/routers/repo.py` — all ChromaDB collection name references  
Change `f"{repo_name}_index"` to `f"{current_user.id}_{repo_name}_index"` everywhere.  
**Effort:** 15 minutes

### Task 2.3: Add LLM Request Timeout
**Risk:** R-11  
**File:** `backend/llm_service.py`  
```python
response = requests.post(url, json=payload, timeout=60)
```
**Effort:** 2 minutes

### Task 2.4: Wire SSE Notifications to Analysis Worker
**Risk:** R-07 (A-07 smell)  
**File:** `backend/services/worker.py`  
Call `task_manager.notify(user_id, repo_name, "analysis", status)` at each stage. Requires passing `user_id` and `repo_name` into `AnalysisWorker.process()` or retrieving them from the job.  
**Effort:** 1 hour

---

## Priority 3 — Code Quality (Maintenance Sprint)

### Task 3.1: Delete Dead Code
**Risk:** R-09, R-20  

Files to delete (evidence in [06-dead-code-report.md](./06-dead-code-report.md)):
- `backend/main.py.orig`
- `backend/intelligence/pipeline.py`
- `backend/intelligence/parser.py`
- `backend/intelligence/stages/`
- `backend/intelligence/store/`
- `backend/intelligence/orchestrator/`
- `backend/intelligence/visualization/`
- `backend/intelligence/query/`
- `backend/intelligence/experiences/`
- `backend/intelligence/rim/query.py`
- `backend/intelligence/graphs/call_graph.py`
- `backend/intelligence/graphs/dependency_graph.py`
- `backend/intelligence/graphs/graph_view.py`
- `src/analysis/` (entire directory)
- `tests/` (root level — tests dead code)
- `frontend/components/CallGraph.jsx`
- `frontend/components/ViewTabs.jsx`
- `frontend/components/RepositoryList.jsx`
- `frontend/utils/graph.js`
- `enqueue_job()` function in `backend/routers/repo.py`
- `_serialize_dataclass()` in `backend/services/worker.py`

**Effort:** 2 hours

### Task 3.2: Split `repo.py` God Router
**Risk:** A-01  
Create sub-routers and split `repo.py` into focused modules:

| New File | Routes |
|----------|--------|
| `routers/repos.py` | list, delete, reanalyze, import, scan |
| `routers/health.py` | health/scores, health/metrics, health/findings, health/smells, health/cycles |
| `routers/search.py` | index, search, symbols/index, symbols/search |
| `routers/semantic.py` | semantic-status, semantic-index, semantic-search |
| `routers/graph.py` | dependencies, call-graph, graph/search, graph/query, architecture |
| `routers/summary.py` | summary, summary/generate |
| `routers/trace.py` | trace, trace/explain |
| `routers/stream.py` | tasks, tasks/stream |

Move shared helpers to `backend/services/analysis_service.py`.  
**Effort:** 1-2 days

### Task 3.3: Standardize Frontend API Layer
**Risk:** A-05  
Extend `services/repository.js` to cover all endpoints. Update all components that call `fetch()` directly.  
**Effort:** 4 hours

### Task 3.4: Implement a Real Health Score Engine
**Risk:** R-13  
Replace the synthetic health score formula with real metrics:
- Cyclomatic complexity (from metrics artifact)
- Dependency depth (from dependencies artifact)
- Test coverage (from test artifact)
- Code duplication (from patterns artifact)

**Effort:** 2 days

---

## Estimated Timeline

| Priority | Work | Estimated Time |
|----------|------|----------------|
| P0 (Security) | Tasks 0.1-0.3 | 1 hour |
| P1 (Bug fixes) | Tasks 1.1-1.6 | 2-3 hours |
| P2 (Performance) | Tasks 2.1-2.4 | 1-2 days |
| P3 (Code quality) | Tasks 3.1-3.4 | 1 week |
| **Total** | | **~10 working days** |
