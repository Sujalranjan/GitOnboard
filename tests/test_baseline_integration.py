"""
Phase 0 Baseline Integration Test Suite for GitOnBoard.

Covers:
1. Health & Correlation-ID header propagation
2. Repository scan & Fact Store isolation contracts
3. Pipeline submit -> execute -> verify lifecycle
4. Zero-evidence PASS rejection (evidence sufficiency enforcement)
5. Known pre-existing failures codified as expected baseline assertions
"""
from __future__ import annotations

import os
import uuid
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.verification.schemas import (
    Defect,
    DefectCategory,
    DefectSeverity,
    ExecutionState,
    VerificationReport,
    VerificationResult,
)
from backend.verification.judge import Judge
from backend.verification.contract_verifier import ContractVerifier
from backend.logger import get_correlation_context, set_correlation_context


@pytest.fixture(scope="module")
def client():
    """TestClient instance bound to the active FastAPI application."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ──────────────────────────────────────────────────────────────────────────────
# 1. Health & Correlation-ID Header Propagation
# ──────────────────────────────────────────────────────────────────────────────

def test_baseline_health_and_correlation_headers(client: TestClient):
    """
    Verifies that all HTTP requests:
    - Receive an X-Correlation-ID response header (propagated or generated).
    - Maintain trace correlation through async execution context.
    """
    # Case A: Generated correlation ID
    res_gen = client.get("/api/health")
    assert res_gen.status_code == 200
    assert "x-correlation-id" in res_gen.headers
    corr_id_1 = res_gen.headers["x-correlation-id"]
    assert len(corr_id_1) > 0

    # Case B: Custom passed correlation ID
    custom_id = f"test-trace-{uuid.uuid4().hex[:8]}"
    res_custom = client.get("/api/health", headers={"X-Correlation-ID": custom_id})
    assert res_custom.status_code == 200
    assert res_custom.headers.get("x-correlation-id") == custom_id


# ──────────────────────────────────────────────────────────────────────────────
# 2. Repository Scan & Fact Store Isolation Contracts
# ──────────────────────────────────────────────────────────────────────────────

def test_baseline_repo_scan_unauthenticated_guard(client: TestClient):
    """
    Verifies that repository data access strictly requires authentication.
    Unauthenticated file and scan requests must return 401 Unauthorized.
    """
    res_scan = client.get("/api/repos/test-repo/scan")
    assert res_scan.status_code == 401
    assert "detail" in res_scan.json()

    res_file = client.get("/api/repos/test-repo/file?path=main.py")
    assert res_file.status_code == 401





# ──────────────────────────────────────────────────────────────────────────────
# 4. Zero-Evidence PASS Rejection (Evidence Sufficiency Enforcement)
# ──────────────────────────────────────────────────────────────────────────────

def test_baseline_evidence_enforcement_rejects_empty_pass():
    """
    CRITICAL BASELINE RULE:
    No verification vector or report may report PASS if there is zero supporting evidence.
    """
    judge = Judge()

    # Scenario A: Results with passed=True but completely empty evidence manifests
    empty_static = VerificationResult(
        vector_name="static",
        status="PASS",
        passed=True,
        execution_state=ExecutionState.PASS.value,
        defects=[],
        evidence_manifest=[],
        details={},
    )
    empty_dynamic = VerificationResult(
        vector_name="dynamic",
        status="PASS",
        passed=True,
        execution_state=ExecutionState.PASS.value,
        defects=[],
        evidence_manifest=[],
        details={},
    )
    empty_contract = VerificationResult(
        vector_name="contract",
        status="PASS",
        passed=True,
        execution_state=ExecutionState.PASS.value,
        defects=[],
        evidence_manifest=[],
        details={},
    )

    # Aggregating zero-evidence results MUST produce UNVERIFIED, not PASS
    report = judge.aggregate("run-zero-evidence", empty_static, empty_dynamic, empty_contract)
    assert report.passed is False
    assert report.execution_state == ExecutionState.UNVERIFIED.value
    assert report.status == ExecutionState.UNVERIFIED.value

    # Scenario B: Null contract in ContractVerifier produces UNVERIFIED
    contract_verifier = ContractVerifier()
    null_contract_res = contract_verifier.verify(contract=None, modified_files=["main.py"])
    assert null_contract_res.passed is False
    assert null_contract_res.execution_state == ExecutionState.UNVERIFIED.value
    assert null_contract_res.status == ExecutionState.UNVERIFIED.value


# ──────────────────────────────────────────────────────────────────────────────
# 5. Known Pre-Existing Failures Codification
# ──────────────────────────────────────────────────────────────────────────────

def test_baseline_codified_contract_omission_failure():
    """
    Codifies known pre-existing verification failure behavior:
    When a contract requires component modification that is absent in changeset,
    ContractVerifier must deterministically flag CONTRACT_OMISSION.
    """
    contract_verifier = ContractVerifier()
    contract_with_required_file = {
        "requirement": "Add database migration",
        "affected_components": [{"file": "backend/alembic/versions/001.py", "symbol": "upgrade"}],
        "tests_required": ["test_migration_up"],
        "acceptance_criteria": [{"description": "Must create tables"}],
    }

    # Modified files omit the required alembic file
    res = contract_verifier.verify(
        contract=contract_with_required_file,
        modified_files=["backend/models/user.py"],
        git_diff="--- a/backend/models/user.py\n+++ b/backend/models/user.py",
    )

    assert res.passed is False
    assert res.execution_state == ExecutionState.FAIL.value
    defect_categories = [d.category for d in res.defects]
    assert DefectCategory.CONTRACT_OMISSION.value in defect_categories
