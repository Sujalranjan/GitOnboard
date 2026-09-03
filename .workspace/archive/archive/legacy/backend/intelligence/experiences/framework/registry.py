import yaml
import os
from typing import Dict, List
from .experience import ExperienceDefinition

class ExperienceRegistry:
    """
    Loads and serves declarative AI experiences.
    """
    def __init__(self):
        self._registry: Dict[str, ExperienceDefinition] = {}
        
    def load_from_directory(self, dir_path: str):
        if not os.path.exists(dir_path):
            return
            
        for filename in os.listdir(dir_path):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                filepath = os.path.join(dir_path, filename)
                with open(filepath, 'r') as f:
                    data = yaml.safe_load(f)
                    definition = ExperienceDefinition(**data)
                    self._registry[definition.id] = definition
                    
    def get(self, experience_id: str) -> ExperienceDefinition:
        if experience_id not in self._registry:
            raise ValueError(f"Experience '{experience_id}' not found.")
        return self._registry[experience_id]
        
    def find_by_intent(self, intent: str) -> ExperienceDefinition:
        for exp in self._registry.values():
            if intent in exp.intents:
                return exp
        raise ValueError(f"No experience handles intent '{intent}'")
