"""
Typed tool contracts, results, errors, and execution contexts for the Agent Tool Layer.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class ToolErrorCode(str, Enum):
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    TIMEOUT = "TIMEOUT"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    WORKTREE_NOT_FOUND = "WORKTREE_NOT_FOUND"
    ISOLATION_VIOLATION = "ISOLATION_VIOLATION"


class ToolError(BaseModel):
    """Structured, normalized tool failure payload."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error explanation")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Optional diagnostic details")


class ToolResult(BaseModel):
    """
    Standard envelope returned by every agent tool invocation.
    Guarantees the agent never receives arbitrary raw backend exceptions.
    """
    success: bool = Field(..., description="Whether the tool execution succeeded")
    data: Optional[Any] = Field(default=None, description="Structured result data on success")
    error: Optional[ToolError] = Field(default=None, description="Error details on failure")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution metadata (duration, timestamp, tool name)")

    @classmethod
    def ok(cls, data: Any, tool_name: str, duration_ms: float = 0.0, **extra_meta) -> "ToolResult":
        meta = {"tool_name": tool_name, "duration_ms": round(duration_ms, 2)}
        meta.update(extra_meta)
        return cls(success=True, data=data, error=None, metadata=meta)

    @classmethod
    def fail(
        cls,
        code: ToolErrorCode | str,
        message: str,
        tool_name: str,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: float = 0.0,
        **extra_meta,
    ) -> "ToolResult":
        err_code = code.value if isinstance(code, ToolErrorCode) else str(code)
        meta = {"tool_name": tool_name, "duration_ms": round(duration_ms, 2)}
        meta.update(extra_meta)
        return cls(
            success=False,
            data=None,
            error=ToolError(code=err_code, message=message, details=details),
            metadata=meta,
        )


class AgentToolContext(BaseModel):
    """
    Authenticated execution context for tool invocations.
    Guarantees tools cannot escape assigned repository or worktree boundaries.
    """
    agent_run_id: str
    repository_id: str
    task_id: Optional[str] = None
    worktree_path: Optional[str] = None
    user_id: Optional[int] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    
    # Internal runtime references (excluded from serialization)
    db: Optional[Any] = Field(default=None, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolDefinition(BaseModel):
    """
    Metadata and runtime handler contract for a registered agent tool.
    Handler callable is strictly internal and never serialized over API.
    """
    name: str = Field(..., description="Unique tool identifier")
    description: str = Field(..., description="Description of tool purpose and behavior")
    category: str = Field(..., description="Tool category (repository, workspace, terminal, verification, git)")
    input_schema: Dict[str, Any] = Field(..., description="JSON Schema of required and optional arguments")
    output_schema: Optional[Dict[str, Any]] = Field(default=None, description="Optional schema of output data")
    default_timeout_sec: float = Field(default=30.0, description="Execution timeout in seconds")
    
    # Internal runtime handler callable (never serialized over API)
    handler: Optional[Callable[[Dict[str, Any], AgentToolContext], Any]] = Field(default=None, exclude=True)

    def to_catalog_item(self, policy_state: str = "ALLOWED") -> Dict[str, Any]:
        """Returns safe, serializable metadata for tool catalog inspection."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "default_timeout_sec": self.default_timeout_sec,
            "policy": policy_state,
        }
