# Module Dependency Graph

**Confidence:** Verified (traced via imports)  
**Cross-reference:** [01-project-architecture.md](./01-project-architecture.md)

---

## Backend Module Import Graph

### Core Layer (no internal deps)
- `backend/config.py` — imports: `pydantic_settings`
- `backend/logger.py` — imports: `logging`
- `backend/intelligence/rim/enums.py` — imports: `enum`
- `backend/intelligence/rim/location.py` — imports: `pydantic`
- `backend/intelligence/rim/identity.py` — imports: `hashlib`, `uuid`

### Data Layer
- `backend/database.py` → `config.py`
- `backend/models/user.py` → `database.py`
- `backend/models/repository.py` → `database.py`

### Service Layer
- `backend/services/github_oauth.py` → `config.py`, `models/user.py`, `httpx`, `jwt`
- `backend/services/github.py` → `httpx`, `zipfile`, `fastapi`
- `backend/services/queue.py` → `asyncio` (abstract)
- `backend/services/worker.py` → `database.py`, `models/*`, `services/queue.py`, `services/github.py`, `intelligence/engine/orchestration/pipeline.py`, `intelligence/patterns/engine.py`, `intelligence/capabilities/engine.py`, `intelligence/features/engine.py`, `intelligence/rim/serialization.py`

### RIM Data Model Layer
```
rim/repository.py → rim/entity.py → rim/enums.py, rim/location.py
                  → rim/relationship.py
                  → rim/metadata.py
                  → patterns/model.py → pydantic
                  → capabilities/model.py → pydantic
                  → features/model.py → pydantic
```

### Analysis Engine Layer (Active)
```
engine/orchestration/pipeline.py
  → engine/scanner/scanner.py → engine/scanner/manifest.py, engine/scanner/detector.py
  → engine/parser/manager.py → engine/parser/providers/python.py, typescript.py, java.py, base.py
  → engine/analyzers/__init__.py
       → engine/analyzers/symbol.py → rim/*, engine/analyzers/base.py
       → engine/analyzers/callgraph.py → rim/*
       → engine/analyzers/imports.py → rim/*
       → engine/analyzers/dependency.py → rim/*
       → engine/analyzers/route.py → rim/*
       → engine/analyzers/type.py → rim/*
       → engine/analyzers/config.py → rim/*
       → engine/analyzers/test.py → rim/*
       → engine/analyzers/database.py → rim/*
  → rim/validation.py → rim/repository.py
```

### Router Layer
```
routers/repo.py
  → database.py, models/*, dependencies/auth.py
  → services/github.py
  → task_manager.py
  → intelligence/graphs/graph_query_service.py → rim/repository.py
  → intelligence/query_layer.py → rim/*
  → intelligence/feature_tracing.py → rim/*
  → intelligence/rim/serialization.py
  → intelligence/rim/enums.py
  → llm_service.py
  → main.py [circular!] (via enqueue_job() → from backend.main import repo_queue)

routers/auth.py
  → database.py, models/user.py, dependencies/auth.py, config.py
  → services/github_oauth.py

routers/health.py
  → database.py
```

### 🚨 Circular Dependency
**Evidence:** `routers/repo.py`, function `enqueue_job()` (lines 97-105):
```python
def enqueue_job(job_id: int):
    from backend.main import repo_queue  # ← imports from main.py
    import asyncio
    asyncio.create_task(repo_queue.enqueue(job_id))
```
`main.py` imports `routers/repo.py` (via `from backend.routers.repo import repo_router, import_router`).  
`repo.py` imports `main.py` (via `from backend.main import repo_queue`).

**This is a circular import.** It is deferred inside a function body to avoid import-time failure, but it is still architecturally fragile and `asyncio.create_task()` called from a non-async context will raise `RuntimeError`.

---

## Frontend Module Import Graph

### Services (no internal dependencies)
- `services/api.js` — no internal imports
- `services/repository.js` → `services/api.js`

### Hooks
- `hooks/useTaskStatus.js` — no internal imports (uses `EventSource` browser API)

### Utilities
- `utils/graphBuilder.js` — no internal imports
- `utils/layout.js` → `dagre` (npm)
- `utils/vfs.js` — no internal imports
- `utils/graph.js` — ⚠️ no internal imports, NOT imported by anything (dead)

### Common Components
- `components/common/Badge.jsx`, `Button.jsx`, `Card.jsx`, `LanguageIcons.jsx`, `Modal.jsx` — no internal imports

### Layout Components
- `components/layout/Header.jsx` → `components/common/Button.jsx`
- `components/layout/Sidebar.jsx` — no internal component imports

### Feature Components
- `components/DependencyGraph.jsx` → `utils/layout.js`, `utils/vfs.js`, `utils/graphBuilder.js`, `components/common/LanguageIcons.jsx`
- `components/CallExplorer.jsx` → `dagre` (npm)
- `components/ArchitectureExplorer.jsx` → `dagre` (npm)
- `components/SemanticSearch.jsx` → `hooks/useTaskStatus.js`
- `components/Search.jsx` → `hooks/useTaskStatus.js`
- `components/RepositorySummary.jsx` → `hooks/useTaskStatus.js`, `react-markdown`
- `components/repository/ExplorerView.jsx` → `services/repository.js`, `components/FileExplorer.jsx`, `components/CodeDetailsViewer.jsx`
- `components/repository/RepositoryOverview.jsx` → `components/common/*`, `components/common/LanguageIcons.jsx`

### Pages
- `app/layout.tsx` → `components/layout/Header.jsx`, `app/globals.css`
- `app/page.tsx` → `components/common/Button.jsx`, `components/common/Modal.jsx`
- `app/dashboard/page.tsx` → `services/repository.js`, `components/common/*`
- `app/repository/[repoName]/layout.tsx` → `components/layout/Sidebar.jsx`
- `app/repository/[repoName]/page.tsx` → `services/repository.js`, `components/repository/RepositoryOverview.jsx`
- `app/repository/[repoName]/[tab]/page.tsx` → all feature components
- `app/repository/[repoName]/trace/page.tsx` → `components/common/*`

---

## Orphaned Modules (Confirmed Not Imported by Active Code)

| Module | Evidence of No Import |
|--------|----------------------|
| `backend/intelligence/orchestrator/**` | Grep confirms zero imports from routers or worker |
| `backend/intelligence/visualization/**` | Grep confirms zero imports from routers or worker |
| `backend/intelligence/query/**` | Grep confirms zero imports from routers or worker |
| `backend/intelligence/experiences/**` | Grep confirms zero imports from routers or worker |
| `backend/intelligence/store/store.py` | Not imported anywhere in active paths |
| `backend/intelligence/graphs/call_graph.py` | Not imported (GraphQueryService is from `graph_query_service.py`) |
| `backend/intelligence/graphs/dependency_graph.py` | Not imported |
| `backend/intelligence/graphs/graph_view.py` | Not imported |
| `backend/intelligence/pipeline.py` | Old pipeline, not imported by worker.py |
| `backend/intelligence/parser.py` | LanguageParser (tree-sitter), not used by active pipeline |
| `backend/intelligence/stages/metadata_stage.py` | Not called from worker.py |
| `backend/intelligence/stages/metrics_stage.py` | Not called from worker.py |
| `backend/intelligence/rim/query.py` | Not imported anywhere |
| `src/analysis/**` | Entire package, no imports from backend/ |
| `frontend/components/CallGraph.jsx` | Not imported in any page |
| `frontend/components/ViewTabs.jsx` | Not imported anywhere |
| `frontend/components/RepositoryList.jsx` | Not imported anywhere |
| `frontend/utils/graph.js` | Not imported anywhere |
