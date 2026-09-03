from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Dict

class AIResponse(BaseModel):
    answer: str
    evidence_links: List[str]
    confidence: float

class AIProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> AIResponse:
        pass
