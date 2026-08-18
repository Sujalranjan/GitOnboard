"""
Phase 3 Hallucination Baseline Test Suite.
Tests all required edge cases for deterministic claim extraction, evidence support classification,
citation entailment, hallucination categorization, evaluable claims, conditional hallucination rate,
separate citation quality tracking, and refined false rejection analysis.
"""
import pytest
from pathlib import Path

from backend.summary.schemas import (
    DeployableUnit,
    EvidenceItem,
    EvidenceSourceType,
    RepositoryClaim,
    SourceClassification,
    VerificationStatus,
)
from evaluation.phase3.schemas import (
    AtomicClaim,
    ClaimType,
    HallucinationCategory,
    SupportStatus,
    CitationStatus,
)
from evaluation.phase3.extractor import AtomicClaimExtractor
from evaluation.phase3.classifier import ClaimClassifier
from evaluation.phase3.citation import CitationEvaluator
from evaluation.phase3.leakage import LeakageAnalyzer
from evaluation.phase3.runner import Phase3Runner


@pytest.fixture
def sample_evidence():
    return {
        "ev_0001": EvidenceItem(
            evidence_id="ev_0001",
            source_type=EvidenceSourceType.MANIFEST_DEPENDENCY,
            source_classification=SourceClassification.CONFIGURATION,
            file_path="requirements.txt",
            snippet="fastapi==0.110.0",
            symbol_name="fastapi",
        ),
        "ev_0002": EvidenceItem(
            evidence_id="ev_0002",
            source_type=EvidenceSourceType.CONFIG_ENTRY,
            source_classification=SourceClassification.CONFIGURATION,
            file_path="app/settings.py",
            snippet="DATABASE_URL = 'postgresql://localhost:5432/db'",
            symbol_name="postgresql",
        ),
        "ev_0003": EvidenceItem(
            evidence_id="ev_0003",
            source_type=EvidenceSourceType.AST_DEFINITION,
            source_classification=SourceClassification.TEST,
            file_path="tests/test_auth.py",
            snippet="def test_login(): pass",
            symbol_name="test_login",
        ),
    }


@pytest.fixture
def sample_verified_claims():
    return [
        RepositoryClaim(
            claim_id="claim_001",
            subject="fastapi",
            claim_category="framework",
            status=VerificationStatus.STRONGLY_SUPPORTED,
            supporting_evidence_ids=["ev_0001"],
        ),
        RepositoryClaim(
            claim_id="claim_002",
            subject="sqlite",
            claim_category="database",
            status=VerificationStatus.CONTRADICTED,
            supporting_evidence_ids=["ev_0002"],
        ),
    ]


@pytest.fixture
def sample_known_files():
    return [
        "requirements.txt",
        "app/settings.py",
        "app/main.py",
        "app/routes/users.py",
        "tests/test_auth.py",
    ]


# 1. Supported technology claim
def test_supported_technology_claim(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C001",
        repository="test_repo",
        text="The project uses FastAPI (Framework). Status: supported.",
        claim_type=ClaimType.TECHNOLOGY,
        citations=["ev_0001"],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert result.support_status == SupportStatus.SUPPORTED
    assert len(result.hallucination_categories) == 0


# 2. Unsupported technology claim
def test_unsupported_technology_claim(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C002",
        repository="test_repo",
        text="The project uses Django (Framework). Status: supported.",
        claim_type=ClaimType.TECHNOLOGY,
        citations=[],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert result.support_status == SupportStatus.UNSUPPORTED
    assert HallucinationCategory.INCORRECT_TECHNOLOGY in result.hallucination_categories


# 3. Contradicted technology claim
def test_contradicted_technology_claim(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C003",
        repository="test_repo",
        text="The project uses SQLite as its primary database.",
        claim_type=ClaimType.DATABASE,
        citations=["ev_0002"],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert result.support_status == SupportStatus.CONTRADICTED
    assert HallucinationCategory.INCORRECT_TECHNOLOGY in result.hallucination_categories


# 4. Existing path
def test_existing_path_claim(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C004",
        repository="test_repo",
        text="Deployable unit 'users_api' exists at root path 'app/routes'.",
        claim_type=ClaimType.PATH,
        citations=[],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert result.support_status == SupportStatus.SUPPORTED


# 5. Fabricated path
def test_fabricated_path_claim(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C005",
        repository="test_repo",
        text="Deployable unit 'admin' exists at root path '/services/admin_dashboard'.",
        claim_type=ClaimType.PATH,
        citations=[],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert result.support_status == SupportStatus.UNSUPPORTED
    assert HallucinationCategory.FABRICATED_PATH in result.hallucination_categories


# 6. Existing file
def test_existing_file_claim(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C006",
        repository="test_repo",
        text="Configuration defined in file 'app/settings.py'.",
        claim_type=ClaimType.FILE,
        citations=[],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert result.support_status == SupportStatus.SUPPORTED


# 7. Fabricated file
def test_fabricated_file_claim(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C007",
        repository="test_repo",
        text="Entrypoint defined in file 'app/nonexistent_server.py'.",
        claim_type=ClaimType.FILE,
        citations=[],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert result.support_status == SupportStatus.UNSUPPORTED
    assert HallucinationCategory.FABRICATED_FILE in result.hallucination_categories


# 8. Existing symbol
def test_existing_symbol_claim(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C008",
        repository="test_repo",
        text="Module exports function 'test_login'.",
        claim_type=ClaimType.SYMBOL,
        citations=["ev_0003"],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert result.support_status == SupportStatus.SUPPORTED


# 9. Fabricated symbol
def test_fabricated_symbol_claim(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C009",
        repository="test_repo",
        text="Module exports function 'calculate_revenue_matrix'.",
        claim_type=ClaimType.SYMBOL,
        citations=[],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert result.support_status == SupportStatus.UNSUPPORTED
    assert HallucinationCategory.FABRICATED_SYMBOL in result.hallucination_categories


# 10. False contradiction
def test_false_contradiction_detection(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C010",
        repository="test_repo",
        text="Documentation claims 'GraphQL API', but actual code exhibits 'REST endpoints only'.",
        claim_type=ClaimType.CONTRADICTION,
        citations=[],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert result.support_status == SupportStatus.UNSUPPORTED
    assert HallucinationCategory.FALSE_CONTRADICTION in result.hallucination_categories


# 11. Valid citation
def test_valid_citation(sample_evidence):
    evals = CitationEvaluator.evaluate_citations(
        citations=["ev_0001"],
        claim_text="Uses FastAPI framework",
        known_evidence=sample_evidence,
    )
    assert len(evals) == 1
    assert evals[0].status == CitationStatus.VALID


# 12. Invalid citation ID (Reported separately under citation quality, not hallucination taxonomy)
def test_invalid_citation_id_separate_from_hallucination(sample_evidence, sample_verified_claims, sample_known_files):
    claim = AtomicClaim(
        claim_id="C012",
        repository="test_repo",
        text="The project uses FastAPI (Framework). Status: supported.",
        claim_type=ClaimType.TECHNOLOGY,
        citations=["ev_9999_bogus"],
        support_status=SupportStatus.UNRESOLVED,
    )
    result = ClaimClassifier.classify_claim(
        claim=claim,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    # Core claim is supported
    assert result.support_status == SupportStatus.SUPPORTED
    # Citation is evaluated as INVALID_ID
    assert len(result.citation_evaluations) == 1
    assert result.citation_evaluations[0].status == CitationStatus.INVALID_ID
    # But INVALID_CITATION is NOT in content hallucination categories
    assert len(result.hallucination_categories) == 0


# 13. Citation that exists but does not entail the claim
def test_citation_not_entailed(sample_evidence):
    evals = CitationEvaluator.evaluate_citations(
        citations=["ev_0003"],  # test_auth.py test function
        claim_text="The project uses Celery distributed task queue strongly_supported",
        known_evidence=sample_evidence,
    )
    assert len(evals) == 1
    assert evals[0].status == CitationStatus.NOT_ENTAILED


# 14. Validator rejection correctly reflected in leakage analysis
def test_validator_rejection_reflected_in_leakage(sample_evidence, sample_verified_claims, sample_known_files):
    raw_writer_output = {
        "overview": {"text": "Test App", "evidence_ids": ["ev_0001"]},
        "deployable_units": [
            {"name": "admin", "unit_type": "service", "root_path": "/fake/admin", "summary": "Admin", "evidence_ids": []}
        ],
        "technologies": [],
        "data_and_storage": {},
        "operations_and_deployment": {},
        "discrepancies": [],
        "unverified_doc_claims": [],
    }
    claims = AtomicClaimExtractor.extract_claims(raw_writer_output, "test_repo")
    for c in claims:
        ClaimClassifier.classify_claim(c, sample_evidence, sample_verified_claims, sample_known_files)

    res = LeakageAnalyzer.analyze_repository(
        repo_id="test_repo",
        raw_writer_output=raw_writer_output,
        claims=claims,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert res.invalid_claims_before_validator >= 1
    assert res.invalid_claims_rejected >= 1
    assert res.invalid_claims_leaked == 0
    assert res.leakage_rate == 0.0


# 15. Refined false rejection definition (supported + correctly evidenced claims rejected)
def test_refined_false_rejection_definition(sample_evidence, sample_verified_claims, sample_known_files):
    raw_writer_output = {
        "overview": {"text": "Valid FastAPI App", "evidence_ids": ["ev_0001"]},
        "deployable_units": [],
        "technologies": [
            {"name": "fastapi", "category": "Framework", "status": "strongly_supported", "evidence_ids": ["ev_0001"]}
        ],
        "data_and_storage": {},
        "operations_and_deployment": {},
        "discrepancies": [],
        "unverified_doc_claims": [],
    }
    claims = AtomicClaimExtractor.extract_claims(raw_writer_output, "test_repo")
    for c in claims:
        ClaimClassifier.classify_claim(c, sample_evidence, sample_verified_claims, sample_known_files)

    res = LeakageAnalyzer.analyze_repository(
        repo_id="test_repo",
        raw_writer_output=raw_writer_output,
        claims=claims,
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert res.supported_claims >= 1
    assert res.supported_correctly_evidenced_claims >= 1
    assert res.supported_correctly_evidenced_rejected == 0
    assert res.false_rejection_rate == 0.0


# 16. Evaluable claims and conditional hallucination rate calculation
def test_evaluable_claims_and_conditional_hallucination_rate(sample_evidence, sample_verified_claims, sample_known_files):
    supported_claim = AtomicClaim(
        claim_id="C1", repository="r1", text="The project uses FastAPI (Framework). Status: supported.",
        claim_type=ClaimType.TECHNOLOGY, citations=["ev_0001"], support_status=SupportStatus.SUPPORTED
    )
    unsupported_claim = AtomicClaim(
        claim_id="C2", repository="r1", text="The project uses Django (Framework). Status: supported.",
        claim_type=ClaimType.TECHNOLOGY, citations=[], support_status=SupportStatus.UNSUPPORTED
    )
    unresolved_claim = AtomicClaim(
        claim_id="C3", repository="r1", text="The system provides an intuitive workflow for all users.",
        claim_type=ClaimType.OTHER, citations=[], support_status=SupportStatus.UNRESOLVED
    )

    res = LeakageAnalyzer.analyze_repository(
        repo_id="r1",
        raw_writer_output={"overview": {"text": "App overview"}},
        claims=[supported_claim, unsupported_claim, unresolved_claim],
        known_evidence=sample_evidence,
        verified_claims=sample_verified_claims,
        known_file_paths=sample_known_files,
    )
    assert res.total_claims == 3
    assert res.evaluable_claims == 2   # C1 (Supported) + C2 (Unsupported)
    assert res.supported == 1
    assert res.unsupported == 1
    assert res.unresolved == 1

    # Overall Hallucination Rate = (1 unsupported) / 3 total = 33.33%
    assert res.hallucination_rate == 33.33
    # Conditional Hallucination Rate = (1 unsupported) / 2 evaluable = 50.0%
    assert res.conditional_hallucination_rate == 50.0
