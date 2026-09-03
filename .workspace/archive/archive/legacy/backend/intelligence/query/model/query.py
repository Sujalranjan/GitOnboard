from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum

class TargetType(str, Enum):
    FEATURE = "FEATURE"
    PATTERN = "PATTERN"
    CAPABILITY = "CAPABILITY"
    ENTITY = "ENTITY"

class ActionType(str, Enum):
    FIND = "FIND"
    FROM = "FROM"

class ClauseType(str, Enum):
    FOLLOW = "FOLLOW"
    INCLUDE = "INCLUDE"
    TRACE = "TRACE"

class QueryClause(BaseModel):
    type: ClauseType
    target: str           # e.g., "USES", "Routes", "IMPLEMENTATION"
    depth: Optional[int] = None

class RepositoryQuery(BaseModel):
    action: ActionType
    target_type: TargetType
    target_name: str
    clauses: List[QueryClause] = Field(default_factory=list)
