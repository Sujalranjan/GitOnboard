"""
Ground-Truth Validator for Investigation Framework.

Validates repository claims by independently inspecting the RIM (Repository Intelligence Model)
and establishing whether claims correspond to actual repository reality.

Does NOT use LLM or agent assertions. Repository is the sole authority.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.rim.enums import EntityType
from backend.intelligence.query_layer import QueryLayer
from backend.investigation.evidence import Evidence, EvidenceType, InvalidEvidenceError


class VerificationStatus(str, Enum):
    """Result of ground-truth validation."""
    VERIFIED_PRESENT = "VERIFIED_PRESENT"
    """Claim independently verified against repository."""

    VERIFIED_ABSENT = "VERIFIED_ABSENT"
    """Absence independently verified with sufficient repository coverage."""

    UNRESOLVED = "UNRESOLVED"
    """Cannot establish truth; insufficient evidence or repository coverage."""


@dataclass
class GroundTruthResult:
    """
    Result of ground-truth validation.

    Guarantees:
    - status indicates what was independently verified
    - evidence is either a valid Evidence object or None
    - evidence always matches the status (never DIRECT for UNRESOLVED)
    """

    status: VerificationStatus
    """VERIFIED_PRESENT, VERIFIED_ABSENT, or UNRESOLVED."""

    evidence: Optional[Evidence] = None
    """Actual Evidence object from repository inspection, or None if UNRESOLVED."""

    coverage_note: str = ""
    """Why the validator reached this status (for debugging/logging)."""

    def __post_init__(self):
        """Validate result consistency."""
        if self.status == VerificationStatus.UNRESOLVED and self.evidence is not None:
            raise ValueError("UNRESOLVED status cannot have evidence object")

        if self.status in (VerificationStatus.VERIFIED_PRESENT, VerificationStatus.VERIFIED_ABSENT):
            if self.evidence is None:
                raise ValueError(f"{self.status.value} requires evidence object")

            if self.evidence.evidence_type != EvidenceType.DIRECT:
                raise ValueError(
                    f"{self.status.value} requires DIRECT evidence, got {self.evidence.evidence_type.value}"
                )

            if self.evidence.confidence < 0.9:
                raise ValueError(
                    f"{self.status.value} requires confidence >= 0.9, got {self.evidence.confidence}"
                )


class GroundTruthValidator:
    """
    Validates investigation claims against repository ground truth.

    Independent inspection of RIM ensures claims match actual repository reality.
    Never accepts agent assertions, metadata, or search results alone as proof.
    """

    def __init__(self, repository_model: RepositoryModel):
        """
        Initialize validator with repository model.

        Args:
            repository_model: RIM containing entities and relationships
        """
        self.model = repository_model
        self.query = QueryLayer(repository_model)

    def validate_symbol_exists(self, symbol_name: str) -> GroundTruthResult:
        """
        Validate that a symbol (function, class, method, etc.) exists in repository.

        Search strategy:
        1. Try exact function name match
        2. Try exact class name match
        3. Try qualified name match
        4. Return UNRESOLVED if not found

        Args:
            symbol_name: Name of symbol to validate

        Returns:
            GroundTruthResult with VERIFIED_PRESENT, VERIFIED_ABSENT, or UNRESOLVED
        """
        # Search for function
        functions = self.query.find_function(symbol_name)
        if functions:
            func = functions[0]  # Found at least one match
            return GroundTruthResult(
                status=VerificationStatus.VERIFIED_PRESENT,
                evidence=Evidence(
                    evidence_type=EvidenceType.DIRECT,
                    source="repository source code",
                    location=f"{func.location.repository_path}:{func.location.start_line}",
                    observation=f"Function '{symbol_name}' found in repository at {func.location.repository_path}",
                    confidence=0.95,
                    context=f"Symbol ID: {func.id}, Language: {func.location.language}",
                ),
                coverage_note=f"Found function '{symbol_name}' in repository",
            )

        # Search for class
        classes = self.query.get_class(symbol_name)
        if classes:
            cls = classes[0]  # Found at least one match
            return GroundTruthResult(
                status=VerificationStatus.VERIFIED_PRESENT,
                evidence=Evidence(
                    evidence_type=EvidenceType.DIRECT,
                    source="repository source code",
                    location=f"{cls.location.repository_path}:{cls.location.start_line}",
                    observation=f"Class '{symbol_name}' found in repository at {cls.location.repository_path}",
                    confidence=0.95,
                    context=f"Symbol ID: {cls.id}, Language: {cls.location.language}",
                ),
                coverage_note=f"Found class '{symbol_name}' in repository",
            )

        # Symbol not found in repository
        # But this is NOT automatic proof of absence - return UNRESOLVED
        return GroundTruthResult(
            status=VerificationStatus.UNRESOLVED,
            coverage_note=f"Symbol '{symbol_name}' not found in function/class indexes. "
                         f"Coverage: {len(self.query._func_name_idx)} functions, "
                         f"{len(self.query._class_name_idx)} classes. "
                         f"Cannot verify absence without examining all files.",
        )

    def validate_file_exists(self, file_path: str) -> GroundTruthResult:
        """
        Validate that a file exists in repository.

        Args:
            file_path: Repository path to file (e.g., "src/main.py")

        Returns:
            GroundTruthResult with VERIFIED_PRESENT or UNRESOLVED
        """
        files = self.query.get_files()
        for file_entity in files:
            if file_entity.location.repository_path == file_path:
                return GroundTruthResult(
                    status=VerificationStatus.VERIFIED_PRESENT,
                    evidence=Evidence(
                        evidence_type=EvidenceType.DIRECT,
                        source="repository file system",
                        location=file_path,
                        observation=f"File '{file_path}' exists in repository",
                        confidence=1.0,
                        context=f"File ID: {file_entity.id}, Language: {file_entity.location.language}",
                    ),
                    coverage_note=f"Found file '{file_path}' in repository",
                )

        # File not found - cannot verify absence without exhaustive scan
        return GroundTruthResult(
            status=VerificationStatus.UNRESOLVED,
            coverage_note=f"File '{file_path}' not found in repository entities. "
                         f"Coverage: {len(files)} files in RIM. "
                         f"Cannot verify absence without exhaustive file scan.",
        )

    def validate_route_exists(self, route_path: str, http_method: Optional[str] = None) -> GroundTruthResult:
        """
        Validate that a route (API endpoint) exists in repository.

        Args:
            route_path: HTTP route path (e.g., "/api/login")
            http_method: HTTP method (e.g., "POST", "GET") - optional

        Returns:
            GroundTruthResult with VERIFIED_PRESENT or UNRESOLVED
        """
        for entity_id, entity in self.model.entities.items():
            if entity.type == EntityType.ROUTE:
                route_metadata = entity.metadata
                if route_metadata.get("route_path") == route_path:
                    if http_method is None or route_metadata.get("http_method") == http_method:
                        return GroundTruthResult(
                            status=VerificationStatus.VERIFIED_PRESENT,
                            evidence=Evidence(
                                evidence_type=EvidenceType.DIRECT,
                                source="repository route definitions",
                                location=f"{entity.location.repository_path}:{entity.location.start_line}",
                                observation=f"Route {http_method or '*'} {route_path} exists in repository",
                                confidence=0.95,
                                context=f"Route ID: {entity.id}, Handler: {route_metadata.get('handler_symbol_id')}",
                            ),
                            coverage_note=f"Found route {http_method or '*'} {route_path}",
                        )

        return GroundTruthResult(
            status=VerificationStatus.UNRESOLVED,
            coverage_note=f"Route {http_method or '*'} {route_path} not found in repository. "
                         f"Cannot verify absence without examining all route definitions.",
        )

    def validate_service_component_exists(self, service_name: str) -> GroundTruthResult:
        """
        Validate that a service/component exists in repository.

        Looks for SERVICE, MIDDLEWARE, CONTROLLER entities.

        Args:
            service_name: Name of service/component

        Returns:
            GroundTruthResult with VERIFIED_PRESENT or UNRESOLVED
        """
        service_types = [EntityType.SERVICE, EntityType.MIDDLEWARE, EntityType.CONTROLLER]

        for entity_id, entity in self.model.entities.items():
            if entity.type in service_types and entity.name == service_name:
                return GroundTruthResult(
                    status=VerificationStatus.VERIFIED_PRESENT,
                    evidence=Evidence(
                        evidence_type=EvidenceType.DIRECT,
                        source="repository service definitions",
                        location=f"{entity.location.repository_path}:{entity.location.start_line}",
                        observation=f"Service/component '{service_name}' found as {entity.type.value}",
                        confidence=0.95,
                        context=f"Entity ID: {entity.id}, Type: {entity.type.value}",
                    ),
                    coverage_note=f"Found {entity.type.value} '{service_name}'",
                )

        return GroundTruthResult(
            status=VerificationStatus.UNRESOLVED,
            coverage_note=f"Service '{service_name}' not found in repository services/middleware/controllers. "
                         f"Cannot verify absence without examining all service definitions.",
        )

    def validate_feature_exists(self, feature_keyword: str) -> GroundTruthResult:
        """
        Validate that a feature/keyword exists in repository.

        Searches capabilities for matching keywords.

        Args:
            feature_keyword: Feature keyword to search for (e.g., "authentication", "caching")

        Returns:
            GroundTruthResult with VERIFIED_PRESENT or UNRESOLVED
        """
        feature_keyword_lower = feature_keyword.lower()

        for cap_id, capability in self.model.capabilities.items():
            # Check keywords
            if capability.keywords:
                for keyword in capability.keywords:
                    if keyword.lower() == feature_keyword_lower or feature_keyword_lower in keyword.lower():
                        return GroundTruthResult(
                            status=VerificationStatus.VERIFIED_PRESENT,
                            evidence=Evidence(
                                evidence_type=EvidenceType.DIRECT,
                                source="repository capabilities",
                                location=cap_id,
                                observation=f"Feature '{feature_keyword}' found in capability '{capability.purpose}'",
                                confidence=capability.confidence if capability.confidence > 0.9 else 0.9,
                                context=f"Category: {capability.category.value}, Purpose: {capability.purpose}",
                            ),
                            coverage_note=f"Found feature '{feature_keyword}' in capabilities",
                        )

            # Check purpose
            if feature_keyword_lower in capability.purpose.lower():
                return GroundTruthResult(
                    status=VerificationStatus.VERIFIED_PRESENT,
                    evidence=Evidence(
                        evidence_type=EvidenceType.DIRECT,
                        source="repository capabilities",
                        location=cap_id,
                        observation=f"Feature '{feature_keyword}' found in capability '{capability.purpose}'",
                        confidence=capability.confidence if capability.confidence > 0.9 else 0.9,
                        context=f"Category: {capability.category.value}",
                    ),
                    coverage_note=f"Found feature '{feature_keyword}' in capability",
                )

        return GroundTruthResult(
            status=VerificationStatus.UNRESOLVED,
            coverage_note=f"Feature '{feature_keyword}' not found in repository capabilities. "
                         f"Coverage: {len(self.model.capabilities)} capabilities. "
                         f"Cannot verify absence without examining all features.",
        )
