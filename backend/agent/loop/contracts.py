"""
Phase 6 Engineering Agent Loop Contracts and Data Models.

Defines the typed models for:
  - StopReason: Authoritative termination and failure modes
  - AgentLoopConfig: Configurable hard execution limits and timeouts
  - ToolCall & ToolObservation: Normalized tool invocation and result envelopes
  - CompletionSignal & CriterionEvaluation: Structured completion validation protocol
  - AgentExecutionResult: Structured outcome returned by the EngineeringAgentLoop
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StopReason(str, Enum):
    """Authoritative stop reasons for the EngineeringAgentLoop."""
    COMPLETED_FOR_VERIFICATION = "COMPLETED_FOR_VERIFICATION"
    MAX_TURNS_EXCEEDED = "MAX_TURNS_EXCEEDED"
    MAX_TOOL_CALLS_EXCEEDED = "MAX_TOOL_CALLS_EXCEEDED"
    MAX_COMMANDS_EXCEEDED = "MAX_COMMANDS_EXCEEDED"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    REPEATED_TOOL_CALL_LIMIT = "REPEATED_TOOL_CALL_LIMIT"
    POLICY_DENIED = "POLICY_DENIED"
    INVALID_TOOL_CALL = "INVALID_TOOL_CALL"
    INVALID_COMPLETION = "INVALID_COMPLETION"
    MODEL_ERROR = "MODEL_ERROR"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    CANCELLED = "CANCELLED"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class AgentLoopConfig(BaseModel):
    """Configurable hard execution limits and safety guardrails."""
    max_agent_turns: int = Field(default=30, ge=1, description="Maximum agent turns before termination")
    max_tool_calls: int = Field(default=50, ge=1, description="Maximum total tool invocations permitted")
    max_command_executions: int = Field(default=10, ge=0, description="Maximum terminal / shell command executions permitted")
    max_execution_seconds: float = Field(default=900.0, gt=0.0, description="Hard timeout for entire task execution in seconds")
    max_command_seconds: float = Field(default=120.0, gt=0.0, description="Timeout for individual command execution in seconds")
    max_observation_bytes: int = Field(default=50000, ge=10, description="Maximum byte length of tool observation data before truncation")
    max_repeated_tool_calls: int = Field(default=3, ge=2, description="Consecutive identical tool calls allowed before loop termination")


class ToolCall(BaseModel):
    """Normalized tool call request proposed by the model."""
    tool_call_id: str = Field(..., description="Unique ID for this tool call invocation")
    tool_name: str = Field(..., description="Target tool name in the registry")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Validated arguments dictionary")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of invocation")


class ToolObservation(BaseModel):
    """Normalized tool execution observation returned back to the model context."""
    tool_call_id: str = Field(..., description="Matching ToolCall identifier")
    tool_name: str = Field(..., description="Name of invoked tool")
    success: bool = Field(..., description="Whether tool execution succeeded")
    data: Optional[Any] = Field(default=None, description="Structured result data on success")
    error: Optional[Dict[str, Any]] = Field(default=None, description="Structured error payload on failure")
    duration_ms: float = Field(default=0.0, description="Execution duration in milliseconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional tool execution metadata")


class CriterionEvaluation(BaseModel):
    """Evaluation of a single acceptance criterion by the agent."""
    criterion: str = Field(..., description="The acceptance criterion text")
    status: str = Field(default="satisfied", description="Satisfaction status (satisfied, partially_satisfied, unmet)")
    evidence: str = Field(..., description="Concrete technical evidence of satisfaction in the worktree")


class CompletionSignal(BaseModel):
    """
    Structured completion protocol.
    The agent MUST provide explicit evidence and request verification to complete.
    """
    type: str = Field(default="task_completion", description="Completion signal discriminant")
    summary: str = Field(..., description="Technical summary of implemented changes")
    acceptance_criteria_status: List[CriterionEvaluation] = Field(
        ..., min_length=1, description="Structured evaluation of each acceptance criterion"
    )
    verification_requested: bool = Field(
        default=True, description="Explicit request to hand off to Phase 7 verification"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional completion metadata")


class AgentExecutionResult(BaseModel):
    """
    Final structured outcome returned by the EngineeringAgentLoop boundary.
    Contains no raw reasoning, only structured artifacts, diffs, and observations.
    """
    status: str = Field(..., description="Outcome status (e.g. COMPLETED_FOR_VERIFICATION, FAILED, CANCELLED)")
    task_id: str = Field(..., description="Identifier of the task executed")
    iterations: int = Field(default=0, description="Number of agent turns completed")
    tool_call_count: int = Field(default=0, description="Total number of tools invoked")
    changed_files: List[str] = Field(default_factory=list, description="List of files modified, created, or deleted")
    diff: Optional[str] = Field(default=None, description="Unified git diff of changes made in the worktree")
    observations: List[str] = Field(default_factory=list, description="Chronological list of technical observation summaries")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Structured log of all tool calls and results")
    completion_signal: Optional[CompletionSignal] = Field(default=None, description="Parsed completion signal if completed")
    stop_reason: StopReason = Field(..., description="Authoritative termination reason")
    error: Optional[str] = Field(default=None, description="Error message if execution stopped due to failure")
    duration_ms: float = Field(default=0.0, description="Total elapsed time in milliseconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary execution metadata")
