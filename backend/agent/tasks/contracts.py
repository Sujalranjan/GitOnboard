"""
Task Orchestration Contracts & Data Models for GitOnBoard Engineering Agent.

Defines the typed models for:
  - TaskExecutionContext (isolated context passed to the execution boundary)
  - TaskExecutionResult (structured output of task execution)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from backend.agent.planning.contracts import PlanTask, PlanTaskStatus


class TaskExecutionContext(BaseModel):
    """
    Execution context provided to the TaskExecutor for a single task.
    Derived deterministically from the AgentRun and Plan.
    """
    agent_run_id: str = Field(description="Unique identifier of the overall agent run")
    plan_id: str = Field(description="ID of the approved implementation plan")
    task_id: str = Field(description="ID of the task being executed")
    repository_id: str = Field(description="ID of the target repository")
    worktree_path: Optional[str] = Field(default=None, description="Filesystem path of the isolated git worktree")
    task_definition: PlanTask = Field(description="Full PlanTask definition including dependencies and criteria")
    repository_context_summary: Dict[str, Any] = Field(default_factory=dict, description="Bounded summary from Phase 3 context")
    execution_config: Dict[str, Any] = Field(default_factory=dict, description="Runtime flags and limits")


class TaskExecutionResult(BaseModel):
    """
    Structured outcome returned by the TaskExecutor boundary.
    Contains no raw chain-of-thought, only structured artifacts and observations.
    """
    task_id: str = Field(description="ID of the executed task")
    success: bool = Field(description="True if implementation completed without unhandled exceptions")
    status: PlanTaskStatus = Field(default=PlanTaskStatus.VERIFYING, description="Target status post-execution")
    summary: str = Field(description="Concise description of the actions executed")
    changed_files: List[str] = Field(default_factory=list, description="Files modified or created during task")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Structured log of tools invoked")
    observations: List[str] = Field(default_factory=list, description="Key technical observations recorded")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")
    duration_ms: float = Field(default=0.0, description="Elapsed execution time in milliseconds")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary execution metadata")
