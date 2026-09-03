from typing import Any
from ..parser.dsl_parser import DSLParser
from .executor import QueryExecutor
from ..indexes.index_manager import IndexManager
from ..model.result import QueryResult
from ...rim.repository import RepositoryModel

class QueryEngine:
    def __init__(self, model: RepositoryModel):
        self.parser = DSLParser()
        self.index_manager = IndexManager(model)
        self.executor = QueryExecutor(self.index_manager)
        
    def execute_dsl(self, query_str: str) -> QueryResult[Any]:
        # 1. Parse
        ast = self.parser.parse(query_str)
        # 2. Plan and Execute
        return self.executor.execute(ast)
