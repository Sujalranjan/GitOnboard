from abc import ABC, abstractmethod
from typing import List
from backend.intelligence.rim.repository import RepositoryModel
from backend.intelligence.capabilities.model import CapabilityDetection

class BaseCapabilityDetector(ABC):
    """
    Abstract Base Class for multi-fact deterministic capability detectors.
    """

    @abstractmethod
    def detect(self, rim: RepositoryModel) -> List[CapabilityDetection]:
        """
        Analyzes RIM graph entities and relationships to emit deterministic capability detections.
        """
        pass
