# Architecture Decision Records (ADRs)

This document records the foundational architecture and technology decisions established in the Repository Intelligence Platform.

---

## ADR 01: Canonical Layer 4 Fact Store in PostgreSQL

- **Decision**: Persist all code facts (symbols, relationships, routes, database objects, capabilities, evidence) into PostgreSQL relational tables rather than an external Graph Database (e.g., Neo4j).
- **Rationale**: Keeps infrastructure simple, container-friendly, highly performant, and fully relational with standard SQL querying and ACID guarantees.
- **Consequence**: In-memory graph traversal is handled by the Repository Intelligence Model (RIM), and persistent querying is powered by canonical relational tables and pgAdmin 4.

---

## ADR 02: Deterministic Multi-Language Parsing via Tree-sitter

- **Decision**: Use Tree-sitter grammar providers for CST/AST generation across Python, JavaScript, TypeScript, Java, C, C++, Go, and Ruby.
- **Rationale**: Tree-sitter provides robust, error-tolerant, high-speed parsing across multiple programming languages without executing arbitrary code.
- **Consequence**: AST parsing and symbol extraction are 100% deterministic and do not depend on external compiler installations.

---

## ADR 03: Analysis-Scoped Fact Primary Keys

- **Decision**: Construct primary keys in Fact Store tables using the format `f"{analysis_id}:{entity_id}"`.
- **Rationale**: Guarantees complete data isolation across multiple re-analysis runs of the same or different repositories, preventing primary key collisions while allowing clean cascade deletions.
- **Consequence**: Queries filtering by `analysis_id` perform fast index scans, and deleting an `Analysis` cleanly deletes all child facts.

---

## ADR 04: Next.js 16 App Router Frontend

- **Decision**: Implement the user interface using Next.js 16 (App Router), React 19, Tailwind CSS 4, and ReactFlow.
- **Rationale**: Modern server and client component support, clean routing conventions (`frontend/app/`), and interactive canvas-based code and dependency visualization.
- **Consequence**: Frontend communicates strictly via REST APIs and Server-Sent Events with the backend.

---

## ADR 05: Asynchronous In-Memory Queue with SSE Progress Streaming

- **Decision**: Manage background analysis jobs using an in-memory asynchronous worker queue (`backend/services/queue.py`) paired with PostgreSQL status tracking and Server-Sent Events (`sse-starlette`).
- **Rationale**: Eliminates the overhead and maintenance of external message brokers (Celery/Redis/RabbitMQ) while providing zero-latency real-time progress updates to the frontend.
- **Consequence**: Real-time progress is streamed over a single persistent HTTP connection per repository.

---

## ADR 06: Local Ollama LLM Integration for Grounded Synthesis

- **Decision**: Connect LLM operations (summary generation, flow explanation) to a local Ollama instance (`qwen2.5-coder:7b`) strictly grounded on deterministic metadata.
- **Rationale**: Keeps repository analysis private, local, cost-free, and prevents hallucination by feeding deterministic AST facts directly into prompts.
- **Consequence**: The platform functions fully without internet access or paid third-party API keys.

---

## ADR 07: Strict Legacy Archiving Policy

- **Decision**: Move all deprecated and orphaned prototype code into `archive/legacy/` and prohibit imports into active runtime code.
- **Rationale**: Preserves historical development experiments without contaminating active architecture or misleading AI coding assistants.
- **Consequence**: Active application modules never import from `archive/legacy/`.
