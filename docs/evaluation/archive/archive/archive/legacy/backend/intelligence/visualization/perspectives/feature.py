from typing import Optional
from ..engine.perspective import Perspective
from ..model.visual_model import VisualGraph, VisualNode, VisualEdge
from ...query.api.base import RepositoryAPI

class FeaturePerspective(Perspective):
    @property
    def name(self) -> str:
        return "Feature"
        
    @property
    def description(self) -> str:
        return "Shows high-level business features and their implementations."
        
    def build(self, api: RepositoryAPI, target_id: Optional[str] = None) -> VisualGraph:
        graph = VisualGraph()
        
        # We query the engine! No graph traversal!
        if target_id:
            # Query specific feature
            res = api.engine.parser.parse(f"FIND FEATURE {target_id}")
            result = api.engine.executor.execute(res)
            features = [result.result] if result.result else []
        else:
            # Note: For MVP, we'll just mock this as returning all if no target
            # A real implementation would have a FIND ALL FEATURES query
            features = [f for f in api.engine.model.features.values()]
            
        for feature in features:
            graph.nodes.append(VisualNode(
                id=feature.id,
                label=feature.name,
                type="feature",
                metadata={"confidence": feature.confidence}
            ))
            
            # Map members
            for member in feature.members:
                graph.nodes.append(VisualNode(
                    id=member.item_id,
                    label=member.item_id.split(":")[-1],
                    type="entity",
                    group=feature.name
                ))
                graph.edges.append(VisualEdge(
                    source=feature.id,
                    target=member.item_id,
                    label="contains",
                    style="dashed"
                ))
                
        return graph
