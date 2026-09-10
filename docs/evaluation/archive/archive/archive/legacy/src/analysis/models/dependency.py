from enum import Enum
from dataclasses import dataclass, field
from typing import List

class DependencyType(Enum):
    IMPORT = "IMPORT"
    CALL = "CALL"
    INHERITANCE = "INHERITANCE"
    API = "API"
    DATABASE = "DATABASE"
    CONFIG = "CONFIG"
    EVENT = "EVENT"
    DECORATOR = "DECORATOR"

@dataclass
class DependencyEdge:
    source: str
    destination: str
    type: DependencyType
    evidence: str
    confidence: float

@dataclass
class DependencyGraph:
    edges: List[DependencyEdge] = field(default_factory=list)
