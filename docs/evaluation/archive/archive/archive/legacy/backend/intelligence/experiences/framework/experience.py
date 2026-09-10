from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class ExperienceDefinition(BaseModel):
    id: str
    name: str
    intents: List[str]
    knowledge_requirements: List[str]
    prompt_template: str
    output_type: str = "markdown"

class ExperienceRequest(BaseModel):
    query: str
    experience_id: Optional[str] = None

class ExperienceResponse(BaseModel):
    answer: str
    evidence_links: List[str]
    confidence: float
