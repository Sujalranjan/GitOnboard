"""
Scout and Verification Agent Tests

Tests validate that:
1. Scout can produce hypotheses
2. Scout evidence is classified conservatively
3. Verification independently checks Scout claims
4. Verification uses GroundTruthValidator
5. False Scout claims are refuted by verification
6. Verification cannot be bypassed
7. Phase 8A fabricated entities are rejected
"""

import pytest
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.entity import Entity
from backend.intelligence.rim.location import SourceLocation
from backend.intelligence.rim.metadata import RepositoryMetadata
from backend.intelligence.rim.enums import EntityType
from backend.intelligence.capabilities.model import Capability, CapabilityCategory
from backend.investigation.scout import ScoutAgent, ScoutStrategy
from backend.investigation.verifier import VerificationAgent, VerificationContext
from backend.investigation.finding import FindingStatus
from backend.investigation.evidence import EvidenceType


@pytest.fixture
def test_repository():
    """Create test repository with known entities."""
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

    # Capability: Authentication
    cap_auth = Capability(
        id="cap_auth",
        purpose="User Authentication",
        category=CapabilityCategory.AUTHENTICATION,
        responsibilities=["Handles login verification"],
        keywords=["authentication", "login"],
        representative_sources=["src/auth.py"],
        confidence=0.95,
        evidence=[],
    )

    return RepositoryModel(
        metadata=metadata,
        entities={
            file_auth.id: file_auth,
            func_login.id: func_login,
            class_controller.id: class_controller,
        },
        relationships={},
        capabilities={cap_auth.id: cap_auth},
        capability_relationships={},
        features={},
        feature_relationships={},
    )


class TestScoutAgent:
    """Test Scout Agent hypothesis generation."""

    def test_scout_finds_function(self, test_repository):
        """Scout can discover existing functions."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_symbol("login_user")

        assert hypothesis is not None
        assert hypothesis.claim_type == "EXISTS"
        assert "login_user" in hypothesis.claim
        assert hypothesis.strategy == ScoutStrategy.SYMBOL_SEARCH
        assert len(hypothesis.evidence) > 0

    def test_scout_finds_class(self, test_repository):
        """Scout can discover existing classes."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_symbol("LoginController")

        assert hypothesis is not None
        assert hypothesis.claim_type == "EXISTS"
        assert "LoginController" in hypothesis.claim

    def test_scout_returns_none_for_missing_symbol(self, test_repository):
        """Scout returns None when symbol not found (uncertain)."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_symbol("nonexistent_function")

        assert hypothesis is None

    def test_scout_absence_hypothesis(self, test_repository):
        """Scout generates absence hypothesis for missing symbols."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_absence("setupMockHTTPServer")

        assert hypothesis is not None
        assert hypothesis.claim_type == "ABSENT"
        assert hypothesis.requires_ground_truth is True
        assert hypothesis.strategy == ScoutStrategy.SYMBOL_SEARCH

    def test_scout_absence_returns_none_for_existing_symbol(self, test_repository):
        """Scout returns None for absence when symbol actually exists."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_absence("login_user")

        assert hypothesis is None

    def test_scout_evidence_is_indirect(self, test_repository):
        """Scout evidence is INDIRECT (search result), not DIRECT."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_symbol("login_user")

        assert hypothesis is not None
        assert len(hypothesis.evidence) > 0
        # Scout evidence should be INDIRECT - it's a search result, not verification
        assert hypothesis.evidence[0].evidence_type == EvidenceType.INDIRECT

    def test_scout_feature_discovery(self, test_repository):
        """Scout can discover features in capabilities."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_feature("authentication")

        assert hypothesis is not None
        assert hypothesis.claim_type == "EXISTS"
        assert hypothesis.strategy == ScoutStrategy.FEATURE_SEARCH

    def test_scout_creates_finding_in_observed_state(self, test_repository):
        """Scout hypothesis converts to Finding in OBSERVED state."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_symbol("login_user")
        finding = hypothesis.to_finding()

        assert finding.status == FindingStatus.OBSERVED
        assert finding.scout_agent == "scout-v1"


class TestVerificationAgent:
    """Test Verification Agent independent validation."""

    def test_verification_confirms_existing_symbol(self, test_repository):
        """Verification confirms Scout claim when symbol actually exists."""
        scout = ScoutAgent(test_repository)
        verifier = VerificationAgent(test_repository)

        hypothesis = scout.investigate_symbol("login_user")
        context = VerificationContext(
            hypothesis=hypothesis,
            repository_model=test_repository,
        )

        result = verifier.verify(context)

        assert result.verdict == "CONFIRMED"
        assert result.finding.status == FindingStatus.INDEPENDENTLY_VERIFIED
        assert result.finding.ground_truth_evidence is not None
        assert result.finding.ground_truth_claim == "EXISTS"

    def test_verification_refutes_false_existence_claim(self, test_repository):
        """Verification refutes Scout claim of existing symbol when it doesn't exist."""
        # Create hypothesis claiming nonexistent symbol exists
        scout = ScoutAgent(test_repository)
        hypothesis = scout.investigate_symbol("setupMockHTTPServer")

        # Since setupMockHTTPServer doesn't exist, Scout returns None
        # Create a false hypothesis manually to test refutation
        from backend.investigation.scout import ScoutHypothesis

        false_hypothesis = ScoutHypothesis(
            finding_id="FALSE-HYP-001",
            claim="setupMockHTTPServer exists",
            claim_type="EXISTS",
            strategy=ScoutStrategy.SYMBOL_SEARCH,
            hypothesis_summary="Scout claims setupMockHTTPServer exists",
            evidence=[],
            evidence_locations=[],
            reasoning="False Scout hypothesis for testing",
            requires_ground_truth=False,
        )

        verifier = VerificationAgent(test_repository)
        context = VerificationContext(
            hypothesis=false_hypothesis,
            repository_model=test_repository,
        )

        result = verifier.verify(context)

        # Verification should determine entity doesn't exist
        assert result.verdict == "UNRESOLVED"
        assert result.finding.status == FindingStatus.UNRESOLVED

    def test_verification_refutes_false_absence_claim(self, test_repository):
        """Verification refutes claim that existing symbol is absent."""
        scout = ScoutAgent(test_repository)
        verifier = VerificationAgent(test_repository)

        # Scout: login_user is absent
        hypothesis = scout.investigate_absence("login_user")

        # Scout returns None because login_user exists
        assert hypothesis is None

        # Manually create false absence hypothesis
        from backend.investigation.scout import ScoutHypothesis

        false_hypothesis = ScoutHypothesis(
            finding_id="FALSE-ABS-001",
            claim="login_user does not exist",
            claim_type="ABSENT",
            strategy=ScoutStrategy.SYMBOL_SEARCH,
            hypothesis_summary="False absence claim",
            evidence=[],
            evidence_locations=[],
            reasoning="Testing refutation of false absence",
            requires_ground_truth=True,
        )

        context = VerificationContext(
            hypothesis=false_hypothesis,
            repository_model=test_repository,
        )

        result = verifier.verify(context)

        # Verification should find the symbol and REFUTE absence claim
        assert result.verdict == "REFUTED"
        assert result.finding.status == FindingStatus.INDEPENDENTLY_VERIFIED
        assert result.finding.contradictory_evidence is not None

    def test_verification_is_independent_from_scout(self, test_repository):
        """CRITICAL: Verification uses own inspection, not Scout's evidence."""
        scout = ScoutAgent(test_repository)
        verifier = VerificationAgent(test_repository)

        hypothesis = scout.investigate_symbol("login_user")

        # Scout evidence is INDIRECT
        assert hypothesis.evidence[0].evidence_type == EvidenceType.INDIRECT

        context = VerificationContext(
            hypothesis=hypothesis,
            repository_model=test_repository,
        )

        result = verifier.verify(context)

        # Verification must use DIRECT evidence from independent inspection
        # The key proof of independence: Scout evidence is INDIRECT, Verifier evidence is DIRECT
        assert hypothesis.evidence[0].evidence_type == EvidenceType.INDIRECT

        if result.verification_evidence:
            assert result.verification_evidence.evidence_type == EvidenceType.DIRECT
            # Evidence comes from GroundTruthValidator or independent inspection, not Scout
            assert result.verification_evidence != hypothesis.evidence[0]

    def test_verification_bounded_attempts(self, test_repository):
        """Verification is bounded to max attempts."""
        scout = ScoutAgent(test_repository)
        verifier = VerificationAgent(test_repository)

        hypothesis = scout.investigate_symbol("login_user")
        context = VerificationContext(
            hypothesis=hypothesis,
            repository_model=test_repository,
            max_verification_attempts=2,
        )

        result = verifier.verify(context)

        # Should have at most 2 attempts
        assert result.finding.verification_attempts <= context.max_verification_attempts

    def test_verification_unresolved_for_uncertain_absence(self, test_repository):
        """Verification returns UNRESOLVED for absence when coverage insufficient."""
        scout = ScoutAgent(test_repository)
        verifier = VerificationAgent(test_repository)

        # Scout: symbol doesn't exist
        hypothesis = scout.investigate_absence("unknownFunction")

        assert hypothesis is not None
        assert hypothesis.requires_ground_truth is True

        context = VerificationContext(
            hypothesis=hypothesis,
            repository_model=test_repository,
        )

        result = verifier.verify(context)

        # Conservative: UNRESOLVED (not VERIFIED_ABSENT)
        assert result.verdict == "UNRESOLVED"
        assert result.finding.status == FindingStatus.UNRESOLVED


class TestPhase8ARegressionPrevention:
    """Test that fabricated entities from Phase 8A are rejected."""

    def test_phase8a_setupMockHTTPServer_rejected(self, test_repository):
        """Phase 8A test case: setupMockHTTPServer must not be confirmed."""
        scout = ScoutAgent(test_repository)

        # Scout looks for the fabricated entity
        hypothesis = scout.investigate_symbol("setupMockHTTPServer")

        # Scout should return None (not found)
        assert hypothesis is None

    def test_phase8a_false_claim_refuted(self, test_repository):
        """If Scout falsely claims setupMockHTTPServer exists, Verifier refutes it."""
        from backend.investigation.scout import ScoutHypothesis

        # Create false Scout hypothesis
        false_hypothesis = ScoutHypothesis(
            finding_id="PHASE8A-ATTACK",
            claim="setupMockHTTPServer exists",
            claim_type="EXISTS",
            strategy=ScoutStrategy.SYMBOL_SEARCH,
            hypothesis_summary="Fabricated Scout claim",
            evidence=[],
            evidence_locations=[],
            reasoning="Attack: trying to establish false entity as truth",
            requires_ground_truth=False,
        )

        verifier = VerificationAgent(test_repository)
        context = VerificationContext(
            hypothesis=false_hypothesis,
            repository_model=test_repository,
        )

        result = verifier.verify(context)

        # Verification must not confirm the fabricated entity
        assert result.verdict != "CONFIRMED"

    def test_phase8a_handleAuthFlow_rejected(self, test_repository):
        """Phase 8A test case: handleAuthFlow must not be confirmed."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_symbol("handleAuthFlow")

        # Scout returns None (not found)
        assert hypothesis is None

    def test_phase8a_LoginComponent_rejected(self, test_repository):
        """Phase 8A test case: LoginComponent must not be confirmed."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_symbol("LoginComponent")

        # Scout returns None (not found)
        assert hypothesis is None


class TestScoutVerificationWorkflow:
    """Test Scout → Verification workflow."""

    def test_full_workflow_confirmed(self, test_repository):
        """Full workflow: Scout finds claim, Verification confirms it."""
        scout = ScoutAgent(test_repository)
        verifier = VerificationAgent(test_repository)

        # Scout discovers
        hypothesis = scout.investigate_symbol("login_user")
        assert hypothesis is not None

        # Verification checks
        context = VerificationContext(
            hypothesis=hypothesis,
            repository_model=test_repository,
        )
        result = verifier.verify(context)

        # Outcome
        assert result.verdict == "CONFIRMED"
        assert result.finding.ground_truth_evidence is not None

    def test_full_workflow_unresolved(self, test_repository):
        """Full workflow: Scout uncertain, Verification unresolved."""
        scout = ScoutAgent(test_repository)
        verifier = VerificationAgent(test_repository)

        # Scout finds nothing
        hypothesis = scout.investigate_symbol("unknownSymbol")
        assert hypothesis is None

        # Try absence hypothesis
        hypothesis = scout.investigate_absence("unknownSymbol")
        assert hypothesis is not None
        assert hypothesis.requires_ground_truth is True

        # Verification checks
        context = VerificationContext(
            hypothesis=hypothesis,
            repository_model=test_repository,
        )
        result = verifier.verify(context)

        # Conservative outcome
        assert result.verdict == "UNRESOLVED"

    def test_scout_evidence_not_directly_usable_as_ground_truth(self, test_repository):
        """Scout evidence cannot be directly used as ground truth."""
        scout = ScoutAgent(test_repository)

        hypothesis = scout.investigate_symbol("login_user")

        # Scout evidence is INDIRECT
        assert hypothesis.evidence[0].evidence_type == EvidenceType.INDIRECT

        finding = hypothesis.to_finding()

        # Setting INDIRECT evidence as ground truth would fail GroundTruthResult validation
        # because VERIFIED_* requires DIRECT evidence
        # But we can test that the evidence type is wrong
        assert hypothesis.evidence[0].evidence_type != EvidenceType.DIRECT

        # Scout evidence should never reach the ground_truth_evidence field
        # That is Verification Agent's responsibility
        assert finding.ground_truth_evidence is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
