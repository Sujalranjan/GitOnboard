from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class RepositoryMetrics:
    total_files: int = 0
    total_lines: int = 0
    complexity: float = 0.0
    custom_metrics: Dict[str, Any] = None

    def __post_init__(self):
        if self.custom_metrics is None:
            self.custom_metrics = {}
