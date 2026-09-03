from typing import Dict, List
from ...rim.repository import RepositoryModel
from ...features.model import Feature
from ...patterns.model import Pattern
from ...rim.entity import Entity

class IndexManager:
    """
    Manages lookups to avoid scanning the graph.
    """
    def __init__(self, model: RepositoryModel):
        self.model = model
        self.feature_index: Dict[str, Feature] = {}
        self.pattern_index: Dict[str, Pattern] = {}
        self.entity_index: Dict[str, Entity] = {}
        
        self._build_indexes()
        
    def _build_indexes(self):
        # 1. Feature Index
        if hasattr(self.model, "features"):
            for feature in self.model.features.values():
                # Index by name
                self.feature_index[feature.name.lower()] = feature
                
        # 2. Pattern Index
        if hasattr(self.model, "patterns"):
            for pattern in self.model.patterns.values():
                self.pattern_index[pattern.type.value.lower()] = pattern
                
        # 3. Entity Index
        for entity in self.model.entities.values():
            self.entity_index[entity.name.lower()] = entity

    def find_feature_by_name(self, name: str) -> Feature:
        return self.feature_index.get(name.lower())
        
    def find_pattern_by_name(self, name: str) -> Pattern:
        return self.pattern_index.get(name.lower())
        
    def find_entity_by_name(self, name: str) -> Entity:
        return self.entity_index.get(name.lower())
