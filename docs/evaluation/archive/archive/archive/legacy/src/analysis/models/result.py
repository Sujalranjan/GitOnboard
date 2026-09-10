from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from .finding import Finding
from .metrics import RepositoryMetrics
from .health import RepositoryHealth

@dataclass
class AnalysisResult:
    analyzer_name: str
    findings: List[Finding]
    metrics: Optional[RepositoryMetrics] = None
    health: Optional[RepositoryHealth] = None
    duration: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
