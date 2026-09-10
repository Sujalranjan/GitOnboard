# Project Structure

## Overview

This project is organized into logical directories based on usage and development workflow:

```
repository_intelligence_platform/
├── backend/                    # Backend application
├── frontend/                   # Frontend application
├── data/                       # Runtime data and artifacts
├── logs/                       # Application logs
├── docs/                       # Project documentation
├── scripts/                    # Utility and automation scripts
├── tests/                      # Test suites
├── docker/                     # Docker configurations
├── alembic/                    # Database migrations
├── .workspace/                 # Development workspace (diagnostics, analysis)
├── Configuration files         # Root-level configuration
└── Dependencies                # Python and lock files
```

## Directory Reference

### Core Application

| Directory | Purpose | Usage |
|-----------|---------|-------|
| `backend/` | Backend server (FastAPI, services, intelligence engines) | Daily development, API implementation |
| `frontend/` | Frontend application (React, UI components) | UI development, feature implementation |
| `docker/` | Docker configuration and compose definitions | Container building, environment setup |
| `alembic/` | Database schema migrations | Database version control, schema changes |

### Runtime & Data

| Directory | Purpose | Usage |
|-----------|---------|-------|
| `data/` | Runtime data including worktrees, indexes, caches | Auto-generated during analysis |
| `logs/` | Application logs (backend, frontend, system) | Debugging, troubleshooting, monitoring |

### Development & Documentation

| Directory | Purpose | Usage |
|-----------|---------|-------|
| `docs/` | Project documentation | Setup guides, architecture, API reference |
| `docs/architecture/` | Architecture and design documents | System design, data models |
| `docs/guides/` | Developer guides and instructions | Development workflow, testing |
| `docs/reports/` | Implementation reports | Feature completion reports |
| `scripts/` | Utility and automation scripts | Database setup, deployment, testing |
| `tests/` | Test suites and fixtures | Unit tests, integration tests |

### Development Workspace

| Directory | Purpose | Usage |
|-----------|---------|-------|
| `.workspace/` | Temporary workspace for development | Research, analysis, diagnostics |
| `.workspace/diagnostics/` | Investigation reports and findings | Troubleshooting history |
| `.workspace/scripts/` | Test and debug scripts | Experimentation, verification |
| `.workspace/analysis/` | Analysis outputs and logs | Data investigation results |
| `.workspace/benchmark/` | Performance benchmarks | Performance testing |
| `.workspace/evaluation/` | Evaluation scenarios | Feature testing |
| `.workspace/archive/` | Old code and archives | Legacy implementations |
| `.workspace/reports/` | Historical reports | Previous findings |

### Configuration Files (Root)

| File | Purpose |
|------|---------|
| `pyproject.toml` | Python project metadata, dependencies |
| `uv.lock` | Python dependency lock file |
| `alembic.ini` | Database migration configuration |
| `docker-compose.yml` | Docker services orchestration |
| `.env` | Environment variables (local) |
| `.env.example` | Environment template |
| `.gitignore` | Git ignore patterns |
| `.github/` | GitHub workflows and templates |

## Development Workflow

### Adding New Features

1. **Backend feature**: Edit in `backend/`
2. **Frontend feature**: Edit in `frontend/`
3. **Database schema**: Create migration in `alembic/versions/`
4. **Tests**: Add to `tests/`
5. **Documentation**: Update `docs/`

### Running the Application

```bash
# Start services
docker-compose up -d

# Run migrations
uv run alembic upgrade head

# Start backend (development)
cd backend && uv run python -m uvicorn main:app --reload

# Start frontend (development)
cd frontend && npm start
```

### Database Management

All database migrations are in `alembic/`:
- Create new migration: `alembic revision --autogenerate -m "description"`
- Apply migrations: `alembic upgrade head`
- View migration history: `alembic current`

## Code Organization

### Backend Structure

```
backend/
├── models/           # Database models
├── services/         # Business logic services
├── routers/          # API endpoints
├── intelligence/     # Analysis engines and RIM
├── storage/          # Storage backends (Azure, local)
├── database/         # Database configuration
└── logger.py         # Logging configuration
```

### Frontend Structure

```
frontend/
├── src/
│   ├── components/   # React components
│   ├── pages/        # Page components
│   ├── services/     # API clients
│   ├── hooks/        # Custom React hooks
│   └── App.tsx       # Root component
└── public/           # Static assets
```

## Key Patterns

### Logging

- **Structured logging**: Use Python `logging` module with descriptive prefixes
- **Log format**: `[PREFIX] Message with context`
- **Examples**: `[BLOB_UPLOAD]`, `[CLEANUP]`, `[SOURCE_READER]`

### Error Handling

- Fail explicitly with clear error messages
- Log errors with full context and traceback
- Use custom exception types when helpful

### Database

- All schema changes via Alembic migrations
- Write migrations that are reversible
- Test migrations on fresh database

## Clean Repository Policy

- `docs/` contains project documentation only
- `.workspace/` contains temporary work, diagnostics, analysis
- No temporary files in root
- No uncommitted configuration in version control

## Maintenance

### Disk Cleanup

```bash
# Remove old workspace files
rm -rf .workspace/diagnostics/*.md

# Clear analysis outputs
rm -rf .workspace/analysis/*

# Clean Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
```

### Documentation Updates

Keep documentation in sync with code:
- Update `docs/architecture/` when changing system design
- Update `docs/guides/` when changing development workflow
- Archive old reports to `.workspace/reports/`

---

**Last Updated**: 2026-09-03  
**Organized By**: Claude Haiku 4.5
