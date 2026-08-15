---
trigger: always_on
---

# Project Specific Engineering Rules

Key architectural principles for the Repository Intelligence Platform:

## 1. Deterministic Extraction Over LLM Guesswork
- The repository intelligence pipeline is built on deterministic code analysis:
  1. Tree-sitter CST parsing (`backend/intelligence/engine/`)
  2. Symbol & reference extraction (`symbols.py`, `routes.py`, `database.py`)
  3. Repository Intelligence Model graph construction (`backend/intelligence/rim/`)
  4. Layer 6 Rule-based Capability Detection (`backend/intelligence/capabilities/`)
  5. Relational Fact Store persistence (`backend/intelligence/store/fact_store.py`)
- Never replace deterministic AST/graph extraction with LLM prompts.
- LLMs are reserved for synthesizing text summaries (`backend/llm_service.py`) from extracted metadata.

## 2. PostgreSQL Layer 4 Fact Store
- All code facts (files, symbols, relationships, routes, database objects, capabilities, evidence) are persisted in PostgreSQL.
- Fact IDs use analysis-scoped composite keys (`{analysis_id}:{entity_id}`) to ensure complete data isolation across re-analyses.

## 3. Real-Time Task Streaming
- Background jobs are executed via `AnalysisWorker` (`backend/services/worker.py`).
- Status transitions (`Queued`, `Downloading`, `Analyzing`, `Saving`, `Completed`, `Failed`) are published via `TaskManager` and streamed to the frontend over Server-Sent Events (SSE).
