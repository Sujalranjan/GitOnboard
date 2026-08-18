# Command Execution Playbook & Zero-Guesswork Standard

This rule defines the canonical, verified commands for developing, testing, running, and inspecting services in this repository on **Windows** using **PowerShell (`pwsh` / Windows PowerShell)** and **Linux / WSL 2**. Always use these exact commands to prevent trial-and-error.

### Terminal & Environment Notes (Windows)
- **Primary Shell**: PowerShell 7+ (`pwsh`) or Windows PowerShell 5.1
- **API Probing**: Use `curl.exe` (explicit `.exe` suffix) instead of `curl` on PowerShell to avoid invoking PowerShell's native `Invoke-WebRequest` alias. Alternatively use `Invoke-RestMethod`.
- **uv on Windows**: Install via `irm https://astral.sh/uv/install.ps1 | iex` in PowerShell.
- **WSL 2 Integration**: When running Linux bash commands, use `wsl -e bash -c "<command>"`.

---

## 1. Python Dependency Governance: The "Never Use Pip" Rule

This project strictly uses `uv` for Python 3.10+ package management, dependency resolution, and virtualenv execution.

### Why Raw `pip` is Forbidden
1. **No Lockfile Tracking**: Raw `pip install` mutates environment packages without resolving constraints into `uv.lock` or updating `pyproject.toml`.
2. **Environment Pollution & Drift**: Leads to broken builds, unpinned sub-dependencies, and unreproducible states between local dev, Docker, and CI/CD.
3. **Speed & Determinism**: `uv` provides sub-second deterministic installs, reproducible lockfiles, and managed Python runtimes.

### Pip-to-UV Translation Matrix
| Legacy `pip` Action | Mandatory `uv` Command | Notes |
| :--- | :--- | :--- |
| `pip install <pkg>` | `uv add <pkg>` | Adds dependency to `pyproject.toml` and updates `uv.lock` |
| `pip install -r req.txt` | `uv sync` | Fast sync of `.venv` with `uv.lock` |
| `pip install --dev <pkg>` | `uv add --dev <pkg>` | Adds to `[dependency-groups] dev` |
| `pip uninstall <pkg>` | `uv remove <pkg>` | Removes package and prunes unused dependencies |
| `pip freeze` | `uv lock` / `uv export` | Manages and exports locked dependencies |
| `python script.py` | `uv run python script.py` | Runs strictly within managed virtualenv |
| `python -m pytest` | `uv run pytest` | Executes test runner in `.venv` |
| `pip list` | `uv tree` / `uv pip list` | Inspects full dependency resolution graph |

---

## 2. Docker: Individual Container Operations & Life Cycle

The local infrastructure consists of 4 distinct services defined in `docker-compose.yml`:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        DOCKER COMPOSE SERVICES                         │
│                                                                        │
│  1. postgres (5432)  ──► PostgreSQL 15 database container              │
│  2. azurite (10100)  ──► Azure Blob Storage local emulator             │
│  3. pgadmin (5050)   ──► pgAdmin 4 web management UI                   │
│  4. backend (8000)   ──► FastAPI application container with live mount │
└────────────────────────────────────────────────────────────────────────┘
```

### A. Managing Individual Containers
| Action | Command | Purpose |
| :--- | :--- | :--- |
| **Start Database Only** | `docker compose up -d postgres` | Starts PostgreSQL on port `5432` |
| **Start Storage Only** | `docker compose up -d azurite` | Starts Blob (`10100`), Queue (`10101`), Table (`10102`) |
| **Start pgAdmin Only** | `docker compose up -d pgadmin` | Starts Web UI on `http://localhost:5050` |
| **Start Backend Container** | `docker compose up -d --build backend` | Rebuilds and starts FastAPI backend container |
| **Start All Backing Services**| `docker compose up postgres pgadmin azurite -d` | Ready for host-based FastAPI execution |
| **Start Full Stack** | `docker compose up --build -d` | All 4 services running containerized |
| **Restart Single Container** | `docker compose restart <service_name>` | e.g. `docker compose restart backend` |
| **Stop Single Container** | `docker compose stop <service_name>` | Gracefully stops specific service |
| **Inspect Active Containers** | `docker ps` | Lists container IDs, images, uptime, and port maps |

### B. Container Logs & Shell Access
| Target | Follow Logs | Interactive Shell / Exec |
| :--- | :--- | :--- |
| **Postgres** | `docker compose logs -f postgres` | `docker compose exec postgres sh` |
| **Azurite** | `docker compose logs -f azurite` | `docker compose exec azurite sh` |
| **pgAdmin** | `docker compose logs -f pgadmin` | `docker compose exec pgadmin sh` |
| **Backend** | `docker compose logs -f backend` | `docker compose exec backend sh` (or `bash`) |

### C. Direct Database (psql) Operations in Container
| Database Task | Verified Command |
| :--- | :--- |
| **Interactive psql Shell** | `docker compose exec postgres psql -U myuser -d repository_intelligence` |
| **List All Tables** | `docker compose exec postgres psql -U myuser -d repository_intelligence -c "\dt"` |
| **Execute Arbitrary Query** | `docker compose exec postgres psql -U myuser -d repository_intelligence -c "<SQL_QUERY>"` |
| **Database Backup (Dump)** | `docker compose exec postgres pg_dump -U myuser repository_intelligence > backup.sql` |
| **Database Restore** | `docker compose exec -i postgres psql -U myuser -d repository_intelligence < backup.sql` |

---

## 3. Database Migrations (`alembic`)

Alembic migrations manage schema evolutions in `alembic/versions/`.

### Preferred: Containerized Execution (Direct DB Network)
Because `alembic.ini` connects to `postgres:5432` by default inside Docker:
```bash
# Check current migration revision
docker compose exec backend alembic current

# Check migration history
docker compose exec backend alembic history

# Apply all pending migrations to latest schema
docker compose exec backend alembic upgrade head

# Rollback 1 migration step
docker compose exec backend alembic downgrade -1

# Generate auto-migration from model changes
docker compose exec backend alembic revision --autogenerate -m "describe changes"
```

### Host Execution (Outside Docker)
If running Alembic from host PowerShell/bash, override the connection URL to `localhost:5432`:
```powershell
# PowerShell (Windows)
$env:DATABASE_URL="postgresql+psycopg://myuser:mypassword@localhost:5432/repository_intelligence"; uv run alembic upgrade head
```
```bash
# Bash (Linux/macOS)
DATABASE_URL="postgresql+psycopg://myuser:mypassword@localhost:5432/repository_intelligence" uv run alembic upgrade head
```

---

## 4. Automated Testing Suites (`pytest`)

Always execute test suites using `uv run pytest`:

| Test Target | Command | Scope |
| :--- | :--- | :--- |
| **Core Suite (73+ Passing Tests)** | `uv run pytest backend/tests/test_capabilities.py backend/tests/test_fact_store.py backend/tests/test_sql_integrity.py backend/tests/unit tests/ -v` | Layer 6 capabilities, Fact Store, SQL schema integrity, Blob storage, AI models, and integration tests |
| **Capability Engine Only** | `uv run pytest backend/tests/test_capabilities.py -v` | Deterministic AST & rule-based engine |
| **Fact Store Only** | `uv run pytest backend/tests/test_fact_store.py -v` | Relational Fact Store persistence |
| **SQL Integrity Only** | `uv run pytest backend/tests/test_sql_integrity.py -v` | Foreign keys and composite keys |
| **Inside Docker Container** | `docker compose exec backend pytest backend/tests/ -v` | Runs test runner within container environment |

---

## 5. FastAPI Backend Live Probing & Verification

| Goal | Command | Response / Invariant |
| :--- | :--- | :--- |
| **Start Local Dev Server** | `uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload` | Live reload on code changes |
| **API Health Probe (curl)** | `curl.exe -s http://localhost:8000/api/health` | `{"status":"healthy","database":"connected"}` |
| **API Root Probe (curl)** | `curl.exe -s http://localhost:8000/` | `{"message":"Welcome to Repository Intelligence Platform API"}` |
| **PowerShell Native Probe** | `Invoke-RestMethod http://localhost:8000/api/health` | Native PowerShell object |
| **Swagger Interactive Docs** | Open browser to `http://localhost:8000/docs` | OpenAPI 3.0 API explorer |

---

## 6. Next.js 16 Frontend (React 19 & Tailwind CSS 4)

Frontend commands must be run from `frontend/`:

| Goal | Command | Notes |
| :--- | :--- | :--- |
| **Install Packages** | `cd frontend && npm install` | Uses npm for Next.js 16 App Router |
| **Start Dev Server** | `cd frontend && npm run dev` | UI served on `http://localhost:3000` |
| **Production Build** | `cd frontend && npm run build` | Next.js Turbopack build |
| **Lint Code** | `cd frontend && npm run lint` | ESLint check |

---

## 7. Storage Verification (Azurite Blob)

Validate Blob emulator read/write object roundtrips via Python:

```bash
uv run python -c "from backend.storage import get_storage; s = get_storage(); s.ensure_container_exists(); s.put_object('test.txt', 'hello from azurite'); print('Storage verified:', s.get_object_text('test.txt'))"
```

---

## 8. Code Quality & Formatting (`ruff`)

```bash
# Check Python lint errors
uv run ruff check backend tests

# Format Python code
uv run ruff format backend tests
```
