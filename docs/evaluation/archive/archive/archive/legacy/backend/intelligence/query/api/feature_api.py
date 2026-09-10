from typing import Any
from ..engine.query_engine import QueryEngine
from ..model.result import QueryResult
from ...features.model import Feature

class FeatureAPI:
    def __init__(self, engine: QueryEngine):
        self.engine = engine
        
    def find_feature(self, name: str) -> QueryResult[Feature]:
        return self.engine.execute_dsl(f"FIND FEATURE {name}")
        
    def trace_feature(self, name: str) -> QueryResult[Any]:
        return self.engine.execute_dsl(f"FROM FEATURE {name} TRACE IMPLEMENTATION")
