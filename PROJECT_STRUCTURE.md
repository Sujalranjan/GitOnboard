# Repository Structure & Development Workflow

This document describes the directory layout and development organization of the Repository Intelligence Platform (GitOnboard).

---

## Directory Layout

```
GitOnboard/
├── CLAUDE.md                    # Project engineering standards & constraints
├── PROJECT_STRUCTURE.md         # This file
├── docker-compose.yml           # Docker Compose configuration (PostgreSQL, Azurite, pgAdmin, Backend)
├── alembic.ini                  # Database migration tool configuration
├── pyproject.toml               # Python dependencies (uv-managed)
├── uv.lock                      # Locked dependency versions
├── .env                         # Environment variables (local development)
├── .env.example                 # Template for environment configuration
├── .gitignore                   # Git ignore rules
│
├── alembic/                     # Database migration scripts (Alembic)
│   ├── versions/                # Migration revision files
│   ├── env.py                   # Alembic environment configuration
│   └── script.py.mako           # Migration template
│
├── backend/                     # FastAPI backend application (Dockerized)
│   ├── main.py                  # Application entry point
│   ├── database.py              # SQLAlchemy PostgreSQL session management
│   ├── config.py                # Environment configuration (Pydantic Settings)
│   ├── task_manager.py          # Task dispatcher & SSE publisher
│   ├── logger.py                # Logging configuration
│   │
│   ├── models/                  # SQLAlchemy ORM models
│   ├── routers/                 # FastAPI route handlers (REST & SSE)
│   ├── services/                # Business logic & domain services
│   ├── dependencies/            # FastAPI dependency injection
│   ├── utils/                   # Utility functions & helpers
│   │
│   ├── intelligence/            # Core repository analysis engine
│   │   ├── scanner.py           # Repository file traversal & loading
│   │   ├── rim.py               # Repository Intelligence Model (RIM) graph
│   │   ├── capability_engine.py # Layer 6 capability detection
│   │   ├── symbol_resolver.py   # Symbol graph & relationship resolution
│   │   └── parsers/             # Tree-sitter AST parsers (Python, JS, TS, Java, C, C++, Go, Ruby)
│   │
│   ├── agent/                   # LangGraph AI agent orchestration
│   │   ├── agent.py             # Main agent loop & decision logic
│   │   ├── tools.py             # Agent tool definitions
│   │   └── state.py             # Agent execution state schema
│   │
│   ├── verification/            # Sandboxed testing & verification
│   │   ├── docker_runner.py     # Docker container verification engine
│   │   ├── worktree_manager.py  # Git worktree isolation for patches
│   │   └── repair_loop.py       # AI-driven test failure remediation
│   │
│   ├── storage/                 # Azure Blob Storage / Azurite integration
│   │   ├── azurite.py           # Storage client wrapper
│   │   └── repository_store.py  # Repository snapshot persistence
│   │
│   ├── evaluation/              # Summary pipeline & quality evaluation
│   ├── summary/                 # Repository summarization logic
│   ├── planning/                # Implementation planning engine
│   ├── ai/                      # LLM provider integrations & prompting
│   ├── validation/              # Input validation & security checks
│   │
│   ├── tests/                   # Backend unit & integration tests
│   └── Dockerfile               # Backend container image definition
│
├── frontend/                    # Next.js 16 web dashboard (React 19 + TypeScript)
│   ├── app/                     # Next.js App Router pages & layouts
│   │   ├── page.tsx             # Homepage
│   │   ├── layout.tsx           # Root layout
│   │   └── [routes]/            # Dynamic route segments
│   │
│   ├── components/              # Reusable React components
│   │   ├── Dashboard.tsx        # Main dashboard view
│   │   ├── RepositoryExplorer.tsx # Repository browser
│   │   ├── CodeEditor.tsx       # Monaco editor integration
│   │   ├── TerminalUI.tsx       # Xterm.js terminal
│   │   └── GraphCanvas.tsx      # ReactFlow graph visualization
│   │
│   ├── services/                # API client & business logic
│   │   ├── api.ts               # REST client (fetch wrapper)
│   │   └── taskClient.ts        # SSE task status client
│   │
│   ├── lib/ & utils/            # Utility functions & helpers
│   ├── types/                   # TypeScript type definitions
│   ├── hooks/                   # Custom React hooks
│   ├── context/                 # React context providers
│   ├── assets/                  # Static images & files
│   ├── public/                  # Publicly served static files
│   │
│   ├── next.config.ts           # Next.js configuration
│   ├── tailwind.config.js       # Tailwind CSS configuration
│   ├── tsconfig.json            # TypeScript configuration
│   ├── package.json             # Node.js dependencies (npm)
│   ├── package-lock.json        # Locked npm versions
│   ├── CLAUDE.md                # Frontend-specific guidelines
│   └── README.md                # Frontend setup & development
│
├── docker/                      # Docker image definitions
│   └── verification.Dockerfile  # Verification container image (sandboxed tests)
│
├── data/                        # Local development data (not committed)
│   ├── worktrees/               # Git worktree checkouts for patch testing
│   └── repositories/            # Cloned & cached repository sources
│
├── docs/                        # Project documentation
│   ├── README.md                # Documentation index & quick start
│   ├── architecture/            # Technical architecture & design docs
│   │   ├── ARCHITECTURE.md      # System design & pipeline flow
│   │   ├── DATA_MODEL.md        # PostgreSQL schema & data relationships
│   │   ├── API.md               # REST API contract & endpoints
│   │   ├── IMPLEMENTATION_GUIDE.md # Detailed implementation reference
│   │   └── [other detailed architecture docs]/
│   │
│   ├── guides/                  # Developer guides & runbooks
│   │   ├── DEVELOPMENT.md       # Detailed local setup & development
│   │   ├── CONTRIBUTING.md      # Contribution standards & PR checklist
│   │   ├── TESTING.md           # Test suite structure & execution
│   │   ├── DECISIONS.md         # Architectural decision records (ADRs)
│   │   ├── AGENTS.md            # AI agent development guide
│   │   └── Plan.md              # Long-term development roadmap
│   │
│   ├── diagnostics/             # Diagnostic & debugging reports
│   │   ├── GEMINI_429_DIAGNOSTIC_SUMMARY.md
│   │   ├── GEMINI_RATE_LIMITER.md
│   │   ├── MODEL_ROUTING_FIX.md
│   │   ├── PROD_MODE_QWEN_FILTERING.md
│   │   ├── READ_FILE_FIX.md
│   │   ├── SSL_CERTIFICATE_FIX.md
│   │   ├── STRICT_ROUTING_IMPLEMENTATION.md
│   │   └── TOOLS_ARCHITECTURE.md
│   │
│   ├── contracts/               # API contract specifications
│   ├── decisions/               # Technical decision documents
│   ├── reports/                 # Implementation status & readiness reports
│   ├── bugs/                    # Known issues & bug tracking
│   └── evaluation/              # Evaluation framework & metrics
│
├── scripts/                     # Development & maintenance scripts (not deployed)
│   ├── analyze_logs.py          # Log analysis utilities
│   ├── reset_all_data.py        # Database & storage reset for fresh start
│   ├── manual_test_flow.py      # Manual testing workflows
│   ├── test_import_flow.py      # Repository import testing
│   ├── cleanup_orphaned_blobs.py # Storage cleanup utility
│   ├── fix_repository_ids.py    # Data migration helpers
│   │
│   ├── archive/                 # Deprecated scripts (historical)
│   ├── benchmarks/              # Performance measurement scripts
│   ├── maintenance/             # System maintenance & cleanup
│   ├── validation/              # Data validation utilities
│   └── debug/                   # Debugging & diagnostics helpers
│
├── tests/                       # Root-level integration & system tests
│   ├── test_*.py                # Integration test suites
│   ├── conftest.py              # Pytest fixtures & configuration
│   └── [comprehensive test coverage for agent, verification, and end-to-end flows]
│
├── evaluation/                  # Evaluation runs & results (not committed)
│   └── runs/                    # Timestamped evaluation execution logs
│
├── logs/                        # Runtime logs (not committed)
│   ├── app.log                  # Application runtime log
│   ├── errors.log               # Error log
│   ├── execution.jsonl          # Agent execution traces
│   ├── llm_requests/            # LLM request/response logs
│   ├── tool_calls/              # Agent tool invocation logs
│   └── [other diagnostic logs]/
│
└── graphify-out/                # Graphify output artifacts (not committed)
```

---

## Key Development Workflows

### Local Development Setup

1. **Environment**: Copy `.env.example` to `.env` and configure
2. **Backend & Database**: `docker compose up -d --build`
3. **Frontend**: `cd frontend && npm install && npm run dev`
4. **Migrations**: `docker compose exec backend alembic upgrade head`

See [docs/guides/DEVELOPMENT.md](docs/guides/DEVELOPMENT.md) for detailed setup.

### Git Workflow

- Main branch: `main` (production-ready)
- Feature branches: `feature/...`
- Bug branches: `bugfix/...`
- Enable git hooks: `git config core.hooksPath .githooks`

See [docs/guides/CONTRIBUTING.md](docs/guides/CONTRIBUTING.md) for contribution guidelines.

### Testing

```bash
# Backend tests
uv run pytest backend/tests/ tests/ -v

# Frontend lint
cd frontend && npm run lint
```

See [docs/guides/TESTING.md](docs/guides/TESTING.md) for comprehensive test documentation.

---

## Technology Stack

| Component | Technology | Location |
|-----------|-----------|----------|
| Backend | FastAPI + Uvicorn (Python 3.10+) | `backend/` |
| Frontend | Next.js 16 + React 19 + TypeScript | `frontend/` |
| Database | PostgreSQL 15 (SQLAlchemy ORM) | Docker container |
| Storage | Azure Blob / Azurite | Docker container |
| Analysis | Tree-sitter multi-language AST | `backend/intelligence/parsers/` |
| Vector Search | ChromaDB | Docker volume |
| Agent Orchestration | LangGraph | `backend/agent/` |
| Container Verification | Docker-out-of-Docker | `backend/verification/` |

---

## Important Notes

- **Docker-First Backend**: The entire backend, PostgreSQL, and Azurite run in Docker Compose. No SQLite; PostgreSQL only.
- **No SQLite**: The project strictly prohibits SQLite. All persistence uses PostgreSQL in a Docker container. See CLAUDE.md §Architecture Rules.
- **Data Directory**: The `./data` directory (mounted as `/app/data` in Docker) persists worktrees and cached repositories.
- **Environment Variables**: Always configure `.env` for LOCAL development; use environment variables in PROD.

---

## Documentation Index

Start here based on your role:

- **New Developer**: Read [docs/README.md](docs/README.md) → [docs/guides/DEVELOPMENT.md](docs/guides/DEVELOPMENT.md)
- **Contributing Code**: [docs/guides/CONTRIBUTING.md](docs/guides/CONTRIBUTING.md) → [docs/guides/TESTING.md](docs/guides/TESTING.md)
- **Understanding Architecture**: [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) → [docs/architecture/DATA_MODEL.md](docs/architecture/DATA_MODEL.md)
- **Building Agent Features**: [docs/guides/AGENTS.md](docs/guides/AGENTS.md) → [backend/AGENTS.md](backend/AGENTS.md)
- **Debugging Issues**: [docs/diagnostics/](docs/diagnostics/) → Relevant error logs in `logs/`
