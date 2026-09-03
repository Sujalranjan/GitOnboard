from typing import Optional
from ..engine.perspective import Perspective
from ..model.visual_model import VisualGraph, VisualNode, VisualEdge
from ...query.api.base import RepositoryAPI

class ArchitecturePerspective(Perspective):
    @property
    def name(self) -> str:
        return "Architecture"
        
    @property
    def description(self) -> str:
        return "Shows high-level architecture layers, features, and patterns."
        
    def build(self, api: RepositoryAPI, target_id: Optional[str] = None) -> VisualGraph:
        graph = VisualGraph()
        
        # We query the engine to get features and patterns
        features = api.engine.model.features.values()
        
        for feature in features:
            graph.nodes.append(VisualNode(
                id=feature.id,
                label=feature.name,
                type="feature",
                group="architecture"
            ))
            
        # We also query the analysis engine to get circular dependencies
        # and highlight them!
        cycles_result = api.engine.analysis.execute_analysis("CircularDependency", api.engine.model)
        cycle_edges = set()
        if cycles_result and cycles_result.result:
            for cycle in cycles_result.result:
                # Add edges to represent the cycle
                for i in range(len(cycle)):
                    source = cycle[i]
                    target = cycle[(i + 1) % len(cycle)]
                    cycle_edges.add((source, target))
        
        for rel in api.engine.model.feature_relationships.values():
            style = "solid"
            if (rel.source_id, rel.target_id) in cycle_edges:
                style = "bold_red" # Highlight cycles!
                
            graph.edges.append(VisualEdge(
                source=rel.source_id,
                target=rel.target_id,
                label=rel.type.name,
                style=style
            ))
            
        return graph
