import json
from .base import Exporter
from ..model.visual_model import VisualGraph

class JsonExporter(Exporter):
    def export(self, graph: VisualGraph) -> str:
        return graph.model_dump_json(indent=2)
