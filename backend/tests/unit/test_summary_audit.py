"""
Unit and Integration Tests for Configurable Verbose Audit Logging & Deterministic Validation Fixes.
"""
import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.summary.pipeline import SummaryPipeline
from backend.summary.schemas import (
    ClaimCategory,
    DeployableUnit,
    DeployableUnitType,
    EvidenceItem,
    EvidenceSourceType,
    RepositoryClaim,
    SourceClassification,
    VerificationStatus,
)
from backend.summary.extractor import EvidenceExtractor
from backend.summary.validator import DeterministicValidator
from backend.summary.audit import redact_secrets, SummaryAuditCollector
from backend.ai.service import LLMService
from backend.ai.schemas import LLMResponse, TokenUsage


def test_secret_redaction():
    text = "Authorization: Bearer my_super_secret_jwt_token_123 and password='mysecretpassword123' ghp_123456789012345678901234567890123456"
    sanitized = redact_secrets(text)
    assert "mysecretpassword123" not in sanitized
    assert "ghp_123456789012345678901234567890123456" not in sanitized
    assert "[REDACTED]" in sanitized


def test_fake_path_rejected_by_validator():
    ev_item = EvidenceItem(
        evidence_id="ev_0001",
        source_type=EvidenceSourceType.MANIFEST_DEPENDENCY,
        source_classification=SourceClassification.APPLICATION,
        file_path="pyproject.toml",
        snippet="fastapi>=0.110.0",
        symbol_name="fastapi"
    )
    known_ev = {"ev_0001": ev_item}
    known_paths = ["pyproject.toml", "main.py"]
    authoritative_units = [
        DeployableUnit(unit_id="root", name="api", unit_type=DeployableUnitType.BACKEND_API, root_path="/", entrypoints=["main.py"])
    ]

    raw_llm_json = {
        "overview": {"text": "FastAPI App", "evidence_ids": ["ev_0001"]},
        "deployable_units": [
            {
                "name": "FastAPI Application",
                "unit_type": "backend_api",
                "root_path": "/path/to/fastapi/app",  # FAKE PATH
                "summary": "Fake API",
                "evidence_ids": ["ev_0001"]
            }
        ],
        "technologies": [],
        "discrepancies": []
    }

    structured, rejected, stats = DeterministicValidator.validate_and_sanitize(
        raw_data=raw_llm_json,
        known_evidence=known_ev,
        verified_claims=[],
        deployable_units=authoritative_units,
        known_file_paths=known_paths,
    )

    # Fake path must be REJECTED and omitted from valid deployable units
    assert len(structured.deployable_units) == 0
    assert stats["fabricated_paths_count"] == 1
    assert len(rejected) == 1
    assert "/path/to/fastapi/app" in rejected[0].statement


def test_false_contradiction_rejected():
    ev_item = EvidenceItem(
        evidence_id="ev_0001",
        source_type=EvidenceSourceType.MANIFEST_DEPENDENCY,
        source_classification=SourceClassification.APPLICATION,
        file_path="pyproject.toml",
        snippet="fastapi>=0.110.0",
        symbol_name="fastapi"
    )
    known_ev = {"ev_0001": ev_item}

    # Verified claims do NOT contain any positive contradiction for Typer
    verified_claims = [
        RepositoryClaim(
            claim_id="c1",
            category=ClaimCategory.DEPENDENCY,
            subject="Typer",
            statement="Typer is declared but unused.",
            status=VerificationStatus.DECLARED_UNUSED,
            supporting_evidence_ids=["ev_0001"]
        )
    ]

    raw_llm_json = {
        "overview": {"text": "App", "evidence_ids": ["ev_0001"]},
        "technologies": [],
        "discrepancies": [
            {
                "claimed_in_doc": "Typer is inspired by FastAPI",
                "actual_code_fact": "Typer is not directly related to FastAPI",
                "evidence_ids": ["ev_0001"]
            }
        ]
    }

    structured, rejected, stats = DeterministicValidator.validate_and_sanitize(
        raw_data=raw_llm_json,
        known_evidence=known_ev,
        verified_claims=verified_claims,
    )

    # False contradiction must be rejected
    assert len(structured.discrepancies) == 0
    assert stats["false_contradictions_rejected_count"] == 1
    assert len(rejected) == 1
    assert "No authoritative CONTRADICTED claim found" in rejected[0].reason


@pytest.mark.asyncio
async def test_verbose_audit_off_persists_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("SUMMARY_VERBOSE_AUDIT", "false")
    run_dir = tmp_path / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'clean'\ndependencies = ['fastapi']\n")
    main_py = tmp_path / "main.py"
    main_py.write_text("import fastapi\n")

    mock_llm = MagicMock(spec=LLMService)
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps({
                "overview": {"text": "Clean App", "evidence_ids": ["ev_0001"]},
                "deployable_units": [],
                "technologies": [{"name": "fastapi", "category": "Framework", "status": "strongly_supported", "evidence_ids": ["ev_0001"]}],
                "discrepancies": []
            }),
            usage=TokenUsage(prompt_tokens=200, completion_tokens=50, total_tokens=250),
            provider="mock",
            model="mock",
        )
    )

    pipeline = SummaryPipeline(llm_service=mock_llm)
    result = await pipeline.run(
        repo_name="clean",
        metadata={"entrypoints": ["main.py"]},
        repo_root=tmp_path,
        verbose_audit=False,
    )

    assert result.summary_markdown.startswith("# clean — Repository Summary")
    # Verify no runs created in default directory
    assert not any(Path("evaluation/runs").glob("run_*_audit_test"))


@pytest.mark.asyncio
async def test_verbose_audit_on_persists_full_artifacts(tmp_path, monkeypatch):
    test_runs_dir = tmp_path / "test_runs"
    test_runs_dir.mkdir(parents=True, exist_ok=True)

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'audited'\ndependencies = ['fastapi']\n")
    main_py = tmp_path / "main.py"
    main_py.write_text("import fastapi\n")

    mock_llm = MagicMock(spec=LLMService)
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps({
                "overview": {"text": "Audited App", "evidence_ids": ["ev_0001"]},
                "deployable_units": [],
                "technologies": [{"name": "fastapi", "category": "Framework", "status": "strongly_supported", "evidence_ids": ["ev_0001"]}],
                "discrepancies": []
            }),
            usage=TokenUsage(prompt_tokens=200, completion_tokens=50, total_tokens=250),
            provider="mock",
            model="mock",
        )
    )

    collector = SummaryAuditCollector(run_id="run_audit_unit_test", base_dir=str(test_runs_dir))

    pipeline = SummaryPipeline(llm_service=mock_llm)
    result = await pipeline.run(
        repo_name="audited",
        metadata={"entrypoints": ["main.py"]},
        repo_root=tmp_path,
        verbose_audit=True,
    )

    # Check generated files in evaluation/runs
    run_folders = sorted(Path("evaluation/runs").glob("run_*"))
    assert len(run_folders) >= 1
    latest_run = run_folders[-1]

    expected_files = [
        "01_repository_metadata.json",
        "02_evidence_index.json",
        "03_hierarchy.json",
        "04_retrieval_decisions.json",
        "05_context_sent_to_llm.json",
        "06_llm_request.json",
        "07_llm_response.json",
        "08_validation_results.json",
        "09_rejected_claims.json",
        "10_final_summary.md",
        "11_audit_report.json",
    ]

    for ef in expected_files:
        p = latest_run / ef
        assert p.exists(), f"Expected audit artifact {ef} not found at {latest_run}"
        assert p.stat().st_size > 0

    # Inspect audit coverage report
    with open(latest_run / "11_audit_report.json", "r", encoding="utf-8") as f:
        rep = json.load(f)
    assert "evidence_coverage" in rep
    assert "validation_metrics" in rep

def test_route_evidence_exact_file_and_line_provenance():
    extractor = EvidenceExtractor()
    py_code = """
from fastapi import APIRouter
router = APIRouter()

@router.get("/users")
def get_users():
    return []

@router.post("/users")
def create_user():
    return {}
"""
    routes = extractor.extract_routes_from_source("src/api/users.py", py_code)
    assert len(routes) == 2
    assert routes[0].file_path == "src/api/users.py"
    assert routes[0].line_start == 5
    assert routes[0].snippet == "GET /users"
    assert routes[1].file_path == "src/api/users.py"
    assert routes[1].line_start == 9
    assert routes[1].snippet == "POST /users"


def test_route_evidence_distinct_across_files_and_deduplication():
    extractor = EvidenceExtractor()
    file_a = """
@app.put("/items/{item_id}")
def update_item_a(item_id: int):
    pass
"""
    file_b = """
@app.put("/items/{item_id}")
def update_item_b(item_id: int):
    pass
"""
    routes_a = extractor.extract_routes_from_source("docs_src/body/tutorial001.py", file_a)
    routes_b = extractor.extract_routes_from_source("docs_src/extra_models/tutorial001.py", file_b)
    
    assert len(routes_a) == 1
    assert len(routes_b) == 1
    assert routes_a[0].file_path == "docs_src/body/tutorial001.py"
    assert routes_b[0].file_path == "docs_src/extra_models/tutorial001.py"
    # Source classification is EXAMPLE for docs_src
    assert routes_a[0].source_classification == SourceClassification.EXAMPLE
    assert routes_b[0].source_classification == SourceClassification.EXAMPLE
