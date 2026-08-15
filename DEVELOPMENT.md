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

Copy the example environment configuration:

```bash
cp .env.example .env
```

Key configuration parameters in `.env`:
```ini
DATABASE_URL=postgresql+psycopg://myuser:mypassword@localhost:5432/repository_intelligence
LOCAL_DATABASE_URL=postgresql+psycopg://myuser:mypassword@localhost:5432/repository_intelligence
FRONTEND_URL=http://localhost:3000
ENVIRONMENT=development
JWT_SECRET=your_jwt_secret_key
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
```

---

## 3. Starting the Services

### Option A: Docker Compose (Full Stack Backend + Database + pgAdmin)
```bash
docker compose up --build -d
```
- **FastAPI Backend**: `http://localhost:8000`
- **Swagger API Docs**: `http://localhost:8000/docs`
- **PostgreSQL Database**: `localhost:5432` (`repository_intelligence`)
- **pgAdmin 4 Web UI**: `http://localhost:5050` (`admin@example.com` / `adminpassword`)

### Option B: Local Backend with Dockerized Database
Start only the database and pgAdmin in Docker:
```bash
docker compose up postgres pgadmin -d
```
Install backend dependencies and run the FastAPI server:
```bash
uv sync
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
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
