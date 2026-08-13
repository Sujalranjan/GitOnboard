from pydantic import BaseModel, Field
from typing import List, Dict, Any, Tuple, Optional
from enum import Enum
from dataclasses import dataclass, field

class CapabilityCategory(str, Enum):
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    CRUD = "CRUD"
    BACKGROUND_TASKS = "BACKGROUND_TASKS"
    FILE_UPLOAD = "FILE_UPLOAD"
    PERSISTENCE = "PERSISTENCE"
    COMMUNICATION = "COMMUNICATION"
    BUSINESS_OPERATION = "BUSINESS_OPERATION"
    VALIDATION = "VALIDATION"
    TRANSFORMATION = "TRANSFORMATION"
    CONFIGURATION = "CONFIGURATION"
    SCHEDULING = "SCHEDULING"
    INTEGRATION = "INTEGRATION"
    EVENT_HANDLING = "EVENT_HANDLING"
    CACHING = "CACHING"
    LOGGING = "LOGGING"
    ERROR_HANDLING = "ERROR_HANDLING"

class CapabilityMemberRole(str, Enum):
    ENTRY_POINT = "entry_point"
    HANDLER = "handler"
    SERVICE = "service"
    REPOSITORY = "repository"
    TABLE = "table"
    WORKER = "worker"
    MEMBER = "member"

class CapabilityRelationshipType(str, Enum):
    DEPENDS_ON = "DEPENDS_ON"
    USES = "USES"
    TRIGGERS = "TRIGGERS"
    VALIDATES = "VALIDATES"
    PERSISTS = "PERSISTS"
    PUBLISHES = "PUBLISHES"
    CONSUMES = "CONSUMES"
    CONFIGURES = "CONFIGURES"

@dataclass
class CapabilityDetection:
    rule_id: str
    category: CapabilityCategory
    name: str
    members: List[Tuple[str, str]] = field(default_factory=list)  # (symbol_id, role)
    evidence: List[Dict[str, Any]] = field(default_factory=list)

class CapabilityRelationship(BaseModel):
    id: str
    type: CapabilityRelationshipType
    source_id: str
    target_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class Capability(BaseModel):
    id: str
    purpose: str
    category: CapabilityCategory
    responsibilities: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    representative_sources: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    rule_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
