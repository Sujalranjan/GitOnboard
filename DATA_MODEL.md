# Database Schema & Data Model Specification

This document details the PostgreSQL schema, SQLAlchemy ORM models, and the Layer 4 Relational Fact Store.

---

## 1. Application & Job Management Models (`backend/models/`)

### `users` (`User` in `backend/models/user.py`)
Tracks authenticated platform users.
- `id` (Integer, PK)
- `github_id` (String, unique, index)
- `username` (String, unique, index)
- `email` (String, unique, nullable)
- `avatar` (String, nullable)
- `github_access_token` (String, nullable)

### `repositories` (`Repository` in `backend/models/repository.py`)
Tracks imported GitHub repositories.
- `id` (Integer, PK)
- `github_repo_id` (String, unique, index)
- `url` (String, unique, index)
- `default_branch` (String, nullable)
- `user_id` (Integer, FK ──► `users.id`)

### `analyses` (`Analysis` in `backend/models/repository.py`)
Tracks individual analysis runs for a repository.
- `id` (Integer, PK)
- `repository_id` (Integer, FK ──► `repositories.id`, cascade delete)
- `commit_sha` (String, nullable)
- `engine_version` (String, default="v1.0")
- `status` (String, default="Queued") # Queued, Downloading, Analyzing, Saving, Completed, Failed, Cancelled
- `created_at` (DateTime with timezone)

### `analysis_artifacts` (`AnalysisArtifact` in `backend/models/repository.py`)
Stores serialized analysis artifacts (metrics, enriched metadata, compressed core model).
- `id` (Integer, PK)
- `analysis_id` (Integer, FK ──► `analyses.id`, cascade delete)
- `type` (String, index) # `metrics`, `enriched_metadata`, `summary`, `core_model`
- `data` (JSONType / JSONB)
- `blob_data` (LargeBinary, nullable)

### `analysis_jobs` (`AnalysisJob` in `backend/models/repository.py`)
Tracks background worker job execution.
- `id` (Integer, PK)
- `analysis_id` (Integer, FK ──► `analyses.id`, cascade delete)
- `status` (String) # Queued, Downloading, Analyzing, Saving, Completed, Failed, Cancelled
- `started_at` (DateTime with timezone, nullable)
- `completed_at` (DateTime with timezone, nullable)
- `error` (String, nullable)

### `task_statuses` (`TaskStatus` in `backend/models/repository.py`)
Tracks granular sub-task progress (e.g. `summary`, `semantic_index`).
- `id` (Integer, PK)
- `user_id` (Integer, FK ──► `users.id`)
- `repo_name` (String)
- `task_name` (String)
- `status` (String, default="pending") # pending, processing, completed, failed
- `updated_at` (DateTime with timezone)

---

## 2. Layer 4 Relational Fact Store (`backend/models/fact_store.py`)

All Fact Store tables use analysis-scoped composite IDs (`id = f"{analysis_id}:{entity_id}"`) ensuring complete database isolation across multiple re-analysis runs.

```text
               ┌───────────────┐
               │   analyses    │
               └───────┬───────┘
                       │
       ┌───────────────┼───────────────┬────────────────┐
       ▼               ▼               ▼                ▼
┌─────────────┐ ┌─────────────┐ ┌───────────────┐ ┌───────────────┐
│    files    │ │   symbols   │ │ relationships │ │ capabilities  │
└──────┬──────┘ └──────┬──────┘ └───────────────┘ └───────┬───────┘
       │               │                                  │
       │        ┌──────┴──────┐                           ▼
       ▼        ▼             ▼                 ┌───────────────────┐
┌─────────────┐ ┌───────────────────┐           │capability_members │
│   routes    │ │ database_objects  │           └─────────┬─────────┘
└─────────────┘ └───────────────────┘                     ▼
                                                ┌───────────────────┐
                                                │     evidence      │
                                                └───────────────────┘
```

### Fact Store Tables Summary
1. `files`: Source files, languages, content hashes, and line counts.
2. `symbols`: AST-extracted classes, functions, methods, variables, routes, and database models.
3. `relationships`: Typed graph edges (`CONTAINS`, `CALLS`, `IMPORTS`, `INHERITS`, `USES`, `EXPOSES`, `DECLARES`, `DEPENDS_ON`) with code evidence snippets.
4. `routes`: HTTP API endpoints with HTTP method, path, and handler symbol references.
5. `database_objects`: Database tables, ORM models, and query patterns.
6. `capabilities`: High-level system capabilities detected by Layer 6 (e.g. `Authentication`, `CRUD`, `Background Tasks`, `File Upload`).
7. `capability_members`: Symbols participating in a capability, mapped with structural roles (`entry_point`, `handler`, `service`, `table`, `worker`).
8. `evidence`: Concrete AST and code location evidence grounding capability assertions.

---

## 3. Cross-Database Compatibility

All JSON columns utilize:
```python
JSONType = JSON().with_variant(JSONB, "postgresql")
```
This guarantees native binary `JSONB` indexing and querying in production PostgreSQL while allowing in-memory SQLite for fast test suite execution.
