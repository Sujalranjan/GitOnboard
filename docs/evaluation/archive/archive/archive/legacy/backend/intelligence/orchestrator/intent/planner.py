from typing import List
from pydantic import BaseModel
from .analyzer import UserIntent, IntentType

class QueryPlan(BaseModel):
    queries: List[str]

class QueryPlanner:
    """
    Converts a structured Intent into a series of RepositoryAPI queries.
    """
    def plan(self, intent: UserIntent) -> QueryPlan:
        queries = []
        
        if intent.type == IntentType.EXPLAIN_FEATURE:
            for target in intent.targets:
                queries.append(f"FIND FEATURE {target}")
                queries.append(f"FROM FEATURE {target} FOLLOW DEPENDS_ON")
                
        return QueryPlan(queries=queries)
