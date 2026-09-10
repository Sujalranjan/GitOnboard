from ...rim.repository import RepositoryModel
from ..engine.query_engine import QueryEngine
from .feature_api import FeatureAPI
from .architecture_api import ArchitectureAPI

class RepositoryAPI:
    """
    The top-level facade for querying the Repository Intelligence Model.
    """
    def __init__(self, model: RepositoryModel):
        self.engine = QueryEngine(model)
        
        self.features = FeatureAPI(self.engine)
        self.architecture = ArchitectureAPI(self.engine)
        
        # Other domain APIs would be added here
