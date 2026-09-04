"""
Verification Agent for Investigation Framework.

Independently verifies Scout hypotheses against repository evidence.
Verification is skeptical and cannot be bypassed.

Verification must NOT simply agree with Scout.
Verification must independently inspect the repository.
"""

from dataclasses import dataclass
from typing import Optional
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.query_layer import QueryLayer
from backend.investigation.finding import (
    Finding,
    FindingStatus,
    MissingGroundTruthError,
    InvalidFindingStateError,
)
from backend.investigation.evidence import Evidence, EvidenceType
from backend.investigation.ground_truth import (
    GroundTruthValidator,
    VerificationStatus,
)
from backend.investigation.scout import ScoutHypothesis


@dataclass
class VerificationContext:
    """
    Minimal context for verification.

    Contains only what the verifier needs to independently check the claim.
    Artifact locations are for navigation, not proof.
    """

    hypothesis: ScoutHypothesis
    """Scout's hypothesis to verify."""

    repository_model: RepositoryModel
    """Repository to inspect."""

    max_verification_attempts: int = 2
    """Maximum verification passes (Scout + one additional investigation)."""


@dataclass
class VerificationResult:
    """Result of independent verification."""

    finding: Finding
    """Finding with updated status and evidence."""

    verdict: str
    """CONFIRMED, REFUTED, or UNRESOLVED."""

    reasoning: str
    """Why verification reached this conclusion."""

    verification_evidence: Optional[Evidence] = None
    """Direct evidence from independent verification."""


class VerificationAgent:
    """
    Verification Agent: Independently validates Scout hypotheses.

    Verification must:
    1. Not trust Scout's conclusion
    2. Independently inspect repository
    3. Use GroundTruthValidator for ground truth
    4. Distinguish CONFIRMED / REFUTED / UNRESOLVED
    5. Be bounded in search attempts
    """

    def __init__(self, repository_model: RepositoryModel):
        """
        Initialize Verification Agent.

        Args:
            repository_model: RIM for independent inspection
        """
        self.model = repository_model
        self.query = QueryLayer(repository_model)
        self.validator = GroundTruthValidator(repository_model)

    def verify(self, context: VerificationContext) -> VerificationResult:
        """
        Independently verify a Scout hypothesis.

        Verification process:
        1. Parse the Scout claim
        2. Independently inspect repository
        3. Use GroundTruthValidator for ground-truth claims
        4. Attempt bounded second investigation if needed
        5. Return CONFIRMED / REFUTED / UNRESOLVED

        Args:
            context: VerificationContext with hypothesis and repository

        Returns:
            VerificationResult with updated Finding and verdict
        """
        finding = context.hypothesis.to_finding()

        # Determine claim type and perform appropriate verification
        if context.hypothesis.claim_type == "EXISTS":
            return self._verify_existence(finding, context)
        elif context.hypothesis.claim_type == "ABSENT":
            return self._verify_absence(finding, context)
        else:
            return self._verify_functional(finding, context)

    def _verify_existence(
        self, finding: Finding, context: VerificationContext
    ) -> VerificationResult:
        """
        Verify positive existence claim independently.

        Scout said something exists. Verifier independently checks repository.
        """
        # Extract what Scout is claiming exists
        claim = finding.claim

        # Try to extract symbol name from claim (handles quoted and unquoted)
        target_symbol = None
        if "'" in claim:
            parts = claim.split("'")
            if len(parts) >= 2:
                target_symbol = parts[1]
        else:
            # Fallback: use Scout's hypothesis claim
            target_symbol = context.hypothesis.claim.split()[0] if context.hypothesis.claim else None

        if not target_symbol:
            finding.status = FindingStatus.UNRESOLVED
            return VerificationResult(
                finding=finding,
                verdict="UNRESOLVED",
                reasoning="Could not parse symbol name from claim",
                verification_evidence=None,
            )

        # First pass: independent repository inspection using GroundTruthValidator
        for entity_id, entity in self.model.entities.items():
            if entity.name.lower() == target_symbol.lower():
                # Found matching entity - verify independently
                gt_result = self.validator.validate_symbol_exists(entity.name)

                if gt_result.status == VerificationStatus.VERIFIED_PRESENT:
                    finding.evidence = [gt_result.evidence]
                    finding.ground_truth_evidence = gt_result.evidence
                    finding.ground_truth_claim = "EXISTS"
                    finding.status = FindingStatus.INDEPENDENTLY_VERIFIED
                    finding.verification_attempts = 1

                    return VerificationResult(
                        finding=finding,
                        verdict="CONFIRMED",
                        reasoning=f"Independently verified that {entity.name} exists in repository",
                        verification_evidence=gt_result.evidence,
                    )

        # Second pass: targeted search if first pass inconclusive
        if not target_symbol:
            finding.status = FindingStatus.UNRESOLVED
            finding.verification_attempts = 2
            return VerificationResult(
                finding=finding,
                verdict="UNRESOLVED",
                reasoning="Could not extract symbol name for second verification pass",
                verification_evidence=None,
            )

        functions = self.query.find_function(target_symbol)
        if functions:
            func = functions[0]
            direct_evidence = Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="independent verification - source code",
                location=f"{func.location.repository_path}:{func.location.start_line}",
                observation=f"Independent verification found function '{target_symbol}'",
                confidence=0.95,
                context="Direct source code inspection by verifier",
            )

            finding.evidence = [direct_evidence]
            finding.ground_truth_evidence = direct_evidence
            finding.ground_truth_claim = "EXISTS"
            finding.status = FindingStatus.INDEPENDENTLY_VERIFIED
            finding.verification_attempts = 2

            return VerificationResult(
                finding=finding,
                verdict="CONFIRMED",
                reasoning=f"Second verification pass confirmed {target_symbol} exists",
                verification_evidence=direct_evidence,
            )

        classes = self.query.get_class(target_symbol)
        if classes:
            cls = classes[0]
            direct_evidence = Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="independent verification - source code",
                location=f"{cls.location.repository_path}:{cls.location.start_line}",
                observation=f"Independent verification found class '{target_symbol}'",
                confidence=0.95,
                context="Direct source code inspection by verifier",
            )

            finding.evidence = [direct_evidence]
            finding.ground_truth_evidence = direct_evidence
            finding.ground_truth_claim = "EXISTS"
            finding.status = FindingStatus.INDEPENDENTLY_VERIFIED
            finding.verification_attempts = 2

            return VerificationResult(
                finding=finding,
                verdict="CONFIRMED",
                reasoning=f"Second verification pass confirmed {target_symbol} exists",
                verification_evidence=direct_evidence,
            )

        # Neither pass found evidence
        finding.status = FindingStatus.UNRESOLVED
        finding.verification_attempts = 2

        return VerificationResult(
            finding=finding,
            verdict="UNRESOLVED",
            reasoning=f"Verification could not confirm '{target_symbol}' exists. "
                     f"Coverage may be incomplete.",
            verification_evidence=None,
        )

    def _verify_absence(
        self, finding: Finding, context: VerificationContext
    ) -> VerificationResult:
        """
        Verify negative absence claim independently.

        Scout said something is absent. Verifier independently checks repository.
        Conservative: returns UNRESOLVED unless confident of absence.
        """
        # Extract symbol name from claim
        claim = finding.claim
        target_symbol = None

        if "'" in claim:
            parts = claim.split("'")
            if len(parts) >= 2:
                target_symbol = parts[1]
        else:
            # Fallback: try to extract from words
            words = claim.split()
            for word in words:
                if word and word[0].isalpha():
                    target_symbol = word
                    break

        if not target_symbol:
            finding.status = FindingStatus.UNRESOLVED
            finding.verification_attempts = 1
            return VerificationResult(
                finding=finding,
                verdict="UNRESOLVED",
                reasoning="Could not parse symbol name from absence claim",
                verification_evidence=None,
            )

        # First pass: independent repository inspection
        functions = self.query.find_function(target_symbol)
        if functions:
            # Symbol EXISTS - Scout hypothesis is REFUTED
            func = functions[0]
            contradicting_evidence = Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="independent verification - source code",
                location=f"{func.location.repository_path}:{func.location.start_line}",
                observation=f"Verification found '{target_symbol}' EXISTS, contradicting absence claim",
                confidence=0.95,
                context="Direct source code inspection",
            )

            finding.status = FindingStatus.INDEPENDENTLY_VERIFIED
            finding.evidence = [contradicting_evidence]
            finding.contradictory_evidence = f"found at {func.location.repository_path}"
            finding.verification_attempts = 1

            return VerificationResult(
                finding=finding,
                verdict="REFUTED",
                reasoning=f"Independent verification found '{target_symbol}' exists, "
                         f"contradicting absence claim",
                verification_evidence=contradicting_evidence,
            )

        classes = self.query.get_class(target_symbol)
        if classes:
            # Symbol EXISTS - Scout hypothesis is REFUTED
            cls = classes[0]
            contradicting_evidence = Evidence(
                evidence_type=EvidenceType.DIRECT,
                source="independent verification - source code",
                location=f"{cls.location.repository_path}:{cls.location.start_line}",
                observation=f"Verification found '{target_symbol}' EXISTS, contradicting absence claim",
                confidence=0.95,
                context="Direct source code inspection",
            )

            finding.status = FindingStatus.INDEPENDENTLY_VERIFIED
            finding.evidence = [contradicting_evidence]
            finding.contradictory_evidence = f"found at {cls.location.repository_path}"
            finding.verification_attempts = 1

            return VerificationResult(
                finding=finding,
                verdict="REFUTED",
                reasoning=f"Independent verification found '{target_symbol}' exists, "
                         f"contradicting absence claim",
                verification_evidence=contradicting_evidence,
            )

        # Symbol not found in indexes
        # But we CANNOT confirm absence without exhaustive verification
        # Return UNRESOLVED - conservative approach
        finding.status = FindingStatus.UNRESOLVED
        finding.verification_attempts = 2

        return VerificationResult(
            finding=finding,
            verdict="UNRESOLVED",
            reasoning=f"Symbol '{target_symbol}' not found in repository indexes. "
                     f"Cannot confirm absence without exhaustive coverage. "
                     f"Requires ground-truth verification.",
            verification_evidence=None,
        )

    def _verify_functional(
        self, finding: Finding, context: VerificationContext
    ) -> VerificationResult:
        """
        Verify functional/behavior claims.

        For now, return UNRESOLVED - requires code analysis beyond scope.
        """
        finding.status = FindingStatus.UNRESOLVED
        finding.verification_attempts = 1

        return VerificationResult(
            finding=finding,
            verdict="UNRESOLVED",
            reasoning="Functional claims require code analysis. Not implemented in Stage 3.",
            verification_evidence=None,
        )
