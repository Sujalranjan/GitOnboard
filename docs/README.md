# Repository Intelligence Platform

Repository Intelligence Platform is an advanced code analysis and intelligence platform. It ingests GitHub repositories, builds deterministic abstract syntax trees (CST/AST) and in-memory knowledge graphs (Repository Intelligence Model), detects multi-fact architectural capabilities, persists relational facts into a canonical PostgreSQL Fact Store, and provides semantic search, execution flow tracing, and interactive Next.js visualization.

---

## Component Status

```text
ACTIVE (Implemented & Tested)
├── Tree-sitter Multi-Language CST/AST Engine (Python, JS, TS, Java, C, C++, Go, Ruby)
├── Repository Intelligence Model (RIM) in-memory knowledge graph
├── Layer 4 Relational Fact Store (PostgreSQL with 8 canonical tables)
├── Layer 6 Deterministic Capability Detection Engine (Auth, CRUD, Background, File Upload)
├── Feature Discovery & Execution Flow Reconstruction
├── ChromaDB Vector Index for Semantic Code Search
├── FastAPI Asynchronous Queue Worker & SSE Task Streaming
├── PostgreSQL Database + pgAdmin 4 Containerized Visualization
└── Next.js 16 App Router UI (React 19, Tailwind CSS 4, ReactFlow graph canvas)

PLANNED (Future Pipeline Stages)
├── Autonomous AI Implementation Engine (Worktrees & Patch Generation)
├── Independent Verification Engine (Isolated Test Execution & Linting)
├── Self-Repair Loop (Automated Test Diagnostics & Fix Iteration)
└── Pull Request Generation & Git Export

LEGACY (Archived Historical Material)
└── archive/legacy/ (Deprecated prototypes — read-only)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | FastAPI (Python 3.12+) with SSE streaming (`sse-starlette`) |
| **Package Management** | `uv` (`pyproject.toml`, `uv.lock`) |
| **Relational Database** | PostgreSQL 15 (SQLAlchemy 2.0 ORM with `psycopg`) |
| **Database UI** | pgAdmin 4 (port `5050`) |
| **Parsing & AST** | Tree-sitter multi-language grammar providers |
| **Vector Store** | ChromaDB (`chromadb`) with persistent volume cache |
| **LLM Integration** | Local Ollama (`http://localhost:11434`, `qwen2.5-coder:7b`) |
| **Frontend Framework** | Next.js 16 (App Router) + React 19 + TypeScript |
| **Styling & Graphs** | Tailwind CSS 4, ReactFlow, Dagre, Lucide React, Framer Motion |

---

## Quick Start (Local Development)

### 1. Prerequisites
- Docker & Docker Compose
- Node.js 18+ & npm
- Python 3.10+ with `uv`
- Ollama running locally (optional for AI summaries)

### 2. Backend & Database (Docker Compose)
```bash
docker compose up --build -d
```
- FastAPI API: `http://localhost:8000` (Docs: `http://localhost:8000/docs`)
- PostgreSQL: `localhost:5432` (`repository_intelligence`)
- pgAdmin 4: `http://localhost:5050` (`admin@example.com` / `adminpassword`)

### 3. Frontend (Next.js 16)
```bash
cd frontend
npm install
npm run dev
```
- Frontend UI: `http://localhost:3000`

---

## Documentation Index

### Project Organization
- [Project Structure & Directory Reference](../PROJECT_STRUCTURE.md) — Directory guide, development workflow

### Architecture & Design
- [Architecture & Pipeline](architecture/ARCHITECTURE.md)
- [Data Model & Database Schema](architecture/DATA_MODEL.md)
- [API Contract Specification](architecture/API.md)
- [Implementation Guide](architecture/IMPLEMENTATION_GUIDE.md)

### Guides
- [Development & Environment Setup](guides/DEVELOPMENT.md)
- [Testing & Integrity Guide](guides/TESTING.md)
- [Architectural Decisions (ADRs)](guides/DECISIONS.md)
- [Contribution Guidelines](guides/CONTRIBUTING.md)
- [Development Plan](guides/Plan.md)
- [AI Agent Master Guide](guides/AGENTS.md)

### Reports & Diagnostics
- [Implementation Summary](reports/IMPLEMENTATION_SUMMARY.md)
- [Deployment Checklist](reports/DEPLOYMENT_CHECKLIST_RIM_FIX.md)
- [Production Readiness Report](reports/FINAL_PRODUCTION_READINESS_REPORT.md)
