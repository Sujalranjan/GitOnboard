from pydantic import BaseModel, Field
from typing import Dict
from .entity import Entity
from .relationship import Relationship
from .metadata import RepositoryMetadata
from ..capabilities.model import Capability, CapabilityRelationship
from ..features.model import Feature, FeatureRelationship

class RepositoryModel(BaseModel):
    metadata: RepositoryMetadata = Field(..., description="Top-level repository metadata.")
    entities: Dict[str, Entity] = Field(default_factory=dict, description="Canonical software artifacts mapped by stable ID.")
    relationships: Dict[str, Relationship] = Field(default_factory=dict, description="Graph edges representing relationships between entities.")
    capabilities: Dict[str, Capability] = Field(default_factory=dict)
    capability_relationships: Dict[str, CapabilityRelationship] = Field(default_factory=dict)
    features: Dict[str, Feature] = Field(default_factory=dict)
    feature_relationships: Dict[str, FeatureRelationship] = Field(default_factory=dict)
