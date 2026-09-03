from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from .finding import Finding
from .metrics import RepositoryMetrics
from .health import RepositoryHealth
from .result import AnalysisResult

@dataclass
class AnalysisReport:
    results: List[AnalysisResult]
    overall_findings: List[Finding]
    overall_metrics: Optional[RepositoryMetrics] = None
    overall_health: Optional[RepositoryHealth] = None
    execution_summary: Dict[str, Any] = None

    def __post_init__(self):
        if self.execution_summary is None:
            self.execution_summary = {}
