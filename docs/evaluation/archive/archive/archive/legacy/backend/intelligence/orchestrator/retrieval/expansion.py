from typing import List, Any
from ...query.api.base import RepositoryAPI
from ...query.model.result import QueryResult
from ..intent.planner import QueryPlan

class EvidenceCollector:
    """
    Executes the query plan against the RepositoryAPI to gather raw evidence.
    """
    def __init__(self, api: RepositoryAPI):
        self.api = api
        
    def collect(self, plan: QueryPlan) -> List[QueryResult]:
        results = []
        for query_str in plan.queries:
            # Parse and execute through the deterministic query engine
            ast = self.api.engine.parser.parse(query_str)
            res = self.api.engine.executor.execute(ast)
            if res:
                results.append(res)
        return results

class GraphExpansion:
    """
    Expands the initial evidence set by following predefined relationships 
    (e.g., pulling in capabilities associated with a feature).
    """
    def expand(self, evidence: List[QueryResult]) -> List[Any]:
        # For MVP, we just extract the inner payload from QueryResult
        # A full implementation would intelligently trace relationships (e.g. Feature -> Capabilities)
        expanded = []
        for res in evidence:
            if res.result:
                expanded.append(res.result)
        return expanded
