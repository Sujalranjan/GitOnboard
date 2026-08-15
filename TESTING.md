# Testing & Data Integrity Guide

This document explains the test strategy, active test suites, and instructions for verifying the Repository Intelligence Platform.

---

## 1. Test Architecture & Structure

Tests are organized into two main locations:

```text
├── backend/tests/                 # Fact Store persistence, capability detection, SQL data integrity
│   ├── test_capabilities.py       # Layer 6 capability detection positive/negative unit tests
│   ├── test_fact_store.py         # Fact Store persistence, RIM reconstruction, cascade deletion
│   └── test_sql_integrity.py      # Non-null thresholds, format validations, primary key scoping
└── tests/                         # Integration & API contract tests
    ├── test_auth_hardening.py     # JWT token expiration, OAuth callbacks, CORS validation
    ├── test_context_builder.py    # LLM context builder endpoint & feature context validation
    ├── test_feature_discovery.py  # Feature discovery endpoint & route sorting
    └── test_scanner.py            # Language detector, framework detector, Git metadata
```

---

## 2. Running Automated Tests

Run the complete test suite:
```bash
uv run pytest -v
```

### Running Specific Test Modules
```bash
# Run Layer 6 Capability Detection tests
uv run pytest backend/tests/test_capabilities.py -v

# Run Layer 4 Fact Store persistence tests
uv run pytest backend/tests/test_fact_store.py -v

# Run SQL Data Integrity tests
uv run pytest backend/tests/test_sql_integrity.py -v

# Run Auth & API integration tests
uv run pytest tests/test_auth_hardening.py tests/test_context_builder.py -v
```

---

## 3. What to Test When Modifying Components

| Component Changed | Required Tests to Run / Add |
|---|---|
| **Tree-sitter Parser / Scanner** | Run `tests/test_scanner.py`; verify CST token extraction and framework detection. |
| **RIM Graph Model** | Run `backend/tests/test_fact_store.py`; verify entity and relationship integrity and serialization. |
| **Layer 6 Capability Detectors** | Run `backend/tests/test_capabilities.py`; test positive detection, negative false-positive resistance, and idempotency. |
| **Fact Store Models / Queries** | Run `backend/tests/test_sql_integrity.py` and `backend/tests/test_fact_store.py`; ensure non-null constraints and cascade deletes work. |
| **FastAPI Routers** | Run `tests/test_context_builder.py`, `tests/test_feature_discovery.py`, `tests/test_auth_hardening.py`. |
| **ChromaDB / Vector Search** | Test `/api/repos/{repo_name}/semantic-search` endpoint response format and embedding status. |
