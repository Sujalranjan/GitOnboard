from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from .models.result import AnalysisResult

if TYPE_CHECKING:
    from rim.models import Repository

class Analyzer(ABC):
    """Abstract base class for all repository analyzers.
    
    Analyzers must ONLY read from the RIM (the repository object)
    and must not parse files directly.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique name of the analyzer."""
        pass
        
    @abstractmethod
    def analyze(self, repository: 'Repository') -> AnalysisResult:
        """Perform the analysis on the given repository model and return the result."""
        pass
