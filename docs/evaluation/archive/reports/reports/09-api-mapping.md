# API Endpoint Mapping

**Confidence:** Verified  
**Cross-reference:** [08-frontend-backend-integration.md](./08-frontend-backend-integration.md)

---

## Complete API Route Inventory

### Authentication Routes (`auth_router`, prefix: `/api`)

| Method | Path | Handler | Auth | Frontend Consumer |
|--------|------|---------|------|-------------------|
| GET | `/api/auth/github/login` | `github_login()` | No | `Header.jsx` (⚠️ hard-coded absolute URL) |
| GET | `/api/auth/github/callback` | `github_callback()` | No | GitHub OAuth redirect |
| GET | `/api/auth/github/me` | `get_current_user_info()` | Yes | `Header.jsx` via `fetch('/api/auth/github/me')` |
| POST | `/api/auth/github/logout` | `logout()` | Yes | `Header.jsx` via `fetch('/api/auth/github/logout')` |

### Health Route (`health_router`, prefix: `/api`)

| Method | Path | Handler | Auth | Frontend Consumer |
|--------|------|---------|------|-------------------|
| GET | `/api/health` | `check_health()` | No | Not called by frontend |

### Import Route (`import_router`, prefix: `/api/import`)

| Method | Path | Handler | Auth | Frontend Consumer |
|--------|------|---------|------|-------------------|
| POST | `/api/import` | `import_repo()` | Yes | `repositoryService.import()` → `dashboard/page.tsx` |

### Repository Routes (`repo_router`, prefix: `/api/repos`)

| Method | Path | Handler Function | Auth | Frontend Consumer |
|--------|------|-----------------|------|-------------------|
| GET | `/api/repos` | `list_repos()` | Yes | `repositoryService.getAll()` |
| DELETE | `/api/repos/{repo_name}` | `delete_repo()` | Yes | `repositoryService.delete()` |
| POST | `/api/repos/{repo_name}/reanalyze` | `reanalyze_repo()` | Yes | `repositoryService.reanalyze()` |
| GET | `/api/repos/{repo_name}/tasks` | `get_tasks()` | Yes | (internal polling) |
| GET | `/api/repos/{repo_name}/tasks/stream` | `stream_tasks()` | Yes | `useTaskStatus.js` (EventSource) |
| GET | `/api/repos/{repo_name}/scan` | `scan_repo()` | Yes | `repositoryService.scan()` |
| GET | `/api/repos/{repo_name}/parse` | `parse_repo_file()` | Yes | `repositoryService.parseFile()` → ExplorerView |
| GET | `/api/repos/{repo_name}/dependencies` | `get_dependencies()` | Yes | `DependencyGraph.jsx` |
| GET | `/api/repos/{repo_name}/call-graph` | `get_call_graph()` | Yes | ⚠️ Not directly called by frontend (CallExplorer uses `/graph/search` and `/graph/query`) |
| GET | `/api/repos/{repo_name}/symbols` | `get_symbols()` | Yes | ⚠️ Not called by frontend (SymbolExplorer uses `/symbols/search`) |
| GET | `/api/repos/{repo_name}/stats` | `get_stats()` | Yes | `RepositoryOverview.jsx` via direct `fetch` |
| GET | `/api/repos/{repo_name}/health/findings` | `get_health_findings()` | Yes | `RepositoryAnalysis.jsx`, `RepositoryOverview.jsx` |
| GET | `/api/repos/{repo_name}/health/cycles` | `get_health_cycles()` | Yes | ⚠️ Not called by frontend |
| GET | `/api/repos/{repo_name}/health/scores` | `get_health_scores()` | Yes | `RepositoryHealth.jsx`, `RepositoryOverview.jsx` |
| GET | `/api/repos/{repo_name}/health/metrics` | `get_health_metrics()` | Yes | `RepositoryMetrics.jsx` |
| GET | `/api/repos/{repo_name}/health/smells` | `get_health_smells()` | Yes | `RepositoryAnalysis.jsx` |
| GET | `/api/repos/{repo_name}/health/layers` | `get_health_layers()` | Yes | ⚠️ Not called by frontend |
| GET | `/api/repos/{repo_name}/health/dependencies` | `get_health_dependencies()` | Yes | ⚠️ Not called by frontend |
| GET | `/api/repos/{repo_name}/health/dead-code` | `get_health_dead_code()` | Yes | ⚠️ Not called by frontend |
| GET | `/api/repos/{repo_name}/architecture` | `get_architecture()` | Yes | `ArchitectureExplorer.jsx` |
| POST | `/api/repos/{repo_name}/index` | `index_repo()` | Yes | `Search.jsx` |
| GET | `/api/repos/{repo_name}/search` | `search_repo()` | Yes | `Search.jsx` |
| POST | `/api/repos/{repo_name}/symbols/index` | `index_symbols()` | Yes | ⚠️ Not called by frontend |
| GET | `/api/repos/{repo_name}/symbols/search` | `search_symbols()` | Yes | `SymbolExplorer.jsx` |
| GET | `/api/repos/{repo_name}/summary` | `get_summary()` | Yes | `RepositorySummary.jsx` |
| POST | `/api/repos/{repo_name}/summary/generate` | `generate_summary()` | Yes | `RepositorySummary.jsx` |
| GET | `/api/repos/{repo_name}/semantic-status` | `semantic_status()` | Yes | `SemanticSearch.jsx` |
| POST | `/api/repos/{repo_name}/semantic-index` | `semantic_index()` | Yes | `SemanticSearch.jsx` |
| GET | `/api/repos/{repo_name}/semantic-search` | `semantic_search()` | Yes | `SemanticSearch.jsx` |
| GET | `/api/repos/{repo_name}/graph/search` | `graph_search()` | Yes | `CallExplorer.jsx` |
| POST | `/api/repos/{repo_name}/graph/query` | `graph_query()` | Yes | `CallExplorer.jsx` |
| GET | `/api/repos/{repo_name}/trace` | `trace_feature()` | Yes | `trace/page.tsx` |
| POST | `/api/repos/{repo_name}/trace/explain` | `explain_trace()` | Yes | `trace/page.tsx` |

---

## Summary Counts

| Category | Count |
|----------|-------|
| Total routes | 35 |
| Routes with frontend consumers | 27 |
| Backend-only routes (no frontend) | 8 |
| Routes with integration bugs | 3 |

---

## Backend-Only Routes (No Frontend Consumer)

These routes exist on the backend but are not called by any current frontend component:

| Route | Potential Purpose |
|-------|-----------------|
| `GET /api/health` | Health check for infrastructure (Docker healthcheck, load balancer) |
| `GET /api/repos/{name}/call-graph` | Superceded by `/graph/search` + `/graph/query` |
| `GET /api/repos/{name}/symbols` | Superceded by `/symbols/search` |
| `GET /api/repos/{name}/health/cycles` | Planned feature |
| `GET /api/repos/{name}/health/layers` | Planned feature |
| `GET /api/repos/{name}/health/dependencies` | Planned feature |
| `GET /api/repos/{name}/health/dead-code` | Planned feature |
| `POST /api/repos/{name}/symbols/index` | Frontend uses `/symbols/search` directly |

---

## Frontend API Calls Not Going Through `repositoryService`

Some components bypass `repositoryService` and call `fetch()` directly. This is inconsistent:

| Component | Direct Fetch URL |
|-----------|-----------------|
| `RepositoryHealth.jsx` | `/api/repos/${repoName}/health/scores` |
| `RepositoryMetrics.jsx` | `/api/repos/${repoName}/health/metrics` |
| `RepositoryAnalysis.jsx` | `/api/repos/${repoName}/health/findings`, `/health/smells` |
| `DependencyGraph.jsx` | `/api/repos/${repoName}/dependencies` |
| `CallExplorer.jsx` | `/api/repos/${repoName}/graph/search`, `/graph/query` |
| `ArchitectureExplorer.jsx` | `/api/repos/${repoName}/architecture` |
| `Search.jsx` | `/api/repos/${repoName}/index`, `/api/repos/${repoName}/search` |
| `SemanticSearch.jsx` | `/api/repos/${repoName}/semantic-status`, `/semantic-index`, `/semantic-search` |
| `RepositorySummary.jsx` | `/api/repos/${repoName}/summary`, `/summary/generate` |
| `SymbolExplorer.jsx` | `/api/repos/${repoName}/symbols/search` |
| `RepositoryOverview.jsx` | `/api/repos/${repoName}/health/scores`, `/stats`, `/health/findings` |
| `trace/page.tsx` | `/api/repos/${repoName}/trace`, `/trace/explain` |
| `Header.jsx` | `/api/auth/github/me`, `/api/auth/github/logout` |
