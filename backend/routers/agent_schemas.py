"""
Pydantic Request & Response Schemas for the Engineering Agent Router.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ClassifyIntentRequest(BaseModel):
    requirement: str = Field(..., description="User prompt to classify")
    repository_id: Optional[str] = Field(default=None, description="Optional target repository identifier")


class ClassifyIntentResponse(BaseModel):
    intent: str
    confidence: float
    reason: str
    method: str
    response: str
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    plan: Optional[Dict[str, Any]] = None
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    rim_trace: Optional[Dict[str, Any]] = Field(default=None, description="RIM metadata: anchors, expanded entities, and relationships")


class QuickIntentResponse(BaseModel):
    intent: str
    confidence: float
    reason: str
    method: str


class CreateAgentRunRequest(BaseModel):
    repository_id: str = Field(..., description="Target repository name or identifier")
    user_requirement: str = Field(..., description="Natural language feature requirement")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional configuration parameters")


class StateTransitionItem(BaseModel):
    from_state: str
    to_state: str
    reason: Optional[str] = None
    timestamp: str


class EventItem(BaseModel):
    event_id: str
    sequence: int
    agent_run_id: str
    task_id: Optional[str] = None
    event_type: str
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    timestamp: Optional[str] = None


class AgentRunResponse(BaseModel):
    id: str
    task_id: str
    repository_id: Optional[str]
    user_requirement: Optional[str]
    current_state: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    cancellation_reason: Optional[str] = None
    error_message: Optional[str] = None


class AgentRunDetailResponse(AgentRunResponse):
    transitions: List[StateTransitionItem] = Field(default_factory=list)
    events: List[EventItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TransitionStateRequest(BaseModel):
    to_state: str = Field(..., description="Target AgentState (e.g. PLANNING, EXECUTING, VERIFYING, COMPLETED, FAILED)")
    reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ControlledActionRequest(BaseModel):
    action_type: str = Field(default="inspect_repository", description="Action to execute (e.g. inspect_repository, read_file, get_symbol)")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ControlledActionResponse(BaseModel):
    run_id: str
    action_type: str
    status: str
    duration_ms: float
    result: Dict[str, Any]


class CancelAgentRunRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Reason for cancellation")


class RevisePlanRequest(BaseModel):
    feedback: str = Field(..., description="Review comments or requested modifications to incorporate into the plan")


class RejectPlanRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Reason for rejecting the plan")


class ApprovalRequestItem(BaseModel):
    id: str
    agent_run_id: str
    task_id: Optional[str] = None
    action_type: str
    action_description: str
    risk_level: str
    command: Optional[str] = None
    reason: Optional[str] = None
    status: str
    requested_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    rejection_reason: Optional[str] = None


class ApproveActionRequest(BaseModel):
    resolved_by: Optional[str] = Field(default="human_user", description="Identifier of human approving action")


class RejectActionRequest(BaseModel):
    reason: str = Field(..., description="Reason explaining why action was rejected")
    resolved_by: Optional[str] = Field(default="human_user", description="Identifier of human rejecting action")


class WorkspaceChangesResponse(BaseModel):
    agent_run_id: str
    worktree_path: Optional[str] = None
    modified_files: List[str] = Field(default_factory=list)
    added_files: List[str] = Field(default_factory=list)
    deleted_files: List[str] = Field(default_factory=list)
    diff: str = ""


class WorkspaceSnapshotResponse(BaseModel):
    run: AgentRunDetailResponse
    plan: Optional[Dict[str, Any]] = None
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    active_task: Optional[Dict[str, Any]] = None
    changes: WorkspaceChangesResponse
    verification: Optional[Dict[str, Any]] = None
    pending_approvals: List[ApprovalRequestItem] = Field(default_factory=list)
    latest_events: List[EventItem] = Field(default_factory=list)


# Repository tool schemas
class FileContentRequest(BaseModel):
    """Request to read file content from repository."""
    repo_hash: str = Field(description="Repository UUID hash")
    file_path: str = Field(description="Repository-relative file path")
    start_line: Optional[int] = Field(default=None, description="Start line (1-indexed)")
    end_line: Optional[int] = Field(default=None, description="End line (1-indexed)")


class FileContentResponse(BaseModel):
    """Response with file content."""
    file_path: str
    content: str
    total_lines: int
    returned_lines: int
    start_line: Optional[int]
    end_line: Optional[int]


class SymbolGraphQueryRequest(BaseModel):
    """Request to query symbol relationships."""
    repo_hash: str = Field(description="Repository UUID hash")
    symbol_id: str = Field(description="Symbol ID to query")
    direction: str = Field(default="both", description="incoming, outgoing, or both")
    depth: int = Field(default=1, description="How many levels deep (1-10)")


class SymbolGraphNode(BaseModel):
    """A node in the symbol graph."""
    symbol_id: str
    name: str
    symbol_type: str
    file_path: str


class SymbolGraphEdge(BaseModel):
    """An edge in the symbol graph."""
    from_id: str
    to_id: str
    rel_type: str


class SymbolGraphQueryResponse(BaseModel):
    """Response with symbol relationships."""
    nodes: List[SymbolGraphNode]
    edges: List[SymbolGraphEdge]
    center_symbol: str


class ExplainSymbolRequest(BaseModel):
    """Request to explain a symbol."""
    repo_hash: str = Field(description="Repository UUID hash")
    symbol_id: str = Field(description="Symbol ID to explain")


class SymbolExplanation(BaseModel):
    """Symbol explanation."""
    symbol_id: str
    name: str
    symbol_type: str
    file_path: str
    explanation: Optional[str] = None
    cached: bool = False
