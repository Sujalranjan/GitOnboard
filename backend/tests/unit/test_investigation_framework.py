"""
Tests for the Multi-Agent Investigation Framework.

Tests cover:
- Finding schema and state machine
- Evidence classification
- Ground-truth validation
- Phase 8A corruption detection
"""

import pytest
from datetime import datetime
from backend.investigation.finding import (
    Finding,
    FindingStatus,
    FindingSeverity,
    FindingPacket,
    MissingGroundTruthError,
)
from backend.investigation.evidence import (
    Evidence,
    EvidenceType,
)


class TestFindingSchema:
    """Test Finding dataclass and state machine."""

    def test_finding_creation(self):
        """Test basic finding creation."""
        finding = Finding(
            finding_id="RETRIEVAL-001",
            claim="Class symbols are not searchable",
            claim_type="RETRIEVAL_FAILURE",
        )

        assert finding.finding_id == "RETRIEVAL-001"
        assert finding.claim == "Class symbols are not searchable"
        assert finding.status == FindingStatus.OBSERVED
        assert finding.severity == FindingSeverity.P1

    def test_finding_status_transitions(self):
        """Test valid state machine transitions."""
        finding = Finding(
            finding_id="PARSER-001",
            claim="Parser does not extract functions",
            claim_type="PARSER_FAILURE",
        )

        # OBSERVED -> HYPOTHESIS
        finding.advance_status(FindingStatus.HYPOTHESIS)
        assert finding.status == FindingStatus.HYPOTHESIS

        # HYPOTHESIS -> GROUND_TRUTH_VERIFIED (for negative claim)
        finding.claim_type = "ABSENT"
        finding.advance_status(FindingStatus.GROUND_TRUTH_VERIFIED)
        assert finding.status == FindingStatus.GROUND_TRUTH_VERIFIED

        # -> INVESTIGATED
        finding.advance_status(FindingStatus.INVESTIGATED)
        assert finding.status == FindingStatus.INVESTIGATED

    def test_finding_severity_levels(self):
        """Test all severity levels."""
        for severity in [FindingSeverity.P0, FindingSeverity.P1, FindingSeverity.P2]:
            finding = Finding(
                finding_id="TEST-001",
                claim="Test",
                claim_type="EXISTS",
                severity=severity,
            )
            assert finding.severity == severity

    def test_finding_can_proceed_to_investigation(self):
        """Test gating on can_proceed_to_investigation."""
        # Positive claim (EXISTS) can proceed from HYPOTHESIS
        finding = Finding(
            finding_id="POS-001",
            claim="Symbol exists",
            claim_type="EXISTS",
            status=FindingStatus.HYPOTHESIS,
        )
        assert finding.can_proceed_to_investigation()

        # Negative claim (ABSENT) cannot proceed from HYPOTHESIS
        finding_neg = Finding(
            finding_id="NEG-001",
            claim="Symbol does not exist",
            claim_type="ABSENT",
            status=FindingStatus.HYPOTHESIS,
        )
        assert not finding_neg.can_proceed_to_investigation()

        # Negative claim CAN proceed from GROUND_TRUTH_VERIFIED
        finding_neg.advance_status(FindingStatus.GROUND_TRUTH_VERIFIED)
        assert finding_neg.can_proceed_to_investigation()

    def test_finding_has_direct_evidence(self):
        """Test has_direct_evidence check."""
        finding = Finding(
            finding_id="EV-001",
            claim="Test claim",
            claim_type="EXISTS",
        )

        assert not finding.has_direct_evidence()

        # Metadata alone is not sufficient
        finding.evidence_files = ["evidence.json"]
        assert not finding.has_direct_evidence()

        finding.evidence_summary = "Found in parser output"
        assert not finding.has_direct_evidence()  # Still needs actual Evidence object

        # Add actual DIRECT evidence
        direct_evidence = Evidence.from_parser_output("output.json", extracted=True)
        finding.evidence = [direct_evidence]
        assert finding.has_direct_evidence()

    def test_finding_is_ready_for_confirmation(self):
        """Test is_ready_for_confirmation gating."""
        direct_evidence = Evidence.from_parser_output("output.json", extracted=True)

        finding = Finding(
            finding_id="CONF-001",
            claim="Test claim",
            claim_type="EXISTS",
            status=FindingStatus.INDEPENDENTLY_VERIFIED,
            evidence=[direct_evidence],
            evidence_files=["evidence.json"],
            evidence_summary="Test evidence",
            verification_attempts=1,
        )

        assert finding.is_ready_for_confirmation()

        # Negative claim requires ground truth - raises exception if missing
        finding.claim_type = "ABSENT"
        with pytest.raises(MissingGroundTruthError):
            finding.is_ready_for_confirmation()

        gt_evidence = Evidence.from_source_code("file.ts", "Symbol", 42)
        gt_evidence.observation = "Symbol NOT found in source"
        finding.ground_truth_claim = "ABSENT"
        finding.ground_truth_evidence = gt_evidence
        assert finding.is_ready_for_confirmation()

    def test_finding_last_updated_changes(self):
        """Test that last_updated changes with status transitions."""
        finding = Finding(
            finding_id="TIME-001",
            claim="Test",
            claim_type="EXISTS",
        )

        time1 = finding.last_updated
        finding.advance_status(FindingStatus.HYPOTHESIS)
        time2 = finding.last_updated

        assert time2 >= time1


class TestEvidenceClassification:
    """Test Evidence schema and classification."""

    def test_evidence_direct(self):
        """Test DIRECT evidence creation."""
        evidence = Evidence(
            evidence_type=EvidenceType.DIRECT,
            source="source code",
            location="src/file.ts:42",
            observation="Function resetModal found",
            confidence=0.95,
        )

        assert evidence.evidence_type == EvidenceType.DIRECT
        assert "resetModal found" in evidence.observation

        # Retrieval result should be INDIRECT, not DIRECT
        evidence_found = Evidence.from_retrieval_result(
            "resetModal",
            found=True,
            result_count=1
        )
        assert evidence_found.evidence_type == EvidenceType.INDIRECT  # Retrieval behavior, not repository state
        assert "1 results" in evidence_found.observation

        evidence_not_found = Evidence.from_retrieval_result(
            "nonExistent",
            found=False,
            result_count=0
        )
        assert evidence_not_found.evidence_type == EvidenceType.INDIRECT
        assert "no results" in evidence_not_found.observation

    def test_evidence_from_test_fixture(self):
        """Test factory for unverified fixture evidence."""
        evidence = Evidence.from_test_fixture(
            "PHASE8A6_GROUND_TRUTH",
            "Symbol 'setupMockHTTPServer' exists"
        )

        assert evidence.evidence_type == EvidenceType.UNVERIFIED
        assert evidence.source == "test fixture"
        assert evidence.confidence == 0.3

    def test_evidence_from_agent_report(self):
        """Test factory for agent report evidence."""
        evidence = Evidence.from_agent_report(
            "Agent A",
            "Found symbol in source",
            confidence_hint=0.5
        )

        assert evidence.evidence_type == EvidenceType.UNVERIFIED
        assert "Agent A" in evidence.location
        assert evidence.confidence == 0.5

    def test_evidence_string_representation(self):
        """Test evidence string formatting."""
        evidence = Evidence(
            evidence_type=EvidenceType.DIRECT,
            source="parser",
            location="output.json",
            observation="Symbol extracted",
            confidence=0.95,
        )

        str_repr = str(evidence)
        assert "DIRECT" in str_repr
        assert "parser" in str_repr
        assert "95%" in str_repr


class TestPhase8AProtection:
    """Test protection against Phase 8A corruption (bad test fixtures)."""

    def test_negative_claim_blocks_without_ground_truth(self):
        """Test that ABSENT/MISSING claims are blocked without GT verification."""
        finding = Finding(
            finding_id="PHASE8A-TEST-001",
            claim="setupMockHTTPServer does not exist",
            claim_type="ABSENT",
            status=FindingStatus.HYPOTHESIS,
        )

        # Cannot proceed without ground truth verification
        assert not finding.can_proceed_to_investigation()

        # Mark as ground truth verified
        finding.ground_truth_claim = "ABSENT"
        finding.advance_status(FindingStatus.GROUND_TRUTH_VERIFIED)

        # Now can proceed
        assert finding.can_proceed_to_investigation()

    def test_fabricated_fixture_detection(self):
        """
        Test that fabricated test fixtures are marked UNVERIFIED
        and blocked from being treated as facts.
        """
        # This simulates Phase 8A.6's bad ground truth
        fixture_evidence = Evidence.from_test_fixture(
            "PHASE8A6_GROUND_TRUTH",
            "setupMockHTTPServer exists",
        )

        # Should be UNVERIFIED, not DIRECT
        assert fixture_evidence.evidence_type == EvidenceType.UNVERIFIED
        assert fixture_evidence.confidence == 0.3

        # Should NOT be sufficient for confirmation
        assert not fixture_evidence.is_sufficient_for_confirmation()

    def test_unverified_evidence_blocks_diagnosis(self):
        """
        Test that diagnostic findings based only on UNVERIFIED evidence
        cannot reach CONFIRMED state.
        """
        finding = Finding(
            finding_id="DIAG-001",
            claim="Parser is the bottleneck",
            claim_type="PARSER_FAILURE",
            status=FindingStatus.INVESTIGATED,
            evidence_files=["phase8a6_results.json"],  # This was the ONLY evidence
            evidence_summary="Phase 8A.6 reported 50% false-negative rate",
        )

        # Create evidence representing Phase 8A.6's claim
        bad_evidence = Evidence.from_test_fixture(
            "PHASE8A6_RETRIEVAL_ADEQUACY",
            "Retrieval false-negative rate: 50%"
        )

        # This evidence is UNVERIFIED
        assert bad_evidence.evidence_type == EvidenceType.UNVERIFIED

        # Finding cannot be confirmed with only UNVERIFIED evidence
        # (This would be enforced in orchestrator)
        assert not bad_evidence.is_sufficient_for_confirmation()

    def test_ground_truth_overrides_fixture_claim(self):
        """
        Test that ground-truth verification overrides test fixture claims.

        Simulates Phase 8A.10 audit that found setupMockHTTPServer doesn't exist.
        """
        # Initial claim from test fixture
        fixture_evidence = Evidence.from_test_fixture(
            "PHASE8A6_GROUND_TRUTH",
            "setupMockHTTPServer exists"
        )

        # But actual ground truth verification finds it doesn't exist
        ground_truth_evidence = Evidence.from_source_code(
            "Deep-Guard-Frontend",
            "setupMockHTTPServer",
            0
        )
        ground_truth_evidence.observation = "Symbol NOT found in repository source"

        # The ground truth (DIRECT) evidence overrides fixture (UNVERIFIED)
        assert ground_truth_evidence.evidence_type == EvidenceType.DIRECT
        assert fixture_evidence.evidence_type == EvidenceType.UNVERIFIED
        assert ground_truth_evidence.is_sufficient_for_confirmation()


class TestFindingPacket:
    """Test context-minimized finding transmission."""

    def test_finding_packet_creation(self):
        """Test FindingPacket for main agent."""
        packet = FindingPacket(
            finding_id="PACKET-001",
            severity=FindingSeverity.P0,
            status=FindingStatus.CONFIRMED,
            summary="Parser successfully extracts React components despite ES6 export gap.",
            evidence_location="investigations/findings/PACKET-001.md",
            data_location="investigations/findings/PACKET-001.json",
            recommended_next_investigation="None; parser is not the bottleneck.",
            is_actionable=True,
        )

        assert packet.finding_id == "PACKET-001"
        assert packet.is_actionable
        assert packet.severity == FindingSeverity.P0

    def test_finding_packet_context_string(self):
        """Test context string for main agent (should be compact)."""
        packet = FindingPacket(
            finding_id="DEMO-001",
            severity=FindingSeverity.P1,
            status=FindingStatus.CONFIRMED,
            summary="Test finding summary.",
            evidence_location="findings/DEMO-001.md",
            data_location="findings/DEMO-001.json",
            recommended_next_investigation="Do not fix parser",
            is_actionable=True,
        )

        context = packet.to_context_string()

        # Should be compact
        assert len(context) < 500
        assert "✓" in context  # Confirmed status symbol
        assert "DEMO-001" in context
        assert "[P1]" in context

    def test_finding_packet_unconfirmed_symbol(self):
        """Test packet for unconfirmed finding."""
        packet = FindingPacket(
            finding_id="UNCERTAIN-001",
            severity=FindingSeverity.P1,
            status=FindingStatus.INVESTIGATED,
            summary="Possible issue; verification pending.",
            evidence_location="findings/UNCERTAIN-001.md",
            data_location="findings/UNCERTAIN-001.json",
            recommended_next_investigation="Run verification agent",
            is_actionable=False,
        )

        context = packet.to_context_string()
        assert "⚠" in context  # Unconfirmed symbol
        assert not packet.is_actionable


class TestInvestigationState:
    """Test full investigation state tracking."""

    def test_investigation_lifecycle_positive_claim(self):
        """Test full lifecycle for positive claim (simpler path)."""
        finding = Finding(
            finding_id="LIFECYCLE-POS-001",
            claim="ForgotPasswordModal is extracted by parser",
            claim_type="EXISTS",
        )

        # Start at OBSERVED
        assert finding.status == FindingStatus.OBSERVED

        # Hypothesis
        finding.advance_status(FindingStatus.HYPOTHESIS)
        assert finding.status == FindingStatus.HYPOTHESIS

        # Can proceed (positive claim)
        assert finding.can_proceed_to_investigation()

        # Scout investigates
        finding.advance_status(FindingStatus.INVESTIGATED)
        finding.evidence_files = ["parser_output.json"]
        finding.evidence_summary = "Parser extracted ForgotPasswordModal"

        # Verification agent tests
        finding.advance_status(FindingStatus.INDEPENDENTLY_VERIFIED)
        finding.verification_attempts += 1

        # Add actual DIRECT evidence
        direct_evidence = Evidence.from_parser_output("parser_output.json", extracted=True)
        finding.evidence = [direct_evidence]

        # Ready for confirmation
        assert finding.is_ready_for_confirmation()

        # Mark confirmed
        finding.advance_status(FindingStatus.CONFIRMED)
        assert finding.status == FindingStatus.CONFIRMED

    def test_investigation_lifecycle_negative_claim(self):
        """Test full lifecycle for negative claim (stricter path)."""
        finding = Finding(
            finding_id="LIFECYCLE-NEG-001",
            claim="setupMockHTTPServer does not exist",
            claim_type="ABSENT",
        )

        # Hypothesis state
        finding.advance_status(FindingStatus.HYPOTHESIS)

        # Cannot proceed without GT verification
        assert not finding.can_proceed_to_investigation()

        # GT validation required
        gt_evidence = Evidence.from_source_code("server.ts", "setupMockHTTPServer", 42)
        gt_evidence.observation = "setupMockHTTPServer NOT found in source"
        finding.ground_truth_claim = "ABSENT"
        finding.ground_truth_evidence = gt_evidence
        finding.advance_status(FindingStatus.GROUND_TRUTH_VERIFIED)

        # Now can proceed
        assert finding.can_proceed_to_investigation()

        # Investigation proceeds
        finding.advance_status(FindingStatus.INVESTIGATED)
        finding.evidence_files = ["audit_results.json"]
        finding.evidence_summary = "No matches in source code"

        # Verification
        finding.advance_status(FindingStatus.INDEPENDENTLY_VERIFIED)
        finding.verification_attempts += 1

        # Add actual DIRECT evidence
        direct_evidence = Evidence.from_source_code("server.ts", "setupMockHTTPServer")
        direct_evidence.observation = "setupMockHTTPServer not found"
        finding.evidence = [direct_evidence]

        # Ready and confirmed
        finding.advance_status(FindingStatus.CONFIRMED)
        assert finding.status == FindingStatus.CONFIRMED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
