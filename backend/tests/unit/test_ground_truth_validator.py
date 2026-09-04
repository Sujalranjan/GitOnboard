"""
Ground-Truth Validator Tests

Tests validate that:
1. Repository-grounded claims produce VERIFIED_PRESENT
2. Agent assertions cannot establish ground truth
3. Search zero-results cannot prove absence
4. Absence claims require sufficient coverage
5. Metadata/file paths cannot establish ground truth
6. Phase 8A fabricated entities are not accepted as present
"""

import pytest
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.relationship import Relationship
from backend.intelligence.rim.enums import EntityType, RelationshipType
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.capabilities.model import Capability, CapabilityCategory
from backend.investigation.ground_truth import (
    GroundTruthValidator,
    VerificationStatus,
    GroundTruthResult,
)
from backend.investigation.evidence import EvidenceType


@pytest.fixture
def simple_repository():
    """
    Create a simple test repository with known entities.

    Entities:
    - auth.py (file)
    - login_user (function in auth.py)
    - LoginController (class in auth.py)
    - POST /api/login (route)
    - NOT present: setupMockHTTPServer (Phase 8A test case)
    """
    metadata = RepositoryMetadata(
        name="TestRepo",
        path="/test",
        languages=["Python"],
    )

    # File: auth.py
    file_auth = Entity(
        id="file_auth",
        type=EntityType.FILE,
        name="auth.py",
        location=SourceLocation(
            repository_path="src/auth.py",
            start_line=1,
            end_line=100,
            language="Python",
        ),
        metadata={"language": "Python"},
    )

    # Function: login_user
    func_login = Entity(
        id="func_login_user",
        type=EntityType.FUNCTION,
        name="login_user",
        qualified_name="auth.login_user",
        location=SourceLocation(
            repository_path="src/auth.py",
            start_line=10,
            end_line=25,
            language="Python",
        ),
        metadata={"file_id": "file_auth"},
    )

    # Class: LoginController
    class_controller = Entity(
        id="class_login_controller",
        type=EntityType.CLASS,
        name="LoginController",
        location=SourceLocation(
            repository_path="src/auth.py",
            start_line=30,
            end_line=60,
            language="Python",
        ),
        metadata={"file_id": "file_auth"},
    )

    # Route: POST /api/login
    route_login = Entity(
        id="route_post_login",
        type=EntityType.ROUTE,
        name="post_login",
        location=SourceLocation(
            repository_path="src/auth.py",
            start_line=9,
            end_line=9,
            language="Python",
        ),
        metadata={
            "http_method": "POST",
            "route_path": "/api/login",
            "handler_symbol_id": "func_login_user",
        },
    )

    # Service: AuthService
    service_auth = Entity(
        id="service_auth",
        type=EntityType.SERVICE,
        name="AuthService",
        location=SourceLocation(
            repository_path="src/auth.py",
            start_line=65,
            end_line=95,
            language="Python",
        ),
        metadata={},
    )

    # Capability: Authentication
    cap_auth = Capability(
        id="cap_auth",
        purpose="User Authentication",
        category=CapabilityCategory.AUTHENTICATION,
        responsibilities=["Handles login verification"],
        keywords=["authentication", "login", "password"],
        representative_sources=["src/auth.py"],
        confidence=0.95,
        evidence=[
            {
                "symbol_id": "func_login_user",
                "role": "handler",
                "type": "source_code",
                "location": "src/auth.py:10",
            }
        ],
    )

    return RepositoryModel(
        metadata=metadata,
        entities={
            file_auth.id: file_auth,
            func_login.id: func_login,
            class_controller.id: class_controller,
            route_login.id: route_login,
            service_auth.id: service_auth,
        },
        relationships={},
        capabilities={
            cap_auth.id: cap_auth,
        },
        capability_relationships={},
        features={},
        feature_relationships={},
    )


class TestPositiveClaims:
    """Test validation of positive existence claims."""

    def test_existing_function_validates_present(self, simple_repository):
        """VERIFIED_PRESENT when function actually exists in repository."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_symbol_exists("login_user")

        assert result.status == VerificationStatus.VERIFIED_PRESENT
        assert result.evidence is not None
        assert result.evidence.evidence_type == EvidenceType.DIRECT
        assert result.evidence.confidence >= 0.9
        assert "login_user" in result.evidence.observation
        assert "src/auth.py" in result.evidence.location

    def test_existing_class_validates_present(self, simple_repository):
        """VERIFIED_PRESENT when class actually exists in repository."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_symbol_exists("LoginController")

        assert result.status == VerificationStatus.VERIFIED_PRESENT
        assert result.evidence is not None
        assert result.evidence.evidence_type == EvidenceType.DIRECT
        assert "LoginController" in result.evidence.observation

    def test_existing_file_validates_present(self, simple_repository):
        """VERIFIED_PRESENT when file actually exists in repository."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_file_exists("src/auth.py")

        assert result.status == VerificationStatus.VERIFIED_PRESENT
        assert result.evidence is not None
        assert result.evidence.confidence == 1.0

    def test_existing_route_validates_present(self, simple_repository):
        """VERIFIED_PRESENT when route actually exists in repository."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_route_exists("/api/login", "POST")

        assert result.status == VerificationStatus.VERIFIED_PRESENT
        assert result.evidence is not None
        assert "POST" in result.evidence.observation
        assert "/api/login" in result.evidence.observation

    def test_existing_service_validates_present(self, simple_repository):
        """VERIFIED_PRESENT when service actually exists in repository."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_service_component_exists("AuthService")

        assert result.status == VerificationStatus.VERIFIED_PRESENT
        assert result.evidence is not None
        assert "AuthService" in result.evidence.observation

    def test_existing_feature_validates_present(self, simple_repository):
        """VERIFIED_PRESENT when feature exists in capabilities."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_feature_exists("authentication")

        assert result.status == VerificationStatus.VERIFIED_PRESENT
        assert result.evidence is not None
        assert result.evidence.confidence >= 0.9


class TestNegativeClaims:
    """Test validation of negative absence claims."""

    def test_nonexistent_symbol_not_automatically_absent(self, simple_repository):
        """UNRESOLVED when symbol not found (not automatic VERIFIED_ABSENT)."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_symbol_exists("nonexistent_function")

        # NOT verified absent - just unresolved
        assert result.status == VerificationStatus.UNRESOLVED
        assert result.evidence is None
        assert "Cannot verify absence" in result.coverage_note

    def test_nonexistent_file_not_automatically_absent(self, simple_repository):
        """UNRESOLVED when file not found (not automatic VERIFIED_ABSENT)."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_file_exists("src/nonexistent.py")

        assert result.status == VerificationStatus.UNRESOLVED
        assert result.evidence is None

    def test_nonexistent_route_not_automatically_absent(self, simple_repository):
        """UNRESOLVED when route not found (not automatic VERIFIED_ABSENT)."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_route_exists("/api/nonexistent", "GET")

        assert result.status == VerificationStatus.UNRESOLVED
        assert result.evidence is None


class TestAgentAssertionBypass:
    """Test that agent assertions cannot establish ground truth."""

    def test_agent_assertion_not_ground_truth(self):
        """Agent assertion cannot become ground truth without repository evidence."""
        # Simulate an agent claiming something exists
        agent_claim = "setupMockHTTPServer exists in repository"

        # Create empty repository
        repository = RepositoryModel(
            metadata=RepositoryMetadata(name="Empty", path="/empty", languages=[]),
            entities={},
            relationships={},
            capabilities={},
            capability_relationships={},
            features={},
            feature_relationships={},
        )

        validator = GroundTruthValidator(repository)

        # Try to validate the symbol
        result = validator.validate_symbol_exists("setupMockHTTPServer")

        # Should be UNRESOLVED, NOT validated present just because agent said so
        assert result.status == VerificationStatus.UNRESOLVED
        assert result.evidence is None

    def test_metadata_path_not_ground_truth(self, simple_repository):
        """File path in metadata cannot establish ground truth without actual entity."""
        # This simulates Phase 8A.6 where a metadata path was used as proof
        metadata_path = "fixtures/phase8a6_ground_truth.json"

        # Just having a metadata path is not enough
        result = simple_repository.entities.get("file_" + metadata_path)

        # No entity exists for this metadata path
        assert result is None

        # Validator should not find anything
        validator = GroundTruthValidator(simple_repository)
        validation_result = validator.validate_file_exists(metadata_path)

        assert validation_result.status == VerificationStatus.UNRESOLVED


class TestSearchZeroResultsNotAbsence:
    """Test that search zero-results does not prove absence."""

    def test_search_failure_not_verified_absent(self, simple_repository):
        """
        Zero search results ≠ VERIFIED_ABSENT.

        This is the critical Phase 8A distinction:
        - Search("setupMockHTTPServer") -> 0 results
        - Does NOT mean setupMockHTTPServer is absent
        - Could mean: not indexed, search incomplete, etc.
        """
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_symbol_exists("setupMockHTTPServer")

        # UNRESOLVED, NOT verified absent
        assert result.status == VerificationStatus.UNRESOLVED
        assert result.evidence is None
        assert "Cannot verify absence" in result.coverage_note

    def test_zero_search_results_never_becomes_direct_evidence(self, simple_repository):
        """Zero search results cannot be converted to DIRECT evidence of absence."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_symbol_exists("fake_entity")

        # Never produces DIRECT evidence
        assert result.evidence is None or result.evidence.evidence_type != EvidenceType.DIRECT
        assert result.status != VerificationStatus.VERIFIED_PRESENT


class TestPhase8ARegressionProtection:
    """Test protection against Phase 8A fabricated entity attacks."""

    def test_phase8a_setupMockHTTPServer_not_accepted(self, simple_repository):
        """Phase 8A test case: setupMockHTTPServer should NOT be verified present."""
        # This was a fabricated entity in Phase 8A.6
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_symbol_exists("setupMockHTTPServer")

        # Must NOT be VERIFIED_PRESENT
        assert result.status != VerificationStatus.VERIFIED_PRESENT
        assert result.evidence is None

    def test_phase8a_handleAuthFlow_not_accepted(self, simple_repository):
        """Phase 8A test case: handleAuthFlow should NOT be verified present."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_symbol_exists("handleAuthFlow")

        assert result.status != VerificationStatus.VERIFIED_PRESENT
        assert result.evidence is None

    def test_phase8a_LoginComponent_not_accepted(self, simple_repository):
        """Phase 8A test case: LoginComponent should NOT be verified present."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_symbol_exists("LoginComponent")

        assert result.status != VerificationStatus.VERIFIED_PRESENT
        assert result.evidence is None

    def test_phase8a_fixture_path_cannot_establish_truth(self, simple_repository):
        """
        Phase 8A attack vector: using fixture path as ground truth.

        Simulates: ground_truth_evidence = "phase8a6_ground_truth.json"
        """
        # Metadata path pointing to a fixture
        fixture_metadata_path = "fixtures/PHASE8A6_GROUND_TRUTH/setupMockHTTPServer.json"

        validator = GroundTruthValidator(simple_repository)

        # Validator must not find anything
        result = validator.validate_file_exists(fixture_metadata_path)

        # Fixture path cannot establish truth
        assert result.status == VerificationStatus.UNRESOLVED
        assert result.evidence is None


class TestGroundTruthResultValidation:
    """Test that GroundTruthResult enforces safety invariants."""

    def test_unresolved_cannot_have_evidence(self):
        """UNRESOLVED status cannot carry evidence object."""
        from backend.investigation.evidence import Evidence

        # UNRESOLVED with None evidence is OK
        result = GroundTruthResult(
            status=VerificationStatus.UNRESOLVED,
            evidence=None,
        )
        assert result.evidence is None

        # But evidence object with UNRESOLVED is forbidden
        dummy_evidence = Evidence(
            evidence_type=EvidenceType.DIRECT,
            source="test",
            location="test",
            observation="test",
            confidence=0.95,
        )

        with pytest.raises(ValueError, match="UNRESOLVED status cannot have evidence"):
            GroundTruthResult(
                status=VerificationStatus.UNRESOLVED,
                evidence=dummy_evidence,
            )

    def test_verified_requires_evidence(self):
        """VERIFIED_PRESENT and VERIFIED_ABSENT require evidence object."""
        # VERIFIED_PRESENT without evidence is forbidden
        with pytest.raises(ValueError, match="VERIFIED_PRESENT requires evidence"):
            GroundTruthResult(
                status=VerificationStatus.VERIFIED_PRESENT,
                evidence=None,
            )

        # VERIFIED_ABSENT without evidence is forbidden
        with pytest.raises(ValueError, match="VERIFIED_ABSENT requires evidence"):
            GroundTruthResult(
                status=VerificationStatus.VERIFIED_ABSENT,
                evidence=None,
            )

    def test_verified_requires_direct_evidence(self):
        """VERIFIED_* must use DIRECT evidence, never INDIRECT/UNVERIFIED."""
        from backend.investigation.evidence import Evidence

        # Create INDIRECT evidence (wrong type)
        indirect_evidence = Evidence.from_retrieval_result("symbol", found=True, result_count=1)

        with pytest.raises(ValueError, match="requires DIRECT evidence"):
            GroundTruthResult(
                status=VerificationStatus.VERIFIED_PRESENT,
                evidence=indirect_evidence,
            )

    def test_verified_requires_high_confidence(self):
        """VERIFIED_* requires confidence >= 0.9."""
        from backend.investigation.evidence import Evidence, InvalidEvidenceError

        # Cannot even create low-confidence DIRECT evidence
        with pytest.raises(InvalidEvidenceError):
            Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="test",
                location="test",
                observation="test",
                confidence=0.85,  # Below 0.9
            )


class TestValidatorProvenance:
    """Test that validator evidence includes proper provenance."""

    def test_function_evidence_has_location(self, simple_repository):
        """Function evidence must include actual source location."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_symbol_exists("login_user")

        assert result.evidence is not None
        # Must have repository path and line number
        assert "src/auth.py" in result.evidence.location
        assert ":" in result.evidence.location

    def test_function_evidence_has_context(self, simple_repository):
        """Function evidence must include symbol ID and language."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_symbol_exists("login_user")

        assert result.evidence is not None
        assert result.evidence.context is not None
        assert "Symbol ID" in result.evidence.context or "func_login_user" in result.evidence.context

    def test_route_evidence_has_handler_info(self, simple_repository):
        """Route evidence must include HTTP method and path."""
        validator = GroundTruthValidator(simple_repository)

        result = validator.validate_route_exists("/api/login", "POST")

        assert result.evidence is not None
        assert "POST" in result.evidence.observation
        assert "/api/login" in result.evidence.observation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
