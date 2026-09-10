from abc import ABC, abstractmethod
from ..model.visual_model import VisualGraph

class Exporter(ABC):
    @abstractmethod
    def export(self, graph: VisualGraph) -> str:
        pass
