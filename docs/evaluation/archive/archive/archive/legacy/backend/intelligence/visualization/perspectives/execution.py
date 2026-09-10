from typing import Optional
from ..engine.perspective import Perspective
from ..model.visual_model import VisualGraph, VisualNode, VisualEdge
from ...query.api.base import RepositoryAPI

class ExecutionPerspective(Perspective):
    @property
    def name(self) -> str:
        return "Execution"
        
    @property
    def description(self) -> str:
        return "Shows runtime execution flows from API routes."
        
    def build(self, api: RepositoryAPI, target_id: Optional[str] = None) -> VisualGraph:
        graph = VisualGraph()
        
        if not target_id:
            return graph # Need a target route to trace
            
        # We query the analysis engine to get the call path
        # from the route to any database repositories.
        # For MVP we'll just mock pulling the whole execution graph.
        
        # A real implementation would trace the target route using CallPathAnalysis
        # and render only that path.
        for node_id, entity in api.engine.model.entities.items():
            if entity.type.value in ["ROUTE", "CLASS", "FUNCTION"]:
                graph.nodes.append(VisualNode(
                    id=node_id,
                    label=entity.name,
                    type=entity.type.value.lower()
                ))
                
        for rel in api.engine.model.relationships.values():
            if rel.type.value == "CALLS":
                graph.edges.append(VisualEdge(
                    source=rel.source_id,
                    target=rel.target_id,
                    label="calls",
                    style="solid"
                ))
                
        return graph
