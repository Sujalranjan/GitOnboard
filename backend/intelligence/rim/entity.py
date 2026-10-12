from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from .enums import EntityType
from .location import SourceLocation
EntityLocation = SourceLocation  # Alias for backward compatibility

class Entity(BaseModel):
    id: str = Field(..., description="The unique, deterministic stable ID for this entity.")
    type: EntityType = Field(..., description="The type of this entity.")
    name: str = Field(..., description="The name of this entity.")
    qualified_name: Optional[str] = Field(None, description="The fully qualified name, e.g. auth.login.")
    display_name: Optional[str] = Field(None, description="A human-friendly display name, e.g. login().")
    location: SourceLocation = Field(..., description="The source location of this entity.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extensible metadata specific to this entity.")
