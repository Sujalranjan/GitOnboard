import time
from typing import Any, Dict, List
from ..model.query import RepositoryQuery
from ..model.result import QueryResult
from .planner import QueryPlanner, ExecutionPlan
from ..indexes.index_manager import IndexManager
from ...rim.repository import RepositoryModel

class QueryExecutor:
    """
    Executes a QueryAST against the indexes (and graph only if requested).
    """
    def __init__(self, index_manager: IndexManager):
        self.index_manager = index_manager
        self.planner = QueryPlanner()
        
    def execute(self, query: RepositoryQuery) -> QueryResult[Any]:
        start_time = time.time()
        
        # 1. Plan Execution
        plan = self.planner.plan(query)
        
        # 2. Index Lookup (O(1))
        root_node = None
        if plan.use_feature_index:
            root_node = self.index_manager.find_feature_by_name(plan.target_name)
        elif plan.use_pattern_index:
            root_node = self.index_manager.find_pattern_by_name(plan.target_name)
        elif plan.use_entity_index:
            root_node = self.index_manager.find_entity_by_name(plan.target_name)
            
        if not root_node:
            return QueryResult(
                result=None,
                evidence=[{"error": f"Target {plan.target_name} not found in index."}],
                confidence=0.0,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
            
        # 3. Simple FIND query ends here without touching the graph
        if not plan.requires_graph_traversal:
            return QueryResult(
                result=root_node,
                evidence=[{"source": "Direct index lookup"}],
                confidence=1.0,
                execution_time_ms=int((time.time() - start_time) * 1000)
            )
            
        # 4. Handle Complex Traversals (e.g. TRACE IMPLEMENTATION)
        # Note: In a full system, this would delegate to specialized GraphExecutors.
        # For the MVP, we just demonstrate pulling properties from the root node.
        
        result_data = {"root": root_node}
        
        for clause in query.clauses:
            if clause.type.value == "TRACE" and clause.target == "IMPLEMENTATION":
                # Only valid for Features currently
                if plan.use_feature_index:
                    entities = []
                    for member in root_node.members:
                        if member.item_type == "entity":
                            entities.append(member.item_id)
                    result_data["implementation"] = entities
                    
        return QueryResult(
            result=result_data,
            evidence=[{"source": "Graph traversal starting from index"}],
            confidence=1.0,
            execution_time_ms=int((time.time() - start_time) * 1000)
        )
