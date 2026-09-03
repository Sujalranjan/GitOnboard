from typing import List, Any
from ...features.model import Feature
from ...rim.entity import Entity
from ...rim.enums import EntityType

class ContextRanking:
    """
    Ranks expanded evidence based on relevance signals.
    """
    def rank(self, items: List[Any]) -> List[Any]:
        # For MVP, we'll just sort Features first
        def score(item):
            if isinstance(item, Feature):
                return 100
            return 10
            
        return sorted(items, key=score, reverse=True)

class SourceSelection:
    """
    Filters down raw implementation files to just the representative sources.
    """
    def select_representative(self, items: List[Any]) -> List[Any]:
        filtered = []
        for item in items:
            # Keep features/patterns as is
            if not isinstance(item, Entity):
                filtered.append(item)
                continue
                
            # For entities, only keep core architectural components (e.g. CLASSES, ROUTES)
            if item.type in [EntityType.CLASS, EntityType.ROUTE]:
                filtered.append(item)
                
        return filtered
