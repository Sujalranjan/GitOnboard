# Phase 3 evaluation schemas
import enum
from dataclasses import dataclass, field
from typing import List

class ClaimType(enum.Enum):
    TECHNOLOGY = "technology"
    DATABASE = "database"
    PATH = "path"
    FILE = "file"
    SYMBOL = "symbol"
    CONTRADICTION = "contradiction"
    OTHER = "other"

class SupportStatus(enum.Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"

class HallucinationCategory(enum.Enum):
    INCORRECT_TECHNOLOGY = "incorrect_technology"
    FABRICATED_PATH = "fabricated_path"
    FABRICATED_FILE = "fabricated_file"
    FABRICATED_SYMBOL = "fabricated_symbol"
    FALSE_CONTRADICTION = "false_contradiction"
    # other categories omitted for brevity

class CitationStatus(enum.Enum):
    VALID = "valid"
    INVALID_ID = "invalid_id"
    NOT_ENTAILED = "not_entailed"
    # other statuses omitted

@dataclass
class AtomicClaim:
    claim_id: str
    repository: str
    text: str
    claim_type: ClaimType
    citations: List[str] = field(default_factory=list)
    support_status: SupportStatus = SupportStatus.UNRESOLVED

@dataclass
class CitationEvaluation:
    citation_id: str
    status: CitationStatus

@dataclass
class ClaimResult:
    support_status: SupportStatus
    hallucination_categories: List[HallucinationCategory] = field(default_factory=list)
    citation_evaluations: List[CitationEvaluation] = field(default_factory=list)
