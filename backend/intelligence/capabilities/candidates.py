from typing import List
from ..rim.repository import RepositoryModel
from ..rim.enums import EntityType

class CandidateSelector:
    """
    Selects which Entities and Patterns should be evaluated to become Capabilities.
    """
    def __init__(self, model: RepositoryModel):
        self.model = model

    def select(self) -> List[str]:
        candidates = []
        
        # Select high-level entities
        for entity in self.model.entities.values():
            if entity.type in [EntityType.ROUTE, EntityType.CLASS, EntityType.FUNCTION]:
                # Heuristic: skip short helper functions or DTOs
                name = entity.name.lower()
                if "dto" in name or "helper" in name or "util" in name:
                    continue
                candidates.append(entity.id)
                
        # Deduplicate
        return list(set(candidates))
