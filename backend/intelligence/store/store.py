from abc import ABC, abstractmethod
from typing import Dict, Any, List
from sqlalchemy.orm import Session

class IntelligenceStore(ABC):
    """
    The canonical persistence layer for all Repository Intelligence artifacts.
    """
    
    @abstractmethod
    def save_repository_model(self, model_data: Dict[str, Any]):
        pass
        
    @abstractmethod
    def save_derived_model(self, model_type: str, data: Any):
        pass
        
    @abstractmethod
    def save_intelligence(self, intelligence: Any):
        pass

class MemoryStore(IntelligenceStore):
    def __init__(self):
        self.repository_model = None
        self.derived_models = {}
        self.intelligence = []
        
    def save_repository_model(self, model_data: Dict[str, Any]):
        self.repository_model = model_data
        
    def save_derived_model(self, model_type: str, data: Any):
        self.derived_models[model_type] = data
        
    def save_intelligence(self, intelligence: Any):
        self.intelligence.append(intelligence)

class PostgreSQLFactStore(IntelligenceStore):
    """
    PostgreSQL-backed Fact Store implementation.
    """
    def __init__(self, db: Session, analysis_id: int):
        self.db = db
        self.analysis_id = analysis_id

    def save_repository_model(self, model: Any):
        from .fact_store import save_rim_to_fact_store
        save_rim_to_fact_store(self.db, self.analysis_id, model)

    def save_derived_model(self, model_type: str, data: Any):
        pass

    def save_intelligence(self, intelligence: Any):
        pass
