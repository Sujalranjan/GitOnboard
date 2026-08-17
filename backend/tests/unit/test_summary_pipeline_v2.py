"""
Unit and Integration Tests for Evidence-Grounded Summary Pipeline (V2).
Tests: evidence IDs, source classification, structural chunking, manifest extraction,
hierarchy inference, claim verification, contradiction semantics, and deterministic validation.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.summary.schemas import (
    ClaimCategory,
    DeployableUnit,
    DeployableUnitType,
    EvidenceItem,
    EvidenceSourceType,
    RepositoryClaim,
    SourceClassification,
    StructuredSummary,
    VerificationStatus,
)
from backend.summary.chunker import StructuralMarkdownChunker, classify_heading_domain
from backend.summary.extractor import EvidenceExtractor
from backend.summary.hierarchy import RepositoryHierarchyEngine
from backend.summary.verifier import ClaimVerifier
from backend.summary.validator import DeterministicValidator
from backend.summary.fallback import generate_deterministic_fallback
from backend.summary.pipeline import SummaryPipeline
from backend.ai.service import LLMService
from backend.ai.schemas import LLMResponse, TokenUsage


def test_evidence_id_uniqueness_and_source_classification():
    extractor = EvidenceExtractor()
    id1 = extractor._next_id()
    id2 = extractor._next_id()
    assert id1 == "ev_0001"
    assert id2 == "ev_0002"

    assert extractor.classify_source("tests/test_auth.py") == SourceClassification.TEST
    assert extractor.classify_source("src/api/auth.test.ts") == SourceClassification.TEST
    assert extractor.classify_source("generated/client_pb2.py") == SourceClassification.GENERATED
    assert extractor.classify_source("node_modules/express/index.js") == SourceClassification.VENDORED
    assert extractor.classify_source("README.md") == SourceClassification.DOCUMENTATION
    assert extractor.classify_source("docker-compose.yml") == SourceClassification.CONFIGURATION
    assert extractor.classify_source("src/main.py") == SourceClassification.APPLICATION


def test_structural_markdown_chunker():
    doc_content = """# My Project
High performance API platform.

## Architecture
Built using clean architecture and domain services.

## Setup & Deployment
Run docker compose up to start.
"""
    chunks = StructuralMarkdownChunker.chunk_document("README.md", doc_content)
    assert len(chunks) == 3
    assert chunks[0].heading == "My Project"
    assert chunks[0].domain == "overview"
    assert chunks[1].heading == "Architecture"
    assert chunks[1].domain == "architecture"
    assert chunks[2].heading == "Setup & Deployment"
    assert chunks[2].domain == "deployment"
    assert chunks[0].line_start == 1


def test_manifest_and_compose_extraction():
    extractor = EvidenceExtractor()
    pyproject_content = """[project]
name = 'my-api'
dependencies = [
    'fastapi>=0.110.0',
    'sqlalchemy>=2.0.0',
    'redis>=5.0.0'
]
"""
    ev_items = extractor.extract_from_manifests("pyproject.toml", pyproject_content)
    dep_symbols = {e.symbol_name for e in ev_items}
    assert "fastapi" in dep_symbols
    assert "sqlalchemy" in dep_symbols
    assert "redis" in dep_symbols
    assert all(e.source_type == EvidenceSourceType.MANIFEST_DEPENDENCY for e in ev_items)

    compose_content = """services:
  db:
    image: postgres:15
  cache:
    image: redis:7-alpine
"""
    compose_items = extractor.extract_from_compose("docker-compose.yml", compose_content)
    svc_symbols = {e.symbol_name for e in compose_items}
    assert "db" in svc_symbols
    assert "cache" in svc_symbols
    assert all(e.source_type == EvidenceSourceType.CONFIG_ENTRY for e in compose_items)


def test_hierarchy_inference_monorepo():
    files = [
        "apps/api/pyproject.toml",
        "apps/api/main.py",
        "apps/web/package.json",
        "apps/web/app/page.tsx",
        "packages/ui/package.json",
        "packages/ui/Button.tsx",
    ]
    extractor = EvidenceExtractor()
    ev_api = extractor.extract_from_manifests("apps/api/pyproject.toml", "dependencies = ['fastapi']\n")
    ev_web = extractor.extract_from_manifests("apps/web/package.json", '{"dependencies": {"next": "14.0.0"}}')
    all_ev = ev_api + ev_web

    units = RepositoryHierarchyEngine.infer_hierarchy(files, all_ev, entrypoints=["apps/api/main.py"])
    assert len(units) >= 3
    unit_types = {u.name: u.unit_type for u in units}
    assert unit_types.get("api") == DeployableUnitType.BACKEND_API
    assert unit_types.get("web") == DeployableUnitType.WEB_APPLICATION


def test_claim_verifier_contradiction_vs_unverified():
    extractor = EvidenceExtractor()
    ev_manifest = extractor.extract_from_manifests("pyproject.toml", "dependencies = ['fastapi', 'psycopg2-binary']\n")
    ev_compose = extractor.extract_from_compose("docker-compose.yml", "services:\n  db:\n    image: postgres:15\n")
    all_ev = ev_manifest + ev_compose

    # Document claims SQLite (Positive Contradiction with PostgreSQL) and Stripe (Unverified)
    doc_text = "# App\nThis app uses SQLite for database storage and integrates with Stripe payments."
    chunks = StructuralMarkdownChunker.chunk_document("README.md", doc_text)

    claims = ClaimVerifier.verify_technology_claims(all_ev, chunks, source_code_texts={"app/main.py": "import fastapi"})
    claims_by_subject = {c.subject.lower(): c for c in claims}

    # 1. SQLite must be CONTRADICTED (because Postgres is actively in code/compose)
    assert "sqlite" in claims_by_subject
    assert claims_by_subject["sqlite"].status == VerificationStatus.CONTRADICTED

    # 2. Stripe must be DOCUMENTED_UNVERIFIED (NOT contradicted, because absence != contradiction)
    assert "stripe" in claims_by_subject
    assert claims_by_subject["stripe"].status == VerificationStatus.DOCUMENTED_UNVERIFIED

    # 3. FastAPI must be STRONGLY_SUPPORTED (declared + imported in application source)
    assert "fastapi" in claims_by_subject
    assert claims_by_subject["fastapi"].status in {VerificationStatus.STRONGLY_SUPPORTED, VerificationStatus.SUPPORTED}


def test_declared_unused_dependency():
    extractor = EvidenceExtractor()
    ev_manifest = extractor.extract_from_manifests("pyproject.toml", "dependencies = ['boto3', 'fastapi']\n")
    chunks = StructuralMarkdownChunker.chunk_document("README.md", "# App\nClean app.")
    
    # boto3 has no import or usage in application source
    claims = ClaimVerifier.verify_technology_claims(ev_manifest, chunks, source_code_texts={"main.py": "import fastapi"})
    claims_by_subject = {c.subject.lower(): c for c in claims}

    assert "boto3" in claims_by_subject
    assert claims_by_subject["boto3"].status == VerificationStatus.DECLARED_UNUSED


def test_deterministic_validator_and_fluff_stripping():
    extractor = EvidenceExtractor()
    ev_item = EvidenceItem(
        evidence_id="ev_0001",
        source_type=EvidenceSourceType.MANIFEST_DEPENDENCY,
        source_classification=SourceClassification.APPLICATION,
        file_path="pyproject.toml",
        snippet="fastapi>=0.110.0",
        symbol_name="fastapi"
    )
    known_ev = {"ev_0001": ev_item}

    raw_llm_json = {
        "overview": {
            "text": "GitOnBoard is a world-class, blazing fast repository platform.",
            "evidence_ids": ["ev_0001", "ev_fake_999"]
        },
        "technologies": [
            {
                "name": "FastAPI",
                "category": "Framework",
                "status": "strongly_supported",
                "evidence_ids": ["ev_0001"]
            },
            {
                "name": "NonExistentDB",
                "category": "Database",
                "status": "strongly_supported",
                "evidence_ids": ["ev_fake_999"]
            }
        ]
    }

    structured, rejected, stats = DeterministicValidator.validate_and_sanitize(raw_llm_json, known_ev, [])
    
    # Marketing fluff stripped
    assert "world-class" not in structured.overview.text
    assert "blazing fast" not in structured.overview.text
    assert "ev_fake_999" not in structured.overview.evidence_ids

    # Real tech kept
    assert len(structured.technologies) == 1
    assert structured.technologies[0].name == "FastAPI"

    # Fake tech rejected and logged
    assert len(rejected) == 1
    assert "NonExistentDB" in rejected[0].statement


def test_deterministic_fallback_formatting():
    units = [
        DeployableUnit(
            unit_id="backend",
            name="Backend API",
            unit_type=DeployableUnitType.BACKEND_API,
            root_path="backend",
            entrypoints=["backend/main.py"]
        )
    ]
    claims = [
        RepositoryClaim(
            claim_id="c1",
            category=ClaimCategory.TECHNOLOGY_DEPENDENCY,
            subject="FastAPI",
            statement="FastAPI is used.",
            status=VerificationStatus.STRONGLY_SUPPORTED
        )
    ]
    md = generate_deterministic_fallback("test-repo", units, claims, metrics={"total_files": 10, "lines_of_code": 500})
    assert "# test-repo — Repository Summary (Deterministic Verification)" in md
    assert "FastAPI" in md
    assert "Backend API" in md
    assert "world-class" not in md


@pytest.mark.asyncio
async def test_summary_pipeline_e2e_v2_mock_llm(tmp_path):
    # Create sample repository
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'demo'\ndependencies = ['fastapi']\n")
    main_py = tmp_path / "main.py"
    main_py.write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    readme = tmp_path / "README.md"
    readme.write_text("# Demo Service\nA lightweight service built with FastAPI.\n")

    mock_llm_response = {
        "overview": {"text": "Demo Service is an HTTP API service built with FastAPI.", "evidence_ids": ["ev_0001"]},
        "deployable_units": [
            {"name": "demo", "unit_type": "backend_api", "root_path": "/", "summary": "Main API", "evidence_ids": ["ev_0001"]}
        ],
        "technologies": [
            {"name": "FastAPI", "category": "Framework", "status": "strongly_supported", "evidence_ids": ["ev_0001"]}
        ],
        "data_and_storage": {},
        "operations_and_deployment": {},
        "discrepancies": [],
        "unverified_doc_claims": []
    }

    mock_llm = MagicMock(spec=LLMService)
    mock_llm.generate = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(mock_llm_response),
            usage=TokenUsage(prompt_tokens=300, completion_tokens=150, total_tokens=450),
            provider="mock_v2",
            model="mock_v2",
        )
    )

    pipeline = SummaryPipeline(llm_service=mock_llm)
    result = await pipeline.run(
        repo_name="demo",
        metadata={"entrypoints": ["main.py"]},
        metrics={"total_files": 3, "lines_of_code": 20},
        repo_root=tmp_path,
    )

    assert "# demo — Repository Summary" in result.summary_markdown
    assert result.structured_summary is not None
    assert result.structured_summary.technologies[0].name == "FastAPI"
    assert result.doc_context_stats["verified_claims_count"] >= 1
