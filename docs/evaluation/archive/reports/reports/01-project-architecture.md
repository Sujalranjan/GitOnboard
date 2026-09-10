# Project Architecture

**Confidence:** Verified  
**Cross-reference:** [02-runtime-flow.md](./02-runtime-flow.md), [03-module-dependency-graph.md](./03-module-dependency-graph.md)

---

## 1. Overall Project Structure

```
repository_intelligence_platform/
├── backend/                  # FastAPI application (PRIMARY)
│   ├── main.py               # Application entry point, lifespan, router registration
│   ├── main.py.orig          # ⚠️ Legacy 111KB monolith (NOT used)
│   ├── config.py             # Pydantic Settings configuration
│   ├── database.py           # SQLAlchemy engine, SessionLocal, Base, get_db()
│   ├── task_manager.py       # In-memory pub/sub for SSE notifications
│   ├── llm_service.py        # Ollama HTTP client wrapper
│   ├── logger.py             # Logging setup
│   ├── Dockerfile            # Backend container definition
│   ├── dependencies/
│   │   └── auth.py           # get_current_user() FastAPI dependency
│   ├── models/
│   │   ├── user.py           # User SQLAlchemy model
│   │   └── repository.py     # Repository, Analysis, AnalysisJob, AnalysisArtifact, TaskStatus
│   ├── routers/
│   │   ├── __init__.py       # Exports auth_router, health_router
│   │   ├── auth.py           # GitHub OAuth routes
│   │   ├── health.py         # Health check route
│   │   └── repo.py           # All repository analysis routes (1210 lines)
│   ├── services/
│   │   ├── github.py         # GitHub API client (download, check limits)
│   │   ├── github_oauth.py   # GitHub OAuth flow functions
│   │   ├── queue.py          # InMemoryQueue + WorkerInterface
│   │   └── worker.py         # AnalysisWorker (background job processor)
│   ├── intelligence/         # Repository Intelligence Model (RIM) Engine
│   │   ├── __init__.py       # Exports RepositoryBuilder, RelationshipBuilder, AnalysisPipeline, QueryLayer
│   │   ├── pipeline.py       # AnalysisPipeline (LEGACY — NOT USED by worker.py)
│   │   ├── parser.py         # LanguageParser (tree-sitter based — NOT USED by main pipeline)
│   │   ├── query_layer.py    # QueryLayer (in-memory entity index)
│   │   ├── feature_tracing.py # DeterministicTracer
│   │   ├── query_layer.py    # Used by all repo router endpoints
│   │   ├── engine/           # Active analysis engine
│   │   │   ├── orchestration/pipeline.py  # AnalysisEngine (ACTIVE entry point)
│   │   │   ├── analyzers/    # SymbolAnalyzer, ImportAnalyzer, CallGraphAnalyzer, etc.
│   │   │   ├── scanner/      # RepositoryScanner, LanguageDetector
│   │   │   ├── parser/       # ASTParserManager, Python/TS/JS/Java providers
│   │   │   ├── core/         # ⚠️ UNUSED sub-package (engine.py, scorecard_engine.py, context.py)
│   │   │   ├── model/        # ⚠️ UNUSED (intelligence.py)
│   │   │   └── providers/    # ⚠️ UNUSED (architecture_health, impact, risk)
│   │   ├── rim/              # Repository Intelligence Model data structures
│   │   │   ├── repository.py # RepositoryModel (Pydantic)
│   │   │   ├── entity.py     # Entity (Pydantic)
│   │   │   ├── relationship.py # Relationship (Pydantic)
│   │   │   ├── enums.py      # EntityType, RelationshipType (rich enums)
│   │   │   ├── location.py   # SourceLocation
│   │   │   ├── metadata.py   # RepositoryMetadata
│   │   │   ├── identity.py   # generate_entity_id(), generate_relationship_id()
│   │   │   ├── serialization.py # serialize_rim() / deserialize_rim()
│   │   │   ├── validation.py # RIMValidator
│   │   │   └── query.py      # ⚠️ Appears unused
│   │   ├── graphs/           # Graph query service
│   │   │   ├── graph_query_service.py  # GraphQueryService (ACTIVE)
│   │   │   ├── call_graph.py # ⚠️ UNUSED
│   │   │   ├── dependency_graph.py # ⚠️ UNUSED
│   │   │   └── graph_view.py # ⚠️ UNUSED
│   │   ├── patterns/         # Pattern recognition engine (ACTIVE)
│   │   ├── capabilities/     # Capability inference engine (ACTIVE)
│   │   ├── features/         # Feature reconstruction engine (ACTIVE)
│   │   ├── stages/           # metadata_stage, metrics_stage (⚠️ UNUSED by main pipeline)
│   │   ├── orchestrator/     # ⚠️ COMPLETELY UNUSED sub-package
│   │   ├── visualization/    # ⚠️ COMPLETELY UNUSED sub-package
│   │   ├── query/            # ⚠️ COMPLETELY UNUSED sub-package
│   │   ├── experiences/      # ⚠️ COMPLETELY UNUSED sub-package
│   │   └── store/            # ⚠️ UNUSED
│   └── tests/                # Backend test suite (for intelligence subsystems)
│
├── frontend/                 # Next.js 16 App Router application
│   ├── app/                  # Next.js App Router pages
│   │   ├── layout.tsx        # Root layout (Header + children)
│   │   ├── page.tsx          # Landing page / login
│   │   ├── dashboard/page.tsx # Repository list + import
│   │   └── repository/[repoName]/
│   │       ├── layout.tsx    # Sidebar layout
│   │       ├── page.tsx      # Repository overview (scan data)
│   │       ├── [tab]/page.tsx # Dynamic tab routing (explorer, graph, etc.)
│   │       └── trace/page.tsx # Feature tracing page
│   ├── components/           # React components
│   │   ├── common/           # Badge, Button, Card, Modal, LanguageIcons
│   │   ├── layout/           # Header, Sidebar
│   │   ├── repository/       # ExplorerView, RepositoryOverview
│   │   ├── DependencyGraph.jsx
│   │   ├── CallExplorer.jsx
│   │   ├── ArchitectureExplorer.jsx
│   │   ├── Search.jsx
│   │   ├── SemanticSearch.jsx
│   │   ├── RepositorySummary.jsx
│   │   ├── SymbolExplorer.jsx
│   │   ├── RepositoryHealth.jsx
│   │   ├── RepositoryMetrics.jsx
│   │   ├── RepositoryAnalysis.jsx
│   │   ├── FileExplorer.jsx
│   │   ├── CodeDetailsViewer.jsx
│   │   ├── CallGraph.jsx          # ⚠️ DEAD — never rendered
│   │   ├── ViewTabs.jsx           # ⚠️ DEAD — never used
│   │   └── RepositoryList.jsx     # ⚠️ DEAD — never used
│   ├── hooks/
│   │   └── useTaskStatus.js       # SSE EventSource hook
│   ├── services/
│   │   ├── api.js                 # fetchAPI() base function
│   │   └── repository.js          # repositoryService object
│   ├── utils/
│   │   ├── graph.js               # ⚠️ DEAD — not imported by any component
│   │   ├── graphBuilder.js        # buildVisibleGraph() — used by DependencyGraph
│   │   ├── layout.js              # layoutGraph(), applyLocalRelaxation() — used by DependencyGraph
│   │   └── vfs.js                 # buildVFS() etc — used by DependencyGraph
│   └── next.config.ts             # Reverse proxy: /api/* → http://127.0.0.1:8000/api/*
│
├── src/analysis/             # ⚠️ COMPLETELY ORPHANED analysis framework
│   ├── interfaces.py         # IAnalyzer, IAnalysisResult (never imported by backend)
│   ├── registry.py           # Plugin registry (dead)
│   ├── runner.py             # Analysis runner (dead)
│   ├── models/               # Finding, Health, Metrics, etc. (dead)
│   └── plugins/              # cycle_analyzer, dead_code_analyzer, etc. (dead)
│
├── tests/                    # Root test suite — tests src/analysis (DEAD)
├── scripts/archive/          # Archived development scripts
├── data/repos/               # User cloned repositories (runtime data)
├── docs/                     # Documentation
├── docker-compose.yml        # PostgreSQL + Backend services
├── pyproject.toml            # Python project config
├── .env                      # Local environment variables (⚠️ contains real secrets)
└── .env.example              # Environment variable template
```

---

## 2. Module Responsibilities

### Backend Core

| Module | Purpose | Depends On | Depended By |
|--------|---------|-----------|------------|
| `backend/main.py` | App entry, lifespan, router registration | config, database, models, routers, services, task_manager | uvicorn (runtime) |
| `backend/config.py` | Pydantic Settings; reads `.env` | pydantic_settings | Everything that needs config |
| `backend/database.py` | SQLAlchemy engine + session factory | config.py | routers, models, services |
| `backend/task_manager.py` | In-memory asyncio pub/sub for SSE | asyncio | main.py, repo router |
| `backend/llm_service.py` | Ollama HTTP client, prompt builder | requests | repo router (summary generation) |
| `backend/logger.py` | `setup_logging()` | logging | main.py |

### Backend Routers

| Module | Routes | Auth Required |
|--------|--------|--------------|
| `routers/auth.py` | GET /api/auth/github/login, GET /api/auth/github/callback, GET /api/auth/github/me, POST /api/auth/github/logout | Only /me and /logout |
| `routers/health.py` | GET /api/health | No |
| `routers/repo.py` (repo_router) | 30+ routes under /api/repos/{repo_name}/* | Yes (all) |
| `routers/repo.py` (import_router) | POST /api/import | Yes |

### Backend Services

| Module | Purpose |
|--------|---------|
| `services/github.py` | `check_repo_limits()`, `download_repo_zipball()`, `fetch_file_content()` |
| `services/github_oauth.py` | `get_github_login_url()`, `exchange_code_for_token()`, `fetch_user_profile()`, `get_or_create_user()`, `create_jwt()` |
| `services/queue.py` | `InMemoryQueue` (asyncio queue wrapper), `WorkerInterface` (ABC) |
| `services/worker.py` | `AnalysisWorker.process()` — downloads, analyzes, saves artifacts |

### Backend Intelligence Engine (Active Path)

The analysis pipeline that runs during job processing:

```
AnalysisWorker.process()
  └─ run_analysis() [in thread]
       ├─ AnalysisEngine.run(repo_name)          [engine/orchestration/pipeline.py]
       │    ├─ RepositoryScanner.scan()           [engine/scanner/scanner.py]
       │    ├─ ASTParserManager.parse_manifest()  [engine/parser/manager.py]
       │    └─ AnalyzerRegistry.get_all()         [engine/analyzers/__init__.py]
       │         ├─ ConfigAnalyzer.analyze()
       │         ├─ DependencyAnalyzer.analyze()
       │         ├─ SymbolAnalyzer.analyze()
       │         ├─ ImportAnalyzer.analyze()
       │         ├─ TypeAnalyzer.analyze()
       │         ├─ CallGraphAnalyzer.analyze()
       │         ├─ RouteAnalyzer.analyze()
       │         ├─ DatabaseAnalyzer.analyze()
       │         └─ TestAnalyzer.analyze()
       ├─ PatternRecognitionEngine.run(model)     [patterns/engine.py]
       ├─ CapabilityBuilderEngine.run(model)      [capabilities/engine.py]
       ├─ FeatureReconstructionEngine.run(model)  [features/engine.py]
       └─ serialize_rim(model)                   [rim/serialization.py]
```

The resulting JSON blob (`core_model`) is stored as an `AnalysisArtifact` with `blob_data`.

### Frontend Architecture

| Layer | Files | Purpose |
|-------|-------|---------|
| App Router Pages | `app/**/*.tsx` | URL routing, page composition |
| Layout Components | `app/layout.tsx`, `app/repository/[repoName]/layout.tsx` | Persistent layouts |
| Feature Components | `components/*.jsx` | Data-fetching + display |
| Common UI | `components/common/*.jsx` | Reusable primitives |
| API Layer | `services/api.js`, `services/repository.js` | Centralized HTTP calls |
| Hooks | `hooks/useTaskStatus.js` | SSE subscription |
| Utilities | `utils/graphBuilder.js`, `utils/layout.js`, `utils/vfs.js` | Graph computation |

---

## 3. External Integrations

| Integration | How | Files |
|-------------|-----|-------|
| GitHub OAuth | HTTPS redirect + code exchange | `services/github_oauth.py`, `routers/auth.py` |
| GitHub API | httpx HTTP client | `services/github.py` |
| PostgreSQL | SQLAlchemy + psycopg3 | `database.py`, all models |
| ChromaDB | `chromadb` Python library | `routers/repo.py` (semantic indexing section) |
| Ollama (LLM) | `requests` HTTP client to localhost:11434 | `llm_service.py` |
| Next.js Proxy | `next.config.ts` rewrites `/api/*` to `http://127.0.0.1:8000/api/*` | `frontend/next.config.ts` |

---

## 4. Database Schema

| Table | Model | Key Columns |
|-------|-------|-------------|
| `users` | `User` | id, github_id, email, username, avatar, github_access_token |
| `repositories` | `Repository` | id, github_repo_id, url, default_branch, user_id (FK) |
| `analyses` | `Analysis` | id, repository_id (FK), commit_sha, engine_version, status |
| `analysis_artifacts` | `AnalysisArtifact` | id, analysis_id (FK), type (string key), data (JSONB), blob_data (LargeBinary) |
| `analysis_jobs` | `AnalysisJob` | id, analysis_id (FK), status, started_at, completed_at, error |
| `task_statuses` | `TaskStatus` | id, user_id (FK), repo_name, task_name, status, updated_at |

**Key relationships:**
- `Repository` → many → `Analysis` (cascade delete)
- `Analysis` → many → `AnalysisArtifact` (cascade delete)
- `Analysis` → many → `AnalysisJob` (cascade delete)
- `User` → many → `Repository` (no cascade declared — potential orphan issue on user delete)
