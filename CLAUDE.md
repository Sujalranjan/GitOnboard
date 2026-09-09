# GitOnBoard - AI Assistant Guidelines

## CRITICAL ARCHITECTURAL RULES (STRICT COMPLIANCE REQUIRED)

> ### ⛔ ABSOLUTELY NO SQLITE
> - **DO NOT USE SQLITE** under any circumstances for development, debugging, scripts, or local testing.
> - **DO NOT CREATE OR REFERENCE sqlite:/// OR *.db FILES** (e.g., intelligence.db).
> - The application **ONLY** runs on **PostgreSQL 15** via Docker Compose (postgresql+psycopg://...).
> - ackend/database.py explicitly rejects SQLite connections when not in isolated test runs. Never configure, mock, or switch the system to SQLite.

> ### 🐳 DOCKER-FIRST BACKEND & SERVICES
> - The entire backend, database, and storage dependencies run inside **Docker Compose**.
> - **PostgreSQL** is **NOT** installed on the host machine. It runs in container postgres on port 5432.
> - **Azure Blob Storage** is **NOT** a cloud instance by default. It runs locally in container zurite (emulating Blob Storage on ports 10100:10000).
> - **FastAPI backend** runs in container ackend on port 8000.
> - Always execute backend migrations, commands, and tests inside the container or against the Dockerized services.

---

## Architecture & Tech Stack

- **Container Engine**: Docker & Docker Compose
- **Backend**: Python 3.10+, FastAPI, Uvicorn, LangGraph, Pydantic Settings, Tree-sitter, ChromaDB
- **Database**: PostgreSQL 15 (SQLAlchemy ORM + Psycopg 3 + Alembic migrations)
- **Object Storage**: Azure Blob Storage / Azurite (Container zurite)
- **Frontend**: TypeScript, Next.js 16 (App Router), React 19, Tailwind CSS 4, React Flow, Monaco Editor, Xterm.js
- **Sandboxing**: Docker-out-of-Docker (/var/run/docker.sock) for ephemeral verification runners

---

## Development & Execution Commands

### Infrastructure & Backend (Docker Compose)
All backend work and persistence rely on Docker Compose:

`ash
# Start all services (PostgreSQL, Azurite, pgAdmin, Backend)
docker compose up -d --build

# View backend logs
docker compose logs -f backend

# Run database migrations (ALWAYS against Dockerized PostgreSQL)
docker compose exec backend alembic upgrade head

# Create a new migration revision
docker compose exec backend alembic revision --autogenerate -m  description

# Run tests inside the backend container
docker compose exec backend pytest

# Restart backend after code or dependency changes
docker compose restart backend

# Stop all containers
docker compose down
`

### Frontend (Host Machine)
Frontend runs locally on Node:

`ash
cd frontend

# Install dependencies
npm install

# Start Next.js development server (connects to backend at http://localhost:8000)
npm run dev

# Lint & build
npm run lint
npm run build
`

---

## Directory Structure Overview

`
├── docker-compose.yml       # Defines postgres, azurite, pgadmin, and backend
├── alembic/                 # PostgreSQL migrations (alembic.ini at root)
├── backend/                 # FastAPI application (Dockerized)
│   ├── main.py              # Application entry point
│   ├── database.py          # SQLAlchemy PostgreSQL session management
│   ├── config.py            # Environment settings (Pydantic)
│   ├── models/              # SQLAlchemy database models
│   ├── routers/             # API routes (REST + SSE)
│   ├── agent/ & ai/         # LangGraph agents & LLM orchestration
│   ├── intelligence/        # Tree-sitter AST parsers & symbol resolvers
│   ├── verification/        # DockerVerificationRunner & test pipelines
│   └── tests/               # Backend test suites
├── frontend/                # Next.js 16 Web Dashboard
│   ├── app/                 # Next.js App Router (pages & layouts)
│   ├── components/          # React components (editor, visualizer, terminal)
│   └── lib/ & services/     # API clients & state utilities
└── data/                    # Worktrees, repository caches (mounted into backend container)
`

---

## Important Connection Details

| Service | Host Port | Internal Docker URL | Credentials / Notes |
| :--- | :--- | :--- | :--- |
| **Backend API** | 8000 | http://backend:8000 | FastAPI docs at http://localhost:8000/docs |
| **PostgreSQL** | 5432 | postgresql+psycopg://myuser:mypassword@postgres:5432/repository_intelligence | Database: epository_intelligence |
| **Azurite (Blob)**| 10100 | http://azurite:10000/devstoreaccount1 | Container: gitonboard-repos |
| **pgAdmin** | 5050 | - | dmin@example.com / dminpassword |
| **ChromaDB** | Volume | Persistent cache volume chroma_cache | Vector index for semantic symbols |

---

## Instructions for AI Assistant

1. **Never switch to or suggest SQLite**: If a database issue arises, verify Docker and container health (docker compose ps, docker compose logs postgres). Do not fall back to SQLite or suggest creating .db files.
2. **Respect Docker paths vs Host paths**: The ./data directory on the host maps to /app/data in the backend container.
3. **Database schema changes**: Always create and apply Alembic migrations using docker compose exec backend alembic ....
