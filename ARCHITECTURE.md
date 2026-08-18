# System Architecture & Technical Specifications

This document describes the **active implementation architecture** of the Repository Intelligence Platform.

---

## 1. High-Level Architecture

```mermaid
flowchart TD
    User([User / Browser])
    
    subgraph Frontend ["Frontend (Next.js 16 App Router)"]
        UI[Dashboard / Repo Workspace]
        RF[ReactFlow Graph Canvas]
        SSE_Client[useTaskStatus SSE Hook]
    end
    
    subgraph Backend ["Backend (FastAPI)"]
        API[FastAPI Routers]
        Queue[InMemoryQueue]
        Worker[AnalysisWorker]
        TM[TaskManager Pub/Sub]
        LLM[Ollama Service]
    end
    
    subgraph Intelligence ["Intelligence Engine (backend/intelligence/)"]
        Scanner[RepositoryScanner]
        TreeSitter[Tree-sitter Multi-Language Parser]
        RIM[Repository Intelligence Model Graph]
        CapEngine[Layer 6 Capability Detection]
        FeatEngine[Feature Reconstruction Engine]
    end
    
    subgraph Persistence ["Persistence Layer"]
        PG[(PostgreSQL Database)]
        FactStore[(Layer 4 Fact Store Tables)]
        Chroma[(ChromaDB Vector Store)]
    end
    
    User <--> UI
    UI -- REST API --> API
    SSE_Client <-- SSE Stream (`/api/repos/{repo}/tasks/stream`) -- TM
    
    API --> Queue
    Queue --> Worker
    Worker --> Scanner --> TreeSitter --> RIM --> CapEngine --> FeatEngine
    Worker -- Persists Facts --> FactStore
    Worker -- Emits Progress --> TM
    Worker -- Embeds Chunks --> Chroma
    
    API -- Read Queries --> FactStore
    API -- Summaries --> LLM
    FactStore --> PG
```

---

## 2. Ingestion & Analysis Pipeline Flow

When a repository is imported via `POST /api/import` or reanalyzed via `POST /api/repos/{repo_name}/reanalyze`:

1. **Pre-flight & Validation**:
   - `backend/services/github.py` validates repository existence, size, and rate limits via GitHub API.
   - Analysis records (`Analysis`, `AnalysisJob`) are created in PostgreSQL with status `Queued`.
2. **Download Phase**:
   - `AnalysisWorker` (`backend/services/worker.py`) downloads the repository archive as a zipball and extracts it into `/tmp/repo-analysis/job_{id}_{repo}/`.
3. **Scanning & Language Detection**:
   - `RepositoryScanner` and `LanguageDetector` scan the file tree, mapping extensions and detecting dominant languages and frameworks.
4. **Tree-sitter Parsing & Symbol Extraction**:
   - Multi-language AST providers parse files into Concrete Syntax Trees (CST/AST), extracting classes, functions, methods, parameters, decorators, imports, routes, and database tables (`backend/intelligence/engine/`).
5. **Repository Intelligence Model (RIM) Graph Construction**:
   - Entities and Relationships (`CONTAINS`, `CALLS`, `IMPORTS`, `INHERITS`, `USES`, `EXPOSES`, `DECLARES`, `DEPENDS_ON`) are assembled into an in-memory directed graph (`backend/intelligence/rim/`).
6. **Layer 6 Capability Detection Engine**:
   - Multi-fact AST rule detectors (`AuthenticationDetector`, `CRUDDetector`, `BackgroundTaskDetector`, `FileUploadDetector`) match patterns across routes, handlers, and models to classify system capabilities.
7. **Feature Reconstruction Engine**:
   - Traces execution flows from entrypoint routes through services down to database tables, clustering related symbols into functional features (`backend/intelligence/features/`).
8. **Layer 4 Fact Store Relational Persistence**:
   - `save_rim_to_fact_store()` (`backend/intelligence/store/fact_store.py`) persists all entities, symbols, relationships, routes, database objects, capabilities, and evidence into PostgreSQL using analysis-scoped primary keys (`{analysis_id}:{entity_id}`).
9. **Artifact Storage & Completion**:
   - Serialized `core_model` (compressed JSON blob), `metrics`, and `enriched_metadata` are saved to `analysis_artifacts`.
   - `AnalysisJob` and `Analysis` statuses are marked `Completed`.

---

## 3. Component Classification (Active vs Planned vs Legacy)

### Active Components
- **Multi-language Tree-sitter Parser**: `backend/intelligence/engine/`
- **RIM Graph Engine**: `backend/intelligence/rim/`
- **Layer 4 Fact Store**: `backend/intelligence/store/fact_store.py`, `backend/models/fact_store.py`
- **Layer 6 Capability Detection Engine**: `backend/intelligence/capabilities/`
- **Feature Reconstruction & Tracing**: `backend/intelligence/features/`, `backend/routers/repo/trace.py`
- **ChromaDB Semantic Vector Index**: `backend/routers/repo/semantic.py`
- **FastAPI Core & Routers**: `backend/routers/`
- **Worker Queue & TaskManager (SSE)**: `backend/services/worker.py`, `backend/task_manager.py`
- **Next.js 16 App Router UI**: `frontend/app/`, `frontend/components/`

### Planned Components (Future Phases)
- **Autonomous AI Implementation Engine**: Target architecture in `docs/contracts/implementation-contract.md`
- **Independent Verification Engine**: Target architecture in `docs/contracts/verification.md`
- **Self-Repair Loop**: Target architecture in `docs/contracts/repair.md`
- **Automated Pull Request Generation**: Target architecture in `docs/contracts/agent.md`

### Legacy / Archived Components
- **`archive/legacy/`**: Verified dead and orphaned code moved out of runtime execution paths. Read-only historical reference.

---

## 4. AI Implementation Agent & Sandboxed Verification (`backend/verification/`, `backend/services/`)

Isolation is deliberately split by step, matching the frozen `docs/contracts/agent.md` / `implementation-contract.md` (worktree-only) vs. `docs/contracts/verification.md` (container sandbox):

- **Agent code-writing** (`VerificationOrchestrator.run_agent`/`judge_and_repair`) and the **human-facing terminal** (`SandboxManager`) both run as plain host subprocess execution scoped to a `GitManager`-created git worktree under `data/worktrees/`. No Docker. This step only writes files / runs `git`; there's no reason to run arbitrary AI-generated code here.
- **Verification's dynamic checks** (`DynamicVerifier` — build/test/lint execution) run inside an ephemeral, resource-capped Docker container (`DockerVerificationRunner`, image built from `docker/verification.Dockerfile`) with the worktree bind-mounted read-write. This is the step that actually *executes* code the agent (or a repair iteration) just wrote, so it gets the stronger isolation: non-root, `cap_drop: ALL`, `no-new-privileges`, CPU/memory/PID limits, and a hard timeout. Falls back to host subprocess execution (`settings.verification_use_docker=False`, or automatically if the Docker daemon is unreachable) — never a hard failure.
- **`StaticVerifier`** and **`ContractVerifier`** never execute anything (pure AST/manifest/contract inspection), so neither needs sandboxing.

```text
Requirement ──► Contract ──► run_agent (worktree, host)  ──► git diff
                                                                │
                                                                ▼
                                          verify_run: Static (host) + Dynamic (Docker) + Contract (host)
                                                                │
                                                    FAIL ───────┴─────── PASS ──► AgentRun COMPLETED
                                                     │
                                                     ▼
                                     judge_and_repair (worktree, host, max 3 iterations)
                                                     │
                                                     ▼
                                                verify_run (repeats)
```

**Docker-outside-of-Docker note**: `backend` itself runs containerized (`backend/Dockerfile`, `docker-compose.yml`). For it to spawn sibling verification containers, `docker-compose.yml` mounts the host's `/var/run/docker.sock` into the `backend` service — a trusted-service-only mount, never exposed to the browser or to agent-generated code. Because a bind-mount path handed to the *host* Docker daemon must resolve on the *host* filesystem (not inside the `backend` container's own filesystem), `docker-compose.yml` also mounts `./data:/app/data` and passes `HOST_DATA_DIR=${PWD}/data`; `DockerVerificationRunner._translate_to_host_path` rebases container-visible worktree paths onto that host path before requesting the mount. This translation is a no-op (paths already match) when the backend runs directly on the host instead of via Compose.

Every AI Implementation Agent execution persists an `AgentRun` with an append-only `AgentEvent` trail and structured `FileChange` diff records (`DATA_MODEL.md` §1.5), streamed live over SSE (`API.md` §8) via the same `TaskManager` pub/sub `backend/task_manager.py` already used for repository analysis progress.

---

## 5. Team Ownership Boundaries

| Role | Directory Ownership | Responsibilities |
|---|---|---|
| **Frontend Teammate** | `frontend/` | Next.js 16 App Router, React 19 components, ReactFlow graph canvas, responsive layouts, client-side state, API client consumption. |
| **Backend / API Teammate** | `backend/` (core app) | FastAPI routers (`auth.py`, `health.py`, `repo/core.py`, `repo/tasks.py`), database configuration, SQLAlchemy models (`user.py`, `repository.py`), queue workers, SSE streaming. |
| **Intelligence / AI Teammate (You)** | `backend/intelligence/`, `backend/models/fact_store.py`, `backend/llm_service.py`, `backend/routers/repo/` (intelligence endpoints) | Tree-sitter AST parsing, RIM graph model, Layer 4 Fact Store, Layer 6 capability detection, feature tracing, ChromaDB vector indexing, Ollama LLM integration. |
