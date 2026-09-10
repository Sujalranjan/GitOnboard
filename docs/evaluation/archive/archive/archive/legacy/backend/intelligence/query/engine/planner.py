from typing import Any, Dict
from pydantic import BaseModel
from ..model.query import RepositoryQuery, ActionType

class ExecutionPlan(BaseModel):
    use_feature_index: bool = False
    use_pattern_index: bool = False
    use_entity_index: bool = False
    requires_graph_traversal: bool = False
    target_name: str
    query: RepositoryQuery

class QueryPlanner:
    """
    Determines the optimal execution path for a query.
    """
    def plan(self, query: RepositoryQuery) -> ExecutionPlan:
        plan = ExecutionPlan(
            target_name=query.target_name,
            query=query
        )
        
        # Determine index to hit
        if query.target_type.value == "FEATURE":
            plan.use_feature_index = True
        elif query.target_type.value == "PATTERN":
            plan.use_pattern_index = True
        elif query.target_type.value == "ENTITY":
            plan.use_entity_index = True
            
        # Determine if graph traversal is needed
        if query.action.value == "FROM" or query.clauses:
            plan.requires_graph_traversal = True
            
        return plan
