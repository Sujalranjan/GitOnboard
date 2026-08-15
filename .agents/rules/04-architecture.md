---
trigger: always_on
---

# Architecture Boundaries & Dependency Direction

Maintain strict separation of concerns across system layers.

## System Boundaries
- **Frontend ──► Backend**: Communication happens strictly over HTTP REST APIs and Server-Sent Events (SSE). The frontend never interacts with PostgreSQL, ChromaDB, or filesystem stores directly.
- **Routers ──► Services / Intelligence**: Route handlers in `backend/routers/` must remain lightweight adapters. Business logic belongs in `backend/services/` or `backend/intelligence/`.
- **Intelligence ──► Database**: Analysis results are persisted via the Layer 4 Fact Store (`backend/intelligence/store/fact_store.py`) into SQLAlchemy ORM models (`backend/models/fact_store.py`).
- **Deterministic First**: Ingestion, AST parsing (Tree-sitter), symbol extraction, graph construction (RIM), and capability detection (Layer 6) are 100% deterministic. LLMs (Ollama) are only invoked for textual summary generation and high-level synthesis.

## Prohibited Patterns
- Do NOT introduce generic Enterprise Design Patterns (complex Abstract Factories, Dependency Injection frameworks, event buses, microservice brokers) unless requested.
- Do NOT introduce message brokers (Kafka, RabbitMQ, Redis) — the platform uses an in-memory asynchronous queue (`backend/services/queue.py`) with PostgreSQL job tracking.
- Do NOT write placeholder stub functions with `# TODO` or `pass` without working implementations.
