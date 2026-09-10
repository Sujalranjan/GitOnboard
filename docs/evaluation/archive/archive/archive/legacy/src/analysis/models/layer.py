from enum import Enum
from dataclasses import dataclass

class ArchitecturalLayer(Enum):
    CONTROLLER = "Controller"
    SERVICE = "Service"
    REPOSITORY = "Repository"
    MODEL = "Model"
    UTILITY = "Utility"
    CONFIG = "Config"
    TEST = "Test"
    UNKNOWN = "Unknown"

@dataclass
class ModuleLayer:
    module_id: str
    module_name: str
    layer: ArchitecturalLayer
    reason: str
