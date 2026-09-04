"""
Stage 1 Final Hardening: Evidence Integrity Tests

Proves that metadata-only bypasses cannot produce confirmation-ready findings.
"""

import pytest
from backend.investigation.finding import Finding, FindingStatus, MissingGroundTruthError
from backend.investigation.evidence import Evidence, EvidenceType


class TestMetadataBypassPrevention:
    """Adversarial tests proving metadata cannot fake evidence."""

    def test_fake_evidence_filename_alone_fails(self):
        """HARDENED: Just having evidence_files doesn't satisfy has_direct_evidence."""
        finding = Finding(
            finding_id="FAKE-001",
            claim="Test",
            claim_type="EXISTS",
            evidence_files=["fake_evidence.json"],
            evidence_summary="Direct evidence confirms issue",
        )

        # No actual Evidence objects → not direct evidence
        assert not finding.has_direct_evidence()
        assert not finding.is_ready_for_confirmation()

    def test_fake_ground_truth_path_fails(self):
        """HARDENED: String path is not sufficient ground truth."""
        finding = Finding(
            finding_id="FAKE-GT-001",
            claim="Symbol does not exist",
            claim_type="ABSENT",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            ground_truth_claim="ABSENT",
            ground_truth_evidence=None,  # No actual Evidence object!
            evidence=[Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="fake",
                location="fake.json",
                observation="Fake evidence",
                confidence=0.95,
            )],
            verification_attempts=1,
        )

        # Raises exception because ground_truth_evidence is None
        with pytest.raises(MissingGroundTruthError, match="Evidence object"):
            finding.is_ready_for_confirmation()

    def test_unverified_evidence_rejected(self):
        """HARDENED: UNVERIFIED evidence doesn't satisfy has_direct_evidence."""
        unverified = Evidence.from_test_fixture("fixture", "claim")

        finding = Finding(
            finding_id="UNVERIFIED-001",
            claim="Test",
            claim_type="EXISTS",
            evidence=[unverified],
            evidence_files=["fixture.json"],
            evidence_summary="Evidence from test fixture",
        )

        # Even with evidence object, UNVERIFIED doesn't count
        assert not finding.has_direct_evidence()

    def test_indirect_evidence_rejected(self):
        """HARDENED: INDIRECT (retrieval) evidence doesn't satisfy has_direct_evidence."""
        retrieval = Evidence.from_retrieval_result("symbol", found=False, result_count=0)

        finding = Finding(
            finding_id="INDIRECT-001",
            claim="Symbol not found",
            claim_type="RETRIEVAL_FAILURE",
            evidence=[retrieval],
            evidence_files=["retrieval.json"],
            evidence_summary="Search returned no results",
        )

        # INDIRECT evidence cannot satisfy confirmation
        assert not finding.has_direct_evidence()

    def test_phase8a_corruption_prevented(self):
        """HARDENED: Bad fixture + retrieval zero + fake GT path cannot bypass."""
        # Simulate Phase 8A corruption attempt
        fixture = Evidence.from_test_fixture("PHASE8A6", "setupMockHTTPServer exists")
        retrieval = Evidence.from_retrieval_result("setupMockHTTPServer", found=False)

        finding = Finding(
            finding_id="PHASE8A-ATTEMPT",
            claim="setupMockHTTPServer missing",
            claim_type="ABSENT",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence=[fixture, retrieval],
            evidence_files=["phase8a6_fixture.json", "retrieval.json"],
            evidence_summary="Fixture claim + retrieval zero-result",
            ground_truth_claim="ABSENT",
            ground_truth_evidence=None,  # NO ACTUAL EVIDENCE
            verification_attempts=1,
        )

        # Cannot proceed: fixture is UNVERIFIED and retrieval is INDIRECT, no DIRECT evidence
        assert not finding.is_ready_for_confirmation()

        # Now try with a fake DIRECT evidence instead of actual evidence
        fake_direct = Evidence(
            evidence_type=EvidenceType.DIRECT,
            source="fake audit",
            location="fake.json",
            observation="Fake observation",
            confidence=1.0,
        )

        finding_with_fake = Finding(
            finding_id="PHASE8A-ATTEMPT-2",
            claim="setupMockHTTPServer missing",
            claim_type="ABSENT",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence=[fake_direct],
            ground_truth_claim="ABSENT",
            ground_truth_evidence=None,  # STILL NO ACTUAL GT EVIDENCE
            verification_attempts=1,
        )

        # Raises exception because ground_truth_evidence is None despite having direct evidence
        with pytest.raises(MissingGroundTruthError, match="Evidence object"):
            finding_with_fake.is_ready_for_confirmation()

    def test_valid_direct_evidence_succeeds(self):
        """HARDENED: Properly constructed findings with DIRECT evidence are ready."""
        direct = Evidence(
            evidence_type=EvidenceType.DIRECT,
            source="repository audit",
            location="audit_results.json",
            observation="Symbol NOT found in source",
            confidence=1.0,
        )

        finding = Finding(
            finding_id="VALID-GT-001",
            claim="Symbol does not exist",
            claim_type="ABSENT",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence=[direct],
            evidence_files=["audit.json"],
            evidence_summary="Confirmed absent from repository",
            ground_truth_claim="ABSENT",
            ground_truth_evidence=direct,
            verification_attempts=1,
        )

        # Properly constructed finding IS ready
        assert finding.has_direct_evidence()
        assert finding.is_ready_for_confirmation()

    def test_direct_evidence_with_low_confidence_rejected(self):
        """HARDENED: DIRECT evidence with low confidence is rejected at creation."""
        from backend.investigation.evidence import InvalidEvidenceError

        # Cannot create DIRECT evidence with low confidence
        with pytest.raises(InvalidEvidenceError, match="confidence >= 0.9"):
            Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="source code",
                location="file.ts",
                observation="Found",
                confidence=0.85,  # Below 0.9 threshold
            )

    def test_contradiction_blocks_even_with_direct_evidence(self):
        """HARDENED: Unresolved contradictions block confirmation."""
        direct = Evidence(
            evidence_type=EvidenceType.DIRECT,
            source="audit",
            location="audit.json",
            observation="Not found",
            confidence=1.0,
        )

        finding = Finding(
            finding_id="CONTRA-001",
            claim="Test",
            claim_type="EXISTS",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence=[direct],
            contradictory_evidence="contradicts.json",
            verification_attempts=1,
        )

        # Even with good evidence, contradiction blocks
        assert not finding.has_direct_evidence()
        assert not finding.is_ready_for_confirmation()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
