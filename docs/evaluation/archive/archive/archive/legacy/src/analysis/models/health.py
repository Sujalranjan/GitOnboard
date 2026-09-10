from dataclasses import dataclass, field
from typing import Optional, List, Dict

@dataclass
class CategoryScore:
    score: float  # 0.0 to 100.0
    explanation: str
    weight: float

@dataclass
class RepositoryHealth:
    health_score: float
    status: str
    issues_count: int
    recommendations: List[str] = field(default_factory=list)
    categories: Dict[str, CategoryScore] = field(default_factory=dict)
