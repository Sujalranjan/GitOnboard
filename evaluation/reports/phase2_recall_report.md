# Phase 2 — Evidence-Based Retrieval & Real Qwen Writer Recall Benchmark Report

## 1. Executive Summary

| Evaluation Metric | Measured Value | Standard / Target |
| :--- | :---: | :---: |
| **Total Curated Facts** | **50 facts** | 100% Curated across 15 Repos |
| **Evidence-Grounded Facts Retrieved** | **50 / 50 (100.0%)** | Authoritative evidence ID present in context |
| **Facts Correctly Synthesized by Writer** | **47 / 50 (94.0%)** | Real Qwen 2.5-Coder output |
| **Deterministic Retrieval Recall** | **100.0%** | Target: >= 95.0% |
| **Writer Recall** | **94.0%** | Target: >= 85.0% |
| **End-to-End Recall** | **94.0%** | Target: >= 85.0% |

### Failure Categorization Breakdown
- **`CORRECT`**: **47 facts** (94.0%)
- **`WRITER_MISSED`**: **3 facts** (6.0%)
- **`RETRIEVER_MISSED`**: **0 facts** (0.0%)
- **`INCORRECT`**: **0 facts** (0.0%)
- **`NEEDS_REVIEW`**: **0 facts** (0.0%)

---

## 2. Per-Repository Recall Matrix

| Repository Fixture | Facts | Retrieved | Correct | Writer Missed | Retriever Missed | Retrieval Recall | Writer Recall | E2E Recall |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `01_small_python_api` | 4 | 4 | 3 | 1 | 0 | 100.0% | 75.0% | 75.0% |
| `02_fastapi_backend` | 7 | 7 | 5 | 2 | 0 | 100.0% | 71.4% | 71.4% |
| `03_nextjs_frontend` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `04_fullstack_monorepo` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `05_go_cli_service` | 3 | 3 | 3 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `06_rust_web_service` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `07_complex_monorepo` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `08_outdated_readme_sqlite` | 3 | 3 | 3 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `09_misleading_doc_redis` | 2 | 2 | 2 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `10_generated_code_repo` | 2 | 2 | 2 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `11_vendored_heavy_node` | 2 | 2 | 2 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `12_sparse_docs_repo` | 3 | 3 | 3 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `13_agent_heavy_repo` | 2 | 2 | 2 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `14_large_repo_10k` | 4 | 4 | 4 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| `15_legacy_dead_code` | 2 | 2 | 2 | 0 | 0 | 100.0% | 100.0% | 100.0% |

---

## 3. Fact-by-Fact Evidence Provenance Audit Trail

| Fact ID | Repo | Category | Ground-Truth Statement | Authoritative Evidence IDs | Retrieved? | Status |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `01_fact_01` | `01_small_python_api` | framework | Click is used for CLI command parsing | `ev_0002` | ✅ | **CORRECT** |
| `01_fact_02` | `01_small_python_api` | dependency | Requests is used for HTTP client calls | `ev_0001` | ✅ | **CORRECT** |
| `01_fact_03` | `01_small_python_api` | entrypoint | main.py is the primary entrypoint | `ev_0002` | ✅ | **WRITER_MISSED** |
| `01_fact_04` | `01_small_python_api` | deployable_unit | Repository represents a single CLI tool deployable unit | `ev_0002` | ✅ | **CORRECT** |
| `02_fact_01` | `02_fastapi_backend` | framework | FastAPI is the primary web framework | `ev_0001` | ✅ | **CORRECT** |
| `02_fact_02` | `02_fastapi_backend` | database | PostgreSQL database is configured in Docker Compose and models | `ev_0004`, `ev_0007` | ✅ | **CORRECT** |
| `02_fact_03` | `02_fastapi_backend` | entrypoint | src/main.py is the application entrypoint | `ev_0001` | ✅ | **CORRECT** |
| `02_fact_04` | `02_fastapi_backend` | deployable_unit | Repository represents a backend API deployable unit | `ev_0001` | ✅ | **CORRECT** |
| `02_fact_05` | `02_fastapi_backend` | dependency | SQLAlchemy is used for ORM data modeling | `ev_0003` | ✅ | **CORRECT** |
| `02_fact_06` | `02_fastapi_backend` | api_surface | Exposes /api/v1/users route endpoints | `ev_0006` | ✅ | **WRITER_MISSED** |
| `02_fact_07` | `02_fastapi_backend` | deployment | Docker Compose configures api and db services | `ev_0007` | ✅ | **WRITER_MISSED** |
| `03_fact_01` | `03_nextjs_frontend` | framework | Next.js is the web application framework | `ev_0001` | ✅ | **CORRECT** |
| `03_fact_02` | `03_nextjs_frontend` | framework | React is the UI library | `ev_0002`, `ev_0003` | ✅ | **CORRECT** |
| `03_fact_03` | `03_nextjs_frontend` | entrypoint | app/page.tsx is the primary page entrypoint | `ev_0001` | ✅ | **CORRECT** |
| `03_fact_04` | `03_nextjs_frontend` | deployable_unit | Repository represents a web application deployable unit | `ev_0001` | ✅ | **CORRECT** |
| `04_fact_01` | `04_fullstack_monorepo` | deployable_unit | Monorepo contains backend API and web application units | `ev_0001`, `ev_0002` | ✅ | **CORRECT** |
| `04_fact_02` | `04_fullstack_monorepo` | framework | Backend is built with FastAPI | `ev_0001` | ✅ | **CORRECT** |
| `04_fact_03` | `04_fullstack_monorepo` | framework | Frontend is built with React | `ev_0002` | ✅ | **CORRECT** |
| `04_fact_04` | `04_fullstack_monorepo` | entrypoint | backend/app.py and frontend/src/index.tsx are unit entrypoints | `ev_0001`, `ev_0002` | ✅ | **CORRECT** |
| `05_fact_01` | `05_go_cli_service` | framework | Cobra is used for Go CLI commands | `ev_0001` | ✅ | **CORRECT** |
| `05_fact_02` | `05_go_cli_service` | entrypoint | main.go is the service entrypoint | `ev_0001` | ✅ | **CORRECT** |
| `05_fact_03` | `05_go_cli_service` | deployable_unit | Repository represents a CLI tool unit | `ev_0001` | ✅ | **CORRECT** |
| `06_fact_01` | `06_rust_web_service` | framework | Actix-web is the web framework | `ev_0001` | ✅ | **CORRECT** |
| `06_fact_02` | `06_rust_web_service` | framework | Tokio is the async runtime | `ev_0002` | ✅ | **CORRECT** |
| `06_fact_03` | `06_rust_web_service` | entrypoint | src/main.rs is the entrypoint | `ev_0001` | ✅ | **CORRECT** |
| `06_fact_04` | `06_rust_web_service` | deployable_unit | Repository represents a backend API unit | `ev_0001` | ✅ | **CORRECT** |
| `07_fact_01` | `07_complex_monorepo` | deployable_unit | Monorepo contains web app, backend API, worker, and shared library | `ev_0001`, `ev_0002`, `ev_0003`, `ev_0004` | ✅ | **CORRECT** |
| `07_fact_02` | `07_complex_monorepo` | framework | FastAPI powers the backend API | `ev_0002` | ✅ | **CORRECT** |
| `07_fact_03` | `07_complex_monorepo` | framework | Next.js powers the frontend web app | `ev_0001` | ✅ | **CORRECT** |
| `07_fact_04` | `07_complex_monorepo` | worker | Celery is used for background workers | `ev_0004` | ✅ | **CORRECT** |
| `08_fact_01` | `08_outdated_readme_sqlite` | contradiction | README claims SQLite but code and docker-compose use PostgreSQL | `ev_0001`, `ev_0002` | ✅ | **CORRECT** |
| `08_fact_02` | `08_outdated_readme_sqlite` | framework | FastAPI is the web framework | `ev_0001` | ✅ | **CORRECT** |
| `08_fact_03` | `08_outdated_readme_sqlite` | database | PostgreSQL is the active database | `ev_0001`, `ev_0002` | ✅ | **CORRECT** |
| `09_fact_01` | `09_misleading_doc_redis` | documentation | README claims Redis caching but Redis is not in manifest or code | `ev_0001` | ✅ | **CORRECT** |
| `09_fact_02` | `09_misleading_doc_redis` | framework | FastAPI is the web framework | `ev_0001` | ✅ | **CORRECT** |
| `10_fact_01` | `10_generated_code_repo` | architecture | Generated gRPC/Protobuf files are excluded from core application business logic | `ev_0001` | ✅ | **CORRECT** |
| `10_fact_02` | `10_generated_code_repo` | framework | FastAPI is the active web framework | `ev_0001` | ✅ | **CORRECT** |
| `11_fact_01` | `11_vendored_heavy_node` | architecture | Vendored node_modules are excluded from project architecture | `ev_0001` | ✅ | **CORRECT** |
| `11_fact_02` | `11_vendored_heavy_node` | framework | Express is the web framework | `ev_0001` | ✅ | **CORRECT** |
| `12_fact_01` | `12_sparse_docs_repo` | framework | Typer is used for CLI commands | `ev_0001` | ✅ | **CORRECT** |
| `12_fact_02` | `12_sparse_docs_repo` | framework | Rich is used for terminal formatting | `ev_0001` | ✅ | **CORRECT** |
| `12_fact_03` | `12_sparse_docs_repo` | deployable_unit | Repository represents a CLI tool unit | `ev_0001` | ✅ | **CORRECT** |
| `13_fact_01` | `13_agent_heavy_repo` | framework | FastAPI is the application framework | `ev_0001` | ✅ | **CORRECT** |
| `13_fact_02` | `13_agent_heavy_repo` | deployable_unit | Repository represents a backend API unit | `ev_0001` | ✅ | **CORRECT** |
| `14_fact_01` | `14_large_repo_10k` | deployable_unit | Contains backend API and background worker deployable units | `ev_0001`, `ev_0002` | ✅ | **CORRECT** |
| `14_fact_02` | `14_large_repo_10k` | framework | FastAPI is the API framework | `ev_0001` | ✅ | **CORRECT** |
| `14_fact_03` | `14_large_repo_10k` | database | PostgreSQL is the database managed with Alembic migrations | `ev_0001`, `ev_0002` | ✅ | **CORRECT** |
| `14_fact_04` | `14_large_repo_10k` | worker | Celery is the distributed task worker | `ev_0001` | ✅ | **CORRECT** |
| `15_fact_01` | `15_legacy_dead_code` | framework | FastAPI is the active web framework | `ev_0001` | ✅ | **CORRECT** |
| `15_fact_02` | `15_legacy_dead_code` | dependency | Deprecated legacy frameworks are declared but unused or isolated | `ev_0001` | ✅ | **CORRECT** |
