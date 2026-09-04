"""
Scout Agent for Investigation Framework.

Discovers potential claims and generates investigation hypotheses.
Scout produces candidates, not confirmations.

Scout is allowed to be wrong. Verification is the skeptic.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.query_layer import QueryLayer
from backend.investigation.finding import Finding, FindingStatus, FindingSeverity
from backend.investigation.evidence import Evidence, EvidenceType


class ScoutStrategy(str, Enum):
    """Investigation strategy the Scout is using."""
    SYMBOL_SEARCH = "SYMBOL_SEARCH"
    """Search for specific function/class/entity by name."""

    FILE_SEARCH = "FILE_SEARCH"
    """Search for files in repository."""

    ROUTE_DISCOVERY = "ROUTE_DISCOVERY"
    """Search for API routes."""

    SERVICE_DISCOVERY = "SERVICE_DISCOVERY"
    """Search for services/middleware/controllers."""

    FEATURE_SEARCH = "FEATURE_SEARCH"
    """Search for features in capabilities."""


@dataclass
class ScoutHypothesis:
    """
    Investigation hypothesis produced by Scout.

    Scout output is NOT confirmed. It must be verified independently.
    Scout evidence is classified by what the Scout observed, not by truth value.
    """

    finding_id: str
    """Unique ID for this hypothesis."""

    claim: str
    """The specific claim/hypothesis."""

    claim_type: str
    """Type of claim: EXISTS, ABSENT, FUNCTIONAL, etc."""

    strategy: ScoutStrategy
    """How the Scout found this hypothesis."""

    hypothesis_summary: str
    """Brief description of the hypothesis."""

    evidence: List[Evidence]
    """Evidence found by Scout (not necessarily trusted)."""

    evidence_locations: List[str]
    """Artifact paths for context/navigation (not proof)."""

    reasoning: str
    """Why the Scout thinks this claim is worth investigating."""

    requires_ground_truth: bool = False
    """True if claim is negative and requires ground-truth verification."""

    def to_finding(self) -> Finding:
        """
        Convert Scout hypothesis to Finding.

        Finding starts in OBSERVED state, not confirmed.
        """
        return Finding(
            finding_id=self.finding_id,
            claim=self.claim,
            claim_type=self.claim_type,
            status=FindingStatus.OBSERVED,
            severity=FindingSeverity.P1,
            evidence=self.evidence,
            evidence_files=self.evidence_locations,
            evidence_summary=self.hypothesis_summary,
            scout_agent="scout-v1",
        )


class ScoutAgent:
    """
    Scout Agent: Discovers investigation hypotheses.

    Scout is allowed to be wrong. Scout produces HYPOTHESES, not confirmations.
    Scout output must be independently verified by VerificationAgent.
    """

    def __init__(self, repository_model: RepositoryModel):
        """
        Initialize Scout with repository model.

        Args:
            repository_model: RIM containing entities and relationships
        """
        self.model = repository_model
        self.query = QueryLayer(repository_model)
        self._hypothesis_counter = 0

    def _next_id(self) -> str:
        """Generate next hypothesis ID."""
        self._hypothesis_counter += 1
        return f"SCOUT-HYP-{self._hypothesis_counter:03d}"

    def investigate_symbol(self, symbol_name: str) -> Optional[ScoutHypothesis]:
        """
        Scout investigates whether a symbol exists in repository.

        Scout searches the repository. If found, Scout produces a hypothesis
        that the symbol exists. If not found, Scout returns None (uncertain).

        Scout is NOT confident about "not found" - that requires verification.

        Args:
            symbol_name: Name of symbol to investigate

        Returns:
            ScoutHypothesis if symbol is found, None otherwise
        """
        # Search for function
        functions = self.query.find_function(symbol_name)
        if functions:
            func = functions[0]
            evidence = Evidence(
                evidence_type=EvidenceType.INDIRECT,
                source="scout symbol search",
                location=f"{func.location.repository_path}:{func.location.start_line}",
                observation=f"Scout found function '{symbol_name}' in repository",
                confidence=0.7,
                context="Scout search result, requires verification",
            )

            return ScoutHypothesis(
                finding_id=self._next_id(),
                claim=f"Function '{symbol_name}' exists in repository",
                claim_type="EXISTS",
                strategy=ScoutStrategy.SYMBOL_SEARCH,
                hypothesis_summary=f"Found function '{symbol_name}' at {func.location.repository_path}",
                evidence=[evidence],
                evidence_locations=[f"{func.location.repository_path}:{func.location.start_line}"],
                reasoning=f"Symbol search located '{symbol_name}' in repository",
                requires_ground_truth=False,
            )

        # Search for class
        classes = self.query.get_class(symbol_name)
        if classes:
            cls = classes[0]
            evidence = Evidence(
                evidence_type=EvidenceType.INDIRECT,
                source="scout symbol search",
                location=f"{cls.location.repository_path}:{cls.location.start_line}",
                observation=f"Scout found class '{symbol_name}' in repository",
                confidence=0.7,
                context="Scout search result, requires verification",
            )

            return ScoutHypothesis(
                finding_id=self._next_id(),
                claim=f"Class '{symbol_name}' exists in repository",
                claim_type="EXISTS",
                strategy=ScoutStrategy.SYMBOL_SEARCH,
                hypothesis_summary=f"Found class '{symbol_name}' at {cls.location.repository_path}",
                evidence=[evidence],
                evidence_locations=[f"{cls.location.repository_path}:{cls.location.start_line}"],
                reasoning=f"Symbol search located '{symbol_name}' in repository",
                requires_ground_truth=False,
            )

        # Symbol not found in repository indexes
        # Scout does NOT conclude "symbol is absent" - that requires verification
        return None

    def investigate_absence(self, symbol_name: str) -> Optional[ScoutHypothesis]:
        """
        Scout investigates whether a symbol appears to be absent.

        Scout returns None if symbol is found (not an absence hypothesis).
        Scout returns a hypothesis ONLY if evidence suggests absence is worth investigating.

        This requires ground-truth verification before confirmation.

        Args:
            symbol_name: Name of symbol to investigate for absence

        Returns:
            ScoutHypothesis if absence is suspicious, None otherwise
        """
        # If symbol exists, no absence hypothesis
        if self.query.find_function(symbol_name) or self.query.get_class(symbol_name):
            return None

        # Symbol not found in indexes - generate absence hypothesis
        # BUT mark it as requiring ground-truth verification
        evidence = Evidence.from_retrieval_result(symbol_name, found=False, result_count=0)

        return ScoutHypothesis(
            finding_id=self._next_id(),
            claim=f"Symbol '{symbol_name}' does not exist in repository",
            claim_type="ABSENT",
            strategy=ScoutStrategy.SYMBOL_SEARCH,
            hypothesis_summary=f"Symbol '{symbol_name}' not found in repository indexes",
            evidence=[evidence],
            evidence_locations=[],
            reasoning=f"Repository search did not locate '{symbol_name}'. Requires ground-truth verification.",
            requires_ground_truth=True,
        )

    def investigate_route(self, route_path: str, http_method: Optional[str] = None) -> Optional[ScoutHypothesis]:
        """
        Scout investigates whether a route exists.

        Args:
            route_path: HTTP route path (e.g., "/api/login")
            http_method: HTTP method (GET, POST, etc.) - optional

        Returns:
            ScoutHypothesis if route is found, None otherwise
        """
        for entity_id, entity in self.model.entities.items():
            if entity.type.value == "ROUTE":
                route_metadata = entity.metadata
                if route_metadata.get("route_path") == route_path:
                    if http_method is None or route_metadata.get("http_method") == http_method:
                        evidence = Evidence(
                            evidence_type=EvidenceType.INDIRECT,
                            source="scout route search",
                            location=f"{entity.location.repository_path}:{entity.location.start_line}",
                            observation=f"Scout found route {http_method or '*'} {route_path}",
                            confidence=0.7,
                            context="Scout search result, requires verification",
                        )

                        return ScoutHypothesis(
                            finding_id=self._next_id(),
                            claim=f"Route {http_method or '*'} {route_path} exists",
                            claim_type="EXISTS",
                            strategy=ScoutStrategy.ROUTE_DISCOVERY,
                            hypothesis_summary=f"Found route {http_method or '*'} {route_path}",
                            evidence=[evidence],
                            evidence_locations=[f"{entity.location.repository_path}:{entity.location.start_line}"],
                            reasoning=f"Route discovery located {http_method or '*'} {route_path}",
                            requires_ground_truth=False,
                        )

        return None

    def investigate_feature(self, feature_keyword: str) -> Optional[ScoutHypothesis]:
        """
        Scout investigates whether a feature exists in repository.

        Args:
            feature_keyword: Feature keyword (e.g., "authentication")

        Returns:
            ScoutHypothesis if feature is found, None otherwise
        """
        feature_lower = feature_keyword.lower()

        for cap_id, capability in self.model.capabilities.items():
            # Check keywords
            if capability.keywords:
                for keyword in capability.keywords:
                    if keyword.lower() == feature_lower or feature_lower in keyword.lower():
                        evidence = Evidence(
                            evidence_type=EvidenceType.INDIRECT,
                            source="scout feature search",
                            location=cap_id,
                            observation=f"Scout found feature '{feature_keyword}' in capability",
                            confidence=0.6,
                            context="Scout capability search, requires verification",
                        )

                        return ScoutHypothesis(
                            finding_id=self._next_id(),
                            claim=f"Feature '{feature_keyword}' exists in repository",
                            claim_type="EXISTS",
                            strategy=ScoutStrategy.FEATURE_SEARCH,
                            hypothesis_summary=f"Found feature in capability '{capability.purpose}'",
                            evidence=[evidence],
                            evidence_locations=[cap_id],
                            reasoning=f"Feature search found '{feature_keyword}' in capabilities",
                            requires_ground_truth=False,
                        )

            # Check purpose
            if feature_lower in capability.purpose.lower():
                evidence = Evidence(
                    evidence_type=EvidenceType.INDIRECT,
                    source="scout feature search",
                    location=cap_id,
                    observation=f"Scout found feature '{feature_keyword}' in capability purpose",
                    confidence=0.6,
                    context="Scout capability search, requires verification",
                )

                return ScoutHypothesis(
                    finding_id=self._next_id(),
                    claim=f"Feature '{feature_keyword}' exists in repository",
                    claim_type="EXISTS",
                    strategy=ScoutStrategy.FEATURE_SEARCH,
                    hypothesis_summary=f"Found feature in capability '{capability.purpose}'",
                    evidence=[evidence],
                    evidence_locations=[cap_id],
                    reasoning=f"Feature search found '{feature_keyword}' in capability purpose",
                    requires_ground_truth=False,
                )

        return None
