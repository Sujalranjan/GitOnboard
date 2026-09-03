from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..model.visual_model import VisualGraph
from ...query.api.base import RepositoryAPI

class Perspective(ABC):
    """
    Contract for a visualization perspective.
    It builds a VisualGraph by querying the RepositoryAPI.
    """
    @property
    @abstractmethod
    def name(self) -> str:
        pass
        
    @property
    @abstractmethod
    def description(self) -> str:
        pass
        
    @abstractmethod
    def build(self, api: RepositoryAPI, target_id: Optional[str] = None) -> VisualGraph:
        """
        Builds the visual graph using the API.
        """
        pass
