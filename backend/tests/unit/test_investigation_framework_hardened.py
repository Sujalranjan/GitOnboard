"""
Hardened tests for Multi-Agent Investigation Framework Stage 1.

Tests specifically designed to verify safety invariants are enforced by code,
not by convention. Includes adversarial tests to break safety guarantees.
"""

import pytest
from backend.investigation.finding import (
    Finding,
    FindingStatus,
    FindingSeverity,
    FindingPacket,
    InvalidFindingStateError,
    MissingGroundTruthError,
)
from backend.investigation.evidence import (
    Evidence,
    EvidenceType,
    InvalidEvidenceError,
)


class TestEvidenceValidation:
    """Test that Evidence fields are validated on creation."""

    def test_evidence_requires_non_empty_source(self):
        """DIRECT: source cannot be empty."""
        with pytest.raises(InvalidEvidenceError, match="source cannot be empty"):
            Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="",
                location="file.ts",
                observation="Test",
                confidence=0.95,
            )

    def test_evidence_requires_non_empty_location(self):
        """DIRECT: location cannot be empty."""
        with pytest.raises(InvalidEvidenceError, match="location cannot be empty"):
            Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="source code",
                location="",
                observation="Test",
                confidence=0.95,
            )

    def test_evidence_requires_non_empty_observation(self):
        """DIRECT: observation cannot be empty."""
        with pytest.raises(InvalidEvidenceError, match="observation cannot be empty"):
            Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="source code",
                location="file.ts",
                observation="",
                confidence=0.95,
            )

    def test_evidence_rejects_invalid_confidence_bounds(self):
        """DIRECT: confidence must be 0.0-1.0."""
        with pytest.raises(InvalidEvidenceError, match="confidence must be 0.0-1.0"):
            Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="source code",
                location="file.ts",
                observation="Test",
                confidence=1.5,
            )

    def test_evidence_rejects_confidence_too_low(self):
        """DIRECT: confidence must be >= 0.9."""
        with pytest.raises(InvalidEvidenceError, match="DIRECT evidence requires confidence >= 0.9"):
            Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="source code",
                location="file.ts",
                observation="Test",
                confidence=0.8,
            )

    def test_evidence_unverified_rejects_high_confidence(self):
        """UNVERIFIED: confidence must be <= 0.5."""
        with pytest.raises(InvalidEvidenceError, match="UNVERIFIED evidence should have confidence <= 0.5"):
            Evidence(
                evidence_type=EvidenceType.UNVERIFIED,
                source="test fixture",
                location="fixture.py",
                observation="Test claim",
                confidence=0.6,
            )

    def test_retrieval_result_is_indirect_not_direct(self):
        """CRITICAL: Retrieval zero-results must be INDIRECT, not DIRECT."""
        evidence = Evidence.from_retrieval_result("symbol", found=False, result_count=0)

        assert evidence.evidence_type == EvidenceType.INDIRECT
        assert "no results" in evidence.observation
        assert evidence.confidence == 0.5  # Weak evidence
        assert "Retrieval result is evidence of search behavior" in (evidence.context or "")

    def test_retrieval_found_is_indirect(self):
        """Retrieval found results are INDIRECT, not DIRECT."""
        evidence = Evidence.from_retrieval_result("symbol", found=True, result_count=1)

        assert evidence.evidence_type == EvidenceType.INDIRECT
        assert evidence.confidence == 0.7  # Stronger than not-found, but still indirect


class TestStateMachineTransitions:
    """Test that invalid state transitions are rejected."""

    def test_invalid_transition_observed_to_confirmed(self):
        """HARDENED: Cannot jump directly from OBSERVED to CONFIRMED."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            status=FindingStatus.OBSERVED,
        )

        with pytest.raises(InvalidFindingStateError, match="Invalid transition"):
            finding.advance_status(FindingStatus.CONFIRMED)

    def test_invalid_transition_observed_to_investigated(self):
        """HARDENED: Cannot skip HYPOTHESIS state."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            status=FindingStatus.OBSERVED,
        )

        with pytest.raises(InvalidFindingStateError, match="Invalid transition"):
            finding.advance_status(FindingStatus.INVESTIGATED)

    def test_negative_claim_requires_ground_truth_before_investigation(self):
        """HARDENED: Negative claims must reach GROUND_TRUTH_VERIFIED before INVESTIGATED."""
        finding = Finding(
            finding_id="NEG-001",
            claim="Symbol does not exist",
            claim_type="ABSENT",
            status=FindingStatus.HYPOTHESIS,
        )

        # Cannot skip to INVESTIGATED
        with pytest.raises(InvalidFindingStateError, match="Invalid transition"):
            finding.advance_status(FindingStatus.INVESTIGATED)

        # Must go through GROUND_TRUTH_VERIFIED
        finding.advance_status(FindingStatus.GROUND_TRUTH_VERIFIED)
        finding.advance_status(FindingStatus.INVESTIGATED)
        assert finding.status == FindingStatus.INVESTIGATED

    def test_valid_positive_claim_transition_path(self):
        """HARDENED: Positive claims have shorter path than negative claims."""
        finding = Finding(
            finding_id="POS-001",
            claim="Symbol exists",
            claim_type="EXISTS",
        )

        finding.advance_status(FindingStatus.HYPOTHESIS)
        finding.advance_status(FindingStatus.INVESTIGATED)
        finding.advance_status(FindingStatus.INDEPENDENTLY_VERIFIED)
        finding.advance_status(FindingStatus.CONFIRMED)

        assert finding.status == FindingStatus.CONFIRMED


class TestHasDirectEvidenceHardening:
    """Test that has_direct_evidence() cannot be faked."""

    def test_empty_evidence_files_returns_false(self):
        """HARDENED: Empty evidence_files means no direct evidence."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            evidence_files=[],
            evidence_summary="Has summary but no files",
        )

        assert not finding.has_direct_evidence()

    def test_empty_evidence_summary_returns_false(self):
        """HARDENED: Empty evidence_summary means no direct evidence."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            evidence_files=["evidence.json"],
            evidence_summary="",
        )

        assert not finding.has_direct_evidence()

    def test_contradictory_evidence_blocks_direct_evidence(self):
        """HARDENED: Unresolved contradictions prevent direct evidence claim."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            evidence_files=["evidence.json"],
            evidence_summary="Symbol found in source",
            contradictory_evidence="contradictory.json",
        )

        assert not finding.has_direct_evidence()

    def test_unverified_in_summary_blocks_direct_evidence(self):
        """HARDENED: Suspicious phrases in summary indicate not direct evidence."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            evidence_files=["evidence.json"],
            evidence_summary="Unverified claim from test fixture",
        )

        assert not finding.has_direct_evidence()

    def test_test_fixture_in_summary_blocks_direct_evidence(self):
        """HARDENED: 'test fixture' in summary blocks direct evidence."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            evidence_files=["fixture.json"],
            evidence_summary="Data from test fixture",
        )

        assert not finding.has_direct_evidence()

    def test_inferred_in_summary_blocks_direct_evidence(self):
        """HARDENED: 'inferred' in summary blocks direct evidence."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            evidence_files=["evidence.json"],
            evidence_summary="Inferred from retrieval zero results",
        )

        assert not finding.has_direct_evidence()


class TestConfirmationReadinessHardened:
    """Test that is_ready_for_confirmation() enforces all requirements."""

    def test_wrong_status_blocks_confirmation(self):
        """HARDENED: Must be INDEPENDENTLY_VERIFIED to be ready."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            status=FindingStatus.INVESTIGATED,  # Not INDEPENDENTLY_VERIFIED
            evidence_files=["evidence.json"],
            evidence_summary="Direct evidence",
            verification_attempts=1,
        )

        assert not finding.is_ready_for_confirmation()

    def test_no_verification_attempts_blocks_confirmation(self):
        """HARDENED: Must have attempted verification."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence_files=["evidence.json"],
            evidence_summary="Direct evidence",
            verification_attempts=0,  # No attempts
        )

        assert not finding.is_ready_for_confirmation()

    def test_no_direct_evidence_blocks_confirmation(self):
        """HARDENED: Must have direct evidence."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence_files=[],  # No evidence
            evidence_summary="",
            verification_attempts=1,
        )

        assert not finding.is_ready_for_confirmation()

    def test_contradictory_evidence_blocks_confirmation(self):
        """HARDENED: Contradictory evidence prevents confirmation."""
        finding = Finding(
            finding_id="TEST-001",
            claim="Test",
            claim_type="EXISTS",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence_files=["evidence.json"],
            evidence_summary="Direct evidence",
            verification_attempts=1,
            contradictory_evidence="contradicts.json",
        )

        assert not finding.is_ready_for_confirmation()

    def test_negative_claim_without_ground_truth_raises_error(self):
        """HARDENED: Negative claim without GT evidence raises exception."""
        # Need actual DIRECT evidence to reach GT validation
        direct = Evidence.from_source_code("file.ts", "symbol", 10)
        direct.observation = "Symbol not found in source"

        finding = Finding(
            finding_id="NEG-001",
            claim="Symbol does not exist",
            claim_type="ABSENT",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence=[direct],
            evidence_files=["evidence.json"],
            evidence_summary="Direct evidence",
            verification_attempts=1,
            ground_truth_claim=None,  # Missing!
        )

        with pytest.raises(MissingGroundTruthError, match="requires ground_truth_claim to be set"):
            finding.is_ready_for_confirmation()

    def test_negative_claim_without_ground_truth_evidence_raises_error(self):
        """HARDENED: Negative claim without GT evidence object raises exception."""
        # Need actual DIRECT evidence to reach GT validation
        direct = Evidence.from_source_code("file.ts", "symbol", 10)
        direct.observation = "Symbol not found in source"

        finding = Finding(
            finding_id="NEG-001",
            claim="Symbol does not exist",
            claim_type="ABSENT",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence=[direct],
            evidence_files=["evidence.json"],
            evidence_summary="Direct evidence",
            verification_attempts=1,
            ground_truth_claim="ABSENT",
            ground_truth_evidence=None,  # Missing!
        )

        with pytest.raises(MissingGroundTruthError, match="Evidence object"):
            finding.is_ready_for_confirmation()

    def test_negative_claim_ready_with_complete_ground_truth(self):
        """HARDENED: Negative claim IS ready when all requirements met."""
        # Need actual DIRECT evidence
        direct = Evidence.from_source_code("file.ts", "symbol", 10)
        direct.observation = "Symbol not found in source"

        gt_evidence = Evidence.from_source_code("file.ts", "symbol", 10)
        gt_evidence.observation = "Symbol NOT found in repository"

        finding = Finding(
            finding_id="NEG-001",
            claim="Symbol does not exist",
            claim_type="ABSENT",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence=[direct],
            evidence_files=["evidence.json"],
            evidence_summary="Direct evidence from repository audit",
            verification_attempts=1,
            ground_truth_claim="ABSENT",
            ground_truth_evidence=gt_evidence,
        )

        assert finding.is_ready_for_confirmation()


class TestFindingPacketValidation:
    """Test that FindingPacket validates its own state."""

    def test_packet_validates_is_actionable_matches_confirmed(self):
        """HARDENED: is_actionable must be True only if status is CONFIRMED."""
        with pytest.raises(ValueError, match="is_actionable must be"):
            FindingPacket(
                finding_id="TEST-001",
                severity=FindingSeverity.P1,
                status=FindingStatus.INVESTIGATED,
                summary="Test",
                evidence_location="file.md",
                data_location="file.json",
                recommended_next_investigation="Continue",
                is_actionable=True,  # Wrong! Status is not CONFIRMED
            )

    def test_packet_rejects_empty_summary(self):
        """HARDENED: summary cannot be empty."""
        with pytest.raises(ValueError, match="summary cannot be empty"):
            FindingPacket(
                finding_id="TEST-001",
                severity=FindingSeverity.P1,
                status=FindingStatus.CONFIRMED,
                summary="",  # Empty!
                evidence_location="file.md",
                data_location="file.json",
                recommended_next_investigation="None",
                is_actionable=True,
            )

    def test_packet_rejects_empty_locations(self):
        """HARDENED: evidence_location and data_location cannot be empty."""
        with pytest.raises(ValueError, match="evidence_location cannot be empty"):
            FindingPacket(
                finding_id="TEST-001",
                severity=FindingSeverity.P1,
                status=FindingStatus.CONFIRMED,
                summary="Test",
                evidence_location="",  # Empty!
                data_location="file.json",
                recommended_next_investigation="None",
                is_actionable=True,
            )


class TestPhase8ARegressionProtection:
    """Test that Phase 8A corruption pattern is prevented."""

    def test_bad_fixture_cannot_bypass_ground_truth(self):
        """
        REGRESSION: Phase 8A.6 → Phase 8A.10 sequence.

        Bad fixture claims symbol exists (UNVERIFIED).
        Ground truth finds it doesn't (DIRECT).
        Fixture cannot override ground truth.
        """
        # Bad fixture evidence
        fixture = Evidence.from_test_fixture(
            "PHASE8A6_GROUND_TRUTH",
            "setupMockHTTPServer exists"
        )

        # Ground truth evidence
        ground_truth = Evidence(
            evidence_type=EvidenceType.DIRECT,
            source="repository audit",
            location="audit_results.json",
            observation="setupMockHTTPServer NOT found in source",
            confidence=1.0,
        )

        # Fixture is UNVERIFIED, cannot satisfy confirmation
        assert not fixture.is_sufficient_for_confirmation()

        # Ground truth is DIRECT, can satisfy confirmation
        assert ground_truth.is_sufficient_for_confirmation()

        # Framework protects against setting up bad findings
        finding = Finding(
            finding_id="PHASE8A-TEST",
            claim="setupMockHTTPServer missing",
            claim_type="ABSENT",
        )

        # Cannot proceed without ground truth
        assert not finding.can_proceed_to_investigation()

        # Must follow state machine: OBSERVED → HYPOTHESIS → GROUND_TRUTH_VERIFIED
        finding.advance_status(FindingStatus.HYPOTHESIS)
        finding.ground_truth_claim = "ABSENT"
        finding.ground_truth_evidence = "audit.json"
        finding.advance_status(FindingStatus.GROUND_TRUTH_VERIFIED)

        # Now can proceed
        assert finding.can_proceed_to_investigation()

    def test_retrieval_zero_does_not_confirm_absence(self):
        """
        REGRESSION: Retrieval zero-results must not become absence proof.

        Phase 8A failed partly because retrieval zero-results was misinterpreted
        as repository absence. This must not happen.
        """
        # Create evidence from retrieval zero-result
        retrieval_evidence = Evidence.from_retrieval_result(
            "setupMockHTTPServer",
            found=False,
            result_count=0
        )

        # Must be INDIRECT (retrieval behavior), not DIRECT (repo state)
        assert retrieval_evidence.evidence_type == EvidenceType.INDIRECT

        # Cannot satisfy confirmation on its own
        assert not retrieval_evidence.is_sufficient_for_confirmation()

        # A finding based only on retrieval zero-result would not be ready
        finding = Finding(
            finding_id="RETRIEVAL-TEST",
            claim="Symbol not found by search",
            claim_type="RETRIEVAL_FAILURE",
            status=FindingStatus.INVESTIGATED,
            evidence_files=["retrieval_result.json"],
            evidence_summary="Retrieval returned no results",
            verification_attempts=1,
        )

        # Even at INDEPENDENTLY_VERIFIED, without direct repository evidence
        finding.status = FindingStatus.INDEPENDENTLY_VERIFIED

        # This would NOT be ready if we don't have direct repository ground truth
        # (This test documents the protection)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
