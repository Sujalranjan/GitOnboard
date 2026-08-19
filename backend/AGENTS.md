# Backend AI Agent Guidelines

This document governs AI agent behavior when working in the `backend/` directory.

## Technology Stack
- **Framework**: FastAPI (Python 3.12+)
- **ORM & Database**: SQLAlchemy 2.0 with PostgreSQL (`psycopg`), SQLite for fast unit testing
- **Code Parsing**: Tree-sitter multi-language parsers (`tree-sitter`, `tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`, `tree-sitter-java`, `tree-sitter-c`, `tree-sitter-cpp`, `tree-sitter-go`, `tree-sitter-ruby`)
- **Vector Search**: ChromaDB (`chromadb`) with persistent model cache
- **LLM Integration**: Shared multi-provider LLM service (`backend/ai/`) supporting Ollama in `LOCAL` mode, and Gemini/OpenRouter in `PROD` mode with deterministic fallback
- **Background Queue**: In-memory worker queue (`backend/services/queue.py`, `backend/services/worker.py`)
- **Real-Time Streaming**: Server-Sent Events (`sse-starlette`, `backend/task_manager.py`)
- **Package Manager**: `uv` (managed with `pyproject.toml`, `uv.lock`)

## Core Backend Rules
1. **Lightweight Route Handlers**: Route handlers in `backend/routers/` must only validate requests, invoke services, and return responses. Heavy computation belongs in `backend/services/` or `backend/intelligence/`.
2. **Deterministic Analysis First**: Ingestion, AST parsing, symbol extraction, RIM graph construction, and Layer 6 capability detection are 100% deterministic. LLMs are only used for text summaries.
3. **Layer 4 Fact Store Persistence**:
   - Persist facts using `save_rim_to_fact_store()` in `backend/intelligence/store/fact_store.py`.
   - Fact Store tables (`files`, `symbols`, `relationships`, `routes`, `database_objects`, `capabilities`, `capability_members`, `evidence`) use analysis-scoped primary keys (`{analysis_id}:{entity_id}`).
4. **Cross-Database Compatibility**: Use `JSONType = JSON().with_variant(JSONB, "postgresql")` across all models to ensure compatibility with both PostgreSQL in production and SQLite in test environments.
5. **Background Tasks & SSE**: Offload long-running operations to `AnalysisWorker`. Emit task state changes via `task_manager.notify(user_id, repo_name, task_name, status)` for real-time SSE streaming.
6. **Authentication & Security**: Use `get_current_user` dependency (`backend/dependencies/auth.py`) for authenticated endpoints. Ensure JWT tokens use HttpOnly secure cookies.
7. **Validation**: Execute automated tests after any backend change:
   ```bash
   uv run pytest backend/tests/ -v
   uv run pytest tests/ -v
   ```
