from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from ...features.model import Feature
from ...capabilities.model import SemanticCapability
from ...patterns.model import Pattern
from ...rim.entity import Entity

class CallPath(BaseModel):
    path: List[str]

class KnowledgePack(BaseModel):
    """
    A strictly typed, reusable artifact containing all intelligence 
    needed to answer a query. This is completely model-independent.
    """
    intent: str
    target_id: Optional[str] = None
    features: List[Feature] = Field(default_factory=list)
    capabilities: List[SemanticCapability] = Field(default_factory=list)
    patterns: List[Pattern] = Field(default_factory=list)
    call_paths: List[CallPath] = Field(default_factory=list)
    representative_sources: List[Entity] = Field(default_factory=list)
