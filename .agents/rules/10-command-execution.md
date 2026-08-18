# Verified Project Command Reference & Execution Guardrails

All commands in this document have been empirically executed and verified on the active system to prevent trial-and-error failures.

---

## 1. Environment & Network Invariants (Crucial!)

| Service | When Running Inside Docker | When Running On Host (Outside Docker) |
| :--- | :--- | :--- |
| **PostgreSQL DB** | `postgresql+psycopg://myuser:mypassword@postgres:5432/repository_intelligence` | `postgresql+psycopg://myuser:mypassword@localhost:5432/repository_intelligence` |
| **Azurite Storage** | `http://azurite:10000/devstoreaccount1` | `http://localhost:10100/devstoreaccount1` |
| **Ollama LLM** | `http://host.docker.internal:11434` | `http://localhost:11434` |
| **FastAPI Backend** | `http://backend:8000` | `http://localhost:8000` |
| **Next.js UI** | — | `http://localhost:3000` |

> [!IMPORTANT]
> When executing test or backend commands directly on the host machine, ensure `LOCAL_DATABASE_URL` points to `localhost:5432` and `AZURE_STORAGE_ENDPOINT` points to `localhost:10100`:
> ```powershell
> $env:LOCAL_DATABASE_URL="postgresql+psycopg://myuser:mypassword@localhost:5432/repository_intelligence"
> ```

---

## 2. Python Backend & Test Suites (`uv`)

*Working Directory*: Root (`e:\GitOnboard`)

### Automated Test Execution

| Target | Command | Notes |
| :--- | :--- | :--- |
| **Phase 2 Sandbox Terminal Tests** | `uv run pytest tests/test_phase2_sandbox_terminal.py -v` | 7/7 PASSED |
| **Phase 1 File Loading & Azurite** | `uv run pytest tests/test_phase1_file_loading.py -v` | 5/5 PASSED |
| **All Unit Test Suites** | `uv run pytest backend/tests/unit/ -v` | 38/38 PASSED |
| **Baseline Integration Tests** | `uv run pytest tests/test_baseline_integration.py -v` | Captures baseline state |
| **Run Single Test by Name** | `uv run pytest tests/test_phase2_sandbox_terminal.py -k test_sandbox_pwd_returns_real_worktree -v` | Filter by function |
| **Show Print Statements & Live Logs** | `uv run pytest tests/test_phase2_sandbox_terminal.py -s --log-cli-level=INFO` | Uncaptured stdout |

### Backend Dev Server & Migrations

| Task | Command | Notes |
| :--- | :--- | :--- |
| **Start Local FastAPI Server** | `uv run uvicorn backend.main:app --reload --port 8000` | API & OpenAPI docs at `/docs` |
| **Apply DB Migrations** | `uv run alembic upgrade head` | Migrates PostgreSQL schema |
| **Generate Autodetected Migration** | `uv run alembic revision --autogenerate -m "description"` | Inspect generated file |
| **Check Current Migration Version** | `uv run alembic current` | Displays active revision |
| **Rollback Migration** | `uv run alembic downgrade -1` | Reverts last migration |

### Dependency Management

| Task | Command | Notes |
| :--- | :--- | :--- |
| **Sync Virtual Environment** | `uv sync` | Updates `.venv` from `uv.lock` |
| **Add Runtime Dependency** | `uv add <package>` | Updates `pyproject.toml` and lock |
| **Add Dev/Test Dependency** | `uv add --dev <package>` | Adds to `[dependency-groups.dev]` |
| **Remove Dependency** | `uv remove <package>` | Removes from `pyproject.toml` |

---

## 3. Frontend Next.js 16 (`npm`)

*Working Directory*: `e:\GitOnboard\frontend` (MANDATORY)

| Task | Command | Notes |
| :--- | :--- | :--- |
| **Start Next.js Dev Server** | `npm run dev` | Runs on `http://localhost:3000` |
| **Production Build & Type Check** | `npm run build` | Verified: 0 TypeScript / compilation errors |
| **Start Production Bundle** | `npm start` | Requires prior `npm run build` |
| **Run ESLint Checks** | `npm run lint` | Runs ESLint 9 against app router |
| **Install Project Dependencies** | `npm install` | Uses `frontend/package.json` |
| **Add Frontend Package** | `npm install <package>` | Installs runtime package |
| **Add Dev Package** | `npm install -D <package>` | Installs build/type package |

---

## 4. Docker & Multi-Container Infrastructure (`docker-compose`)

*Working Directory*: Root (`e:\GitOnboard`)

| Task | Command | Notes |
| :--- | :--- | :--- |
| **Build & Start All Services** | `docker-compose up --build` | Starts backend, postgres, azurite, pgadmin |
| **Start in Background (Detached)** | `docker-compose up -d` | Background mode |
| **View Live Backend Logs** | `docker-compose logs -f backend` | Streams FastAPI logs |
| **View Live Azurite Logs** | `docker-compose logs -f azurite` | Streams blob storage logs |
| **View Live PostgreSQL Logs** | `docker-compose logs -f postgres` | Streams database logs |
| **Restart Single Service** | `docker-compose restart backend` | Reloads backend without full rebuild |
| **Execute Command Inside Backend** | `docker exec gitonboard-backend-1 pytest ...` | Runs inside container environment |
| **Check Container Health** | `docker ps` | Lists container ports and health |
| **Stop All Containers** | `docker-compose down` | Preserves database/storage volumes |
| **Hard Reset Containers & Volumes** | `docker-compose down -v` | Wipes volumes for clean re-init |

---

## 5. Prohibited Anti-Patterns

1. **NEVER use raw `pip install`** or create `requirements.txt`. Always use `uv add` / `uv sync`.
2. **NEVER run `npm` from workspace root**. `package.json` is located in `frontend/`. Always set `Cwd: e:\GitOnboard\frontend`.
3. **NEVER use `cd` in tool commands**. Set the `Cwd` parameter directly in tool calls.
4. **NEVER use hardcoded `localhost` inside Docker or `postgres`/`azurite` hostnames on the Windows host**. Use the table in Section 1.
