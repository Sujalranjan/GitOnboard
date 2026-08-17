# Local Development & Environment Guide

This document contains verifiable commands and instructions for setting up, running, testing, and debugging the Repository Intelligence Platform.

---

## 1. Prerequisites

- **Python**: 3.10 or higher (3.12 recommended)
- **uv**: Fast Python package installer and resolver (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js**: 18+ (Node 20+ recommended) & npm
- **Docker & Docker Compose**: For PostgreSQL container and pgAdmin 4
- **Ollama**: (Optional) For local LLM summary generation (`http://localhost:11434`)

---

## 2. Setting Up Environment Variables

Copy the structured template to `.env`:

```bash
cp .env.example .env
```

### Environment Variable Reference

| Section | Parameter | Description | Default / Example |
| :--- | :--- | :--- | :--- |
| **App & Deployment** | `DEPLOYMENT_TYPE` | Deployment target (`LOCAL` or `PROD`) | `LOCAL` |
| | `ENVIRONMENT` | Environment tag (`development`, `staging`, `production`) | `development` |
| | `APP_NAME` | Display name of the application | `Repository Intelligence Platform` |
| **Database** | `LOCAL_DATABASE_URL` | PostgreSQL connection string for host execution | `postgresql+psycopg://myuser:mypassword@localhost:5432/repository_intelligence` |
| | `DATABASE_URL` | PostgreSQL connection string for Docker container | `postgresql+psycopg://myuser:mypassword@postgres:5432/repository_intelligence` |
| | `PROD_DATABASE_URL` | Production PostgreSQL connection string | (Optional for PROD) |
| **Frontend** | `LOCAL_FRONTEND_URL` | Local Next.js frontend URL for CORS & redirects | `http://localhost:3000` |
| | `PROD_FRONTEND_URL` | Production frontend URL | (Optional for PROD) |
| **Security & Auth** | `JWT_SECRET` | Secret key used to sign session JWTs | `change_me_to_a_secure_random_secret_in_production` |
| | `JWT_ALGORITHM` | Cryptographic algorithm for JWT | `HS256` |
| | `JWT_EXPIRE_MINUTES` | Session token lifetime in minutes | `1440` (24h) |
| **GitHub OAuth** | `GITHUB_CLIENT_ID` | OAuth application Client ID | (From GitHub Developer Settings) |
| | `GITHUB_CLIENT_SECRET` | OAuth application Client Secret | (From GitHub Developer Settings) |
| **Blob Storage** | `AZURE_STORAGE_ACCOUNT_NAME` | Azurite/Azure storage account | `devstoreaccount1` |
| | `AZURE_STORAGE_ACCOUNT_KEY` | Azurite/Azure access key | Azurite standard development key |
| | `AZURE_STORAGE_CONTAINER` | Target Blob container name | `gitonboard-repos` |
| | `AZURE_STORAGE_ENDPOINT` | Storage emulator endpoint URL | `http://localhost:10100/devstoreaccount1` (host) / `http://azurite:10000/devstoreaccount1` (Docker) |
| **AI / LLM Providers** | `OPENROUTER_API_KEY` | OpenRouter API Key (Primary cloud provider) | (Optional) |
| | `NVIDIA_API_KEY` | NVIDIA NIM API Key (Secondary cloud provider) | (Optional) |
| | `GEMINI_API_KEY` | Google Gemini API Key | (Optional) |
| | `OLLAMA_BASE_URL` | Ollama service endpoint (Fallback provider) | `http://localhost:11434` (host) / `http://host.docker.internal:11434` (Docker) |
| | `OLLAMA_MODEL` | Default Ollama model tag | `qwen2.5-coder:7b` |
| | `OLLAMA_TIMEOUT` | Ollama HTTP request timeout in seconds | `300.0` |
| **Summary Pipeline** | `SUMMARY_VERBOSE_AUDIT` | Save full 01-11 telemetry files in evaluation/runs/ | `false` (set `true` for debugging) |

---

## 3. Starting the Services

### Option A: Docker Compose (Full Stack Backend + Database + Azurite + pgAdmin)
```bash
docker compose up --build -d
```
- **FastAPI Backend**: `http://localhost:8000`
- **Swagger API Docs**: `http://localhost:8000/docs`
- **PostgreSQL Database**: `localhost:5432` (`repository_intelligence`)
- **Azurite Blob Storage**: `localhost:10100` (Blob), `10101` (Queue), `10102` (Table)
- **pgAdmin 4 Web UI**: `http://localhost:5050` (`admin@example.com` / `adminpassword`)

### Option B: Local Backend with Dockerized Services
Start the database, pgAdmin, and Azurite in Docker:
```bash
docker compose up postgres pgadmin azurite -d
```
Install backend dependencies and run the FastAPI server:
```bash
uv sync
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 3.1 Verifying & Testing Storage (Azurite)

See [docs/STORAGE_ARCHITECTURE_AND_AZURITE.md](docs/STORAGE_ARCHITECTURE_AND_AZURITE.md) for full testing workflows with Azure CLI, PowerShell, and Python.

**Quick Verification Command**:
```bash
uv run python -c "
from backend.storage import get_storage
storage = get_storage()
storage.ensure_container_exists()
storage.put_object('test.txt', 'hello from azurite')
print('Storage verified:', storage.get_object_text('test.txt'))
"
```

---

## 4. Starting the Frontend (Next.js 16)

```bash
cd frontend
npm install
npm run dev
```
The frontend starts on `http://localhost:3000`.

---

## 5. Running Tests

Execute test suites using `uv run pytest`:

```bash
# Run all active test suites
uv run pytest -v

# Run Fact Store persistence and Layer 6 capability detection tests
uv run pytest backend/tests/ -v

# Run integration and API contract tests
uv run pytest tests/ -v
```

---

## 6. Code Quality & Linting

```bash
# Python linting
uv run ruff check backend tests

# Frontend linting
cd frontend && npm run lint
```
