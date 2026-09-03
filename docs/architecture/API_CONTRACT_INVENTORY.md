# API Contract Inventory

This document provides a complete, machine-readable inventory of all active and baseline API endpoints in the Repository Intelligence Platform.

---

## 1. Authentication & System Health

### `POST /api/auth/github`
- **Handler**: `backend/routers/auth.py::github_auth`
- **Auth Required**: No (OAuth entry point)
- **Request Schema**:
  ```json
  {
    "code": "string (GitHub temporary OAuth code)"
  }
  ```
- **Response Schema (200 OK)**:
  ```json
  {
    "status": "authenticated",
    "user": {
      "id": 1,
      "username": "octocat",
      "email": "user@example.com",
      "avatar_url": "https://avatars.githubusercontent.com/u/1"
    }
  }
  ```
- **Cookies Set**: `access_token` (HTTP-only JWT cookie)
- **Error Codes**:
  - `400 Bad Request`: Missing or invalid OAuth code
  - `401 Unauthorized`: GitHub OAuth exchange failed

### `GET /api/auth/me`
- **Handler**: `backend/routers/auth.py::get_me`
- **Auth Required**: Yes (`access_token` cookie)
- **Response Schema (200 OK)**:
  ```json
  {
    "id": 1,
    "username": "octocat",
    "email": "user@example.com",
    "avatar_url": "https://avatars.githubusercontent.com/u/1"
  }
  ```
- **Error Codes**: `401 Unauthorized`

### `POST /api/auth/logout`
- **Handler**: `backend/routers/auth.py::logout`
- **Auth Required**: No
- **Response Schema (200 OK)**: `{"status": "logged_out"}`

### `GET /api/health`
- **Handler**: `backend/routers/health.py::health_check`
- **Auth Required**: No
- **Response Schema (200 OK)**:
  ```json
  {
    "status": "healthy",
    "database": "connected",
    "queue": "active",
    "version": "0.1.0"
  }
  ```

---

## 2. Repositories & Ingestion

### `GET /api/repos`
- **Handler**: `backend/routers/repo/core.py::list_repos`
- **Auth Required**: Yes (`access_token` cookie)
- **Response Schema (200 OK)**:
  ```json
  {
    "repositories": [
      {
        "id": 1,
        "project_name": "my-repo",
        "url": "https://github.com/owner/my-repo",
        "status": "Completed",
        "job_status": "Completed",
        "import_time": "2026-08-18T10:00:00Z",
        "language": "Python, TypeScript",
        "frameworks": ["FastAPI", "Next.js"],
        "commit": "a1b2c3d",
        "branch": "main"
      }
    ]
  }
  ```

### `POST /api/import`
- **Handler**: `backend/routers/repo/core.py::import_repo`
- **Auth Required**: Yes
- **Request Schema**:
  ```json
  {
    "url": "https://github.com/owner/my-repo"
  }
  ```
- **Response Schema (200 OK)**:
  ```json
  {
    "message": "Repository import queued.",
    "job_id": 1,
    "repo": "my-repo"
  }
  ```
- **Error Codes**: `400 Bad Request` (Invalid GitHub URL), `403 Forbidden` (Repository limits exceeded)

### `GET /api/repos/{repo_name}/scan`
- **Handler**: `backend/routers/repo/structure.py::scan_repo`
- **Auth Required**: Yes
- **Response Schema (200 OK)**:
  ```json
  {
    "status": "completed",
    "overview": {
      "total_files": 42,
      "total_directories": 8,
      "total_functions": 120,
      "total_classes": 15,
      "language": "Python",
      "commit": "a1b2c3d",
      "branch": "main"
    },
    "hierarchy": {
      "name": "my-repo",
      "type": "directory",
      "path": "",
      "children": []
    },
    "files": []
  }
  ```

### `GET /api/repos/{repo_name}/file?path={file_path}`
- **Handler**: `backend/routers/repo/structure.py::get_raw_file`
- **Auth Required**: Yes
- **Response Schema (200 OK)**:
  ```json
  {
    "path": "backend/main.py",
    "content": "import fastapi...",
    "size": 4096,
    "language": "Python",
    "content_type": "text/x-python"
  }
  ```

### `POST /api/repos/{repo_name}/file`
- **Handler**: `backend/routers/repo/structure.py::save_repo_file`
- **Auth Required**: Yes
- **Request Schema**:
  ```json
  {
    "path": "backend/main.py",
    "content": "modified code content..."
  }
  ```
- **Response Schema (200 OK)**:
  ```json
  {
    "status": "saved",
    "path": "backend/main.py",
    "content_length": 1500
  }
  ```

### `GET /api/repos/{repo_name}/parse?file_path={file_path}`
- **Handler**: `backend/routers/repo/structure.py::parse_repo_file`
- **Auth Required**: Yes
- **Response Schema (200 OK)**:
  ```json
  {
    "source_code": "...",
    "imports": [{"module_name": "fastapi"}],
    "functions": [{"name": "read_root", "line": 142}],
    "classes": [{"id": "...", "name": "AppService", "line": 20, "methods": []}],
    "docstring": ""
  }
  ```

### `GET /api/repos/{repo_name}/symbols`
- **Handler**: `backend/routers/repo/structure.py::get_symbols`
- **Auth Required**: Yes
- **Response Schema (200 OK)**:
  ```json
  {
    "symbols": [
      {
        "id": "1:sym_1",
        "name": "read_root",
        "qualified_name": "backend.main.read_root",
        "type": "function",
        "file_path": "backend/main.py",
        "line_number": 142
      }
    ]
  }
  ```

---

## 3. End-to-End Verification Pipeline (`/api/v1/pipeline`)

### `POST /api/v1/pipeline/task/submit`
- **Handler**: `backend/routers/verification_pipeline.py::submit_pipeline_task`
- **Auth Required**: No (scoped by repo name)
- **Request Schema**:
  ```json
  {
    "repo_name": "my-project",
    "prompt": "Add user authentication middleware with JWT validation"
  }
  ```
- **Response Schema (200 OK)**:
  ```json
  {
    "task_id": "task-1718000000",
    "repo_name": "my-project",
    "contract": {
      "id": "contract-1718000000",
      "requirement": "Add user authentication middleware...",
      "title": "User Authentication Middleware",
      "required_endpoints": ["backend/middleware/auth.py"],
      "expected_components": ["backend/middleware/auth.py"],
      "invariants": ["JWT must be signed with HS256", "Reject expired tokens with 401"],
      "required_tests": ["test_auth_valid_jwt", "test_auth_expired_jwt"],
      "affected_components": [
        {
          "file": "backend/middleware/auth.py",
          "symbol": "AuthMiddleware",
          "component_type": "NEW"
        }
      ]
    },
    "status": "CONTRACT_GENERATED"
  }
  ```

### `POST /api/v1/pipeline/task/{task_id}/execute`
- **Handler**: `backend/routers/verification_pipeline.py::execute_pipeline_task`
- **Auth Required**: No
- **Request Schema**:
  ```json
  {
    "repo_name": "my-project",
    "contract_id": "contract-1718000000",
    "contract_data": { ... }
  }
  ```
- **Response Schema (200 OK)**:
  ```json
  {
    "task_id": "task-1718000000",
    "run_id": "task-1718000000",
    "diff": "--- a/backend/middleware/auth.py\n+++ b/backend/middleware/auth.py\n@@ ...",
    "report": {
      "run_id": "task-1718000000",
      "status": "PASS | FAIL | UNVERIFIED | MOCKED | ERROR",
      "passed": true,
      "execution_state": "PASS",
      "static_result": {
        "vector_name": "static",
        "status": "PASS",
        "passed": true,
        "execution_state": "PASS",
        "defects": [],
        "evidence_manifest": [...]
      },
      "dynamic_result": {
        "vector_name": "dynamic",
        "status": "PASS",
        "passed": true,
        "execution_state": "PASS",
        "defects": [],
        "evidence_manifest": [...]
      },
      "contract_result": {
        "vector_name": "contract",
        "status": "PASS",
        "passed": true,
        "execution_state": "PASS",
        "defects": [],
        "evidence_manifest": [...]
      },
      "defects": [],
      "evidence_manifest": [...],
      "summary": "VERIFICATION PASS: ...",
      "created_at": "2026-08-18T10:00:00Z"
    },
    "iteration": 1
  }
  ```

### `POST /api/v1/pipeline/task/{task_id}/repair`
- **Handler**: `backend/routers/verification_pipeline.py::repair_pipeline_task`
- **Auth Required**: No
- **Request Schema**:
  ```json
  {
    "repo_name": "my-project",
    "iteration": 2,
    "defects": [
      {
        "category": "STATIC_IMPORT_MISSING",
        "file_path": "backend/middleware/auth.py",
        "line_number": 5,
        "description": "Missing import for 'jwt'",
        "severity": "HIGH"
      }
    ],
    "contract_data": { ... }
  }
  ```
- **Response Schema (200 OK)**:
  ```json
  {
    "task_id": "task-1718000000",
    "run_id": "task-1718000000",
    "diff": "repaired diff content",
    "report": { ... },
    "iteration": 2,
    "status": "VERIFIED | UNRESOLVED"
  }
  ```

---

## 4. Multi-Vector Verification Engine (`/api/v1/verify` & `/api/v1/repair`)

### `POST /api/v1/verify/run`
- **Handler**: `backend/routers/verification.py::run_verification`
- **Request**: `{"run_id": "run-1", "repo_id": "default", "worktree_path": "data/worktrees/..."}`
- **Response**: `VerificationReport`

### `POST /api/v1/repair/iterate`
- **Handler**: `backend/routers/verification.py::iterate_repair`
- **Request**: `{"run_id": "run-1", "repo_id": "default", "iteration": 2, "defects": [...]}`
- **Response**: `{"run_id": "run-1", "repaired_diff": "...", "verification_report": { ... }}`

---

---

## 5. Worktree Sandbox Command Execution & Persistent Shell Sessions (`/api/v1/sandbox`)

### `POST /api/v1/sandbox/{run_id}/session`
- **Handler**: `backend/routers/sandbox.py::create_sandbox_session`
- **Auth Required**: No (scoped by server-side `run_id` worktree resolution)
- **Purpose**: Creates or retrieves a persistent interactive shell/PTY session tied to the run's authorized worktree directory.
- **Request Schema**:
  ```json
  {
    "session_id": "optional_custom_session_id"
  }
  ```
- **Response Schema (200 OK)**:
  ```json
  {
    "session_id": "session_a1b2c3d4e5",
    "run_id": "task-1718000000",
    "worktree_path": "data/worktrees/task-1718000000",
    "created_at": 1718000000.0,
    "cwd": "data/worktrees/task-1718000000"
  }
  ```

### `DELETE /api/v1/sandbox/{run_id}/session/{session_id}`
- **Handler**: `backend/routers/sandbox.py::close_sandbox_session`
- **Purpose**: Closes and terminates the persistent shell process group and cleans up temporary log files.
- **Response Schema (200 OK)**:
  ```json
  {
    "status": "CLOSED",
    "session_id": "session_a1b2c3d4e5",
    "run_id": "task-1718000000"
  }
  ```

### `POST /api/v1/sandbox/{run_id}/exec`
- **Handler**: `backend/routers/sandbox.py::exec_sandbox_command`
- **Auth Required**: No (scoped by server-side `run_id` worktree resolution)
- **Security Boundary**:
  - Controlled host subprocess execution with persistent shell/PTY session scoped to the validated worktree.
  - Path validation verifies `run_id` worktree path resides within `data/worktrees/`.
  - Directory changes (`cd`) and environment exports (`export`) persist across sequential commands in the same session.
  - Sensitive backend environment variables (`JWT_SECRET`, `GITHUB_CLIENT_SECRET`, `AZURE_STORAGE_ACCOUNT_KEY`, `DATABASE_URL`) are stripped.
  - Streaming stdout/stderr limit enforced at 1MB per stream; process group is terminated immediately on overage.
  - Execution timeout enforced (1-120 seconds, default 30s) with process-group kill and session recovery.
  - Separate sessions (`run_A` vs `run_B`) are strictly isolated with no state leakage.
  - *Note*: This is controlled host subprocess execution and does not provide container/kernel namespace isolation.
- **Request Schema**:
  ```json
  {
    "command": "cd src && pwd",
    "timeout_sec": 30,
    "session_id": "optional_session_id"
  }
  ```
- **Response Schema (200 OK)**:
  ```json
  {
    "run_id": "task-1718000000",
    "command": "cd src && pwd",
    "stdout": "/worktree/src\n",
    "stderr": "",
    "exit_code": 0,
    "timed_out": false,
    "output_truncated": false,
    "duration_ms": 45.2,
    "session_id": "session_a1b2c3d4e5",
    "cwd": "/worktree/src"
  }
  ```
- **Error Codes**:
  - `400 Bad Request`: Empty command or invalid `run_id` format
  - `404 Not Found`: Run worktree does not exist on disk
  - `500 Internal Server Error`: Subprocess spawn or runtime failure

