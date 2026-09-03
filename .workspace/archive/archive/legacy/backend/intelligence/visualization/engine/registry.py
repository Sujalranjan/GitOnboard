from typing import Dict, Type
from .perspective import Perspective

class PerspectiveRegistry:
    def __init__(self):
        self._registry: Dict[str, Type[Perspective]] = {}
        
    def register(self, perspective_class: Type[Perspective]):
        instance = perspective_class()
        self._registry[instance.name.lower()] = perspective_class
        
    def get(self, name: str) -> Type[Perspective]:
        return self._registry.get(name.lower())
