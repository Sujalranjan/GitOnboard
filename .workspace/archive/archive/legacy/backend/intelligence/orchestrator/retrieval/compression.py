from typing import List, Any
from ..knowledge.model import KnowledgePack
from ...features.model import Feature
from ...capabilities.model import SemanticCapability
from ...patterns.model import Pattern
from ...rim.entity import Entity

class ContextCompression:
    """
    Drops artifacts if a token budget is exceeded to fit context windows.
    """
    def __init__(self, max_items: int = 50):
        self.max_items = max_items
        
    def compress(self, intent_str: str, items: List[Any], target_id: str = None) -> KnowledgePack:
        # 1. Truncate list if over budget
        kept_items = items[:self.max_items]
        
        # 2. Build the KnowledgePack
        pack = KnowledgePack(intent=intent_str, target_id=target_id)
        
        for item in kept_items:
            if isinstance(item, Feature):
                pack.features.append(item)
            elif isinstance(item, SemanticCapability):
                pack.capabilities.append(item)
            elif isinstance(item, Pattern):
                pack.patterns.append(item)
            elif isinstance(item, Entity):
                pack.representative_sources.append(item)
                
        return pack
