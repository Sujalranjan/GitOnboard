# Executive Summary

**Confidence:** Verified (all findings backed by source references)  
**Cross-reference:** All reports in this directory  

---

## Overview

The **Repository Intelligence Platform** is a full-stack web application that allows users to import GitHub repositories and explore their architecture through an AI-powered analysis pipeline. The stack is:

- **Frontend:** Next.js 16 (App Router, React 19, TypeScript)
- **Backend:** FastAPI (Python), PostgreSQL (SQLAlchemy), ChromaDB (semantic search), Ollama (LLM)
- **Infrastructure:** Docker Compose (local), no production deployment yet

The codebase is **ambitious and well-structured at the high level**, but has **critical wiring, authentication, and architectural issues** that prevent multiple features from working correctly.

---

## Critical Findings (P0 — Must Fix)

### 1. GitHub OAuth Login URL is Hard-Coded in Frontend
**File:** `frontend/components/layout/Header.jsx`, line ~58  
**Evidence:** `window.location.href = "http://localhost:8000/api/auth/github/login"` — this bypasses the Next.js reverse proxy and will fail in any environment other than local development where the backend is exposed on port 8000.  
**Impact:** Authentication is broken in all non-local environments (Docker, production, Vercel).

### 2. `main.py.orig` — 111KB Legacy Monolith Exists in the Repository
**File:** `backend/main.py.orig`  
**Evidence:** File exists at 111,596 bytes. Not imported. Contains the old monolithic architecture.  
**Impact:** Developer confusion, accidental regression risk, repo bloat.

### 3. `src/analysis/` — Entire Abandoned Framework Present
**Files:** `src/analysis/__init__.py`, `src/analysis/interfaces.py`, `src/analysis/plugins/`, `src/analysis/registry.py`, `src/analysis/runner.py`, `src/analysis/models/`  
**Evidence:** None of these modules are imported by any file in `backend/`. The root `tests/` directory tests this framework, not the current backend.  
**Impact:** High confusion for developers; root-level `tests/` are testing dead code.

### 4. Docker Compose Uses Wrong Environment Variable Key
**File:** `docker-compose.yml`, line 21  
**Evidence:** Sets `DATABASE_URL=postgresql://...` but `backend/database.py` and `backend/config.py` read `LOCAL_DATABASE_URL` (with psycopg3 driver prefix). The Docker environment variable is never consumed.  
**Impact:** Backend **cannot connect to the database when run via Docker Compose**.

### 5. `CallGraph.jsx` Is a Completely Dead Component
**File:** `frontend/components/CallGraph.jsx`  
**Evidence:** The tab routing in `frontend/app/repository/[repoName]/[tab]/page.tsx` (case `'callgraph'`) renders `<CallExplorer>`, not `<CallGraph>`. `CallGraph.jsx` is never imported anywhere.

### 6. `repositoryService.scan()` Returns an Undocumented `repository_path` Field
**Evidence:** `frontend/components/RepositoryList.jsx` accesses `repo.repository_path` but the backend `GET /api/repos` endpoint (line 230 in `repo.py`) returns `url`, not `repository_path`. This field will be `undefined`. Similarly, `import_time` is returned but `RepositoryList.jsx` calls `new Date(repo.import_time)` which would work, but the Dashboard's card uses `repo.import_time || Date.now()`.

---

## High Severity Findings (P1)

| # | Finding | File | Severity |
|---|---------|------|---------|
| P1-1 | Call graph analyzer resolves callee IDs within same file only — cross-file calls produce dangling references | `engine/analyzers/callgraph.py` | High |
| P1-2 | `ViewTabs.jsx` is an unused component — the app uses Next.js file-based routing, not tab state | `components/ViewTabs.jsx` | High (dead code) |
| P1-3 | `RepositoryList.jsx` is a duplicate/unused component — Dashboard renders its own card grid inline | `components/RepositoryList.jsx` | High (dead code) |
| P1-4 | `SemanticSearch` component uses `useTaskStatus` hook wired to `'semantic'` task name, but the backend sets `task_manager.notify` with task name `'semantic_index'` — SSE status never updates the spinner | `SemanticSearch.jsx` + `repo.py:844` | High |
| P1-5 | `enqueue_job()` in `repo.py` calls `asyncio.create_task()` from non-async context (line 103) — this will raise a RuntimeError | `routers/repo.py` L97-105 | High |

---

## Medium Severity Findings (P2)

| # | Finding |
|---|---------|
| P2-1 | `backend/intelligence/orchestrator/` is a completely unused sub-package (intent analyzer, knowledge model, planner, providers, retrieval). Not called from anywhere. |
| P2-2 | `backend/intelligence/visualization/` is completely unused — no router calls it. |
| P2-3 | `backend/intelligence/query/` is completely unused — no router calls it. |
| P2-4 | `backend/intelligence/experiences/` is completely unused. |
| P2-5 | `backend/intelligence/store/store.py` is not used in any active code path. |
| P2-6 | Health score formula is a synthetic calculation from findings severity counts (not real metrics) — misleadingly labeled as "Maintainability", "Reliability", "Security". |
| P2-7 | `frontend/components/repository/RepositoryOverview.jsx` and `frontend/app/repository/[repoName]/page.tsx` both call `repositoryService.scan()` — duplicated logic. |
| P2-8 | `frontend/utils/graph.js` is unused — all graph components directly import `dagre`. |

---

## Integration Health Summary

| Feature | Frontend | Backend | Status |
|---------|----------|---------|--------|
| GitHub OAuth Login | Header.jsx | /api/auth/github/login | ⚠️ Hard-coded URL breaks non-local env |
| GitHub OAuth Callback | (redirect) | /api/auth/github/callback | ✅ Verified |
| Current User | Header.jsx | /api/auth/github/me | ✅ Connected |
| Logout | Header.jsx | /api/auth/github/logout | ✅ Connected |
| List Repositories | Dashboard, RepositoryList | GET /api/repos | ⚠️ Field name mismatch (`repository_path`) |
| Import Repository | Dashboard | POST /api/import | ✅ Connected |
| Delete Repository | Dashboard | DELETE /api/repos/:name | ✅ Connected |
| Re-analyze | Dashboard, RepositoryOverview | POST /api/repos/:name/reanalyze | ✅ Connected |
| Scan / Overview | RepositoryOverview, repo page | GET /api/repos/:name/scan | ✅ Connected |
| File Explorer | ExplorerView | GET /api/repos/:name/scan + /parse | ✅ Connected |
| Dependency Graph | DependencyGraph.jsx | GET /api/repos/:name/dependencies | ✅ Connected |
| Call Explorer | CallExplorer.jsx | GET /api/repos/:name/graph/search + /graph/query | ✅ Connected |
| Architecture Explorer | ArchitectureExplorer.jsx | GET /api/repos/:name/architecture | ✅ Connected |
| Search | Search.jsx | POST /api/repos/:name/index + GET /api/repos/:name/search | ✅ Connected |
| Symbol Explorer | SymbolExplorer.jsx | GET /api/repos/:name/symbols/search | ✅ Connected |
| Semantic Search | SemanticSearch.jsx | GET /api/repos/:name/semantic-status, POST /api/repos/:name/semantic-index, GET /api/repos/:name/semantic-search | ⚠️ SSE task name mismatch |
| AI Summary | RepositorySummary.jsx | GET /api/repos/:name/summary, POST /api/repos/:name/summary/generate | ✅ Connected |
| Health Scores | RepositoryHealth.jsx | GET /api/repos/:name/health/scores | ✅ Connected |
| Health Metrics | RepositoryMetrics.jsx | GET /api/repos/:name/health/metrics | ✅ Connected |
| Health Analysis | RepositoryAnalysis.jsx | GET /api/repos/:name/health/findings + /health/smells | ✅ Connected |
| Feature Tracing | trace/page.tsx | GET /api/repos/:name/trace, POST /api/repos/:name/trace/explain | ✅ Connected |
| Task SSE Stream | useTaskStatus.js, Search.jsx, SemanticSearch.jsx | GET /api/repos/:name/tasks/stream | ✅ Connected (with caveat above) |

---

## Architecture Quality Score

| Dimension | Score | Notes |
|-----------|-------|-------|
| Backend structure | 7/10 | Clean layering, but large orphaned sub-packages |
| Frontend structure | 6/10 | Good component decomposition, some dead code |
| API integration | 6/10 | Mostly wired, several mismatches |
| Authentication | 4/10 | Hard-coded URLs, HttpOnly cookie approach is correct |
| Test coverage | 2/10 | Root tests test dead code; backend tests exist but are in `backend/tests/` |
| Configuration | 4/10 | Docker compose env var mismatch, secrets in `.env` committed |
| Overall | **5/10** | Solid foundation but not production-ready |
