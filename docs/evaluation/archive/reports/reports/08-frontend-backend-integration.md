# Frontend-Backend Integration Report

**Confidence:** Verified  
**Cross-reference:** [09-api-mapping.md](./09-api-mapping.md), [07-wiring-validation.md](./07-wiring-validation.md)

---

## 1. API Proxy Configuration

**File:** `frontend/next.config.ts`  
**Evidence:**
```typescript
async rewrites() {
  return [
    { source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }
  ];
}
```

**Status:** ✅ All frontend API calls use relative `/api/*` paths, which are proxied to the FastAPI backend. This is correct.

**⚠️ Bug:** `Header.jsx` bypasses this proxy by using the absolute URL `http://localhost:8000/api/auth/github/login`. This hardcodes port 8000 and breaks in any containerized or production environment.

---

## 2. Authentication Cookie Flow

| Step | Status | Notes |
|------|--------|-------|
| Login redirect | ⚠️ Broken (non-local) | `Header.jsx` hard-codes `http://localhost:8000` |
| Cookie setting after OAuth callback | ✅ Works | Backend sets `httponly=True` cookie |
| Cookie forwarding by Next.js proxy | ✅ Works | `rewrites()` forwards cookies |
| Cookie reading by backend | ✅ Works | `get_current_user()` reads `request.cookies.get("access_token")` |

---

## 3. Field Name Mismatches

### Issue I-01: `repository_path` field

`RepositoryList.jsx` (line 12) renders `repo.repository_path`:
```jsx
<p className="text-sm text-gray-700 font-mono truncate" title={repo.repository_path}>
  {repo.repository_path}
</p>
```

But `GET /api/repos` (repo.py:230) returns:
```python
results.append({
    "id": r.id,
    "project_name": repo_name,
    "url": r.url,       # ← this field, not "repository_path"
    "status": status,
    "import_time": ...,
    "language": language_str
})
```

**Impact:** `RepositoryList.jsx` will render `undefined` for the path. However, `RepositoryList.jsx` is **dead code** (never imported), so this bug has no current runtime impact. But `Dashboard/page.tsx` has its own card rendering and uses `repo.repository_path` too (line 92). Dashboard is **live** code. This means the Dashboard shows `undefined` for the path field.

**Evidence:** Dashboard `page.tsx` line 92:
```tsx
<p className="text-sm text-slate-600 font-mono bg-slate-50 p-2 rounded line-clamp-1">
  {repo.repository_path}
</p>
```
This renders as blank/undefined. The backend returns `url` not `repository_path`.

### Issue I-02: `import_time` field (minor)

Backend returns `import_time` as an ISO string. Dashboard uses `new Date(repo.import_time || Date.now())` which handles null gracefully.

---

## 4. SSE Integration

| Hook Call | Task Name Used | Backend Task Name Set | Matched? |
|-----------|---------------|----------------------|---------|
| `useTaskStatus(repoName, 'index')` | `'index'` | `'index'` (set_task_status in index_repo) | ✅ |
| `useTaskStatus(repoName, 'semantic')` | `'semantic'` | `'semantic_index'` (set_task_status in semantic_index) | ❌ |
| `useTaskStatus(repoName, 'summary')` | `'summary'` | `'summary'` (set_task_status in generate_summary) | ✅ |

---

## 5. Request Format Validation

| Endpoint | Frontend Sends | Backend Expects | Status |
|----------|----------------|-----------------|--------|
| `POST /api/import` | `{"url": "https://github.com/..."}` | `ImportRepoRequest(url: str)` | ✅ |
| `POST /api/repos/{name}/summary/generate` | `{}` (no body) | No body expected | ✅ |
| `POST /api/repos/{name}/semantic-index` | `{}` (no body) | No body expected | ✅ |
| `POST /api/repos/{name}/index` | `{}` (no body) | No body expected | ✅ |
| `POST /api/repos/{name}/reanalyze` | `{}` (no body) | No body expected | ✅ |
| `POST /api/repos/{name}/graph/query` | `{"function_name": "...", "direction": "..."}` | `GraphQueryRequest` model | ✅ |
| `POST /api/repos/{name}/trace/explain` | `{"feature_query": "...", "trace_data": {...}}` | Parsed from request JSON | ✅ |

---

## 6. Response Format Validation

| Endpoint | Frontend Expects | Backend Returns | Discrepancy? |
|----------|-----------------|-----------------|--------------|
| `GET /api/repos` | `data.repositories` array | `{"repositories": [...]}` | ✅ |
| `GET /api/repos/{name}/scan` | `json.status`, `json.hierarchy`, `json.overview` | All returned | ✅ |
| `GET /api/repos/{name}/health/scores` | `data.health_score`, `data.status`, `data.categories` | All returned | ✅ |
| `GET /api/repos/{name}/health/metrics` | Direct object with metric keys | `art.data` (raw artifact data) | ✅ (depends on analysis completeness) |
| `GET /api/repos/{name}/health/findings` | `data.findings` array | `{"findings": [...]}` | ✅ |
| `GET /api/repos/{name}/health/smells` | `data.smells` array | No `/health/smells` endpoint exists! | ❌ |
| `GET /api/repos/{name}/summary` | `data.summary`, `data.outdated` | `{"summary": ..., "outdated": False}` | ✅ |
| `GET /api/repos/{name}/dependencies` | `data.nodes`, `data.edges` | Returned by `get_dependencies` | ✅ |
| `GET /api/repos/{name}/graph/search` | `data.results` | `{"results": [...]}` | ✅ |
| `GET /api/repos/{name}/symbols/search` | `data.results` array | `{"results": [...]}` | ✅ |
| `GET /api/repos/{name}/trace` | `data.trace` (object with `flow`) | `{"trace": {...}}` | ✅ |

### Issue I-03: `/health/smells` endpoint missing

`RepositoryAnalysis.jsx` (line 17):
```javascript
fetch(`/api/repos/${repoName}/health/smells`)
```

The backend has NO `/health/smells` route. The `get_health_smells` function in `repo.py` exists:
```python
@repo_router.get("/{repo_name}/health/smells")
def get_health_smells(...)
```
Wait — this route DOES exist (verified at repo.py:565). `RepositoryAnalysis.jsx` should receive it. Re-examining...

**Corrected:** The route `GET /api/repos/{repo_name}/health/smells` is registered at repo.py:561. It queries the `"smells"` artifact type. **The endpoint exists and is correctly wired.** The `Analysis` component is functional.

---

## 7. Error Handling Consistency

| Frontend Component | Error Display | Backend Errors |
|--------------------|---------------|----------------|
| `RepositoryHealth.jsx` | Shows error string | 404 from `_get_latest_analysis` → `.message` shown |
| `Dashboard/page.tsx` | `console.error` + alert | No user-facing error for failed imports |
| `RepositoryOverview.jsx` | Shows error in red div | Properly handled |
| `SemanticSearch.jsx` | Shows error string | Partially handled |
| `Search.jsx` | Shows error string | Properly handled |

**Issue I-04:** `Dashboard/page.tsx` `handleImport` shows `(err as any).message` which may expose internal error messages. `fetchAPI` in `api.js` converts API errors to JavaScript `Error` objects with the backend's error detail. This detail could expose internal information (e.g., "Repository not found", "Rate limit exceeded") to users, which is acceptable but should be validated.

---

## 8. Integration Health Summary

| Integration | Severity | Description |
|------------|---------|-------------|
| Login redirect hard-coded URL | **P0** | Breaks auth in non-local envs |
| `repository_path` field mismatch | **P1** | Dashboard shows undefined for repo path |
| `semantic` vs `semantic_index` task name | **P1** | SSE spinner never clears in SemanticSearch |
| `allow_origins=["*"]` + `allow_credentials=True` | **P1** | CORS invalid combination |
| ChromaDB unindexed 500 error | **P2** | Not caught as HTTPException |
| `RepositoryList.jsx` dead (has I-01 bug) | **P2** | Dead code, low priority |
