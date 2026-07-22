from pydantic import BaseModel

class ImportRequest(BaseModel):
    url: str
    
class GraphQueryRequest(BaseModel):
    node_id: str
    direction: str = "both"
    depth: int = 1
    max_nodes: int = 50
    relationship_type: str = "calls"

class ExplainTraceRequest(BaseModel):
    feature_query: str
    trace_data: dict
