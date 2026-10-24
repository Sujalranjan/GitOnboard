# GitOnBoard - Repository Intelligence Platform

An advanced code analysis and intelligence platform that ingests GitHub repositories, builds deterministic abstract syntax trees and knowledge graphs, detects architectural capabilities, and provides semantic search and interactive visualization.

---

## Quick Start (5 minutes)

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ & npm
- Python 3.10+ with `uv`

### Start the Platform

```bash
# Start backend, database, and storage
docker compose up --build -d

# Start frontend (in a new terminal)
cd frontend
npm install
npm run dev
```

**Access:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000 (docs: http://localhost:8000/docs)
- Database UI: http://localhost:5050 (pgAdmin)

For detailed setup, environment configuration, and troubleshooting, see [Development Guide](docs/guides/DEVELOPMENT.md).

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | FastAPI (Python 3.10+), Uvicorn |
| **Frontend** | Next.js 16, React 19, TypeScript |
| **Database** | PostgreSQL 15 (SQLAlchemy ORM) |
| **Storage** | Azure Blob / Azurite |
| **Analysis** | Tree-sitter (multi-language AST parsing) |
| **Containers** | Docker & Docker Compose |

---

## Documentation

- **[Project Structure](PROJECT_STRUCTURE.md)** — Directory layout and file organization
- **[Architecture](docs/architecture/ARCHITECTURE.md)** — System design and pipeline flow
- **[Data Model](docs/architecture/DATA_MODEL.md)** — Database schema and relationships
- **[Development](docs/guides/DEVELOPMENT.md)** — Detailed setup and development workflow
- **[Testing](docs/guides/TESTING.md)** — Test suites and verification
- **[Full Documentation Index](docs/README.md)** — Complete guide to all documentation

---

## Project Guidelines

This is a college-level Final Year Project. See [CLAUDE.md](CLAUDE.md) for engineering principles and architectural constraints.

**Key Rules:**
- Backend and database run in Docker Compose (PostgreSQL only — no SQLite)
- All code follows deterministic, inspectable patterns
- Documentation is kept simple and aligned with actual implementation

---

## License & Commercial Use

GitOnboard is licensed under the **[PolyForm Noncommercial License 1.0.0](LICENSE)**.

- **Noncommercial & Educational Use:** GitOnboard is freely available for qualifying educational, academic, personal, hobby, and other noncommercial purposes (such as learning, teaching, experimentation, and research).
- **Commercial Use Restrictions:** Commercial use is **strictly not permitted** under this license without separate, prior written authorization from the copyright holder.
- **Public Availability:** The public availability of this repository on GitHub does not grant commercial rights or licenses.
- **Inquiries:** Anyone seeking commercial licensing or permissions should contact the project owner, **Dheeraj Salian**, via GitHub: [https://github.com/salianDheeraj](https://github.com/salianDheeraj) or email: [dheerajsalian16@gmail.com](mailto:dheerajsalian16@gmail.com).

