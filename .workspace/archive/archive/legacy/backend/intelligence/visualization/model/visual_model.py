from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class VisualNode(BaseModel):
    id: str
    label: str
    type: str          # e.g., "feature", "database", "route"
    group: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

class VisualEdge(BaseModel):
    source: str
    target: str
    label: str = ""
    style: str = "solid"
    
class VisualGraph(BaseModel):
    nodes: List[VisualNode] = Field(default_factory=list)
    edges: List[VisualEdge] = Field(default_factory=list)
