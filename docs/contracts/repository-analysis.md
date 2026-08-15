# Contract: Repository Analysis & Pipeline

**Status**: `ACTIVE (Implemented & Tested)`

## 1. Purpose
Defines the contract for ingesting a repository, parsing source files into Concrete Syntax Trees (CST/AST), constructing the in-memory Repository Intelligence Model (RIM) graph, executing Layer 6 capability detection, and persisting relational code facts into the Layer 4 Fact Store.

## 2. Pipeline Stages

```text
1. Download ──► 2. Scan & Detect ──► 3. Parse AST ──► 4. Build RIM ──► 5. Capabilities ──► 6. Features ──► 7. Fact Store Persistence
```

1. **Ingestion (`backend/services/github.py`)**:
   - Input: Repository URL, default branch, optional GitHub access token.
   - Output: Extracted directory in `/tmp/repo-analysis/job_{id}_{repo}/`.
2. **Scanner & Language Detection (`backend/intelligence/engine/scanner/`)**:
   - Output: `RepositoryManifest` with file paths, file sizes, dominant languages, and detected frameworks.
3. **AST Parser Providers (`backend/intelligence/engine/`)**:
   - Supported Languages: Python, JavaScript, TypeScript, Java, C, C++, Go, Ruby.
   - Output: Extracted symbols (classes, functions, methods, parameters, imports, routes, tables).
4. **Repository Intelligence Model (`backend/intelligence/rim/`)**:
   - Output: `RepositoryModel` object containing entity dictionaries and typed relationship lists (`CONTAINS`, `CALLS`, `IMPORTS`, `INHERITS`, `USES`, `EXPOSES`, `DECLARES`, `DEPENDS_ON`).
5. **Layer 6 Capability Detection Engine (`backend/intelligence/capabilities/`)**:
   - Detectors: `AuthenticationDetector`, `CRUDDetector`, `BackgroundTaskDetector`, `FileUploadDetector`.
   - Output: Inferred and confirmed system capabilities, capability member roles (`entry_point`, `handler`, `service`, `table`), and evidence records.
6. **Feature Reconstruction Engine (`backend/intelligence/features/`)**:
   - Output: Execution flow chains connecting entrypoint routes to handlers, services, and database tables.
7. **Layer 4 Fact Store Persistence (`backend/intelligence/store/fact_store.py`)**:
   - Output: Populated relational PostgreSQL tables (`files`, `symbols`, `relationships`, `routes`, `database_objects`, `capabilities`, `capability_members`, `evidence`).

## 3. Invariants
- Fact IDs must be composite and analysis-scoped: `f"{analysis_id}:{entity_id}"`.
- All extracted symbols must reference a valid `file_id` or indicate virtual namespace scope.
- Capability detection must be deterministic, idempotent, and non-destructive.
- Analysis failure must clean up temporary download folders in `/tmp/repo-analysis/`.

## 4. Test Verification
- `backend/tests/test_fact_store.py`: Persistence and RIM round-trip reconstruction.
- `backend/tests/test_capabilities.py`: Positive and false-positive capability detection.
- `backend/tests/test_sql_integrity.py`: Fact Store data integrity, non-null thresholds, and primary key scoping.
