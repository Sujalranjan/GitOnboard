from typing import Any
from ..engine.query_engine import QueryEngine
from ..model.result import QueryResult
from ...patterns.model import Pattern

class ArchitectureAPI:
    def __init__(self, engine: QueryEngine):
        self.engine = engine
        
    def find_architecture_pattern(self, name: str) -> QueryResult[Pattern]:
        return self.engine.execute_dsl(f"FIND PATTERN {name}")
