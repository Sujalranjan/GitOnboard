# FastAPI REST & SSE API Specification

This document summarizes the **active API endpoints** exposed by the FastAPI backend.

> [!IMPORTANT]
> The active FastAPI route definitions (`backend/routers/`) and the generated OpenAPI documentation at `http://localhost:8000/docs` are the **canonical source of truth** for request and response schemas.

---

## Base URL
All API routes are prefixed under `/api` (e.g., `http://localhost:8000/api`).

---

## 1. System & Health

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/` | API root welcome message | No |
| `GET` | `/api/health` | Service health & database connectivity probe | No |

---

## 2. Authentication (`/api/auth/github`)

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/auth/github/login` | Redirects user to GitHub OAuth consent screen | No |
| `GET` | `/api/auth/github/callback` | OAuth callback handler; exchanges code, creates user session, sets HttpOnly JWT cookie | No |
| `GET` | `/api/auth/github/me` | Returns profile of currently authenticated user | Yes |
| `POST` | `/api/auth/github/logout` | Clears session cookie and invalidates session | No |

---

## 3. Repository Management (`/api/import` & `/api/repos`)

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/import` | Import a new GitHub repository (`{"url": "https://github.com/owner/repo"}`) and queue analysis | Yes |
| `GET` | `/api/repos` | List all imported repositories and latest analysis statuses for current user | Yes |
| `POST` | `/api/repos/{repo_name}/reanalyze` | Trigger re-analysis of an existing repository | Yes |
| `POST` | `/api/repos/{repo_name}/cancel` | Cancel an ongoing analysis job | Yes |
| `DELETE` | `/api/repos/{repo_name}` | Delete repository and cascade delete all associated analyses, artifacts, and fact store records | Yes |

---

## 4. Real-Time Tasks & Server-Sent Events (SSE)

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/repos/{repo_name}/tasks` | Get snapshot of task statuses (fast in-memory path with DB fallback) | Yes |
| `GET` | `/api/repos/{repo_name}/tasks/stream` | Server-Sent Events (SSE) stream pushing instant task progress updates to the frontend | Yes |

---

## 5. Structure, Symbols, & Graphs (`/api/repos/{repo_name}`)

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/repos/{repo_name}/scan` | Return repository directory/file hierarchy and file overview | Yes |
| `GET` | `/api/repos/{repo_name}/parse` | Return parsed AST details (classes, functions, imports) for a specific file (`?file=path`) | Yes |
| `GET` | `/api/repos/{repo_name}/dependencies` | Return file-level dependency graph (nodes and edges) | Yes |
| `GET` | `/api/repos/{repo_name}/call-graph` | Return function-level call graph (call sites and relationships) | Yes |
| `GET` | `/api/repos/{repo_name}/symbols` | Return all extracted symbols across the repository | Yes |
| `GET` | `/api/repos/{repo_name}/stats` | Return lines of code, symbol counts, and complexity metrics | Yes |
| `GET` | `/api/repos/{repo_name}/architecture` | Return architectural layers, entrypoints, and framework breakdown | Yes |

---

## 6. Intelligence, Features, & Search (`/api/repos/{repo_name}`)

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/repos/{repo_name}/features` | Return reconstructed feature clusters and execution flows | Yes |
| `API_ROUTE` | `/api/repos/{repo_name}/trace` | Reconstruct execution flow path for a specific route handler (supports GET/POST) | Yes |
| `POST` | `/api/repos/{repo_name}/trace/explain` | LLM-assisted plain English explanation of a traced execution flow | Yes |
| `GET` | `/api/repos/{repo_name}/search` | Keyword symbol and entity search across repository facts | Yes |
| `GET` | `/api/repos/{repo_name}/semantic-search` | Semantic vector search powered by ChromaDB embeddings (`?query=...`) | Yes |
| `POST` | `/api/repos/{repo_name}/semantic-index` | Generate ChromaDB semantic embeddings for repository files | Yes |
| `GET` | `/api/repos/{repo_name}/semantic-status` | Check embedding generation status in ChromaDB | Yes |
| `GET` | `/api/repos/{repo_name}/context` | Comprehensive context builder for LLM grounding (combines RIM, features, and graphs) | Yes |

---

## 7. LLM Summary Generation

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/repos/{repo_name}/summary` | Retrieve cached Markdown repository summary | Yes |
| `POST` | `/api/repos/{repo_name}/summary/generate` | Dispatch background task to generate grounded repository summary via local Ollama LLM | Yes |

---

## 8. AI Implementation Pipeline (`/api/v1/pipeline`)

Coding Agent Adapter: requirement → Implementation Contract → isolated git-worktree code generation → multi-vector verification (static AST, dynamic build/test — executed in an ephemeral Docker container, see `ARCHITECTURE.md` §4 — and contract coverage) → bounded (max 3 attempts) repair. Each step persists an `AgentRun`/`AgentEvent`/`FileChange` trail (`DATA_MODEL.md` §1.5) instead of only returning a single synchronous response.

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/v1/pipeline/task/submit` | Synthesizes an `ImplementationContract` from a natural-language requirement prompt | No¹ |
| `POST` | `/api/v1/pipeline/task/{task_id}/execute` | Runs the coding agent in an isolated git worktree and executes multi-vector verification | No¹ |
| `POST` | `/api/v1/pipeline/task/{task_id}/repair` | Runs one bounded repair iteration (max 3) against reported defects and re-verifies | No¹ |
| `GET` | `/api/v1/pipeline/task/{task_id}/events/stream` | Server-Sent Events (SSE) stream of `AgentEvent` progress for the task's most recent `AgentRun` (same TaskManager pub/sub pattern as §4) | No¹ |
| `GET` | `/api/v1/pipeline/task/{task_id}/changes` | Returns persisted, structured `FileChange` rows (path, change type, added/removed line counts, per-file diff) for the task's most recent `AgentRun` | No¹ |

¹ This router does not yet enforce authentication — a pre-existing gap, not introduced by the event/diff persistence work above.
