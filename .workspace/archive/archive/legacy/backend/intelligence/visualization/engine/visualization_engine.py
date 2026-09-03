from typing import Optional
from .registry import PerspectiveRegistry
from ..model.visual_model import VisualGraph
from ...query.api.base import RepositoryAPI

class VisualizationEngine:
    def __init__(self, registry: PerspectiveRegistry, api: RepositoryAPI):
        self.registry = registry
        self.api = api
        
    def generate_view(self, perspective_name: str, target_id: Optional[str] = None) -> VisualGraph:
        perspective_cls = self.registry.get(perspective_name)
        if not perspective_cls:
            raise ValueError(f"Perspective '{perspective_name}' not found.")
            
        perspective = perspective_cls()
        return perspective.build(self.api, target_id)
