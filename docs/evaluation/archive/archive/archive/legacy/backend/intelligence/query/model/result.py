from pydantic import BaseModel, Field
from typing import List, Dict, Any, Generic, TypeVar

T = TypeVar('T')

class QueryResult(BaseModel, Generic[T]):
    result: T
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = 1.0
    execution_time_ms: int = 0
