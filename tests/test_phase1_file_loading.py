"""
Phase 1 Integration Test Suite: File Loading & Azurite Storage Verification.

Verifies:
1. Empty active file rejection (400 Bad Request)
2. Unauthenticated file request guard (401 Unauthorized)
3. Missing file / blob explicit error (404 Not Found, no placeholder fabrication)
4. Complete Azurite read/write/read roundtrip persistence cycle
5. Repository isolation and FactFile upsert behavior
"""
from __future__ import annotations

import os
import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import app
from backend.database import get_db, engine, Base
from backend.models.user import User
from backend.models.repository import Repository, Analysis
from backend.models.fact_store import FactFile
from backend.services.github_oauth import create_jwt
from backend.storage import get_storage, build_blob_key


@pytest.fixture(scope="module")
def db_session():
    """Provides a database session for seeding test entities."""
    db = next(get_db())
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def test_user_and_repo(db_session: Session):
    """Creates an isolated test user and repository with completed analysis."""
    unique_suffix = uuid.uuid4().hex[:8]
    user = User(
        github_id=f"gh_test_{unique_suffix}",
        email=f"tester_{unique_suffix}@example.com",
        username=f"tester_{unique_suffix}",
        avatar="https://example.com/avatar.png",
        github_access_token=f"gho_dummy_token_{unique_suffix}",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    repo_name = f"phase1-repo-{unique_suffix}"
    repo = Repository(
        user_id=user.id,
        url=f"https://github.com/testowner/{repo_name}",
        default_branch="main",
        status="Completed",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    analysis = Analysis(
        repository_id=repo.id,
        commit_hash="c1a2b3d4e5f6",
        status="Completed",
    )
    db_session.add(analysis)
    db_session.commit()
    db_session.refresh(analysis)

    jwt_token = create_jwt(user)
    
    return {
        "user": user,
        "repo": repo,
        "repo_name": repo_name,
        "analysis": analysis,
        "jwt_token": jwt_token,
    }


@pytest.fixture(scope="module")
def client(test_user_and_repo):
    """TestClient configured with authenticated session cookie."""
    with TestClient(app, raise_server_exceptions=False) as c:
        c.cookies.set("access_token", test_user_and_repo["jwt_token"])
        yield c


@pytest.fixture(scope="module")
def unauthed_client():
    """Unauthenticated TestClient."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ──────────────────────────────────────────────────────────────────────────────
# 1. Empty Active File Rejection
# ──────────────────────────────────────────────────────────────────────────────

def test_empty_file_path_returns_400(client: TestClient, test_user_and_repo):
    """
    Verifies that requests with an empty file path reject with 400 Bad Request
    and do not attempt to stream an empty blob from Azurite.
    """
    repo_name = test_user_and_repo["repo_name"]
    res = client.get(f"/api/repos/{repo_name}/file?path=")
    assert res.status_code == 400
    assert "Invalid empty file path" in res.json()["detail"]

    # Also verify empty path on POST save
    res_save = client.post(f"/api/repos/{repo_name}/file", json={"path": "", "content": "..."})
    assert res_save.status_code == 400
    assert "Invalid empty file path" in res_save.json()["detail"]


# ──────────────────────────────────────────────────────────────────────────────
# 2. Unauthenticated Guard
# ──────────────────────────────────────────────────────────────────────────────

def test_unauthenticated_file_request_returns_401(unauthed_client: TestClient, test_user_and_repo):
    """
    Verifies that file access without an authenticated JWT returns 401 Unauthorized.
    """
    repo_name = test_user_and_repo["repo_name"]
    res = unauthed_client.get(f"/api/repos/{repo_name}/file?path=main.py")
    assert res.status_code == 401
    assert "detail" in res.json()


# ──────────────────────────────────────────────────────────────────────────────
# 3. Missing File Returns 404 Not Found (Zero Silent Placeholders)
# ──────────────────────────────────────────────────────────────────────────────

def test_missing_file_returns_404_not_placeholder(client: TestClient, test_user_and_repo):
    """
    CRITICAL PHASE 1 RULE:
    Non-existent files must return 404 Not Found.
    They must NEVER return 200 with fabricated content like '// Content for {filePath}'.
    """
    repo_name = test_user_and_repo["repo_name"]
    missing_path = "src/missing_component_xyz.py"
    
    res = client.get(f"/api/repos/{repo_name}/file?path={missing_path}")
    assert res.status_code == 404
    detail = res.json()["detail"]
    assert "File not found" in detail
    assert missing_path in detail


# ──────────────────────────────────────────────────────────────────────────────
# 4. Complete Azurite Read/Write/Read Roundtrip Persistence Cycle
# ──────────────────────────────────────────────────────────────────────────────

def test_complete_azurite_read_write_read_cycle(client: TestClient, test_user_and_repo, db_session: Session):
    """
    Proves the full Azurite persistence cycle:
    1. Save new/modified file content via POST /api/repos/{repo}/file.
    2. Verify FactFile is persisted/updated in PostgreSQL.
    3. Verify blob payload is stored in Azurite.
    4. Read the file back via GET /api/repos/{repo}/file?path=...
    5. Assert the returned content matches the saved content exactly.
    6. Overwrite with second modification and verify fresh read reflects update.
    """
    repo_name = test_user_and_repo["repo_name"]
    file_path = "backend/api/health_check.py"
    content_v1 = (
        "import fastapi\n\n"
        "router = fastapi.APIRouter()\n\n"
        "@router.get('/healthz')\n"
        "def healthz():\n"
        "    return {'status': 'healthy', 'azurite': 'connected'}\n"
    )

    # 1. Save file content
    save_res = client.post(
        f"/api/repos/{repo_name}/file",
        json={"path": file_path, "content": content_v1},
    )
    assert save_res.status_code == 200
    save_data = save_res.json()
    assert save_data["status"] == "saved"
    assert save_data["path"] == file_path
    assert save_data["content_length"] == len(content_v1)
    blob_name = save_data.get("blob_name")
    assert blob_name is not None

    # 2. Verify FactFile record in DB
    analysis_id = test_user_and_repo["analysis"].id
    fact_file = db_session.query(FactFile).filter(
        FactFile.analysis_id == analysis_id,
        FactFile.path == file_path,
    ).first()
    assert fact_file is not None
    assert fact_file.blob_name == blob_name
    assert fact_file.size == len(content_v1.encode("utf-8"))

    # 3. Verify Azurite blob payload directly from storage
    storage = get_storage()
    azurite_text = storage.get_object_text(blob_name)
    assert azurite_text == content_v1

    # 4. Read back via GET endpoint
    read_res = client.get(f"/api/repos/{repo_name}/file?path={file_path}")
    assert read_res.status_code == 200
    read_data = read_res.json()
    assert read_data["path"] == file_path
    assert read_data["content"] == content_v1
    assert read_data["size"] == len(content_v1.encode("utf-8"))

    # 5. Overwrite file with content_v2
    content_v2 = content_v1 + "\n# Updated in Phase 1 roundtrip test\n"
    save_res_2 = client.post(
        f"/api/repos/{repo_name}/file",
        json={"path": file_path, "content": content_v2},
    )
    assert save_res_2.status_code == 200

    # 6. Read back fresh content and assert exact match
    read_res_2 = client.get(f"/api/repos/{repo_name}/file?path={file_path}")
    assert read_res_2.status_code == 200
    assert read_res_2.json()["content"] == content_v2


# ──────────────────────────────────────────────────────────────────────────────
# 5. Repository Isolation on File Operations
# ──────────────────────────────────────────────────────────────────────────────

def test_repository_isolation_on_file_operations(client: TestClient, test_user_and_repo, db_session: Session):
    """
    Verifies that a user cannot access another repository's files or analyses.
    """
    other_user = User(
        github_id="gh_other_9999",
        email="other@example.com",
        username="other_user",
        avatar="https://example.com/avatar.png",
        github_access_token="gho_other_token",
    )
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    other_repo = Repository(
        user_id=other_user.id,
        url="https://github.com/otherowner/private-repo",
        default_branch="main",
        status="Completed",
    )
    db_session.add(other_repo)
    db_session.commit()
    db_session.refresh(other_repo)

    # Current client (logged in as test_user) attempts to read other_repo's file
    res = client.get("/api/repos/private-repo/file?path=secret.py")
    assert res.status_code == 404
