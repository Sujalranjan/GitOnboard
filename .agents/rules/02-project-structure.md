---
trigger: always_on
---

# Project Structure & Ownership

The repository structure is strictly organized by responsibility:

```text
/
├── backend/          # FastAPI application, intelligence engine, models, database, and workers
├── frontend/         # Next.js 16 App Router UI, React 19 components, ReactFlow graph canvas
├── tests/            # End-to-end integration and API contract test suites
├── docs/             # Technical documentation and domain contracts (docs/contracts/*)
├── reports/          # Static analysis, wiring audits, and architecture health reports
├── data/             # Local cloned repositories (data/repos/) and cache data
├── archive/legacy/   # Deprecated, orphaned code (READ-ONLY / NOT ACTIVE)
├── .agents/          # AI instruction guide and behavioral rules
└── pyproject.toml    # Python project configuration and dependency definitions (uv)
```

## Directory Rules
- **Backend Code**: All backend services, routers, models, and intelligence modules belong inside `backend/`.
- **Frontend Code**: All UI presentation, Next.js routes, components, and client hooks belong inside `frontend/`.
- **Tests**: Automated tests belong inside `tests/` or `backend/tests/`. Never place tests beside runtime implementation files.
- **Root Documentation**: Canonical engineering documentation files (`README.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`, `AGENTS.md`, `DEVELOPMENT.md`, `API.md`, `DATA_MODEL.md`, `TESTING.md`, `DECISIONS.md`) reside in the root directory.
- **Domain Contracts**: Deep architectural contracts and pipeline stage specifications belong in `docs/contracts/`.
- **No Unapproved Directories**: Never create new top-level directories without explicit instruction.
